"""Risk management: contingency, risk cover, the company risk bucket, and how materialised risk costs get funded.

The model (as the company runs it)
  * The estimate gives every CBS item a budget and a risk amount. The project manager only works to the budget; the risk amount is
    a bucket the company holds.
  * The PM separates part of each budget as contingency (market fluctuations). Risk is for what could not reasonably be in the estimate:
    force majeure, rework, delay costs.
  * A risk event is tagged to the costs it causes (Pronto transactions, accruals, forecast items). Those costs land first, as overspend.
  * The PM may put contingency aside as risk cover at any time, including ahead of a risk he sees coming (saving for it). That is his own budget.
  * Money from the company is different: a release from the risk bucket, or an infusion, is only made once the risk has materialised and its
    invoice has landed in Pronto, so overspend stays minimal. The order is:
      1. the PM moves contingency into risk cover, from any CBS item that has contingency;
      2. when contingency is exhausted, the company releases from the risk bucket;
      3. if the bucket is not enough either, the company infuses additional funds.
    All three land in the item's risk cover (an earmark inside its budget that is matched against the risk cost that has occurred).
  * At the end the occurred risk cost is compared with what the estimate allowed, per CBS item and in total, so the estimator can
    spread risk by how risky each item really is instead of one blanket percentage.
"""
import uuid
from collections import defaultdict

from . import db, engine, forecast, services


class RiskError(services.Problem):
    pass


TOL = 0.005


# ---- register ---------------------------------------------------------------
def next_ref(con, pid):
    n = db.scalar(con, "SELECT COUNT(*) FROM risk WHERE project_id=?", (pid,)) + 1
    while db.one(con, "SELECT 1 x FROM risk WHERE project_id=? AND ref=?", (pid, f"R-{n:03d}")):
        n += 1
    return f"R-{n:03d}"


def node_category(con, pid):
    """node id -> Pronto category code of the nearest ancestor that has one."""
    nodes = {r["id"]: r for r in db.rows(con, "SELECT id, parent_id, category FROM cbs_node WHERE project_id=?", (pid,))}
    out = {}

    def cat(i):
        if i in out:
            return out[i]
        n = nodes[i]
        out[i] = n["category"] or (cat(n["parent_id"]) if n["parent_id"] else None)
        return out[i]
    for i in nodes:
        cat(i)
    return out


# ---- tagged costs -----------------------------------------------------------
def tagged_costs(con, pid, M):
    """Every cost currently linked to a risk subject: [{risk_id, node_id, month, amount, kind}], kind actual | accrual | forecast."""
    out = []
    for r in con.execute("SELECT g.id tag_id, g.risk_id, g.amount tag_amount, x.node_id, x.month, x.cost, x.description, x.reference, x.tx_date "
                         "FROM risk_tag g JOIN pronto_tx x ON x.project_id=g.project_id AND x.row_hash=g.row_hash WHERE g.project_id=? AND x.node_id IS NOT NULL", (pid,)):
        out.append(dict(risk_id=r["risk_id"], node_id=r["node_id"], month=r["month"], amount=r["tag_amount"] if r["tag_amount"] is not None else r["cost"],
                        kind="actual", tag_id=r["tag_id"], text=r["description"] or r["reference"], date=r["tx_date"]))
    for r in con.execute("SELECT risk_id, node_id, month, amount, note FROM accrual WHERE project_id=? AND risk_id IS NOT NULL AND status='open'", (pid,)):
        out.append(dict(risk_id=r["risk_id"], node_id=r["node_id"], month=r["month"], amount=r["amount"], kind="accrual", text=r["note"]))
    nodes = {r["id"]: r for r in db.rows(con, "SELECT id, start_date, end_date FROM cbs_node WHERE project_id=?", (pid,))}
    fctx = forecast.load_ctx(con, pid)
    for it in db.rows(con, "SELECT * FROM forecast_item WHERE project_id=? AND risk_id IS NOT NULL", (pid,)):
        manual = {r["month"]: r["amount"] for r in con.execute("SELECT month, amount FROM forecast_manual WHERE item_id=?", (it["id"],))}
        n = nodes.get(it["node_id"], {})
        it = dict(it)
        it["start_date"] = it.get("start_date") or n.get("start_date") or (M + "-01")
        if it.get("spread") != "Roster" or not it.get("swings"):
            it["end_date"] = it.get("end_date") or n.get("end_date") or db.month_end(M)
        for m, v in engine.item_series(it, manual, fctx).items():
            if m >= M and abs(v) > 0.005:
                out.append(dict(risk_id=it["risk_id"], node_id=it["node_id"], month=m, amount=v, kind="forecast", text=it.get("scope")))
    return out


