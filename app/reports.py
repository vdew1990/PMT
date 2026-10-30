"""Dashboard, PMR output, reconciliation, data health and month-end snapshots."""
import json
from collections import defaultdict

from . import db, engine, revenue, variations


def _cum(xs):
    out, t = [], 0.0
    for x in xs:
        t += x
        out.append(t)
    return out


def project_margin(con, pid, res=None):
    res = res or engine.compute(con, pid)
    rs = revenue.summary(con, pid)
    t = res["total"]
    orig_cost = t["orig_budget"] + t["orig_risk"]
    rev_orig = rs["original"]
    rev_rec = rs["recognised"]
    full_allowance = t["budget"] + t["risk"]      # margin is a company measure: it carries the risk bucket as a provision
    gp_orig = rev_orig - orig_cost
    gp_rev_plan = rev_rec - full_allowance
    # the forecast carries the same provision: the risk bucket still unspent sits on top of EAC (which excludes it), as in the original and revised plan
    cost_fc = t["eac"] + t["risk"]
    gp_fc = rev_rec - cost_fc
    pct = lambda a, b: (a / b) if b else None
    return dict(revenue_original=rev_orig, revenue_recognised=rev_rec, revenue_official=rs["official"],
                cost_original=orig_cost, cost_allowance=full_allowance, eac=t["eac"], cost_forecast=cost_fc,
                gp_original=gp_orig, gp_original_pct=pct(gp_orig, rev_orig),
                gp_revised_plan=gp_rev_plan, gp_revised_plan_pct=pct(gp_rev_plan, rev_rec),
                gp_forecast=gp_fc, gp_forecast_pct=pct(gp_fc, rev_rec),
                erosion=gp_fc - gp_orig, eac_cmt_style=t["eac_cmt_style"],
                gp_cmt_style=rev_rec - t["eac_cmt_style"] - t["risk"], accrual_effect=t["acc"])


def margin_bridge(con, pid, res=None):
    """Day-zero profit to forecast profit, in steps that add up exactly:
         original profit
       + revenue added (approved variations, confirmed options: recognised less original revenue)
       - allowance added (budget and risk the variations and any new funds brought: full allowance less the original estimate)
       + budget less EAC (the net of every line's over and underrun)
       = forecast profit.
    The last step is split by CBS line (overruns and underruns, biggest first); whatever the lines do not carry (pots and
    unplaced cost) is shown as its own row so the split always reconciles."""
    res = res or engine.compute(con, pid)
    m = project_margin(con, pid, res)
    t = res["total"]
    rev_added = m["revenue_recognised"] - m["revenue_original"]
    allowance_added = m["cost_allowance"] - m["cost_original"]
    net = t["budget"] - t["eac"]
    leaves = [r for r in engine.scope_leaves(res, None) if (r["eac"] or r["allowance"])]
    pick = lambda r: dict(id=r["id"], node_id=r.get("node_id"), code=r["code"], name=r["name"], gp=r["gp"], allowance=r["allowance"], eac=r["eac"],
                          effect=r["contingency"], function=r.get("function"))
    over = sorted([pick(r) for r in leaves if r["contingency"] < -1], key=lambda r: r["effect"])
    under = sorted([pick(r) for r in leaves if r["contingency"] > 1], key=lambda r: -r["effect"])
    other = net - sum(r["effect"] for r in over) - sum(r["effect"] for r in under)
    # by category (grandparent): what each CBS grandparent contributes
    cats = {}
    for r in over + under:
        c = cats.setdefault(r["gp"], dict(gp=r["gp"], over=0.0, under=0.0))
        c["over" if r["effect"] < 0 else "under"] += r["effect"]
    steps = [dict(key="original", label="Original profit (day zero)", value=m["gp_original"], total=True),
             dict(key="revenue", label="Revenue added: approved variations and confirmed options", value=rev_added),
             dict(key="allowance", label="Allowance added for them (budget and risk, including new funds)", value=-allowance_added),
             dict(key="overruns", label="Overruns on cost lines", value=sum(r["effect"] for r in over)),
             dict(key="underruns", label="Underruns on cost lines", value=sum(r["effect"] for r in under)),
             dict(key="other", label="Not on a cost line (pots and unplaced cost)", value=other),
             dict(key="forecast", label="Forecast profit", value=m["gp_forecast"], total=True)]
    return dict(erosion=m["erosion"], direction="uplift" if m["erosion"] >= 0 else "erosion", steps=steps, over=over, under=under,
                categories=sorted(cats.values(), key=lambda c: c["over"] + c["under"]), margin=m,
                check=round(m["gp_original"] + rev_added - allowance_added + net - m["gp_forecast"], 2))


