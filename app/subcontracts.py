"""Subcontracts: schedule of values, monthly progress claims, approval, and the hand-off to cost control.

A subcontract has schedule lines (milestones, progress items, variations) that plan its value by month.
Payment terms split the price into portions, for example 10% on order, 80% by progress, 10% on QA documents:
  * Milestone: a % of the contract value (or a value), claimed when achieved.
  * Progress: a % of the contract value claimed month by month. When the subcontract has a price table (Price lines),
    the Progress portion is claimed through the price items instead: each item is claimable at price x the progress
    share (the Progress %; with no Progress line, 100% less the milestones), and the Progress line itself is not claimed.
  * Variation: a value.
The subcontractor's own planned claims by month (sub_plan, from their payment schedule) replace the even spread. Each month the
subcontractor claims against those lines; EPEC approves the claim line by line, or in total. What cost control sees:

  * Future months: the scheduled amounts not yet claimed (forecast), net of retention, when the line uses the CLAIM method.
  * Claim months not yet invoiced: an accrual for the approved amount, or the claimed amount where nothing is approved yet.
    It reverses by itself once the invoice reference lands in Pronto.
"""
import re
from collections import defaultdict
from datetime import date

from . import db


def _n(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def _r2(x):
    return round(float(x or 0), 2)


# ---- schedule ---------------------------------------------------------------
def item_series(m, contract_value):
    """Gross amount by month planned for one schedule line: the subcontractor's planned claims where loaded, otherwise
    a milestone in its start month and progress / price items evenly from start to end."""
    val = item_value(m, contract_value)
    if m.get("plan"):
        out = defaultdict(float, m["plan"])
        gap = val - sum(m["plan"].values())
        if gap > 0.005:  # a plan loaded mid-project covers what is left: the rest was planned (and claimed) before it
            out[db.add_months(min(m["plan"]), -1)] += gap
        return out
    s = (m["start_month"] or "")[:7]
    e = (m["end_month"] or "")[:7] or s
    out = defaultdict(float)
    if not s:
        return out
    if m["type"] in ("Progress", "Price") and e > s:
        ms = db.month_range(s, e)
        for x in ms:
            out[x] += val / len(ms)
    else:
        out[s] += val
    return out


def _pct_of(m, cv):
    return (m["pct"] or 0) or (((m["value"] or 0) / cv) if cv else 0.0)


def progress_share(rows, cv):
    """Share of each price-table item that is claimed by progress: the Progress % of the payment terms, or 100% less
    the milestones when the terms have no Progress line. 1 when the subcontract has no price table."""
    if not any(m["type"] == "Price" for m in rows):
        return 1.0
    prog = [m for m in rows if m["type"] == "Progress"]
    if prog:
        return sum(_pct_of(m, cv) for m in prog)
    return max(0.0, 1.0 - sum(_pct_of(m, cv) for m in rows if m["type"] == "Milestone"))


def items(con, sid, claimable_only=True):
    """Schedule lines with their progress share and the subcontractor's planned claims. With a price table, the Progress
    terms line is not claimed itself (its share is claimed through the price items) and is left out unless asked for."""
    rows = db.rows(con, "SELECT * FROM sub_milestone WHERE subcontract_id=? ORDER BY seq, id", (sid,))
    cv = db.scalar(con, "SELECT contract_value FROM subcontract WHERE id=?", (sid,)) or 0
    has_price = any(m["type"] == "Price" for m in rows)
    share = progress_share(rows, cv)
    plans = defaultdict(dict)
    for r in con.execute("SELECT item_id, month, amount FROM sub_plan WHERE subcontract_id=? ORDER BY id", (sid,)):
        if r["amount"] is None:
            plans[r["item_id"]].pop(r["month"], None)
        else:
            plans[r["item_id"]][r["month"]] = r["amount"]
    for m in rows:
        m["share"] = share if m["type"] == "Price" else 1.0
        m["plan"] = {k: v for k, v in plans.get(m["id"], {}).items() if abs(v) > 0.005}
        m["via_price"] = has_price and m["type"] == "Progress"
    return [m for m in rows if not (claimable_only and m["via_price"])]


def item_value(m, cv):
    """What can be claimed on a line: a price item at price x progress share, otherwise its value or % of the contract."""
    if m["type"] == "Price":
        return (m["value"] or 0) * m.get("share", 1.0)
    return m["value"] or ((m["pct"] or 0) * (cv or 0))


def schedule(con, sub):
    """Gross, retention held and net by month for the whole subcontract."""
    gross = defaultdict(float)
    for m in items(con, sub["id"]):
        for k, v in item_series(m, sub.get("contract_value")).items():
            gross[k] += v
    ret_pct = sub.get("retention_pct") or 0
    held = {m: v * ret_pct for m, v in gross.items()}
    net = {m: v - held[m] for m, v in gross.items()}
    rel = (sub.get("retention_release_month") or "")[:7]
    if rel and ret_pct:
        net[rel] = net.get(rel, 0) + sum(held.values())
        gross.setdefault(rel, 0)
    return dict(gross), held, net


# ---- claims -----------------------------------------------------------------
def claim_totals(con, claim, sub):
    """Effective amounts for one claim: per line the approved amount where there is one, otherwise the claimed amount."""
    lines = db.rows(con, "SELECT * FROM sub_claim_line WHERE claim_id=?", (claim["id"],))
    pct = sub.get("retention_pct") or 0
    if lines:
        claimed = sum(l["claimed"] or 0 for l in lines)
        approved = sum(l["approved"] for l in lines if l["approved"] is not None)
        n_appr = sum(1 for l in lines if l["approved"] is not None)
        eff = sum(l["approved"] if l["approved"] is not None else (l["claimed"] or 0) for l in lines)
        held = eff * pct
    else:  # a claim recorded as a lump (older data or a quick entry)
        claimed = approved = eff = claim["gross"] or 0
        n_appr = 1 if claim["status"] in ("approved", "paid") else 0
        held = claim["retention"] or 0
    rel = claim.get("retention_release") or 0
    return dict(lines=len(lines), claimed=claimed, approved=approved, approved_lines=n_appr, effective=eff, retention=held,
                release=rel, net=eff - held + rel, claimed_net=claimed - claimed * pct + rel,
                basis="approved" if lines and n_appr == len(lines) else ("part approved" if n_appr else "claimed"))


def claims_of(con, sid):
    return db.rows(con, "SELECT * FROM sub_claim WHERE subcontract_id=? ORDER BY month, id", (sid,))


def claimed(con, sub):
    """(effective gross, retention, net) over every claim that has been received (drafts excluded)."""
    g = r = n = 0.0
    for c in claims_of(con, sub["id"]):
        if c["status"] == "draft":
            continue
        t = claim_totals(con, c, sub)
        g += t["effective"]
        r += t["retention"]
        n += t["net"]
    return g, r, n


def claim_nodes(con, pid):
    """CBS lines that have a live subcontract with a claim schedule (at least one schedule line): the only lines the CLAIM method suits."""
    return {r["node_id"] for r in db.rows(con, "SELECT DISTINCT s.node_id FROM subcontract s JOIN sub_milestone m ON m.subcontract_id=s.id "
                                                 "WHERE s.project_id=? AND s.node_id IS NOT NULL AND s.status!='closed'", (pid,))}


def node_schedule(con, pid, M=None):
    """node_id -> {net_by_month, net_total, net_claimed, direct}: what the CLAIM forecast method works from.
    A subcontract the PM forecasts on the claim sheet contributes `direct` (net by month, used as is)."""
    out = {}
    for s in db.rows(con, "SELECT * FROM subcontract WHERE project_id=? AND node_id IS NOT NULL AND status!='closed'", (pid,)):
        d = out.setdefault(s["node_id"], {"net_by_month": defaultdict(float), "net_total": 0.0, "net_claimed": 0.0, "direct": defaultdict(float)})
        if M and uses_pm_forecast(con, s["id"]):
            for k, v in direct_net(con, s, M).items():
                d["direct"][k] += v
            continue
        g, held, net = schedule(con, s)
        _, _, nc = claimed(con, s)
        for m, v in net.items():
            d["net_by_month"][m] += v
        d["net_total"] += sum(net.values())
        d["net_claimed"] += nc
    return out


def claim_accruals(con, pid, landed):
    """Accruals implied by received claims whose invoice has not yet landed in Pronto.

    landed: set of normalised references found in the GL. A claim is skipped once its invoice reference has landed, or
    once it is paid. Amount = net of approved lines (claimed where a line is not yet approved).
    """
    out = []
    for s in db.rows(con, "SELECT * FROM subcontract WHERE project_id=? AND node_id IS NOT NULL AND status!='closed'", (pid,)):
        for c in claims_of(con, s["id"]):
            if c["status"] in ("draft", "paid"):
                continue
            if c["inv_ref"] and _n(c["inv_ref"]) in landed:
                continue
            t = claim_totals(con, c, s)
            if abs(t["net"]) < 0.005:
                continue
            out.append(dict(node_id=s["node_id"], month=c["month"][:7], amount=t["net"], subcontract=s["name"], claim_no=c["claim_no"],
                            basis=t["basis"], claim_id=c["id"], sub_id=s["id"], inv_ref=c["inv_ref"]))
    return out


def claim_context(con, sub, claim):
    """Per schedule line: contract value, what has been claimed before, what the schedule says is due, what was claimed now."""
    per = claim["month"][:7]
    prior = defaultdict(float)
    for c in claims_of(con, sub["id"]):
        if c["id"] == claim["id"] or c["status"] == "draft" or c["month"][:7] >= per:
            continue
        for l in db.rows(con, "SELECT * FROM sub_claim_line WHERE claim_id=?", (c["id"],)):
            prior[l["item_id"]] += l["approved"] if l["approved"] is not None else (l["claimed"] or 0)
    mine = {l["item_id"]: l for l in db.rows(con, "SELECT * FROM sub_claim_line WHERE claim_id=?", (claim["id"],))}
    out = []
    for m in items(con, sub["id"]):
        ser = item_series(m, sub.get("contract_value"))
        cum = sum(v for k, v in ser.items() if k <= per)
        val = item_value(m, sub.get("contract_value"))
        l = mine.get(m["id"])
        out.append(dict(item_id=m["id"], name=m["name"], type=m["type"], value=val, price=m["value"] if m["type"] == "Price" else None, share=m["share"],
                        prior=prior[m["id"]], planned_this=ser.get(per, 0.0),
                        cum_planned=cum, suggested=max(0.0, _r2(cum - prior[m["id"]])), claimed=(l["claimed"] if l else 0.0),
                        approved=(l["approved"] if l else None), note=(l or {}).get("note"),
                        remaining=val - prior[m["id"]] - (l["claimed"] if l else 0.0)))
    return out


def supplier_of(con, sub):
    """The subcontractor's directory entry (name, ABN, address, contact), found by its supplier code or name; {} if it is not in the directory."""
    return db.one(con, "SELECT name, abn, address, contacts FROM company WHERE (code IS NOT NULL AND code<>'' AND code=?) OR lower(trim(name))=lower(trim(?)) ORDER BY id LIMIT 1",
                  (sub.get("supplier_code") or "", sub.get("supplier_name") or sub.get("name") or "")) or {}


def claim_detail(con, sid, cid):
    sub = db.one(con, "SELECT * FROM subcontract WHERE id=?", (sid,))
    c = db.one(con, "SELECT * FROM sub_claim WHERE id=? AND subcontract_id=?", (cid, sid))
    if not c or not sub:
        return None
    c["lines"] = claim_context(con, sub, c)
    c.update({k: v for k, v in claim_totals(con, c, sub).items() if k not in ("lines",)})
    c["retention_pct"] = sub["retention_pct"]
    c["node_id"] = sub["node_id"]
    c["supplier"] = supplier_of(con, sub)
    return c


def create_claim(con, sid, month, claim_no=None):
    sub = db.one(con, "SELECT * FROM subcontract WHERE id=?", (sid,))
    n = db.scalar(con, "SELECT COUNT(*) FROM sub_claim WHERE subcontract_id=?", (sid,)) + 1
    cid = db.insert(con, "sub_claim", dict(subcontract_id=sid, claim_no=claim_no or f"C{n}", month=month[:7], status="received",
                                           gross=0, retention=0))
    for l in claim_context(con, sub, db.one(con, "SELECT * FROM sub_claim WHERE id=?", (cid,))):
        if l["suggested"] > 0:
            db.insert(con, "sub_claim_line", dict(claim_id=cid, item_id=l["item_id"], claimed=l["suggested"]))
    refresh_cache(con, cid)
    return cid


def refresh_cache(con, cid):
    c = db.one(con, "SELECT * FROM sub_claim WHERE id=?", (cid,))
    sub = db.one(con, "SELECT * FROM subcontract WHERE id=?", (c["subcontract_id"],))
    if db.scalar(con, "SELECT COUNT(*) FROM sub_claim_line WHERE claim_id=?", (cid,)):
        t = claim_totals(con, c, sub)
        db.update(con, "sub_claim", cid, dict(gross=_r2(t["effective"]), retention=_r2(t["retention"])))


def approve_all(con, cid):
    con.execute("UPDATE sub_claim_line SET approved=claimed WHERE claim_id=?", (cid,))


def approve_total(con, cid, amount):
    """Approve a total amount, shared across the lines in proportion to what was claimed."""
    lines = db.rows(con, "SELECT * FROM sub_claim_line WHERE claim_id=? ORDER BY id", (cid,))
    tot = sum(l["claimed"] or 0 for l in lines)
    if not lines or tot <= 0:
        raise ValueError("There is nothing claimed to approve")
    f = float(amount) / tot
    given = 0.0
    for i, l in enumerate(lines):
        a = _r2((l["claimed"] or 0) * f) if i < len(lines) - 1 else _r2(float(amount) - given)
        given += a
        con.execute("UPDATE sub_claim_line SET approved=? WHERE id=?", (a, l["id"]))


def issue_certificate(con, sid, cid, by=None, today=None):
    """The payment certificate for an approved claim: a number, the date and who certified it. Issuing again keeps the first number and date."""
    c = db.one(con, "SELECT * FROM sub_claim WHERE id=? AND subcontract_id=?", (cid, sid))
    if not c:
        raise ValueError("Claim not found")
    if c["status"] not in ("approved", "paid"):
        raise ValueError("Approve the claim before issuing its payment certificate")
    if not c.get("cert_no"):
        sub = db.one(con, "SELECT * FROM subcontract WHERE id=?", (sid,))
        c["cert_no"] = f"PC-{(sub.get('po_no') or sid)}-{c['claim_no']}".replace(" ", "")
        db.update(con, "sub_claim", cid, dict(cert_no=c["cert_no"], cert_date=db.iso(today) if today else date.today().isoformat(), cert_by=by))
    return db.one(con, "SELECT id, claim_no, cert_no, cert_date, cert_by FROM sub_claim WHERE id=?", (cid,))


def save_claim(con, sid, cid, body, by=None):
    d = {k: body.get(k) for k in ("claim_no", "inv_ref", "note", "cert_note", "status", "retention_release") if k in body}
    for k in ("received_date", "approved_date", "paid_date"):
        if k in body:
            d[k] = db.iso(body[k])
    if "month" in body and body["month"]:
        d["month"] = body["month"][:7]
    if d.get("retention_release") is not None:
        d["retention_release"] = float(d["retention_release"] or 0)
    db.update(con, "sub_claim", cid, d)
    if "lines" in body:
        con.execute("DELETE FROM sub_claim_line WHERE claim_id=?", (cid,))
        for l in body["lines"]:
            if (l.get("claimed") or 0) or l.get("approved") not in (None, ""):
                db.insert(con, "sub_claim_line", dict(claim_id=cid, item_id=int(l["item_id"]), claimed=float(l.get("claimed") or 0),
                                                      approved=None if l.get("approved") in (None, "") else float(l["approved"]), note=l.get("note")))
    act = body.get("action")
    if act == "approve_all":
        approve_all(con, cid)
    elif act == "approve_total":
        approve_total(con, cid, body.get("amount"))
    if act in ("approve_all", "approve_total"):
        db.update(con, "sub_claim", cid, dict(status="approved", approved_date=db.iso(body.get("today"))))
    refresh_cache(con, cid)
    if db.scalar(con, "SELECT status FROM sub_claim WHERE id=?", (cid,), default="") in ("approved", "paid"):
        issue_certificate(con, sid, cid, by, body.get("today"))      # approving a claim issues its payment certificate


# ---- summary ----------------------------------------------------------------
def summary(con, pid):
    rows = []
    for s in db.rows(con, "SELECT s.*, n.code AS node_code, n.name AS node_name FROM subcontract s "
                          "LEFT JOIN cbs_node n ON n.id=s.node_id WHERE s.project_id=? ORDER BY s.id", (pid,)):
        g, held, net = schedule(con, s)
        cg, cr, cn = claimed(con, s)
        planned = sum(g.values())
        pending = [c for c in claims_of(con, s["id"]) if c["status"] == "received"]
        s.update(scheduled_gross=planned, scheduled_net=sum(net.values()), claimed_gross=cg, claimed_retention=cr, claimed_net=cn,
                 to_claim=max(0.0, planned - cg), unscheduled=(s["contract_value"] or 0) - planned, awaiting_approval=len(pending),
                 schedule={m: round(v, 2) for m, v in sorted(net.items())})
        rows.append(s)
    return rows


# ---- the PM's forecast of future claims (lump-sum claim sheet) ---------------------------------------------------
def item_claimed(con, sub):
    """item_id -> {month: {claimed, approved, effective, status, invoiced}} over received claims (drafts excluded)."""
    from . import accruals
    landed = accruals.landed_refs(con, sub["project_id"])
    out = defaultdict(dict)
    for c in claims_of(con, sub["id"]):
        if c["status"] == "draft":
            continue
        inv = c["status"] == "paid" or bool(c["inv_ref"] and _n(c["inv_ref"]) in landed)
        for l in db.rows(con, "SELECT * FROM sub_claim_line WHERE claim_id=?", (c["id"],)):
            cell = out[l["item_id"]].setdefault(c["month"][:7], dict(claimed=0.0, approved=None, effective=0.0, invoiced=inv, claim_id=c["id"], status=c["status"]))
            cell["claimed"] += l["claimed"] or 0
            if l["approved"] is not None:
                cell["approved"] = (cell["approved"] or 0) + l["approved"]
            cell["effective"] += l["approved"] if l["approved"] is not None else (l["claimed"] or 0)
    return out


def forecasts(con, sid):
    """item_id -> {month: amount} as the PM typed it (newest row wins for a cell)."""
    out = defaultdict(dict)
    for r in con.execute("SELECT item_id, month, amount FROM sub_forecast WHERE subcontract_id=? ORDER BY id", (sid,)):
        if r["amount"] is None:
            out[r["item_id"]].pop(r["month"], None)
        else:
            out[r["item_id"]][r["month"]] = r["amount"]
    return out


def _item_future(m, cv, remaining, M, skip=()):
    """Remaining value of a line spread like its schedule over the months from M that have no claim yet; when the
    schedule has no such month left (it is behind), all of it in the first month from M without a claim."""
    if remaining <= 0.005:
        return {}
    ser = {k: v for k, v in item_series(m, cv).items() if k >= M and k not in skip}
    tot = sum(ser.values())
    if tot <= 0.005:
        k = M
        while k in skip:
            k = db.add_months(k, 1)
        return {k: remaining}
    return {k: remaining * v / tot for k, v in ser.items()}


def gross_forecast(con, sub, M):
    """item_id -> {month: gross} still to be claimed from month M: the PM's figures where typed, otherwise the unclaimed
    schedule. A month that already has a received claim is not forecast again (the claim is an accrual or an actual)."""
    cv = sub.get("contract_value")
    fc = forecasts(con, sub["id"])
    cl = item_claimed(con, sub)
    out = {}
    for m in items(con, sub["id"]):
        claimed_months = set(cl.get(m["id"], {}))
        if fc.get(m["id"]):
            out[m["id"]] = {k: v for k, v in fc[m["id"]].items() if k >= M and k not in claimed_months and abs(v) > 0.005}
        else:
            done = sum(x["effective"] for x in cl.get(m["id"], {}).values())
            out[m["id"]] = _item_future(m, cv, item_value(m, cv) - done, M, claimed_months)
    return out


def uses_pm_forecast(con, sid):
    return bool(db.scalar(con, "SELECT COUNT(*) FROM sub_forecast WHERE subcontract_id=?", (sid,)))


def direct_net(con, sub, M):
    """Net-of-retention forecast by month for a subcontract the PM forecasts on the claim sheet."""
    pct = sub.get("retention_pct") or 0
    out = defaultdict(float)
    tot_gross = 0.0
    for ser in gross_forecast(con, sub, M).values():
        for k, v in ser.items():
            out[k] += v * (1 - pct)
            tot_gross += v
    rel = (sub.get("retention_release_month") or "")[:7]
    if rel and pct:
        g, _, _ = claimed(con, sub)
        released = sum(c.get("retention_release") or 0 for c in claims_of(con, sub["id"]) if c["status"] != "draft")
        out[max(rel, M)] += max(0.0, (g + tot_gross) * pct - released)
    return out


def save_forecast(con, sub, cells):
    """cells: {item_id: {month: amount or None}}. Updates a cell in place (so its history reads well)."""
    have = {}
    for r in con.execute("SELECT id, item_id, month FROM sub_forecast WHERE subcontract_id=? ORDER BY id", (sub["id"],)):
        have[(r["item_id"], r["month"])] = r["id"]
    n = 0
    for iid, months in cells.items():
        for m, v in months.items():
            k = (int(iid), m[:7])
            val = None if v in (None, "") else float(v)
            if k in have:
                db.update(con, "sub_forecast", have[k], {"amount": val})
            elif val is not None:
                db.insert(con, "sub_forecast", dict(project_id=sub["project_id"], subcontract_id=sub["id"], item_id=k[0], month=k[1], amount=val))
            n += 1
    return n


def seed_forecast(con, sub, M):
    """Start the PM forecast from the unclaimed schedule (replaces nothing the PM already typed)."""
    have = forecasts(con, sub["id"])
    cv = sub.get("contract_value")
    cl = item_claimed(con, sub)
    cells = {}
    for m in items(con, sub["id"]):
        if have.get(m["id"]):
            continue
        done = sum(x["effective"] for x in cl.get(m["id"], {}).values())
        fut = _item_future(m, cv, item_value(m, cv) - done, M, set(cl.get(m["id"], {})))
        if fut:
            cells[m["id"]] = {k: round(v, 2) for k, v in fut.items()}
    return save_forecast(con, sub, cells)


def shift_forecast(con, sub, M, months=1):
    """Slip every forecast amount from month M on by n months (the subcontractor is running late)."""
    fc = forecasts(con, sub["id"])
    cells = {}
    for iid, ser in fc.items():
        moved = defaultdict(float)
        for k, v in ser.items():
            if k >= M:
                moved[db.add_months(k, months)] += v
        if moved:
            cells[iid] = {k: None for k in ser if k >= M}
            for k, v in moved.items():
                cells[iid][k] = round(v, 2)
    return save_forecast(con, sub, cells)


def sheet(con, sid, M):
    """The claim sheet: per schedule line, what was invoiced, claimed and approved by month, and the PM's forecast."""
    sub = db.one(con, "SELECT s.*, n.code AS node_code, n.name AS node_name FROM subcontract s LEFT JOIN cbs_node n ON n.id=s.node_id WHERE s.id=?", (sid,))
    cv = sub.get("contract_value")
    cl = item_claimed(con, sub)
    fc = forecasts(con, sid)
    fut = gross_forecast(con, sub, M)
    pm = uses_pm_forecast(con, sid)
    months = set()
    rows = []
    for m in items(con, sid):
        val = item_value(m, cv)
        mine = cl.get(m["id"], {})
        sched = item_series(m, cv)
        months.update(mine, fut.get(m["id"], {}), sched)
        claimed_total = sum(x["effective"] for x in mine.values())
        prior = sum(x["effective"] for k, x in mine.items() if k < M)
        f_total = sum(fut.get(m["id"], {}).values())
        rows.append(dict(item_id=m["id"], name=m["name"], type=m["type"], value=val, price=m["value"] if m["type"] == "Price" else None, share=m["share"], claims=mine, forecast=fc.get(m["id"], {}),
                         future=fut.get(m["id"], {}), schedule=dict(sched), prior=prior, claimed=claimed_total, to_claim=val - claimed_total,
                         forecast_total=f_total, unforecast=val - claimed_total - f_total))
    first = min(months) if months else M
    last = max(list(months) + [db.add_months(M, 6)])
    grid = db.month_range(min(first, M), last)
    tot = {k: sum(r[k] for r in rows) for k in ("value", "prior", "claimed", "to_claim", "forecast_total", "unforecast")}
    return dict(sub=sub, month=M, grid=grid, rows=rows, total=tot, pm_forecast=pm, retention_pct=sub.get("retention_pct") or 0)


# ---- payment terms and the subcontractor's planned claims ------------------------------------------------------------
def terms(con, sub):
    """The payment terms at a glance: milestone and progress portions (% of contract), the progress share applied to the
    price table, and checks (portions add up to 100%, price table adds up to the contract value)."""
    rows = items(con, sub["id"], claimable_only=False)
    cv = sub.get("contract_value") or 0
    has_price = any(m["type"] == "Price" for m in rows)
    share = progress_share(rows, cv)
    ms = sum(_pct_of(m, cv) for m in rows if m["type"] == "Milestone")
    pr = sum(_pct_of(m, cv) for m in rows if m["type"] == "Progress")
    if has_price and not any(m["type"] == "Progress" for m in rows):
        pr = share
    price_total = sum(m["value"] or 0 for m in rows if m["type"] == "Price")
    checks = []
    if rows and abs(ms + pr - 1) > 0.0005 and any(m["type"] in ("Milestone", "Progress") for m in rows):
        checks.append(f"Milestones and progress add up to {100 * (ms + pr):.1f}% of the contract, not 100%.")
    if has_price and cv and abs(price_total - cv) > 1:
        checks.append(f"The price table adds up to {price_total:,.0f}, the contract value is {cv:,.0f}.")
    return dict(milestone_pct=ms, progress_pct=pr, share=share, has_price=has_price, price_total=price_total, checks=checks)


def save_plan(con, sub, cells):
    """cells: {item_id: {month: amount or None}}: the subcontractor's planned claims. Updates a cell in place."""
    have = {}
    for r in con.execute("SELECT id, item_id, month FROM sub_plan WHERE subcontract_id=? ORDER BY id", (sub["id"],)):
        have[(r["item_id"], r["month"])] = r["id"]
    n = 0
    for iid, months in cells.items():
        for m, v in months.items():
            k = (int(iid), m[:7])
            val = None if v in (None, "") else float(v)
            if k in have:
                db.update(con, "sub_plan", have[k], {"amount": val})
            elif val is not None:
                db.insert(con, "sub_plan", dict(project_id=sub["project_id"], subcontract_id=sub["id"], item_id=k[0], month=k[1], amount=val))
            n += 1
    return n