# ---- positions --------------------------------------------------------------
def positions(con, pid, res=None):
    """Per CBS category: the estimate's risk, contingency, what has occurred, how it is covered, and what to do next.

    occurred   risk cost already landed (Pronto) or accrued, tagged to a risk event
    cover      risk cover earmarked in the budget: contingency transferred + company release + company infusion
    uncovered  occurred less cover: overspend that still needs funding (uncovered_landed counts only invoices already in Pronto)
    saved      cover set aside beyond what has occurred: the PM saving for a risk that may still happen
    next steps contingency first (PM), then the company bucket (release), then new funds (infusion)
    """
    res = res or engine.compute(con, pid)
    M = res["status_month"]
    cat_of = node_category(con, pid)
    tags = tagged_costs(con, pid, M)
    names = {r["category"]: r["name"] for r in res["rows"] if r["kind"] == "group" and r["level"] == 2}
    by_cat = {}
    for r in res["rows"]:
        if r["kind"] not in ("line", "pot") or not r.get("category"):
            continue
        c = by_cat.setdefault(r["category"], dict(category=r["category"], name=names.get(r["category"], r["category"]), gp=r["gp"], orig_budget=0.0, orig_risk=0.0,
                                                  budget=0.0, bucket=0.0, cont=0.0, cover=0.0, eac=0.0, ctd=0.0, acc=0.0, tagged_actual=0.0, tagged_accrual=0.0,
                                                  tagged_forecast=0.0, from_contingency=0.0, released=0.0, infused=0.0, by_risk=defaultdict(lambda: defaultdict(float))))
        for k, src in (("orig_budget", "orig_budget"), ("orig_risk", "orig_risk"), ("budget", "budget"), ("bucket", "risk"), ("cont", "cont_earmark"), ("cover", "risk_cover"),
                       ("eac", "eac"), ("ctd", "ctd"), ("acc", "acc")):
            c[k] += r.get(src, 0) or 0
    for t in tags:
        c = by_cat.get(cat_of.get(t["node_id"]))
        if not c:
            continue
        c["tagged_" + t["kind"]] += t["amount"]
        c["by_risk"][t["risk_id"]][t["kind"]] += t["amount"]
    for r in con.execute("SELECT target_node_id n, kind, SUM(amount) a FROM risk_release WHERE project_id=? GROUP BY target_node_id, kind", (pid,)):
        c = by_cat.get(cat_of.get(r["n"]))
        if c:
            c[{"contingency": "from_contingency", "release": "released", "infuse": "infused"}.get(r["kind"], "released")] += r["a"] or 0
    out = []
    for c in by_cat.values():
        occurred = c["tagged_actual"] + c["tagged_accrual"]
        uncovered = max(0.0, occurred - c["cover"])
        uncovered_landed = max(0.0, c["tagged_actual"] - c["cover"])          # company money waits for the invoice to land in Pronto
        pm_step = min(uncovered, max(0.0, c["cont"]))
        release_step = min(max(0.0, uncovered_landed - pm_step), max(0.0, c["bucket"]))
        infuse_step = max(0.0, uncovered_landed - pm_step - release_step)
        if not (c["orig_risk"] or c["bucket"] or c["cont"] or c["cover"] or occurred or c["tagged_forecast"]):
            continue
        status = ("INFUSION NEEDED" if infuse_step > 1 else "RELEASE DUE" if release_step > 1 else "TRANSFER CONTINGENCY" if pm_step > 1
                  else "AWAITING INVOICE" if uncovered > 1 else "COVERED" if occurred > 0 else "SAVED FOR RISK" if c["cover"] > 1 else "NO RISK COSTS")
        out.append(dict(category=c["category"], name=c["name"], gp=c["gp"], orig_budget=c["orig_budget"], orig_risk=c["orig_risk"],
                        risk_pct=(c["orig_risk"] / c["orig_budget"]) if c["orig_budget"] else None, budget=c["budget"], bucket_remaining=c["bucket"],
                        bucket=c["bucket"] + c["released"], contingency=c["cont"], cover=c["cover"], from_contingency=c["from_contingency"], released=c["released"],
                        infused=c["infused"], occurred=occurred, tagged_actual=c["tagged_actual"], tagged_accrual=c["tagged_accrual"], tagged_forecast=c["tagged_forecast"],
                        tagged=occurred + c["tagged_forecast"], uncovered=uncovered, uncovered_landed=uncovered_landed, over_covered=max(0.0, c["cover"] - occurred),
                        exposure=max(0.0, occurred + c["tagged_forecast"] - c["cover"]), step_contingency=pm_step, step_release=release_step, step_infuse=infuse_step,
                        status=status, by_risk={str(k): dict(v) for k, v in c["by_risk"].items()}))
    return sorted(out, key=lambda x: x["category"])