def dashboard(con, pid, node=None, from_month=None, to_month=None, res=None):
    res = res or engine.compute(con, pid)
    grid, M = res["grid"], res["status_month"]
    leaves = engine.scope_leaves(res, node)
    scope_row = None
    if node not in (None, "", "root", 0, "0"):
        key = node if str(node).startswith("p") else int(node)
        scope_row = next((r for r in res["rows"] if r["id"] == key), None)
    agg = engine.aggregate(leaves, ("orig_budget", "orig_risk", "allowance", "budget", "risk", "variations", "ctd", "acc",
                                    "ctc", "eac", "outstanding", "po_committed", "ctd_journal", "eac_cmt_style"))
    agg["spent_pct"] = ((agg["ctd"] + agg["acc"]) / agg["allowance"]) if agg["allowance"] else None
    agg["eac_pct_allowance"] = (agg["eac"] / agg["allowance"]) if agg["allowance"] else None
    G = len(grid)
    a = [sum(r["a"][i] for r in leaves) for i in range(G)]
    x = [sum(r["x"][i] for r in leaves) for i in range(G)]
    f = [sum(r["f"][i] for r in leaves) for i in range(G)]
    lo = grid.index(from_month) if from_month in grid else 0
    hi = grid.index(to_month) if to_month in grid else G - 1
    sl = slice(lo, hi + 1)
    cost = dict(months=grid[sl], actual=a[sl], accrual=x[sl], forecast=f[sl])
    total_series = [a[i] + x[i] + f[i] for i in range(G)]
    cost["cum_actual"] = [v if grid[i] <= M else None for i, v in enumerate(_cum([a[i] + x[i] for i in range(G)]))][sl]
    cum_all = _cum(total_series)
    cost["cum_total"] = cum_all[sl]
    cost["cum_forecast"] = [v if grid[i] >= M else None for i, v in enumerate(cum_all)][sl]
    # allowance line (straight to the status month is meaningless, so show the final allowance as a target)
    # drill level: children of the selected node
    by_parent = defaultdict(list)
    for r in res["rows"]:
        by_parent[r["parent_id"]].append(r)
    if scope_row is None:
        kids = [r for r in res["rows"] if r["level"] == 1]
    elif scope_row["kind"] == "group":
        kids = by_parent.get(scope_row["node_id"], [])
    else:
        kids = [scope_row]
    children = [dict(id=k["id"], code=k["code"], name=k["name"], kind=k["kind"], gp=k["gp"],
                     allowance=k["allowance"], ctd=k["ctd"], acc=k["acc"], ctc=k["ctc"], eac=k["eac"],
                     contingency=k["contingency"], status=k["budget_status"]) for k in kids]
    lines = [r for r in leaves if (r["eac"] or r["allowance"])]
    over = sorted([r for r in lines if r["contingency"] < -1], key=lambda r: r["contingency"])
    under = sorted([r for r in lines if r["contingency"] > 1], key=lambda r: -r["contingency"])
    pick = lambda r: dict(id=r["id"], code=r["code"], name=r["name"], gp=r["gp"], allowance=r["allowance"], eac=r["eac"],
                          contingency=r["contingency"], function=r.get("function"))
    top_over = [pick(r) for r in over[:10]]
    top_under = [pick(r) for r in under[:10]]
    concentration = dict(lines_over=len(over), total_over=sum(r["contingency"] for r in over),
                         top10_over=sum(r["contingency"] for r in over[:10]),
                         lines_under=len(under), total_under=sum(r["contingency"] for r in under),
                         top10_under=sum(r["contingency"] for r in under[:10]),
                         worst=pick(over[0]) if over else None, best=pick(under[0]) if under else None)
    # by grandparent over time (for stacked chart)
    by_gp = {}
    for r in leaves:
        d = by_gp.setdefault(r["gp"], [0.0] * G)
        for i in range(G):
            d[i] += r["a"][i] + r["x"][i] + r["f"][i]
    out = dict(
        scope=dict(id=(scope_row["id"] if scope_row else None), code=(scope_row["code"] if scope_row else "ALL"),
                   name=(scope_row["name"] if scope_row else "Whole project"), kind=(scope_row["kind"] if scope_row else "project")),
        status_month=M, kpi=agg, cost=cost, children=children, top_over=top_over, top_under=top_under,
        concentration=concentration, by_gp={k: v[sl] for k, v in by_gp.items()}, months=grid[sl],
        n_leaves=len(leaves),
        top_resources=[dict(id=r["id"], name=r["name"], code=r["code"], function=r.get("function"), ctd=r["ctd"], eac=r["eac"])
                       for r in sorted(leaves, key=lambda r: -(r["ctd"] or 0))[:10] if r["ctd"]],
        status_counts={s: sum(1 for r in lines if r["budget_status"] == s) for s in ("OVERRUN", "ON BUDGET", "UNDERRUN", "NO ALLOWANCE")},
    )
    if scope_row is None:
        out["margin"] = project_margin(con, pid, res)
        out["revenue"] = revenue.revenue_curve(con, pid, grid, M)
        rc = out["revenue"]["series"]
        out["revenue"]["months"] = [s["month"] for s in rc][sl]
        cr = _cum([s["actual"] for s in rc]); cp = _cum([s["actual"] + s["planned"] for s in rc])
        out["revenue"]["cum_actual"] = [v if grid[i] <= M else None for i, v in enumerate(cr)][sl]
        out["revenue"]["cum_total"] = cp[sl]
        rs = revenue.summary(con, pid)
        out["contract"] = rs
        from . import linking
        ids = linking.scope_ids(con, pid)   # a parent project: its children's claims, variations and milestones
        q = ",".join("?" * len(ids))
        cl = db.rows(con, f"SELECT status, COUNT(*) n, COALESCE(SUM((SELECT SUM(COALESCE(certified, amount)) FROM claim_line WHERE claim_id=claim.id)),0) amt FROM claim WHERE project_id IN ({q}) GROUP BY status", ids)
        out["claims"] = {r["status"]: {"n": r["n"], "amount": r["amt"]} for r in cl}
        vs = [v for i in ids for v in variations.listing(con, i)]
        out["variations"] = dict(
            total=len(vs), open=sum(1 for v in vs if not v["closed"]),
            by_status={s: {"n": sum(1 for v in vs if v["client_status"] == s), "value": sum(v["value"] or 0 for v in vs if v["client_status"] == s)}
                       for s in sorted({v["client_status"] for v in vs})},
            recognised_value=sum(v["value"] or 0 for v in vs if v["recognised"]))
        out["milestones"] = db.rows(con, f"SELECT * FROM milestone WHERE project_id IN ({q}) AND COALESCE(forecast_end, baseline_end) >= date(?) "
                                         "AND (actual_date IS NULL OR actual_date='') ORDER BY COALESCE(forecast_end, baseline_end) LIMIT 6",
                                    (*ids, M + "-01"))
        if res.get("is_parent"):
            out["linked"] = res["children"]
    out["health"] = health_counts(con, pid, res)
    return out


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------
def health(con, pid, res=None):
    from . import linking
    if linking.is_parent(con, pid):   # a parent: each child project's checks, named, opening in that child
        return [dict(c, title=f"{k['name']}: {c['title']}", id=f"{k['id']}:{c['id']}", project_id=k["id"])
                for k in linking.children(con, pid) for c in health(con, k["id"])]
    res = res or engine.compute(con, pid)
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    tol = res["tolerance"]
    checks = []

    def add(id_, level, title, detail, count=0, link=None):
        checks.append(dict(id=id_, level=level, title=title, detail=detail, count=count, link=link))

    from . import pronto_raw
    fut = pronto_raw.future_rows(con, pid)
    if fut:
        # an actual is an actual (it stays in CTD) but a date in the future is a keying error in Pronto to raise with finance
        docs = sorted({f"{r['doc_type']} {r['doc_no']}" + (f" ({r['account_desc']})" if r["account_desc"] else "") for r in fut})
        add("pronto_future", "error", f"{len(fut)} Pronto row(s) dated in the future, up to {fut[-1]['tx_date']}",
            f"Worth {sum(r['cost'] or 0 for r in fut):,.2f}, counted in cost to date. A date keyed wrong in Pronto: ask finance to correct "
            f"{', '.join(docs[:6])}{' ...' if len(docs) > 6 else ''}.", len(fut), "pronto?inspect=transactions&check=transactions:future")
    mx = db.scalar(con, "SELECT MAX(tx_date) FROM pronto_tx WHERE project_id=? AND tx_date<=?", (pid, pronto_raw._cutoff(con, pid)), None)
    if not mx:
        add("pronto_none", "warn", "No Pronto transactions loaded", "Upload the GL transactions export on the Pronto page.", 0, "pronto")
    else:
        sd = p["status_date"] or ""
        if sd and mx < sd[:7] + "-01":
            add("pronto_stale", "warn", "Pronto is older than the status month",
                f"Latest transaction is {mx}; the status date is {sd}. The forecast is running on out-of-date actuals.", 0, "pronto")
        else:
            add("pronto_ok", "ok", "Pronto is current", f"Latest transaction {mx}.", 0, "pronto")
    unplaced = res["unplaced"]
    if unplaced:
        add("unplaced", "error", "Cost rows with a category that is not in the CBS",
            ", ".join(f"{u['category']} ({u['n']} rows, {u['cost']:,.0f})" for u in unplaced), sum(u["n"] for u in unplaced), "cbs")
    parked = [r for r in res["rows"] if r["kind"] == "pot" and (r["ctd"] or r["acc"])]
    if parked:
        add("parked", "warn", "Actuals sitting on unallocated pots",
            f"{len(parked)} CBS group(s) have actuals with no resource line. Create the lines from the suggestions list.",
            len(parked), "pronto")
    if db.scalar(con, "SELECT COUNT(*) FROM pronto_po WHERE project_id=?", (pid,)):
        have = {r[0] for r in con.execute("SELECT DISTINCT order_no FROM pronto_po WHERE project_id=?", (pid,))}
        miss = {r[0] for r in con.execute("SELECT DISTINCT doc_no FROM pronto_tx WHERE project_id=? AND doc_type='PO' AND class='actual'", (pid,))} - have
        if miss:
            add("po_missing", "warn", "POs in the GL that are not in the PO export", ", ".join(sorted(miss)[:12]), len(miss), "pronto")
    short = [r for r in res["rows"] if r["kind"] in ("line", "pot") and r.get("po_status") == "SHORT"]
    if short:
        add("ctc_short", "error", "Cost to complete is below open PO commitments",
            f"{len(short)} line(s): " + ", ".join(r["code"] for r in short[:8]), len(short), "costcontrol")
    noeff = [r for r in res["rows"] if r["kind"] == "line" and r["note"]]
    if noeff:
        add("method_note", "warn", "Lines whose forecast method has nothing to work from",
            ", ".join(f"{r['code']} ({r['note']})" for r in noeff[:6]), len(noeff), "costcontrol")
    inv = db.scalar(con, "SELECT COUNT(*) FROM accrual WHERE project_id=? AND status='investigate'", (pid,))
    if inv:
        add("accr_investigate", "error", "Accruals whose invoice landed for a different amount", "Review on the Accruals page.", inv, "accruals")
    old = db.scalar(con, "SELECT COUNT(*) FROM accrual WHERE project_id=? AND status='open' AND month < ?", (pid, db.add_months(res["status_month"], -2)))
    if old:
        add("accr_old", "warn", "Accruals open for more than two months", "Reverse or confirm them.", old, "accruals")
    ctd_rows = db.rows(con, "SELECT category, SUM(actual) a FROM pronto_ctd WHERE project_id=? GROUP BY category", (pid,))
    if ctd_rows:
        mine = defaultdict(float)
        for r in res["rows"]:
            if r["kind"] in ("line", "pot") and r.get("category"):
                mine[r["category"]] += r["ctd"]
        diffs = [(c["category"], c["a"], mine.get(c["category"], 0.0)) for c in ctd_rows
                 if re_cost(c["category"]) and abs((c["a"] or 0) - mine.get(c["category"], 0.0)) > max(tol, 1)]
        if diffs:
            add("ctd_tie", "error", "CTD does not tie to the Pronto CTD overview",
                ", ".join(f"{c} ({a:,.0f} vs {b:,.0f})" for c, a, b in diffs[:6]), len(diffs), "reconcile")
        else:
            add("ctd_tie_ok", "ok", "CTD ties to the Pronto CTD overview", "Every category agrees within tolerance.", 0, "reconcile")
    neg = [r for r in res["rows"] if r["kind"] == "pot" and r["allowance"] < -tol]
    if neg:
        add("overalloc", "error", "Over-allocated pots", "More has been transferred out of these groups than they hold: " + ", ".join(r["code"] for r in neg[:6]), len(neg), "allowance")
    zero = [r for r in res["rows"] if r["kind"] == "line" and r["allowance"] <= tol and (r["ctd"] + r["acc"]) > 1000]
    if zero:
        add("no_allow", "warn", "Lines spending with no allowance", ", ".join(r["code"] for r in zero[:8]), len(zero), "allowance")
    tot_t = res["total"]
    gridsum = sum(tot_t["a"]) + sum(tot_t["x"]) + sum(tot_t["f"])
    if abs(gridsum - tot_t["eac"]) > max(tol, 1):
        add("grid_tie", "error", "Month grid does not tie to EAC", f"Grid {gridsum:,.0f} vs EAC {tot_t['eac']:,.0f}", 1, "costcontrol")
    rs = revenue.summary(con, pid)
    if rs["recognised"]:
        rc = revenue.revenue_curve(con, pid, res["grid"], res["status_month"])
        gap = rs["recognised"] - rc["claimed_to_date"] - rc["future_planned"]
        if abs(gap) > 1000:
            add("phasing", "warn", "Revenue not fully phased", f"{gap:,.0f} of contract value is neither claimed nor scheduled.", 1, "claims")
    return checks


