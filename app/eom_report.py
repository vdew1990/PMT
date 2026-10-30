"""EOM cost and revenue report: the workbook's "EOM Report" sheet, plus a cashflow graph and table.

Blocks, as on the sheet: revenue by stage (claimed, approved, invoiced, paid; base scope and variations, previous / this
month / to date / remaining / contract value), gross margin (original, revised, to date, at completion), approved
variations, claims PMT against Pronto, and the cost table by CBS (allowance, commitments, actuals, accruals, CTC, EAC).
Added: cost and revenue by month with the cumulative position. `build` gathers the numbers; `xlsx` and `pdf` lay them out.
"""
import io
from collections import defaultdict
from datetime import date

import xlsxwriter
import xlsxwriter.utility

from . import db, engine, reports, revenue

TOL = 1.0  # $ difference that still counts as a match between the PMT and Pronto


def _mlabel(m, long=False):
    y, mo = int(m[:4]), int(m[5:7])
    names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    return f"{names[mo - 1]} {y}" if long else f"{names[mo - 1][:3]}-{str(y)[2:]}"


def _split_of(items):
    """contract item id -> 'var' or 'base', from the top-level item it sits under."""
    by_id = {i["id"]: i for i in items}
    out = {}
    for i in items:
        t = i
        while t["parent_id"] is not None and t["parent_id"] in by_id:
            t = by_id[t["parent_id"]]
        out[i["id"]] = "var" if (t["kind"] == "variation" or i["kind"] == "variation") else "base"
    return out


def _stage(prev, this, cv):
    """Base, variations and total rows for one stage. prev/this/cv are {'base': x, 'var': y}."""
    rows = []
    for k, label in (("base", "Base scope"), ("var", "Variations")):
        td = prev[k] + this[k]
        rows.append(dict(scope=label, previous=prev[k], this_month=this[k], to_date=td, remaining=cv[k] - td, contract_value=cv[k]))
    tot = {f: sum(r[f] for r in rows) for f in ("previous", "this_month", "to_date", "remaining", "contract_value")}
    rows.append(dict(scope="Total", total=True, **tot))
    return rows


def _revenue(con, pid, M, rs):
    items = revenue.items_tree(con, pid)
    split = _split_of(items)
    cv = {"base": rs["base"] + rs["optional_taken"], "var": rs["variations_approved"]}
    claimed = {"prev": defaultdict(float), "this": defaultdict(float)}
    approved = {"prev": defaultdict(float), "this": defaultdict(float)}
    for r in con.execute("SELECT c.period, c.status, cl.item_id, cl.amount, cl.certified FROM claim_line cl JOIN claim c ON c.id=cl.claim_id "
                         "WHERE c.project_id=? AND substr(c.period,1,7)<=?", (pid, M)):
        when = "this" if r["period"][:7] == M else "prev"
        if r["status"] == "draft" and when == "prev":
            continue  # a draft from an earlier month was never sent
        k = split.get(r["item_id"], "base")
        claimed[when][k] += r["amount"] or 0
        if r["certified"] is not None:
            approved[when][k] += r["certified"]
    appr_td = {k: approved["prev"][k] + approved["this"][k] for k in ("base", "var")}
    cl_td = {k: claimed["prev"][k] + claimed["this"][k] for k in ("base", "var")}
    basis = appr_td if sum(appr_td.values()) else cl_td
    share_var = (basis["var"] / sum(basis.values())) if sum(basis.values()) else 0.0

    def by_ratio(prev, this):
        return ({"base": prev * (1 - share_var), "var": prev * share_var}, {"base": this * (1 - share_var), "var": this * share_var})
    inv_prev = inv_this = 0.0
    for r in con.execute("SELECT month, -SUM(cost) a FROM pronto_tx WHERE project_id=? AND class='revenue' AND month<=? GROUP BY month", (pid, M)):
        if r["month"] == M:
            inv_this += r["a"] or 0
        else:
            inv_prev += r["a"] or 0
    paid_prev = paid_this = 0.0
    prows = db.rows(con, "SELECT date_paid, paid FROM pronto_claim WHERE project_id=? AND date_paid IS NOT NULL AND paid IS NOT NULL", (pid,))
    if not prows:  # no Pronto claims export: use what was recorded on the claims themselves
        prows = db.rows(con, "SELECT paid_date AS date_paid, paid_amount AS paid FROM claim WHERE project_id=? AND paid_date IS NOT NULL AND paid_amount IS NOT NULL", (pid,))
    for r in prows:
        m = (r["date_paid"] or "")[:7]
        if m == M:
            paid_this += r["paid"] or 0
        elif m and m < M:
            paid_prev += r["paid"] or 0
    stages = [
        dict(stage="Claimed", rows=_stage(claimed["prev"], claimed["this"], cv)),
        dict(stage="Approved", rows=_stage(approved["prev"], approved["this"], cv)),
        dict(stage="Invoiced", rows=_stage(*by_ratio(inv_prev, inv_this), cv)),
        dict(stage="Paid", rows=_stage(*by_ratio(paid_prev, paid_this), cv)),
    ]
    note = ("Claimed = progress claims for the month and before (this month's claim counts even while still a draft). "
            "Approved = client-certified amounts on those claims. Invoiced = Pronto revenue transactions; Paid = Pronto claims "
            "paid amount by date paid; both split base / variations in the approved ratio. Remaining = contract value less to date.")
    return stages, note, items