def _position(con, pid, category, res=None):
    return next((p for p in positions(con, pid, res) if p["category"] == category), None)


def register(con, pid, res=None):
    res = res or engine.compute(con, pid)
    M = res["status_month"]
    cat_of = node_category(con, pid)
    tags = tagged_costs(con, pid, M)
    alloc = defaultdict(float)
    for a in db.rows(con, "SELECT risk_id, SUM(amount) amt FROM risk_alloc WHERE project_id=? GROUP BY risk_id", (pid,)):
        alloc[a["risk_id"]] = a["amt"] or 0
    risks = db.rows(con, "SELECT * FROM risk WHERE project_id=? ORDER BY ref", (pid,))
    for r in risks:
        r["factored"] = (r["estimate"] or 0) * (r["likelihood"] or 0)
        r["factored_days"] = (r["delay_days"] or 0) * (r["likelihood"] or 0) * (1 - (r["effectiveness"] or 0))
        r["factored_revenue"] = (r["revenue_impact"] or 0) * (r["likelihood"] or 0) * (1 - (r["effectiveness"] or 0))
        r["residual"] = r["factored"] * (1 - (r["effectiveness"] or 0))      # treated residual contingency: what the event reserves
        mine = [t for t in tags if t["risk_id"] == r["id"]]
        r["allocated"] = alloc.get(r["id"], 0.0)
        r["actual"] = sum(t["amount"] for t in mine if t["kind"] == "actual")
        r["accrued"] = sum(t["amount"] for t in mine if t["kind"] == "accrual")
        r["forecast"] = sum(t["amount"] for t in mine if t["kind"] == "forecast")
        r["total"] = r["actual"] + r["accrued"] + r["forecast"]
        r["pct_of_alloc"] = (r["total"] / r["allocated"]) if r["allocated"] else None
        r["realised"] = r["actual"] + r["accrued"]
        # exposure still reserved: nothing once the event has ceased, otherwise what the event reserved less what it has cost
        r["exposure"] = 0.0 if r["status"] == "ceased" else max(0.0, r["residual"] - r["realised"] - r["forecast"])
        r["retired"] = max(0.0, r["residual"] - r["realised"]) if r["status"] == "ceased" else 0.0
        r["categories"] = sorted({cat_of.get(t["node_id"]) for t in mine if cat_of.get(t["node_id"])})
    return risks