def re_cost(c):
    import re
    return bool(re.match(r"^(PL|PS|PM|PE)\d{2}$", c or ""))


def health_counts(con, pid, res=None):
    chk = health(con, pid, res)
    return {"error": sum(1 for c in chk if c["level"] == "error"), "warn": sum(1 for c in chk if c["level"] == "warn"),
            "ok": sum(1 for c in chk if c["level"] == "ok")}


# --------------------------------------------------------------------------
# Reconcile (the workbook's Match sheet)
# --------------------------------------------------------------------------
def reconcile(con, pid, res=None):
    res = res or engine.compute(con, pid)
    m = project_margin(con, pid, res)
    ctd_total = res["total"]["ctd"]
    inv = -(db.scalar(con, "SELECT SUM(cost) FROM pronto_tx WHERE project_id=? AND class='revenue'", (pid,)))
    rev_pronto = inv or None
    cmt = db.one(con, "SELECT * FROM cmt_entry WHERE project_id=? ORDER BY as_of DESC, id DESC LIMIT 1", (pid,))
    base = db.one(con, "SELECT * FROM snapshot WHERE project_id=? AND kind='baseline' ORDER BY id DESC LIMIT 1", (pid,))
    day0 = json.loads(base["summary_json"]) if base else None
    table = []

    def pct(g, r):
        return (g / r) if r else None
    pmt = dict(label="PMT (this tool)", as_of=res["status_month"], revenue=m["revenue_recognised"], eac=m["eac"],
               gp=m["gp_forecast"], gm=m["gp_forecast_pct"])
    table.append(pmt)
    if cmt:
        table.append(dict(label="CMT (Finance)", as_of=cmt["as_of"], revenue=cmt["revenue"], eac=cmt["eac"],
                          gp=(cmt["revenue"] or 0) - (cmt["eac"] or 0), gm=pct((cmt["revenue"] or 0) - (cmt["eac"] or 0), cmt["revenue"])))
    table.append(dict(label="Pronto (invoiced less CTD)", as_of=db.scalar(con, "SELECT MAX(tx_date) FROM pronto_tx WHERE project_id=?", (pid,), None),
                      revenue=rev_pronto, eac=ctd_total, gp=(rev_pronto - ctd_total) if rev_pronto else None,
                      gm=pct(rev_pronto - ctd_total, rev_pronto) if rev_pronto else None))
    if day0:
        table.append(dict(label="Day zero (baseline)", as_of=base["status_date"], revenue=day0["margin"]["revenue_original"],
                          eac=day0["margin"]["cost_original"], gp=day0["margin"]["gp_original"], gm=day0["margin"]["gp_original_pct"]))
    # category tie-out
    mine = defaultdict(float)
    for r in res["rows"]:
        if r["kind"] in ("line", "pot") and r.get("category"):
            mine[r["category"]] += r["ctd"]
    pr = {r["category"]: r for r in db.rows(con, "SELECT category, SUM(actual) actual, SUM(budget) budget FROM pronto_ctd WHERE project_id=? GROUP BY category", (pid,))}
    cats = sorted(set(mine) | {c for c in pr if re_cost(c)})
    tie = [dict(category=c, pmt=mine.get(c, 0.0), pronto=(pr.get(c) or {}).get("actual"), pronto_budget=(pr.get(c) or {}).get("budget"),
                diff=(mine.get(c, 0.0) - (pr.get(c) or {}).get("actual", 0.0)) if c in pr else None) for c in cats]
    # claims tie-out
    mine_claims = db.rows(con, "SELECT c.claim_no, c.period, c.status, (SELECT SUM(amount) FROM claim_line WHERE claim_id=c.id) total, c.pronto_claim_no FROM claim c WHERE c.project_id=? ORDER BY c.period", (pid,))
    pronto_claims = db.rows(con, "SELECT * FROM pronto_claim WHERE project_id=? ORDER BY claim_no", (pid,))
    return dict(margin=m, table=table, tie=tie, claims_app=mine_claims, claims_pronto=pronto_claims,
                cmt_note="The CMT calculates EAC as cost-to-date plus cost-to-complete and leaves accruals out. "
                         "This tool includes accruals, so the two will differ by roughly the accrual balance.",
                accruals=res["total"]["acc"], cmt_entry=cmt)