def _variations(con, pid, M, items):
    by_parent = defaultdict(list)
    for i in items:
        by_parent[i["parent_id"]].append(i)

    def under(i):
        out = [i["id"]]
        for c in by_parent.get(i["id"], []):
            out += under(c)
        return out
    claimed = defaultdict(lambda: [0.0, 0.0])  # item -> [this month, to date]
    for r in con.execute("SELECT c.period, c.status, cl.item_id, cl.amount FROM claim_line cl JOIN claim c ON c.id=cl.claim_id "
                         "WHERE c.project_id=? AND substr(c.period,1,7)<=?", (pid, M)):
        if r["status"] == "draft" and r["period"][:7] != M:
            continue
        claimed[r["item_id"]][1] += r["amount"] or 0
        if r["period"][:7] == M:
            claimed[r["item_id"]][0] += r["amount"] or 0
    pron = {(r["variation_no"] or "").strip().upper(): r for r in db.rows(con, "SELECT variation_no, approved FROM pronto_variation WHERE project_id=?", (pid,))}
    out = []
    for v in db.rows(con, "SELECT v.*, (SELECT value FROM variation_rev r WHERE r.variation_id=v.id ORDER BY is_current DESC, rev DESC LIMIT 1) AS value "
                          "FROM variation v WHERE v.project_id=? AND v.client_status='Approved' ORDER BY v.ref", (pid,)):
        ids = [x for i in items if i.get("variation_id") == v["id"] for x in under(i)]
        this = sum(claimed[i][0] for i in ids)
        td = sum(claimed[i][1] for i in ids)
        val = v["value"] or 0.0
        p = pron.get((v["pronto_ref"] or "").strip().upper()) or pron.get(v["ref"].strip().upper())
        if not p:
            state, label = "missing", "✗"
        elif abs((p["approved"] or 0) - val) < TOL:
            state, label = "ok", "✓"
        else:
            state, label = "diff", f"Δ = {abs((p['approved'] or 0) - val):,.0f}"
        out.append(dict(ref=v["ref"], title=v["title"] or "", approved=val, this_month=this, to_be_claimed=max(0.0, val - td), pronto=label, state=state))
    return out


def _claims_check(con, pid):
    pmt_cert = db.one(con, "SELECT COALESCE(SUM(cl.certified),0) s FROM claim_line cl JOIN claim c ON c.id=cl.claim_id WHERE c.project_id=?", (pid,))["s"]
    last = db.one(con, "SELECT c.id FROM claim c JOIN claim_line cl ON cl.claim_id=c.id WHERE c.project_id=? AND cl.certified IS NOT NULL ORDER BY c.period DESC, c.id DESC LIMIT 1", (pid,))
    pmt_last = db.one(con, "SELECT COALESCE(SUM(certified),0) s FROM claim_line WHERE claim_id=?", (last["id"],))["s"] if last else 0.0
    has_pronto = db.one(con, "SELECT COUNT(*) n FROM pronto_claim WHERE project_id=?", (pid,))["n"] > 0
    pr_cert = db.one(con, "SELECT COALESCE(SUM(certified),0) s FROM pronto_claim WHERE project_id=?", (pid,))["s"]
    pl = db.one(con, "SELECT certified FROM pronto_claim WHERE project_id=? AND certified>0 AND date_certified IS NOT NULL ORDER BY date_certified DESC, id DESC LIMIT 1", (pid,))
    pr_last = pl["certified"] if pl else 0.0
    pr_paid = db.one(con, "SELECT COALESCE(SUM(paid),0) s FROM pronto_claim WHERE project_id=?", (pid,))["s"]
    ok = lambda d: "OK" if abs(d) <= TOL else "CHECK"
    rows = [dict(check="Approved / certified to date", pmt=pmt_cert, pronto=pr_cert, diff=round(pr_cert - pmt_cert), status=ok(pr_cert - pmt_cert)),
            dict(check="Latest approved claim", pmt=pmt_last, pronto=pr_last, diff=round(pr_last - pmt_last), status=ok(pr_last - pmt_last)),
            dict(check="Paid to date (receivable)", pmt=pmt_cert, pronto=pr_paid, diff=round(pr_paid - pmt_cert),
                 status="Fully paid" if abs(pr_paid - pmt_cert) <= TOL else "Awaiting payment")]
    return rows, has_pronto


def _cashflow(con, pid, res):
    grid, M = res["grid"], res["status_month"]
    leaves = [r for r in res["rows"] if r["kind"] in ("line", "pot")]
    cost = [sum(r["a"][i] + r["x"][i] + r["f"][i] for r in leaves) for i in range(len(grid))]
    rc = revenue.revenue_curve(con, pid, grid, M)
    rev = [s["actual"] + s["planned"] for s in rc["series"]]
    net = [a - b for a, b in zip(rev, cost)]
    return dict(months=grid, labels=[_mlabel(m) for m in grid], flag=["Actual" if m < M else ("Current" if m == M else "Forecast") for m in grid],
                cost=cost, revenue=rev, net=net, cum_cost=reports._cum(cost), cum_revenue=reports._cum(rev), cum_net=reports._cum(net),
                revenue_source=rc["source"],
                note="Cost: actual and accrued to the status month, forecast after it (the cost control grid). Revenue: claims to the "
                     "status month (certified where certified), then the claim schedule. Both on an earned basis, before payment terms.")