def buckets(con, pid, res=None):
    """Matrix of CBS items holding risk against risk subjects, with what is not yet broken down."""
    res = res or engine.compute(con, pid)
    cat_of = node_category(con, pid)
    nodes = {r["id"]: r for r in db.rows(con, "SELECT id, code, name, kind, parent_id, origin FROM cbs_node WHERE project_id=?", (pid,))}
    rows = []
    risk_by_node = defaultdict(lambda: [0.0, 0.0])
    for r in con.execute("SELECT node_id, SUM(CASE WHEN kind='estimate' THEN risk ELSE 0 END) orig, SUM(risk) cur FROM allowance_ledger WHERE project_id=? GROUP BY node_id", (pid,)):
        risk_by_node[r["node_id"]] = [r["orig"] or 0, r["cur"] or 0]
    rel_by_node = defaultdict(float)
    for r in con.execute("SELECT node_id, SUM(budget) b FROM allowance_ledger WHERE project_id=? AND kind='risk_release' GROUP BY node_id", (pid,)):
        rel_by_node[r["node_id"]] = r["b"] or 0
    alloc = defaultdict(dict)
    for a in db.rows(con, "SELECT risk_id, node_id, amount FROM risk_alloc WHERE project_id=?", (pid,)):
        alloc[a["node_id"]][str(a["risk_id"])] = a["amount"]
    for nid, (orig, cur) in risk_by_node.items():
        if abs(orig) < 0.005 and abs(cur) < 0.005 and not alloc.get(nid):
            continue
        n = nodes[nid]
        a = alloc.get(nid, {})
        bucket = cur + max(0.0, rel_by_node.get(nid, 0.0))
        rows.append(dict(node_id=nid, code=n["code"], name=n["name"], kind=n["kind"], category=cat_of.get(nid), orig_risk=orig, risk_now=cur, released=max(0.0, rel_by_node.get(nid, 0.0)),
                         bucket=bucket, alloc=a, allocated=sum(a.values()), unallocated=bucket - sum(a.values())))
    rows.sort(key=lambda r: r["code"])
    return rows


# ---- funding: contingency transfer, release, infusion ---------------------------------------------------
def _held(con, pid, nid, col):
    return db.scalar(con, f"SELECT COALESCE(SUM({col}),0) FROM allowance_ledger WHERE project_id=? AND node_id=?", (pid, nid))


def _record(con, pid, kind, source, target, amount, date, by, ref, note, pair, forced):
    return db.insert(con, "risk_release", dict(project_id=pid, source_node_id=source, target_node_id=target, amount=amount, date=date, approved_by=by, ref=ref, note=note,
                                               kind=kind, forced=1 if forced else 0, pair_id=pair))


def _check_landed(con, pid, target_id, amount, force):
    """Company money (a release or an infusion) is only made once the risk has materialised and its invoice has landed in Pronto."""
    cat = node_category(con, pid).get(target_id)
    pos = _position(con, pid, cat) if cat else None
    landed = pos["uncovered_landed"] if pos else 0.0
    if amount > landed + TOL and not force:
        accrued = (pos["uncovered"] - landed) if pos else 0.0
        extra = f" A further {accrued:,.2f} is accrued but its invoice has not landed yet." if accrued > 1 else ""
        raise RiskError(f"Company funds follow the invoice: {cat or 'this CBS item'} has {landed:,.2f} of risk cost landed in Pronto and not yet covered, "
                        f"so {amount:,.2f} is too much.{extra} Tag the costs, wait for the invoice, or approve it as an exception.")
    return pos


def set_contingency(con, pid, node_id, amount):
    """The PM separates part of a budget as contingency. It stays inside the budget; it only changes how that budget is earmarked."""
    amount = float(amount or 0)
    n = services.get_node(con, pid, node_id)
    if amount < 0:
        raise RiskError("Contingency cannot be negative")
    budget = _held(con, pid, node_id, "budget")
    cover = _held(con, pid, node_id, "risk_cover")
    if amount + cover > budget + TOL:
        raise RiskError(f"Contingency plus risk cover ({amount + cover:,.2f}) cannot exceed this item's budget ({budget:,.2f}).")
    cur = _held(con, pid, node_id, "contingency")
    if abs(amount - cur) < TOL:
        return
    db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=node_id, kind="contingency_set", contingency=amount - cur, note="Contingency separated from budget by the PM"))
    db.bump(con, pid)