# --------------------------------------------------------------------------
# PMR output
# --------------------------------------------------------------------------
def _risk_totals(con, pid, res):
    from . import risk as risk_mod
    pos = risk_mod.positions(con, pid, res)
    return dict(risk_bucket=sum(x["bucket"] for x in pos), risk_released=sum(x["released"] for x in pos), risk_remaining=sum(x["bucket_remaining"] for x in pos),
                risk_occurred=sum(x["occurred"] for x in pos), risk_uncovered=sum(x["uncovered"] for x in pos), contingency_earmarked=sum(x["contingency"] for x in pos),
                risk_from_contingency=sum(x["from_contingency"] for x in pos), risk_infused=sum(x["infused"] for x in pos))


def pmr(con, pid, res=None):
    res = res or engine.compute(con, pid)
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    m = project_margin(con, pid, res)
    t = res["total"]
    grid, M = res["grid"], res["status_month"]
    rev = revenue.revenue_curve(con, pid, grid, M)
    rs = revenue.summary(con, pid)
    pl = [r for r in res["rows"] if r["kind"] in ("line", "pot") and r["gp"] == "PL"]
    nonpl = [r for r in res["rows"] if r["kind"] in ("line", "pot") and r["gp"] != "PL"]
    G = len(grid)
    series = dict(
        months=grid,
        revenue_actual=[s["actual"] for s in rev["series"]], revenue_planned=[s["planned"] for s in rev["series"]],
        cost_ps_pm_pe=[sum(r["a"][i] + r["x"][i] + r["f"][i] for r in nonpl) for i in range(G)],
        cost_labour=[sum(r["a"][i] + r["x"][i] + r["f"][i] for r in pl) for i in range(G)],
        flag=["Actual" if g < M else ("Current" if g == M else "Forecast") for g in grid])
    ms = db.rows(con, "SELECT * FROM milestone WHERE project_id=? ORDER BY sort_order, id", (pid,))
    return dict(
        identity=dict(project=p["name"], code=p["code"], number=p["number"], client=p["client_name"], pm=p["epec_pm"],
                      client_pm=p["client_pm"], status_date=p["status_date"], project_start=p["project_start"],
                      project_end=p["project_end"]),
        revenue=dict(original=m["revenue_original"], approved_variations=rs["variations_approved"], revised_official=rs["official"],
                     recognised=rs["recognised"], claimed_to_date=rev["claimed_to_date"], residual=rs["recognised"] - rev["claimed_to_date"]),
        cost=dict(original_budget=t["orig_budget"], variations_allowance=t["variations"], current_allowance=t["allowance"],
                  ctd=t["ctd"], accruals=t["acc"], ctc=t["ctc"], eac=t["eac"]),
        contingency=dict(original_risk=t["orig_risk"], current_risk=t["risk"], forecast_at_completion=t["contingency"], **_risk_totals(con, pid, res)),
        margin=m, series=series, milestones=ms,
        check=dict(grid_minus_eac=sum(series["cost_ps_pm_pe"]) + sum(series["cost_labour"]) - t["eac"]))