COST_KEYS = ("allowance", "ordered", "outstanding", "prev_actual", "actual_month", "ctd", "prev_accrued", "accrued_month", "acc", "ctc", "eac")


def _cost(res, hide_zero):
    M = res["status_month"]
    i = res["grid"].index(M) if M in res["grid"] else None
    rows = []
    for r in res["rows"]:
        a_m = r["a"][i] if i is not None else 0.0
        x_m = r["x"][i] if i is not None else 0.0
        line = r["kind"] in ("line", "pot")
        row = dict(level=r["level"], kind=r["kind"], code=r["code"],
                   function=(r.get("function") or "") if line else r["name"],
                   resource_code=(r.get("resource_code") or "") if line else "",
                   resource=("CTC (Unallocated)" if r["kind"] == "pot" else r["name"]) if line else "",
                   allowance=r["allowance"], ordered=r["po_committed"] or 0.0, outstanding=r["outstanding"] or 0.0,
                   prev_actual=r["ctd"] - a_m, actual_month=a_m, ctd=r["ctd"], prev_accrued=r["acc"] - x_m, accrued_month=x_m,
                   acc=r["acc"], ctc=r["ctc"], eac=r["eac"])
        if hide_zero and all(abs(row[k]) < 0.5 for k in COST_KEYS):
            continue
        rows.append(row)
    leaves = [r for r in rows if r["kind"] in ("line", "pot")]
    total = {k: sum(r[k] for r in leaves) for k in COST_KEYS}  # hidden rows are all zero, so this still ties to the engine total
    return rows, total


def build(con, pid, revision=None, hide_zero=True):
    res = engine.compute(con, pid)
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    M = res["status_month"]
    rs = revenue.summary(con, pid)
    m = reports.project_margin(con, pid, res)
    t = res["total"]
    stages, rev_note, items = _revenue(con, pid, M, rs)
    claimed_td = stages[0]["rows"][-1]["to_date"]
    cv_total = stages[0]["rows"][-1]["contract_value"]
    margin = [dict(metric="Revenue", original=m["revenue_original"], revised=cv_total, to_date=claimed_td, at_completion=cv_total),
              dict(metric="Cost", original=m["cost_original"], revised=t["allowance"], to_date=t["ctd"] + t["acc"], at_completion=t["eac"])]
    gm = {k: margin[0][k] - margin[1][k] for k in ("original", "revised", "to_date", "at_completion")}
    margin.append(dict(metric="Gross margin $", **gm))
    margin.append(dict(metric="Gross margin %", pct=True, **{k: (gm[k] / margin[0][k]) if margin[0][k] else 0.0 for k in gm}))
    var_rows = _variations(con, pid, M, items)
    checks, has_pronto = _claims_check(con, pid)
    cost_rows, cost_total = _cost(res, hide_zero)
    if revision is None:
        n = db.one(con, "SELECT COUNT(*) n FROM snapshot WHERE project_id=? AND kind='eom' AND period<=?", (pid, M))["n"]
        revision = f"{max(1, n):02d}"
    number = p.get("number") or p.get("code") or ""
    return dict(
        header=dict(title=f"{number} {p['name']}  —  EOM COST & REVENUE REPORT".strip(), project=p["name"], number=number, client=p.get("client_name") or "",
                    pm=p.get("epec_pm") or "", status_month=M, status_label=_mlabel(M, long=True), status_date=p.get("status_date"),
                    prepared=date.today().strftime("%d-%b-%y"), revision=str(revision)),
        revenue=dict(stages=stages, note=rev_note), margin=margin,
        variations=dict(rows=var_rows, total=dict(approved=sum(r["approved"] for r in var_rows), this_month=sum(r["this_month"] for r in var_rows),
                                                  to_be_claimed=sum(r["to_be_claimed"] for r in var_rows)),
                        to_action=sum(1 for r in var_rows if r["state"] != "ok")),
        claims=dict(rows=checks, has_pronto=has_pronto),
        cashflow=_cashflow(con, pid, res),
        cost=dict(rows=cost_rows, total=cost_total, hide_zero=hide_zero),
        check=dict(eac=cost_total["eac"] - t["eac"], ctd=cost_total["ctd"] - t["ctd"]))


# --------------------------------------------------------------------------
# Excel
# --------------------------------------------------------------------------
COST_COLS = [("CBS", "code", 12), ("Function", "function", 26), ("Resource code", "resource_code", 12), ("Resource", "resource", 30),
             ("Revised value", "allowance", 13), ("Ordered value", "ordered", 13), ("Outstanding commitment", "outstanding", 13),
             ("Previous actuals", "prev_actual", 13), ("Actuals this month", "actual_month", 13), ("CTD", "ctd", 13),
             ("Previously accrued", "prev_accrued", 13), ("Accrued this month", "accrued_month", 13), ("Accruals to date", "acc", 13),
             ("CTC", "ctc", 13), ("EAC", "eac", 14)]