def contingency_to_risk(con, pid, source_id, target_id, amount, date=None, by=None, ref=None, note=None, force=False):
    """The PM puts contingency aside as risk cover, to fund a risk cost on the target item or to save for a risk that may still happen. The source
    can be any item with contingency; when it is a different item its budget moves across with it, so the total budget does not change.
    Nothing needs to have occurred: it is the PM's own budget."""
    amount = float(amount)
    if amount <= 0:
        raise RiskError("Enter an amount")
    services.get_node(con, pid, source_id)
    services.get_node(con, pid, target_id)
    avail = _held(con, pid, source_id, "contingency")
    if amount > avail + TOL:
        raise RiskError(f"Only {avail:,.2f} of contingency is held at the source item. Separate more contingency from its budget first.")
    pair = uuid.uuid4().hex[:10]
    if source_id == target_id:
        db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=target_id, date=date, kind="contingency_to_risk", contingency=-amount, risk_cover=amount, ref=ref,
                                                note=note or "Contingency transferred to risk", pair_id=pair))
    else:
        db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=source_id, date=date, kind="contingency_to_risk", budget=-amount, contingency=-amount, ref=ref,
                                                note=note or "Contingency moved to cover a risk elsewhere", pair_id=pair))
        db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=target_id, date=date, kind="contingency_to_risk", budget=amount, risk_cover=amount, ref=ref,
                                                note=note or "Contingency received as risk cover", pair_id=pair))
    rid = _record(con, pid, "contingency", source_id, target_id, amount, date, by, ref, note, pair, force)
    db.bump(con, pid)
    return rid


def release(con, pid, target_id, amount, source_id=None, date=None, approved_by=None, ref=None, note=None, force=False):
    """The company releases risk from its bucket into the budget of the item that carries the cost (a CBS line is the right level),
    where it becomes risk cover. Limited to what the chosen bucket still holds, and to risk cost whose invoice has landed in Pronto."""
    amount = float(amount)
    if amount <= 0:
        raise RiskError("Enter an amount to release")
    services.get_node(con, pid, target_id)
    if source_id is None:
        cur = target_id
        while cur:
            if _held(con, pid, cur, "risk") > TOL:
                source_id = cur
                break
            n = db.one(con, "SELECT parent_id FROM cbs_node WHERE id=?", (cur,))
            cur = n["parent_id"] if n else None
        if source_id is None:
            raise RiskError("No risk is held at this CBS item or above it, so there is nothing to release")
    avail = _held(con, pid, source_id, "risk")
    if amount > avail + TOL:
        raise RiskError(f"Only {avail:,.2f} of risk is still held at the chosen bucket. A release cannot exceed the bucket.")
    pos = _check_landed(con, pid, target_id, amount, force)
    warnings = []
    if pos and pos["contingency"] > 1 and not force:
        warnings.append(f"{pos['contingency']:,.2f} of contingency is still available on {pos['category']}. Contingency is normally used before the bucket.")
    pair = uuid.uuid4().hex[:10]
    if source_id != target_id:
        db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=source_id, date=date, kind="transfer", risk=-amount, ref=ref, note="Risk moved for release", pair_id=pair))
        db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=target_id, date=date, kind="transfer", risk=amount, ref=ref, note="Risk moved for release", pair_id=pair))
    db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=target_id, date=date, kind="risk_release", budget=amount, risk=-amount, risk_cover=amount, ref=ref,
                                            note=note or "Risk released by the company", pair_id=pair))
    rid = _record(con, pid, "release", source_id, target_id, amount, date, approved_by, ref, note, pair, force)
    db.bump(con, pid)
    return rid