# --------------------------------------------------------------------------
# Snapshots
# --------------------------------------------------------------------------
def create_snapshot(con, pid, label=None, kind="eom"):
    res = engine.compute(con, pid)
    M = res["status_month"]
    p = db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,))
    m = project_margin(con, pid, res)
    rev = revenue.revenue_curve(con, pid, res["grid"], M)
    t = res["total"]
    G = len(res["grid"])
    cost_total = [t["a"][i] + t["x"][i] + t["f"][i] for i in range(G)]
    curve = dict(months=res["grid"], cost=cost_total, revenue=[s["actual"] + s["planned"] for s in rev["series"]])
    summary = dict(margin=m, totals={k: v for k, v in t.items() if not isinstance(v, list)}, status_month=M)
    if kind == "eom":
        old = db.one(con, "SELECT id FROM snapshot WHERE project_id=? AND kind='eom' AND period=?", (pid, M))
        if old:
            con.execute("DELETE FROM snapshot WHERE id=?", (old["id"],))
    else:
        con.execute("DELETE FROM snapshot WHERE project_id=? AND kind=?", (pid, kind))
    sid = db.insert(con, "snapshot", dict(project_id=pid, period=M, label=label or (("Day zero" if kind == "baseline" else "EOM ") + M),
                                          kind=kind, status_date=p["status_date"], summary_json=json.dumps(summary),
                                          curve_json=json.dumps(curve)))
    for r in res["rows"]:
        if r["kind"] == "pot" and not (r["allowance"] or r["eac"]):
            continue
        series = [round(r["a"][i] + r["x"][i] + r["f"][i], 2) for i in range(G)]
        rnd = lambda xs: json.dumps([round(v, 2) for v in xs])
        db.insert(con, "snapshot_line", dict(snapshot_id=sid, node_ref=str(r["id"]), code=r["code"], name=r["name"], level=r["level"],
                                             gp=r["gp"], budget=r["budget"], risk=r["risk"], allowance=r["allowance"],
                                             ctd=r["ctd"], acc=r["acc"], ctc=r["ctc"], eac=r["eac"], months_json=json.dumps(series),
                                             method=r.get("method"), kind=r["kind"], parent_ref=None if r["parent_id"] is None else str(r["parent_id"]),
                                             a_json=rnd(r["a"]), x_json=rnd(r["x"]), f_json=rnd(r["f"])))
    return sid