COST_BANDS = [("ALLOWANCE", 4, 4), ("COMMITMENTS", 5, 6), ("ACTUALS", 7, 9), ("ACCRUALS", 10, 12), ("FORECAST", 13, 14)]
NAVY, ORANGE, GOLD, GREY, SLATE, GREEN = "#102361", "#e56210", "#ffb500", "#e0e6e8", "#335062", "#3c8d40"


def xlsx(d):
    from .exporters import _formats
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    F = _formats(wb)
    base = {"font_name": "Calibri", "font_size": 10}
    mk = lambda **k: wb.add_format({**base, **k})
    num = "#,##0;[Red]-#,##0"
    band = mk(bold=True, font_color="#ffffff", bg_color=ORANGE, align="center")
    sec = mk(bold=True, font_size=12, font_color=NAVY, bottom=2, bottom_color=NAVY)
    stage = mk(bold=True, font_color=NAVY, top=1, top_color="#c9d1d6")
    tot_t, tot_n = mk(bold=True, top=1), mk(bold=True, top=1, num_format=num)
    pct = mk(num_format="0.0%")
    ok, bad, warn = mk(font_color=GREEN, bold=True), mk(font_color="#c62828", bold=True), mk(font_color=ORANGE, bold=True)
    small = mk(italic=True, font_color=SLATE, text_wrap=True, valign="top", font_size=9)
    lvl_t = {1: mk(bold=True, font_color=ORANGE, bg_color=GREY), 2: mk(bold=True, font_color=NAVY)}
    lvl_n = {1: mk(bold=True, font_color=ORANGE, bg_color=GREY, num_format=num), 2: mk(bold=True, font_color=NAVY, num_format=num)}
    fc_n, act_n = mk(num_format=num, bg_color="#DCEDD5"), mk(num_format=num, bg_color="#DDEBF7")

    ws = wb.add_worksheet("EOM Report")
    ws.hide_gridlines(2)
    for c, (_, _, w) in enumerate(COST_COLS):
        ws.set_column(c, c, w)
    h = d["header"]
    ws.write(0, 0, h["title"], F["title"])
    ws.write(1, 0, f"Status month: {h['status_label']}     |     Prepared {h['prepared']}     |     Revision {h['revision']}", F["sub"])
    ws.write(2, 0, "Zero lines hidden" if d["cost"]["hide_zero"] else "All lines shown", small)

    # revenue (A..G) and gross margin (J..N) side by side
    r0 = 4
    ws.write(r0, 0, "REVENUE", sec)
    ws.write_row(r0 + 1, 0, ["Stage", "Scope", "Previous", "This month", "To date", "Remaining", "Contract value"], F["head"])
    r = r0 + 2
    for s in d["revenue"]["stages"]:
        for i, x in enumerate(s["rows"]):
            t = x.get("total")
            ws.write(r, 0, s["stage"] if i == 0 else "", stage if i == 0 else F["txt"])
            ws.write(r, 1, x["scope"], tot_t if t else F["txt"])
            ws.write_row(r, 2, [x["previous"], x["this_month"], x["to_date"], x["remaining"], x["contract_value"]], tot_n if t else F["num"])
            r += 1
    ws.merge_range(r, 0, r + 2, 6, d["revenue"]["note"], small)
    r_rev_end = r + 3

    ws.write(r0, 9, "GROSS MARGIN", sec)
    ws.write_row(r0 + 1, 9, ["Metric", "Original", "Revised", "To date", "At completion"], F["head"])
    for i, x in enumerate(d["margin"]):
        fm = pct if x.get("pct") else (tot_n if x["metric"].startswith("Gross") else F["num"])
        ws.write(r0 + 2 + i, 9, x["metric"], tot_t if x["metric"].startswith("Gross") else F["txt"])
        ws.write_row(r0 + 2 + i, 10, [x["original"], x["revised"], x["to_date"], x["at_completion"]], fm)
    rv = r0 + 2 + len(d["margin"]) + 1
    ws.write(rv, 9, "APPROVED VARIATIONS", sec)
    ws.write_row(rv + 1, 9, ["Variation", "Approved", "This month", "To be claimed", "In Pronto?"], F["head"])
    rr = rv + 2
    for x in d["variations"]["rows"]:
        ws.write(rr, 9, x["ref"], F["txt"])
        ws.write_row(rr, 10, [x["approved"], x["this_month"], x["to_be_claimed"]], F["num"])
        ws.write(rr, 13, x["pronto"], ok if x["state"] == "ok" else bad)
        rr += 1
    vt = d["variations"]["total"]
    ws.write(rr, 9, "Total", tot_t)
    ws.write_row(rr, 10, [vt["approved"], vt["this_month"], vt["to_be_claimed"]], tot_n)
    ws.write(rr, 13, f"{d['variations']['to_action']} to action" if d["variations"]["to_action"] else "All in Pronto", tot_t)

    r = max(r_rev_end, rr + 2)
    ws.write(r, 0, "CLAIMS — PMT vs PRONTO", sec)
    ws.write_row(r + 1, 0, ["Check", "", "PMT (claims)", "Pronto", "Difference", "Status"], F["head"])
    for i, x in enumerate(d["claims"]["rows"]):
        ws.write(r + 2 + i, 0, x["check"], F["txt"])
        ws.write_row(r + 2 + i, 2, [x["pmt"], x["pronto"], x["diff"]], F["num"])
        ws.write(r + 2 + i, 5, x["status"], ok if x["status"] in ("OK", "Fully paid") else warn)
    if not d["claims"]["has_pronto"]:
        ws.write(r + 5, 0, "No Pronto claims export loaded: the Pronto column is empty.", small)
    r += 7

    # cashflow: table (months across) then a combo chart
    cf = d["cashflow"]
    ws.write(r, 0, "CASHFLOW — COST AND REVENUE BY MONTH", sec)
    r += 1
    first = 2
    ws.write(r, 0, "", F["head"]); ws.write(r, 1, "", F["head"])
    for j, lab in enumerate(cf["labels"]):
        ws.write(r, first + j, lab, F["head"])
    ws.write(r + 1, 0, "", small)
    for j, fl in enumerate(cf["flag"]):
        ws.write(r + 1, first + j, fl, mk(font_size=8, align="center", font_color=SLATE, bg_color="#DCEDD5" if fl == "Forecast" else ("#A6C9EC" if fl == "Current" else "#DDEBF7")))
    series = [("Monthly", "Revenue", "revenue"), ("", "Cost", "cost"), ("", "Net", "net"),
              ("Cumulative", "Revenue", "cum_revenue"), ("", "Cost", "cum_cost"), ("", "Net", "cum_net")]
    row_of = {}
    for i, (grp, lab, k) in enumerate(series):
        rr = r + 2 + i
        row_of[k] = rr
        ws.write(rr, 0, grp, stage if grp else F["txt"])
        ws.write(rr, 1, lab, tot_t if lab == "Net" else F["txt"])
        for j, v in enumerate(cf[k]):
            fm = tot_n if lab == "Net" else (fc_n if cf["flag"][j] == "Forecast" else act_n)
            ws.write(rr, first + j, v, fm)
    if len(cf["labels"]) > len(COST_COLS) - first:
        ws.set_column(len(COST_COLS), first + len(cf["labels"]) - 1, 13)
    r += 2 + len(series)
    ws.merge_range(r, 0, r, 9, cf["note"], small)
    r += 1
    last = first + len(cf["labels"]) - 1
    col = xlsxwriter.utility.xl_col_to_name
    cats = f"='EOM Report'!${col(first)}${row_of['revenue'] - 1}:${col(last)}${row_of['revenue'] - 1}"
    ch = wb.add_chart({"type": "column"})
    for k, name, colr in (("revenue", "Revenue (month)", ORANGE), ("cost", "Cost (month)", NAVY)):
        ch.add_series({"name": name, "categories": cats, "values": f"='EOM Report'!${col(first)}${row_of[k] + 1}:${col(last)}${row_of[k] + 1}",
                       "fill": {"color": colr}, "gap": 60})
    ln = wb.add_chart({"type": "line"})
    for k, name, colr, dash in (("cum_revenue", "Cumulative revenue", ORANGE, "solid"), ("cum_cost", "Cumulative cost", NAVY, "solid"), ("cum_net", "Cumulative net", GOLD, "dash")):
        ln.add_series({"name": name, "categories": cats, "values": f"='EOM Report'!${col(first)}${row_of[k] + 1}:${col(last)}${row_of[k] + 1}",
                       "y2_axis": True, "line": {"color": colr, "width": 2.25, "dash_type": dash}})
    ch.combine(ln)
    ch.set_title({"name": "Cashflow", "name_font": {"size": 12, "color": NAVY}})
    ch.set_y_axis({"name": "Monthly", "num_format": "$#,##0,\"k\"", "major_gridlines": {"visible": True, "line": {"color": "#e5e8eb"}}})
    ln.set_y2_axis({"name": "Cumulative", "num_format": "$#,##0.0,,\"m\""})
    ch.set_legend({"position": "bottom"})
    ch.set_size({"width": 1400, "height": 380})
    ws.insert_chart(r, 0, ch)
    r += 20

    # cost table
    ws.write(r, 0, "COST", sec)
    r += 1
    for name, a, b in COST_BANDS:
        if a == b:
            ws.write(r, a, name, band)
        else:
            ws.merge_range(r, a, r, b, name, band)
    ws.write_row(r + 1, 0, [c[0] for c in COST_COLS], F["head"])
    ws.set_row(r + 1, 30)
    head_row = r + 1
    tt = d["cost"]["total"]
    ws.write(r + 2, 0, "TOTAL", tot_t)
    for c, (_, k, _) in enumerate(COST_COLS[4:], start=4):
        ws.write(r + 2, c, tt[k], tot_n)
    r += 3
    for x in d["cost"]["rows"]:
        lv = x["level"]
        line = x["kind"] in ("line", "pot")
        tf, nf = (F["txt"], F["num"]) if line else (lvl_t.get(lv, F["bold"]), lvl_n.get(lv, tot_n))
        ws.write_row(r, 0, [x["code"], x["function"], x["resource_code"], x["resource"]], tf)
        ws.write_row(r, 4, [x[k] for _, k, _ in COST_COLS[4:]], nf)
        ws.set_row(r, None, None, {"level": min(7, max(0, lv - 1)) if line or lv > 1 else 0})
        r += 1
    ws.repeat_rows(head_row)
    ws.set_landscape()
    ws.set_paper(8)  # A3, as the workbook
    ws.fit_to_pages(1, 0)
    ws.center_horizontally()
    ws.set_footer("&L&8Commercial in Confidence&C&8" + h["project"].replace("&", "&&") + " EOM report&R&8Page &P of &N")
    wb.close()
    return buf.getvalue()


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
def _money(v, dash=True):
    if v is None:
        return ""
    if dash and abs(v) < 0.5:
        return "–"
    return f"{v:,.0f}" if v >= 0 else f"({-v:,.0f})"