def infuse(con, pid, target_id, amount, date=None, approved_by=None, ref=None, note=None, force=False):
    """The company adds new money because more risk has occurred than the bucket allowed for. It raises the budget and the risk cover."""
    amount = float(amount)
    if amount <= 0:
        raise RiskError("Enter an amount")
    services.get_node(con, pid, target_id)
    pos = _check_landed(con, pid, target_id, amount, force)
    if pos and (pos["bucket_remaining"] > 1 or pos["contingency"] > 1) and not force:
        raise RiskError(f"{pos['category']} still has {pos['contingency']:,.2f} of contingency and {pos['bucket_remaining']:,.2f} in the risk bucket. "
                        "Use those first, or approve the infusion as an exception.")
    pair = uuid.uuid4().hex[:10]
    db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=target_id, date=date, kind="infuse", budget=amount, risk_cover=amount, ref=ref,
                                            note=note or "Additional company funds", pair_id=pair))
    rid = _record(con, pid, "infuse", None, target_id, amount, date, approved_by, ref, note, pair, force)
    db.bump(con, pid)
    return rid


def reverse_release(con, pid, rid):
    r = db.one(con, "SELECT * FROM risk_release WHERE id=? AND project_id=?", (rid, pid))
    if not r:
        raise RiskError("Funding entry not found")
    con.execute("DELETE FROM allowance_ledger WHERE project_id=? AND pair_id=?", (pid, r["pair_id"]))
    con.execute("DELETE FROM risk_release WHERE id=?", (rid,))
    db.bump(con, pid)


# ---- close-out --------------------------------------------------------------
def closeout(con, pid, res=None):
    """For the estimator: per CBS category, the risk that really occurred, how it was funded, and the risk % each item turned out to need."""
    res = res or engine.compute(con, pid)
    pos = positions(con, pid, res)
    risks = {str(r["id"]): r for r in db.rows(con, "SELECT * FROM risk WHERE project_id=?", (pid,))}
    rows = []
    totals = defaultdict(float)
    for p in pos:
        consumed = p["occurred"]                                     # the risk cost that really landed
        tagged = p["occurred"] + p["tagged_forecast"]
        events = []
        for rid, v in p["by_risk"].items():
            t = v.get("actual", 0) + v.get("accrual", 0)
            share = (t / p["occurred"]) if p["occurred"] else 0.0
            events.append(dict(risk_id=int(rid), ref=risks[rid]["ref"], title=risks[rid]["title"], tagged=t, share=share, risk_funded=consumed * share,
                               pct_of_budget=(consumed * share / p["orig_budget"]) if p["orig_budget"] else None))
            totals[risks[rid]["ref"]] += consumed * share
        events.sort(key=lambda e: e["ref"])
        pct = (consumed / p["orig_budget"]) if p["orig_budget"] else None
        rows.append(dict(category=p["category"], name=p["name"], orig_budget=p["orig_budget"], orig_risk=p["orig_risk"], risk_pct_estimated=p["risk_pct"],
                         risk_needed=consumed, risk_needed_pct_of_budget=pct, suggested_risk_pct=pct, risk_unused=max(0.0, p["bucket"] - p["released"] - 0.0),
                         from_contingency=p["from_contingency"], released=p["released"], infused=p["infused"], uncovered=p["uncovered"],
                         tagged=tagged, events=events, untagged=0.0,
                         bucket_used_pct=(p["released"] / p["bucket"]) if p["bucket"] else None))
    t_budget = sum(r["orig_budget"] for r in rows)
    t_risk = sum(r["orig_risk"] for r in rows)
    t_cons = sum(r["risk_needed"] for r in rows)
    return dict(rows=rows, by_event={k: round(v, 2) for k, v in sorted(totals.items())},
                totals=dict(orig_budget=t_budget, orig_risk=t_risk, risk_needed=t_cons, risk_unused=sum(max(0.0, r["orig_risk"] - r["released"]) for r in rows),
                            from_contingency=sum(r["from_contingency"] for r in rows), released=sum(r["released"] for r in rows), infused=sum(r["infused"] for r in rows),
                            estimated_pct=(t_risk / t_budget) if t_budget else None, actual_pct=(t_cons / t_budget) if t_budget else None,
                            suggested_overall_pct=(t_cons / t_budget) if t_budget else None,
                            overrun_vs_estimate=t_cons - t_risk))