def _snap_side(con, pid, x):
    """One side of a comparison: label, month grid, and rows by CBS code. x is a snapshot id or 'live'."""
    if x == "live":
        res = engine.compute(con, pid)
        G = len(res["grid"])
        rows = {r["code"]: dict(code=r["code"], name=r["name"], level=r["level"], gp=r["gp"], kind=r["kind"], allowance=r["allowance"], ctd=r["ctd"],
                                acc=r["acc"], ctc=r["ctc"], eac=r["eac"], series=[r["a"][i] + r["x"][i] + r["f"][i] for i in range(G)])
                for r in res["rows"]}
        return dict(label="Live (now)", months=res["grid"], rows=rows, margin=project_margin(con, pid, res), status_month=res["status_month"])
    s = db.one(con, "SELECT * FROM snapshot WHERE id=? AND project_id=?", (int(x), pid))
    if not s:
        raise ValueError("Snapshot not found")
    curve = json.loads(s["curve_json"] or "{}")
    summ = json.loads(s["summary_json"] or "{}")
    rows = {}
    for r in db.rows(con, "SELECT * FROM snapshot_line WHERE snapshot_id=?", (s["id"],)):
        r["series"] = json.loads(r.pop("months_json") or "[]")
        rows[r["code"]] = r
    return dict(label=s["label"], months=curve.get("months", []), rows=rows, margin=summ.get("margin"), status_month=s["period"], curve=curve)


def snapshot_compare(con, pid, a, b):
    """Movement between two snapshots (or a snapshot and live) by CBS code, plus the margin on each side."""
    A, B = _snap_side(con, pid, a), _snap_side(con, pid, b)
    out = []
    for code in sorted(set(A["rows"]) | set(B["rows"])):
        x, y = A["rows"].get(code, {}), B["rows"].get(code, {})
        row = dict(code=code, name=(y or x).get("name"), level=(y or x).get("level"), gp=(y or x).get("gp"), kind=(y or x).get("kind"),
                   new=code not in A["rows"], removed=code not in B["rows"])
        for k in ("allowance", "ctd", "acc", "ctc", "eac"):
            row[k + "_a"] = x.get(k, 0) or 0
            row[k + "_b"] = y.get(k, 0) or 0
            row[k + "_d"] = row[k + "_b"] - row[k + "_a"]
        out.append(row)
    return dict(a=dict(label=A["label"], status_month=A["status_month"], margin=A["margin"]),
                b=dict(label=B["label"], status_month=B["status_month"], margin=B["margin"]), rows=out)


def snapshot_series(con, pid, a, b, code=None):
    """Monthly cost (actual, accrual and forecast) for one CBS code, or the whole project, on both sides.

    The difference between the two is the forecast movement: where the PM moved money in time and in total.
    """
    A, B = _snap_side(con, pid, a), _snap_side(con, pid, b)
    months = sorted(set(A["months"]) | set(B["months"]))

    def pick(side):
        if code:
            r = side["rows"].get(code)
            ser = r["series"] if r else []
        else:
            tops = [r for r in side["rows"].values() if r["level"] == 1]
            ser = [sum((r["series"][i] if i < len(r["series"]) else 0) for r in tops) for i in range(len(side["months"]))]
        m = dict(zip(side["months"], ser))
        return [round(m.get(x, 0.0), 2) for x in months]
    sa, sb = pick(A), pick(B)
    return dict(months=months, a=sa, b=sb, delta=[round(y - x, 2) for x, y in zip(sa, sb)], label_a=A["label"], label_b=B["label"],
                status_a=A["status_month"], status_b=B["status_month"])