def _cash_chart(cf, width, height):
    from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
    from reportlab.lib import colors
    C = colors.HexColor
    d = Drawing(width, height)
    n = len(cf["months"])
    if not n:
        return d
    L, R, T, B = 70, 70, 22, 34
    w, hgt = width - L - R, height - T - B
    mon_max, mon_min = max([1.0] + cf["revenue"] + cf["cost"]), 0.0
    cum = cf["cum_revenue"] + cf["cum_cost"] + cf["cum_net"]
    cmax, cmin = max([1.0] + cum), min([0.0] + cum)
    y1 = lambda v: B + (v - mon_min) / (mon_max - mon_min) * hgt
    y2 = lambda v: B + (v - cmin) / (cmax - cmin) * hgt
    slot = w / n
    # forecast months shaded, status month marked
    for i, fl in enumerate(cf["flag"]):
        if fl != "Actual":
            d.add(Rect(L + i * slot, B, slot, hgt, fillColor=C("#DCEDD5" if fl == "Forecast" else "#A3C4A7"), strokeColor=None, fillOpacity=0.45))
    for k in range(5):
        v = mon_min + (mon_max - mon_min) * k / 4
        y = y1(v)
        d.add(Line(L, y, L + w, y, strokeColor=C("#e5e8eb"), strokeWidth=0.5))
        d.add(String(L - 4, y - 3, f"${v / 1000:,.0f}k", fontSize=6.5, textAnchor="end", fillColor=C(SLATE)))
        cv = cmin + (cmax - cmin) * k / 4
        d.add(String(L + w + 4, y2(cv) - 3, f"${cv / 1e6:,.1f}m", fontSize=6.5, fillColor=C(SLATE)))
    if cmin < 0:
        d.add(Line(L, y2(0), L + w, y2(0), strokeColor=C("#9aa5ab"), strokeWidth=0.6, strokeDashArray=[2, 2]))
    bw = slot * 0.36
    for i in range(n):
        x0 = L + i * slot + slot * 0.12
        d.add(Rect(x0, B, bw, max(0, y1(cf["revenue"][i]) - B), fillColor=C(ORANGE), strokeColor=None))
        d.add(Rect(x0 + bw, B, bw, max(0, y1(cf["cost"][i]) - B), fillColor=C(NAVY), strokeColor=None))
        if n <= 40 or i % 2 == 0:
            d.add(String(L + i * slot + slot / 2, B - 10, cf["labels"][i], fontSize=6, textAnchor="middle", fillColor=C(SLATE)))
    for k, colr, dash in (("cum_revenue", ORANGE, None), ("cum_cost", NAVY, None), ("cum_net", GOLD, [4, 2])):
        pts = []
        for i, v in enumerate(cf[k]):
            pts += [L + i * slot + slot / 2, y2(v)]
        d.add(PolyLine(pts, strokeColor=C(colr), strokeWidth=1.8, strokeDashArray=dash))
    d.add(Line(L, B, L + w, B, strokeColor=C(SLATE), strokeWidth=0.6))
    # legend
    lx = L
    for label, colr, kind in (("Revenue (month)", ORANGE, "bar"), ("Cost (month)", NAVY, "bar"), ("Cumulative revenue", ORANGE, "line"),
                              ("Cumulative cost", NAVY, "line"), ("Cumulative net", GOLD, "dash"), ("Forecast months", "#DCEDD5", "bar")):
        if kind == "bar":
            d.add(Rect(lx, height - 12, 9, 7, fillColor=C(colr), strokeColor=None))
        else:
            d.add(Line(lx, height - 8.5, lx + 12, height - 8.5, strokeColor=C(colr), strokeWidth=1.8, strokeDashArray=[3, 2] if kind == "dash" else None))
        d.add(String(lx + 15, height - 11, label, fontSize=7, fillColor=C(SLATE)))
        lx += 15 + len(label) * 3.9 + 16
    d.add(String(4, B + hgt / 2, "Monthly", fontSize=6.5, fillColor=C(SLATE)))
    d.add(String(width - 4, B + hgt / 2, "Cumulative", fontSize=6.5, textAnchor="end", fillColor=C(SLATE)))
    return d