def summary(con, pid, res=None):
    """The risk pot against the events that reserve it (the sample register's R-999 'Unallocated risk' line and impact table)."""
    res = res or engine.compute(con, pid)
    pos = positions(con, pid, res)
    pot = sum(p["bucket"] for p in pos)                # the company's risk bucket: held plus already released
    risks = [r for r in register(con, pid, res) if (r.get("kind") or "Risk") == "Risk"]
    reserved = sum(r["residual"] for r in risks if r["status"] != "ceased")
    impact = sum(r["realised"] + r["forecast"] for r in risks if r["status"] == "materialised")
    live = [r for r in risks if r["status"] != "ceased"]
    mat = [r for r in risks if r["status"] == "materialised"]
    time_rev = dict(delay_planned=sum(r["factored_days"] for r in live), delay_occurred=sum(r["delay_actual"] or 0 for r in risks),
                    delay_worst=sum(r["delay_days"] or 0 for r in live), revenue_planned=sum(r["factored_revenue"] for r in live),
                    revenue_occurred=sum(r["revenue_actual"] or 0 for r in risks), revenue_worst=sum(r["revenue_impact"] or 0 for r in live),
                    margin_hit=impact + sum(r["revenue_actual"] or 0 for r in mat))
    return dict(**time_rev, pot=pot, reserved=reserved, unallocated=pot - reserved, materialised_impact=impact, released=sum(p["released"] for p in pos),
                available=sum(p["bucket_remaining"] for p in pos), n_risks=len(risks), n_open=sum(1 for r in risks if r["status"] == "open"),
                n_materialised=sum(1 for r in risks if r["status"] == "materialised"), n_ceased=sum(1 for r in risks if r["status"] == "ceased"))


# ---- import of the register layout used by the estimator --------------------------------------------
import re as _re


def _k(s):
    return _re.sub(r"[^a-z0-9]", "", str(s or "").lower())


FIELDS = {  # normalised header -> field. Two-row headers are merged (row 2 text, else row 3 text).
    "description of risk opportunity": "title", "descriptionofriskopportunity": "title", "category": "category", "area": "area", "type": "kind",
    "descriptionofconsequences": "consequences", "rootcauses": "cause", "estimatedcost": "estimate", "likelihood": "likelihood", "basisofestimate": "basis",
    "triggeringevent": "trigger_event", "managementcontrolstreatmentaction": "controls", "treatmentmethod": "treatment", "costofcontroltreatmentaction": "control_cost",
    "effectivenessoftreatment": "effectiveness", "owner": "owner", "datelastreviewed": "last_reviewed", "scheduledactualretirementdate": "retire_date",
    "status": "status", "comment": "comment",
}