def snapshot_curves(con, pid, a, b):
    """Cumulative cost and revenue for two versions, for overlaying on one chart."""
    out = {}
    for key, x in (("a", a), ("b", b)):
        side = _snap_side(con, pid, x)
        if x == "live":
            res = engine.compute(con, pid)
            t = res["total"]
            rev = revenue.revenue_curve(con, pid, res["grid"], res["status_month"])
            curve = dict(months=res["grid"], cost=[t["a"][i] + t["x"][i] + t["f"][i] for i in range(len(res["grid"]))],
                         revenue=[s["actual"] + s["planned"] for s in rev["series"]])
        else:
            curve = side["curve"]
        out[key] = dict(label=side["label"], status_month=side["status_month"], months=curve["months"], cost=_cum(curve["cost"]),
                        revenue=_cum(curve["revenue"]), margin=side["margin"])
    return out


# --------------------------------------------------------------------------
# Work performed, invoicing and cash: the three views of revenue against cost
# --------------------------------------------------------------------------
def flows(con, pid, node=None, res=None):
    """Three comparisons, month by month.

    work      revenue claimed against cost incurred, both in the month the work was done (what the PMR reports)
    invoices  invoices sent to the client against bills received from suppliers, by invoice date
    cash      money received against money paid. Pronto's GL report carries no payment dates, so payments are modelled
              from supplier terms (labour is paid in the month it is incurred); receipts use actual paid dates where known.
    """
    res = res or engine.compute(con, pid)
    grid, M = res["grid"], res["status_month"]
    G = len(grid)
    gi = {m: i for i, m in enumerate(grid)}
    st = db.project_settings(con, pid)
    leaves = engine.scope_leaves(res, node)
    whole = node in (None, "", "root", 0, "0")
    nonpl = [r for r in leaves if r["gp"] != "PL"]
    pl = [r for r in leaves if r["gp"] == "PL"]
    arr = lambda rs, k: [sum(r[k][i] for r in rs) for i in range(G)]
    nxt = db.add_months(M, 1)

    # ---- A. value of work performed -----------------------------------------------------------
    # incurred (Pronto actual + accrued, wherever dated) and forecast are kept apart: "to date" never includes forecast
    cost_inc = [arr(leaves, "a")[i] + arr(leaves, "x")[i] for i in range(G)]
    cost_fc = arr(leaves, "f")
    cost_work = [cost_inc[i] + cost_fc[i] for i in range(G)]
    rev_work = rev_act = rev_plan = None
    rev_src = None
    if whole:
        rc = revenue.revenue_curve(con, pid, grid, M)
        rev_act = [s["actual"] for s in rc["series"]]
        rev_plan = [s["planned"] for s in rc["series"]]
        rev_work = [rev_act[i] + rev_plan[i] for i in range(G)]
        rev_src = rc["source"]

    # ---- B. invoices sent against bills received ---------------------------------------------
    inc_labour = bool(st.get("bills_include_labour", False))
    node_ids = sorted({r["node_id"] for r in leaves})
    where_nodes = "" if whole else f" AND node_id IN ({','.join('?' * len(node_ids)) or 'NULL'})"
    bills_actual = defaultdict(float)
    q = "SELECT month, SUM(cost) c FROM pronto_tx WHERE project_id=? AND class='actual' AND doc_type!='TS'" + where_nodes + " GROUP BY month"
    for r in con.execute(q, [pid] + ([] if whole else node_ids)):
        bills_actual[r["month"]] += r["c"] or 0
    labour_actual = defaultdict(float)
    q = "SELECT month, SUM(cost) c FROM pronto_tx WHERE project_id=? AND class='actual' AND doc_type='TS'" + where_nodes + " GROUP BY month"
    for r in con.execute(q, [pid] + ([] if whole else node_ids)):
        labour_actual[r["month"]] += r["c"] or 0
    bills = [bills_actual.get(m, 0.0) + (labour_actual.get(m, 0.0) if inc_labour else 0.0) for m in grid]
    f_np = arr(nonpl, "f")
    f_pl = arr(pl, "f")
    for i, m in enumerate(grid):
        if m >= M:
            bills[i] += f_np[i] + (f_pl[i] if inc_labour else 0.0)
    # work done and accrued but not yet billed arrives as a bill the following month
    acc_np = sum(arr(nonpl, "x")) + (sum(arr(pl, "x")) if inc_labour else 0.0)
    if nxt in gi:
        bills[gi[nxt]] += acc_np

    inv = None
    inv_actual = defaultdict(float)
    claims_pronto = db.rows(con, "SELECT * FROM pronto_claim WHERE project_id=?", (pid,))
    if whole:
        for r in con.execute("SELECT month, -SUM(cost) c FROM pronto_tx WHERE project_id=? AND class='revenue' GROUP BY month", (pid,)):
            inv_actual[r["month"]] += r["c"] or 0
        inv_src = "Pronto invoices" if inv_actual else None
        if not inv_actual:
            for c in revenue.claim_list(con, pid):
                if c["status"] != "draft":
                    inv_actual[(c["submitted_date"] or c["period"])[:7]] += c["effective"]
            inv_src = "claims submitted" if inv_actual else "none"
        planned = [s["planned"] for s in rc["series"]]
        inv = [inv_actual.get(m, 0.0) + (planned[i] if (m > M or (m == M and not inv_actual.get(m))) else 0.0) for i, m in enumerate(grid)]
    else:
        inv_src = None

    # ---- C. cash ------------------------------------------------------------------------------------
    paid_days = [(db.to_date(c["date_paid"]) - db.to_date(c["date_submitted"])).days for c in claims_pronto
                 if c["date_paid"] and c["date_submitted"] and (c["paid"] or 0) > 0]
    client_terms = float(st.get("client_terms_days") or (round(sum(paid_days) / len(paid_days)) if paid_days else 30))
    supplier_terms = float(st.get("supplier_terms_days") or 30)
    sh_c, sh_s = int(round(client_terms / 30)), int(round(supplier_terms / 30))
    receipts = [0.0] * G
    receipts_actual = defaultdict(float)
    receivable = 0.0
    if whole:
        if claims_pronto:
            for c in claims_pronto:
                if c["date_paid"] and (c["paid"] or 0):
                    receipts_actual[c["date_paid"][:7]] += c["paid"]
                outstanding = (c["certified"] or c["total"] or 0) - (c["paid"] or 0)
                if outstanding > 1 and c["status"] != "P":
                    receivable += outstanding
                    due = db.month_of(c["date_submitted"]) or M
                    due = db.add_months(due, sh_c)
                    receipts_actual[max(due, nxt)] += outstanding
        else:
            for c in revenue.claim_list(con, pid):
                if c["status"] == "draft":
                    continue
                pm = (c["paid_date"] or "")[:7]
                if c["status"] == "paid" or c["paid_amount"]:
                    receipts_actual[pm or c["period"][:7]] += c["paid_amount"] or c["effective"]
                else:
                    receivable += c["effective"]
                    receipts_actual[max(db.add_months((c["submitted_date"] or c["period"])[:7], sh_c), nxt)] += c["effective"]
        receipts = [receipts_actual.get(m, 0.0) for m in grid]
        for i, m in enumerate(grid):  # invoices still to be raised are received after the client's terms
            if (m > M or (m == M and not inv_actual.get(m))) and inv is not None and i + sh_c < G:
                receipts[i + sh_c] += planned[i]
    payments = [0.0] * G
    for i, m in enumerate(grid):  # supplier bills, shifted by terms
        nonlab = bills_actual.get(m, 0.0) + (f_np[i] if m >= M else 0.0)
        if i + sh_s < G:
            payments[i + sh_s] += nonlab
    if nxt in gi and gi[nxt] + sh_s < G:
        payments[gi[nxt] + sh_s] += sum(arr(nonpl, "x"))
    lab = arr(pl, "a")
    for i, m in enumerate(grid):  # labour is paid as it is incurred
        payments[i] += lab[i] + (f_pl[i] if m >= M else 0.0) + (arr(pl, "x")[i] if m <= M else 0.0)
    net = [receipts[i] - payments[i] for i in range(G)]
    cumnet = _cum(net)
    payable = sum(payments[i] for i, m in enumerate(grid) if m > M)
    lo = min(range(G), key=lambda i: cumnet[i]) if G else 0

    series = lambda x: [round(v, 2) for v in x]
    return dict(
        status_month=M, months=grid, scope="project" if whole else "scope",
        work=dict(revenue=series(rev_work) if rev_work else None, cost=series(cost_work), source=rev_src,
                  cost_incurred=series(cost_inc), cost_forecast=series(cost_fc), cost_to_date=round(sum(cost_inc), 2),
                  revenue_actual=series(rev_act) if rev_act else None, revenue_planned=series(rev_plan) if rev_plan else None,
                  revenue_to_date=round(sum(rev_act), 2) if rev_act else None,
                  cum_revenue=series(_cum(rev_work)) if rev_work else None, cum_cost=series(_cum(cost_work))),
        invoices=dict(invoiced=series(inv) if inv is not None else None, bills=series(bills),
                      invoiced_to_date=round(sum(inv_actual.values()), 2) if inv is not None else None,
                      bills_to_date=round(sum(bills_actual.values()) + (sum(labour_actual.values()) if inc_labour else 0.0), 2), invoiced_source=inv_src, bills_include_labour=inc_labour,
                      cum_invoiced=series(_cum(inv)) if inv is not None else None, cum_bills=series(_cum(bills))),
        cash=dict(received=series(receipts) if whole else None, paid=series(payments), net=series(net), cum_net=series(cumnet),
                  client_terms_days=client_terms, supplier_terms_days=supplier_terms, receivable=receivable,
                  lowest=dict(month=grid[lo], value=round(cumnet[lo], 2)) if G else None,
                  position_now=round(cumnet[gi[M]], 2) if M in gi else None, payable_after_status=round(payable, 2),
                  note="Payments to suppliers are modelled from payment terms: Pronto's GL report does not include payment dates. Labour is paid in the month incurred. "
                       "Receipts use the paid dates on Pronto claims where loaded; invoices still to raise are received after the client's terms."))