def pdf(d):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    C = colors.HexColor
    buf = io.BytesIO()
    page = landscape(A3)
    margin = 12 * mm
    h = d["header"]

    def frame(c, doc):
        c.saveState()
        c.setFillColor(C(NAVY))
        c.rect(0, page[1] - 9 * mm, page[0], 9 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(margin, page[1] - 6 * mm, h["title"])
        c.drawRightString(page[0] - margin, page[1] - 6 * mm, f"Status month {h['status_label']}  |  Revision {h['revision']}")
        c.setFillColor(C(SLATE))
        c.setFont("Helvetica", 7)
        c.drawString(margin, 6 * mm, "Commercial in Confidence  |  AUD excl. GST")
        c.drawRightString(page[0] - margin, 6 * mm, f"Prepared {h['prepared']}  |  Page {doc.page}")
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=14 * mm, bottomMargin=12 * mm,
                            title=h["title"], author="PMT")
    W = page[0] - 2 * margin
    st_title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=18, textColor=C(ORANGE), leading=22)
    st_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=9, textColor=C(SLATE), leading=12)
    st_sec = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=11, textColor=C(NAVY), leading=14, spaceBefore=6, spaceAfter=4)
    st_note = ParagraphStyle("n", fontName="Helvetica-Oblique", fontSize=7, textColor=C(SLATE), leading=9)
    st_cell = ParagraphStyle("c", fontName="Helvetica", fontSize=7, leading=8.5)

    def grid(data, widths, head_rows=1, extra=(), repeat=False):
        t = (LongTable if repeat else Table)(data, colWidths=widths, repeatRows=head_rows if repeat else 0)
        style = [("FONT", (0, 0), (-1, -1), "Helvetica", 7.5), ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("BACKGROUND", (0, 0), (-1, head_rows - 1), C(NAVY)), ("TEXTCOLOR", (0, 0), (-1, head_rows - 1), colors.white),
                 ("FONT", (0, 0), (-1, head_rows - 1), "Helvetica-Bold", 7.5), ("ALIGN", (0, 0), (-1, head_rows - 1), "CENTER"),
                 ("LINEBELOW", (0, head_rows), (-1, -1), 0.25, C("#e0e6e8")), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        t.setStyle(TableStyle(style + list(extra)))
        return t

    story = [Paragraph(h["title"].replace("&", "&amp;"), st_title),
             Paragraph(f"Status month: <b>{h['status_label']}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Prepared {h['prepared']} &nbsp;&nbsp;|&nbsp;&nbsp; Revision {h['revision']}"
                       + (f" &nbsp;&nbsp;|&nbsp;&nbsp; Client {h['client']}" if h["client"] else "") + (f" &nbsp;&nbsp;|&nbsp;&nbsp; PM {h['pm']}" if h["pm"] else ""), st_sub),
             Spacer(1, 6)]

    # revenue
    rev = [["Stage", "Scope", "Previous", "This month", "To date", "Remaining", "Contract value"]]
    ext = []
    for s in d["revenue"]["stages"]:
        for i, x in enumerate(s["rows"]):
            rev.append([s["stage"] if i == 0 else "", x["scope"]] + [_money(x[k]) for k in ("previous", "this_month", "to_date", "remaining", "contract_value")])
            rr = len(rev) - 1
            if i == 0:
                ext += [("FONT", (0, rr), (0, rr), "Helvetica-Bold", 7.5), ("TEXTCOLOR", (0, rr), (0, rr), C(NAVY)), ("LINEABOVE", (0, rr), (-1, rr), 0.6, C("#9aa5ab"))]
            if x.get("total"):
                ext += [("FONT", (1, rr), (-1, rr), "Helvetica-Bold", 7.5)]
    ext += [("ALIGN", (0, 1), (1, -1), "LEFT")]
    left_w = W * 0.56
    rev_t = grid(rev, [left_w * f for f in (0.11, 0.15, 0.148, 0.148, 0.148, 0.148, 0.148)], extra=ext)

    mg = [["Metric", "Original", "Revised", "To date", "At completion"]]
    ext = [("ALIGN", (0, 1), (0, -1), "LEFT")]
    for x in d["margin"]:
        fmtv = (lambda v: f"{v * 100:.1f}%") if x.get("pct") else _money
        mg.append([x["metric"]] + [fmtv(x[k]) for k in ("original", "revised", "to_date", "at_completion")])
        if x["metric"].startswith("Gross"):
            ext.append(("FONT", (0, len(mg) - 1), (-1, len(mg) - 1), "Helvetica-Bold", 7.5))
    ext.append(("LINEABOVE", (0, 3), (-1, 3), 0.6, C("#9aa5ab")))
    right_w = W - left_w - 14
    mg_t = grid(mg, [right_w * f for f in (0.24, 0.19, 0.19, 0.19, 0.19)], extra=ext)

    vr = [["Variation", "Approved", "This month", "To be claimed", "In Pronto?"]]
    ext = [("ALIGN", (0, 1), (0, -1), "LEFT"), ("ALIGN", (4, 1), (4, -1), "CENTER")]
    for x in d["variations"]["rows"]:
        vr.append([x["ref"], _money(x["approved"]), _money(x["this_month"]), _money(x["to_be_claimed"]), x["pronto"].replace("✓", "OK").replace("✗", "Missing").replace("Δ", "Diff")])
        ext.append(("TEXTCOLOR", (4, len(vr) - 1), (4, len(vr) - 1), C(GREEN if x["state"] == "ok" else "#c62828")))
    vt = d["variations"]["total"]
    vr.append(["Total", _money(vt["approved"]), _money(vt["this_month"]), _money(vt["to_be_claimed"]), f"{d['variations']['to_action']} to action" if d["variations"]["to_action"] else "All in Pronto"])
    ext += [("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 7.5), ("LINEABOVE", (0, -1), (-1, -1), 0.6, C("#9aa5ab"))]
    vr_t = grid(vr, [right_w * f for f in (0.24, 0.19, 0.19, 0.19, 0.19)], extra=ext)

    cl = [["Check", "PMT (claims)", "Pronto", "Difference", "Status"]]
    ext = [("ALIGN", (0, 1), (0, -1), "LEFT")]
    for x in d["claims"]["rows"]:
        cl.append([x["check"], _money(x["pmt"]), _money(x["pronto"]), _money(x["diff"]), x["status"]])
        ext.append(("TEXTCOLOR", (4, len(cl) - 1), (4, len(cl) - 1), C(GREEN if x["status"] in ("OK", "Fully paid") else ORANGE)))
    cl_t = grid(cl, [left_w * f for f in (0.32, 0.17, 0.17, 0.17, 0.17)], extra=ext)

    left = [Paragraph("REVENUE", st_sec), rev_t, Spacer(1, 3), Paragraph(d["revenue"]["note"], st_note), Paragraph("CLAIMS — PMT vs PRONTO", st_sec), cl_t]
    if not d["claims"]["has_pronto"]:
        left.append(Paragraph("No Pronto claims export loaded: the Pronto column is empty.", st_note))
    right = [Paragraph("GROSS MARGIN", st_sec), mg_t, Paragraph("APPROVED VARIATIONS", st_sec), vr_t]
    top = Table([[left, right]], colWidths=[left_w + 14, right_w])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [top, Spacer(1, 8)]

    # cashflow
    cf = d["cashflow"]
    story.append(Paragraph("CASHFLOW — COST AND REVENUE BY MONTH", st_sec))
    story.append(_cash_chart(cf, W, 250))
    story.append(Paragraph(cf["note"], st_note))
    n = len(cf["months"])
    per = -(-n // max(1, -(-n // 18)))  # equal blocks of at most 18 months
    lab_w = 95
    for s in range(0, len(cf["months"]), per):
        idx = list(range(s, min(len(cf["months"]), s + per)))
        cw = (W - lab_w) / per
        data = [[""] + [cf["labels"][i] for i in idx], [""] + [cf["flag"][i] for i in idx]]
        ext = [("BACKGROUND", (0, 1), (-1, 1), colors.white), ("TEXTCOLOR", (0, 1), (-1, 1), C(SLATE)), ("FONT", (0, 1), (-1, 1), "Helvetica", 6),
               ("ALIGN", (0, 2), (0, -1), "LEFT")]
        for j, i in enumerate(idx, start=1):
            fl = cf["flag"][i]
            bg = C("#DCEDD5") if fl == "Forecast" else (C("#A6C9EC") if fl == "Current" else C("#DDEBF7"))
            ext.append(("BACKGROUND", (j, 1), (j, 1), bg))
        for lab, k in (("Revenue", "revenue"), ("Cost", "cost"), ("Net", "net"), ("Cumulative revenue", "cum_revenue"), ("Cumulative cost", "cum_cost"), ("Cumulative net", "cum_net")):
            data.append([lab] + [_money(cf[k][i]) for i in idx])
            if lab.endswith("Net") or lab == "Net":
                ext.append(("FONT", (0, len(data) - 1), (-1, len(data) - 1), "Helvetica-Bold", 7.5))
        ext.append(("LINEABOVE", (0, 5), (-1, 5), 0.8, C(NAVY)))
        story += [KeepTogether([grid(data, [lab_w] + [cw] * len(idx), head_rows=1, extra=ext)]), Spacer(1, 5)]

    # cost table
    story.append(Paragraph("COST", st_sec))
    widths = [52, 120, 52, 150] + [(W - 374) / 11] * 11
    bands = [""] * 15
    for name, a, b in COST_BANDS:
        bands[a] = name
    data = [bands, [c[0] for c in COST_COLS]]
    ext = [("BACKGROUND", (0, 0), (-1, 0), colors.white), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    for name, a, b in COST_BANDS:
        ext += [("SPAN", (a, 0), (b, 0)), ("BACKGROUND", (a, 0), (b, 0), C(ORANGE))]
    ext += [("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 6.5), ("ALIGN", (0, 2), (3, -1), "LEFT")]
    tt = d["cost"]["total"]
    data.append(["TOTAL", "", "", ""] + [_money(tt[k]) for _, k, _ in COST_COLS[4:]])
    ext += [("FONT", (0, 2), (-1, 2), "Helvetica-Bold", 7.5), ("LINEBELOW", (0, 2), (-1, 2), 0.8, C(NAVY))]
    for x in d["cost"]["rows"]:
        line = x["kind"] in ("line", "pot")
        data.append([x["code"], Paragraph(x["function"].replace("&", "&amp;"), st_cell), x["resource_code"], Paragraph(x["resource"].replace("&", "&amp;"), st_cell)]
                    + [_money(x[k]) for _, k, _ in COST_COLS[4:]])
        rr = len(data) - 1
        if not line and x["level"] == 1:
            ext += [("BACKGROUND", (0, rr), (-1, rr), C(GREY)), ("TEXTCOLOR", (0, rr), (-1, rr), C(ORANGE)), ("FONT", (0, rr), (-1, rr), "Helvetica-Bold", 7.5)]
        elif not line:
            ext += [("TEXTCOLOR", (0, rr), (-1, rr), C(NAVY)), ("FONT", (0, rr), (-1, rr), "Helvetica-Bold", 7.5)]
    story.append(grid(data, widths, head_rows=2, extra=ext, repeat=True))
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()