def parse_register(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        sheets = [list(ws.iter_rows(values_only=True)) for ws in wb.worksheets]
    finally:
        wb.close()              # Windows will not delete a file that is still open
    for rows in sheets:
        for hi in range(min(6, len(rows))):
            heads = {}
            for j, h in enumerate(rows[hi]):
                key = _k(h)
                sub = _k(rows[hi + 1][j]) if hi + 1 < len(rows) and j < len(rows[hi + 1]) else ""
                for cand in (key, sub):
                    f = next((v for kk, v in FIELDS.items() if _k(kk) == cand), None) if cand else None
                    if f and f not in heads.values():
                        heads[j] = f
                        break
                if rows[hi][j] is not None and _k(rows[hi][j]) == "" or key == "":
                    pass
            if "title" in heads.values() and any(_k(r) == "1" or str(r).strip() == "#" for r in rows[hi][:1]):
                refcol = 0
                out, skipped = [], []
                for row in rows[hi + 1:]:
                    ref = str(row[refcol] or "").strip()
                    if not _re.match(r"^R-?\d+$", ref, flags=_re.I):
                        continue
                    ref = ref.upper() if "-" in ref else "R-" + ref[1:]
                    d = {f: row[j] if j < len(row) else None for j, f in heads.items()}
                    if not d.get("title"):
                        skipped.append(ref)
                        continue
                    if ref == "R-999" or "unallocated" in str(d["title"]).lower():
                        continue
                    num = lambda v: float(v) if isinstance(v, (int, float)) else 0.0
                    kind = "Opportunity" if str(d.get("kind") or "").strip().lower().startswith("opp") else "Risk"
                    st = str(d.get("status") or "open").strip().lower()
                    st = "materialised" if st.startswith("mater") or st.startswith("occur") else "ceased" if st.startswith(("cease", "clos", "retir")) else "open"
                    eff = num(d.get("effectiveness"))
                    out.append(dict(ref=ref, title=str(d["title"]).strip(), kind=kind, category=d.get("category"), area=d.get("area"), consequences=d.get("consequences"),
                                    cause=d.get("cause"), estimate=num(d.get("estimate")), likelihood=num(d.get("likelihood")), basis=d.get("basis") and str(d["basis"]),
                                    trigger_event=d.get("trigger_event"), controls=d.get("controls"), treatment=d.get("treatment"), control_cost=num(d.get("control_cost")),
                                    effectiveness=eff / 100 if eff > 1 else eff, owner=d.get("owner"), last_reviewed=db.iso(d.get("last_reviewed")),
                                    retire_date=db.iso(d.get("retire_date")), status=st, comment=d.get("comment")))
                return out, skipped
    raise ValueError("Could not find the risk register table. Expected columns such as '#', 'Description of Risk / Opportunity', 'Estimated Cost ($)' and 'Likelihood (%)'.")


def import_register(con, pid, path):
    rows, skipped = parse_register(path)
    new = upd = 0
    for r in rows:
        r = {k: (str(v).strip() if isinstance(v, str) else v) for k, v in r.items() if v is not None}
        ex = db.one(con, "SELECT id FROM risk WHERE project_id=? AND ref=?", (pid, r["ref"]))
        if ex:
            db.update(con, "risk", ex["id"], {k: v for k, v in r.items() if k != "ref"})
            upd += 1
        else:
            db.insert(con, "risk", dict(project_id=pid, **r))
            new += 1
    db.bump(con, pid)
    return dict(created=new, updated=upd, skipped_without_description=skipped)


# ---- close-out, both ways ---------------------------------------------------------------------------
def closeout_by_event(con, pid, res=None, co=None):
    """Each risk event broken into the CBS categories it hit: the other way round from the CBS view."""
    co = co or closeout(con, pid, res)
    reg = {r["id"]: r for r in register(con, pid, res)}
    ev = {}
    for row in co["rows"]:
        for e in row["events"]:
            x = ev.setdefault(e["risk_id"], dict(risk_id=e["risk_id"], ref=e["ref"], title=e["title"], tagged=0.0, risk_funded=0.0, categories=[]))
            x["tagged"] += e["tagged"]
            x["risk_funded"] += e["risk_funded"]
            x["categories"].append(dict(category=row["category"], name=row["name"], tagged=e["tagged"], risk_funded=e["risk_funded"],
                                        pct_of_budget=e["pct_of_budget"], share_of_cbs=e["share"], orig_budget=row["orig_budget"]))
    out = []
    for x in sorted(ev.values(), key=lambda v: v["ref"]):
        r = reg.get(x["risk_id"], {})
        for c in x["categories"]:
            c["pct_of_event"] = (c["tagged"] / x["tagged"]) if x["tagged"] else None
            c["pct_of_event_funded"] = (c["risk_funded"] / x["risk_funded"]) if x["risk_funded"] else None
        x["categories"].sort(key=lambda c: -abs(c["tagged"]))
        x.update(delay_days=r.get("delay_days", 0.0), delay_actual=r.get("delay_actual", 0.0), revenue_impact=r.get("revenue_impact", 0.0), revenue_actual=r.get("revenue_actual", 0.0),
                 planned=r.get("residual", 0.0), estimate=r.get("estimate", 0.0), likelihood=r.get("likelihood", 0.0), status=r.get("status"), allocated=r.get("allocated", 0.0))
        out.append(x)
    cats = sorted({c["category"] for x in out for c in x["categories"]})
    matrix = {c: {x["ref"]: next((k["tagged"] for k in x["categories"] if k["category"] == c), 0.0) for x in out} for c in cats}
    return dict(events=out, matrix=matrix, refs=[x["ref"] for x in out])
