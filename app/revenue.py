"""Revenue side: contract value, schedule of values, claim schedule and client progress claims."""
from collections import defaultdict
from datetime import date, timedelta

from . import db


def _num(x):
    return float(x or 0)


def items_tree(con, pid):
    items = db.rows(con, "SELECT * FROM contract_item WHERE project_id=? ORDER BY sort_order, id", (pid,))
    by_id = {i["id"]: i for i in items}
    kids = defaultdict(list)
    for i in items:
        kids[i["parent_id"]].append(i["id"])
    claimed = defaultdict(float)
    # a claimed line counts at its certified amount once the client has certified it
    for r in con.execute("SELECT cl.item_id, SUM(COALESCE(cl.certified, cl.amount)) a FROM claim_line cl JOIN claim c ON c.id=cl.claim_id "
                         "WHERE c.project_id=? AND c.status!='draft' GROUP BY cl.item_id", (pid,)):
        claimed[r["item_id"]] = r["a"] or 0
    claimed_m = defaultdict(dict)       # item -> {month: amount} for claims already issued: those months are claimed, not forecast
    for r in con.execute("SELECT cl.item_id, c.period, SUM(COALESCE(cl.certified, cl.amount)) a FROM claim_line cl JOIN claim c ON c.id=cl.claim_id "
                         "WHERE c.project_id=? AND c.status!='draft' GROUP BY cl.item_id, c.period", (pid,)):
        claimed_m[r["item_id"]][r["period"][:7]] = r["a"] or 0
    in_draft = defaultdict(float)
    for r in con.execute("SELECT cl.item_id, SUM(cl.amount) a FROM claim_line cl JOIN claim c ON c.id=cl.claim_id "
                         "WHERE c.project_id=? AND c.status='draft' GROUP BY cl.item_id", (pid,)):
        in_draft[r["item_id"]] = r["a"] or 0
    issued = {r[0][:7] for r in con.execute("SELECT period FROM claim WHERE project_id=? AND status!='draft'", (pid,))}
    smonth = ((db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,)) or {}).get("status_date") or "")[:7] or None
    links = defaultdict(list)
    for r in con.execute("SELECT id, name, link_item_id, COALESCE(layer,'internal') layer FROM programme_task WHERE project_id=? AND link_item_id IS NOT NULL", (pid,)):
        links[r["link_item_id"]].append(dict(task_id=r["id"], name=r["name"], layer=r["layer"]))
    manual = defaultdict(dict)
    for r in con.execute("SELECT rp.item_id, rp.month, rp.amount FROM revenue_plan rp JOIN contract_item ci ON ci.id=rp.item_id WHERE ci.project_id=?", (pid,)):
        manual[r["item_id"]][r["month"]] = r["amount"]

    def counted(i):
        # an optional price counts once confirmed; still offered, it counts only if it is part of the original contract
        # value (until it is cancelled); cancelled, never
        if i["kind"] == "optional":
            st = opt_status(i.get("optional_status"))
            return st == "confirmed" or (st == "offered" and in_original(i))
        if i["kind"] == "variation" and not i.get("variation_id"):
            # a variation listed in the schedule: approved counts; pending only if it is in the original contract value
            st = var_status(i.get("optional_status"))
            return st == "approved" or (st == "pending" and in_original(i))
        return True

    def walk(iid, depth):
        i = by_id[iid]
        i["depth"] = depth
        ch = kids.get(iid, [])
        if ch:
            for c in ch:
                walk(c, depth + 1)
            i["is_leaf"] = False
            i["value_calc"] = sum(by_id[c]["value_calc"] for c in ch)
            i["claimed"] = sum(by_id[c]["claimed"] for c in ch)
            i["draft"] = sum(by_id[c]["draft"] for c in ch)
            i["plan"] = defaultdict(float)
            i["claimed_m"] = defaultdict(float)
            for c in ch:
                for m, v in by_id[c]["plan"].items():
                    i["plan"][m] += v
                for m, v in by_id[c]["claimed_m"].items():
                    i["claimed_m"][m] += v
        else:
            i["is_leaf"] = True
            i["value_calc"] = _num(i["value"]) if counted(i) else 0.0
            i["claimed"] = claimed.get(iid, 0.0)
            i["draft"] = in_draft.get(iid, 0.0)
            i["claimed_m"] = dict(claimed_m.get(iid, {}))
            i["plan"] = plan_series(i, manual.get(iid), i["claimed"], issued, smonth) if counted(i) else defaultdict(float)
    for iid in kids.get(None, []):
        walk(iid, 0)
    reg = {r["id"]: r["client_status"] for r in con.execute("SELECT id, client_status FROM variation WHERE project_id=?", (pid,))}
    for i in items:
        i["links"] = links.get(i["id"], [])
        i["in_orig"] = in_original(i)
        i["status"] = opt_status(i.get("optional_status")) if i["kind"] == "optional" else \
            (reg.get(i["variation_id"]) or "approved") if i["kind"] == "variation" and i.get("variation_id") else \
            var_status(i.get("optional_status")) if i["kind"] == "variation" else None
        i["plan"] = {m: round(v, 2) for m, v in sorted(i["plan"].items())}
        i["claimed_m"] = {m: round(v, 2) for m, v in sorted(i["claimed_m"].items())}
        i["residual"] = i["value_calc"] - i["claimed"]
        i["pct_claimed"] = (i["claimed"] / i["value_calc"]) if i["value_calc"] else 0
        i["plan_total"] = sum(i["plan"].values())
    return items


def plan_series(item, manual=None, claimed=0.0, locked=(), status_month=None):
    out = defaultdict(float)
    v = _num(item["value"])
    s, e = (item.get("start_date") or "")[:7], (item.get("end_date") or "")[:7]
    m = item.get("method") or "even"
    if m == "window":
        # the window set on the line (typed, or from the client's schedule): what is not yet claimed is spread over the window's months
        # that are still open (this month onwards, never a month already claimed); a window that has passed puts the rest in this month
        if s:
            base = max(s, status_month or s)
            months = [k for k in db.month_range(base, e) if k not in locked] if e and e >= base else []
            months = months or [base]
            rest = max(0.0, v - claimed)
            each = round(rest / len(months), 2)
            for k in months:
                out[k] += each
            out[months[-1]] += round(rest - each * len(months), 2)
    elif m == "manual":
        for k, a in (manual or {}).items():
            out[k] += a
    elif s:
        if m == "lump" or not e or e <= s:
            out[s] += v
        else:
            ms = db.month_range(s, e)
            for k in ms:
                out[k] += v / len(ms)
    return out


def summary(con, pid):
    from . import linking
    if linking.is_parent(con, pid):   # a parent project: its children's contract values added up
        return linking.sum_dicts([summary(con, c["id"]) for c in linking.children(con, pid)]) or summary_empty()
    items = items_tree(con, pid)
    vars_ = db.rows(con, "SELECT v.*, (SELECT value FROM variation_rev r WHERE r.variation_id=v.id ORDER BY is_current DESC, rev DESC LIMIT 1) AS value FROM variation v WHERE v.project_id=?", (pid,))
    # sums by kind are taken from the lines, not the top-level groups: a template or schedule can put a base group above optional prices
    # and variations (1 > 1.01 base, 1.09 optional), and the group's kind says nothing about what is under it
    leaves_all = [i for i in items if i["is_leaf"]]
    base = sum(i["value_calc"] for i in leaves_all if i["kind"] == "base")
    optional_taken = sum(i["value_calc"] for i in leaves_all if i["kind"] == "optional")   # what the optional prices count now
    optional_all = sum(_num(i["value"]) for i in items if i["kind"] == "optional" and i["is_leaf"])
    opt_by, var_by = defaultdict(float), defaultdict(float)
    for i in items:
        if i["kind"] == "optional" and i["is_leaf"]:
            opt_by[i["status"]] += _num(i["value"])
        elif i["kind"] == "variation" and i["is_leaf"]:
            var_by["approved" if i.get("variation_id") else i["status"]] += _num(i["value"])
    var_items = [i for i in leaves_all if i["kind"] == "variation"]
    approved = sum(i["value_calc"] for i in var_items)
    # original contract value: what was in the contract at award. Optional prices and variations listed in the claim
    # schedule count there only when the import said so (in_original); an optional price in it and later declined, or a
    # variation already in it, shows as the difference between original and revised.
    leaves = [i for i in items if i["is_leaf"]]
    orig = [i for i in leaves if in_original(i)]
    original = sum(_num(i["value"]) for i in orig)
    opt_declined = sum(_num(i["value"]) for i in orig if i["kind"] == "optional" and i["status"] == "cancelled")
    var_in_orig = sum(_num(i["value"]) for i in orig if i["kind"] == "variation")
    recognised = base + optional_taken + approved
    official = base + optional_taken + sum(i["value_calc"] for i in var_items if _is_official(i, vars_))
    # original to revised (recognised): less options in the original not taken, plus options taken and variations on top
    bridge = dict(original=original, optional_not_taken=-opt_declined,
                  optional_added=sum(i["value_calc"] for i in leaves if i["kind"] == "optional" and not in_original(i)),
                  variations_added=sum(i["value_calc"] for i in leaves if i["kind"] == "variation" and not in_original(i)),
                  variations_declined=-sum(_num(i["value"]) for i in orig if i["kind"] == "variation" and i["status"] == "declined"),
                  other=0.0)
    bridge["other"] = recognised - (bridge["original"] + bridge["optional_not_taken"] + bridge["optional_added"] + bridge["variations_added"] + bridge["variations_declined"])
    by_id = {i["id"]: i for i in items}

    def stage_of(i):
        while i is not None:
            if i.get("stage"):
                return i["stage"]
            i = by_id.get(i["parent_id"])
        return "Unassigned"
    stages = defaultdict(float)
    for i in items:
        if i["is_leaf"]:
            stages[stage_of(i)] += i["value_calc"]
    return dict(base=base, optional_taken=optional_taken, optional_total=optional_all, variations_approved=approved,
                optional_confirmed=opt_by["confirmed"], optional_offered=opt_by["offered"], optional_cancelled=opt_by["cancelled"],
                variations_approved_value=var_by["approved"], variations_pending=var_by["pending"], variations_declined=var_by["declined"],
                recognised=recognised, official=official, original=original, optional_declined_in_original=opt_declined,
                variations_in_original=var_in_orig, optional_in_original=any(i["kind"] == "optional" for i in orig),
                variations_listed=sum(_num(i["value"]) for i in leaves if i["kind"] == "variation"), bridge=bridge,
                stages=dict(stages), n_items=len(items))


OPT_CONFIRMED = {"confirmed", "taken", "accepted", "approved", "awarded", "exercised", "yes", "y", "included"}
OPT_CANCELLED = {"cancelled", "canceled", "declined", "rejected", "withdrawn", "not taken", "deleted", "no", "n", "excluded"}


def opt_status(v):
    """An optional price's status: offered (no client answer yet), confirmed or cancelled; older words and other
    spellings ("taken", "Declined", "Cancelled" from a template) are read as these."""
    s = str(v or "").strip().lower()
    return "confirmed" if s in OPT_CONFIRMED else "cancelled" if s in OPT_CANCELLED else "offered"


VAR_APPROVED = {"approved", "agreed", "confirmed", "taken", "accepted", "awarded", "yes", "y", "executed"}
VAR_DECLINED = {"declined", "rejected", "cancelled", "canceled", "withdrawn", "denied", "no", "n", "not taken"}


def var_status(v):
    """A variation listed in the claim schedule: approved, pending or declined. Nothing recorded = approved (a
    schedule lists the variations it claims)."""
    s = str(v or "").strip().lower()
    if not s:
        return "approved"
    return "approved" if s in VAR_APPROVED else "declined" if s in VAR_DECLINED else "pending"


def item_counts(i):
    """Does this payment milestone count in the contract value now? Confirmed options and approved variations do; an option still offered
    or a variation pending only if it is in the original contract value; cancelled or declined never. (Same rule as items_tree.)"""
    if i["kind"] == "optional":
        st = opt_status(i.get("optional_status"))
        return st == "confirmed" or (st == "offered" and in_original(i))
    if i["kind"] == "variation" and not i.get("variation_id"):
        st = var_status(i.get("optional_status"))
        return st == "approved" or (st == "pending" and in_original(i))
    return True


def in_original(i):
    """Is this item part of the original contract value? As set at import (in_original); otherwise base and optional
    prices are, variations are not."""
    if i.get("in_original") is not None:
        return bool(i["in_original"])
    return i["kind"] in ("base", "optional")


def _is_official(item, vars_):
    v = next((x for x in vars_ if x["id"] == item.get("variation_id")), None)
    if not v:
        return True
    return v["contract_change"] == "No" or v["contract_status"] == "Executed"


# ---- claims ---------------------------------------------------------------
def claim_list(con, pid):
    out = []
    for c in db.rows(con, "SELECT * FROM claim WHERE project_id=? ORDER BY period, id", (pid,)):
        r = db.one(con, "SELECT COALESCE(SUM(amount),0) a, COALESCE(SUM(COALESCE(certified, amount)),0) e, "
                        "COALESCE(SUM(certified),0) k, COUNT(certified) n, COUNT(*) t FROM claim_line WHERE claim_id=?", (c["id"],))
        c.update(total=r["a"], effective=r["e"], certified_total=r["k"], certified_lines=r["n"], lines=r["t"],
                 basis="certified" if r["t"] and r["n"] == r["t"] else ("part certified" if r["n"] else "claimed"))
        out.append(c)
    return out


def claim_detail(con, pid, cid):
    c = db.one(con, "SELECT * FROM claim WHERE id=? AND project_id=?", (cid, pid))
    if not c:
        return None
    items = items_tree(con, pid)
    lines = {l["item_id"]: l for l in db.rows(con, "SELECT * FROM claim_line WHERE claim_id=?", (cid,))}
    prior = defaultdict(float)
    for r in con.execute("SELECT cl.item_id, SUM(COALESCE(cl.certified, cl.amount)) a FROM claim_line cl JOIN claim c ON c.id=cl.claim_id "
                         "WHERE c.project_id=? AND c.id!=? AND c.status!='draft' AND c.period<? GROUP BY cl.item_id", (pid, cid, c["period"])):
        prior[r["item_id"]] = r["a"]
    out = []
    per = c["period"][:7]
    for i in items:
        if not i["is_leaf"] or i["value_calc"] == 0:
            continue
        cum_plan = sum(v for m, v in i["plan"].items() if m <= per)
        this_plan = i["plan"].get(per, 0.0)
        suggested = max(0.0, cum_plan - prior[i["id"]])
        out.append(dict(item_id=i["id"], ref=i["ref"], description=i["description"], stage=i["stage"], kind=i["kind"],
                        value=i["value_calc"], prior=prior[i["id"]], planned_this=this_plan, cum_planned=cum_plan,
                        suggested=round(suggested, 2), amount=(lines[i["id"]]["amount"] if i["id"] in lines else 0.0),
                        certified=(lines[i["id"]]["certified"] if i["id"] in lines else None),
                        remaining=i["value_calc"] - prior[i["id"]] - (lines[i["id"]]["amount"] if i["id"] in lines else 0.0)))
    c["lines"] = out
    c["total"] = sum(l["amount"] for l in out)
    c["effective"] = sum(l["certified"] if l["certified"] is not None else l["amount"] for l in out)
    c["certified_total"] = sum(l["certified"] for l in out if l["certified"] is not None)
    return c


def certify_all(con, cid):
    con.execute("UPDATE claim_line SET certified=amount WHERE claim_id=?", (cid,))


def certify_total(con, cid, amount):
    """Certify a total amount, shared across the lines in proportion to what was claimed."""
    lines = db.rows(con, "SELECT * FROM claim_line WHERE claim_id=? ORDER BY id", (cid,))
    tot = sum(l["amount"] or 0 for l in lines)
    if not lines or tot <= 0:
        raise ValueError("There is nothing claimed to certify")
    f, given = float(amount) / tot, 0.0
    for i, l in enumerate(lines):
        a = round((l["amount"] or 0) * f, 2) if i < len(lines) - 1 else round(float(amount) - given, 2)
        given += a
        con.execute("UPDATE claim_line SET certified=? WHERE id=?", (a, l["id"]))


def summary_empty():
    return dict(base=0.0, optional_taken=0.0, optional_total=0.0, variations_approved=0.0, optional_confirmed=0.0, optional_offered=0.0,
                optional_cancelled=0.0, variations_approved_value=0.0, variations_pending=0.0, variations_declined=0.0, recognised=0.0,
                official=0.0, original=0.0, optional_declined_in_original=0.0, variations_in_original=0.0, optional_in_original=False,
                variations_listed=0.0, bridge=dict(original=0.0, optional_not_taken=0.0, optional_added=0.0, variations_added=0.0,
                                                   variations_declined=0.0, other=0.0), stages={}, n_items=0)


def revenue_curve(con, pid, grid, M):
    """Monthly revenue: claims issued up to the status month, then the remaining schedule (with catch-up in M+1)."""
    from . import linking
    if linking.is_parent(con, pid):   # a parent project: each child at its own status month, added month by month
        from . import engine
        parts = []
        for c in linking.children(con, pid):
            parts.append(revenue_curve(con, c["id"], grid, engine.project_status_month(c)))
        srcs = {x["source"] for x in parts}
        return {"source": "claims" if "claims" in srcs else "pronto" if "pronto" in srcs else "none",
                "series": [dict(month=m, actual=sum(x["series"][i]["actual"] for x in parts), planned=sum(x["series"][i]["planned"] for x in parts))
                           for i, m in enumerate(grid)],
                "claimed_to_date": sum(x["claimed_to_date"] for x in parts), "future_planned": sum(x["future_planned"] for x in parts)}
    items = items_tree(con, pid)
    actual = defaultdict(float)
    for r in con.execute("SELECT c.period, SUM(COALESCE(cl.certified, cl.amount)) a FROM claim c JOIN claim_line cl ON cl.claim_id=c.id "
                         "WHERE c.project_id=? AND c.status!='draft' GROUP BY c.period", (pid,)):
        actual[r["period"][:7]] += r["a"] or 0
    source = "claims"
    if not actual:
        for r in con.execute("SELECT month, -SUM(cost) a FROM pronto_tx WHERE project_id=? AND class='revenue' GROUP BY month", (pid,)):
            if r["a"]:
                actual[r["month"]] += r["a"]
        source = "pronto" if actual else "none"
    planned = defaultdict(float)
    nxt = db.add_months(M, 1)
    claim_in_month = actual.get(M, 0.0) > 0  # a claim already issued for the status month stands in for its schedule
    catch = db.add_months(M, 1) if claim_in_month else M
    for i in items:
        if not i["is_leaf"]:
            continue
        cum_plan = sum(v for m, v in i["plan"].items() if m <= M)
        behind = max(0.0, cum_plan - i["claimed"]) if source == "claims" else 0.0
        if behind:
            planned[catch] += behind
        for m, v in i["plan"].items():
            if m > M or (m == M and not claim_in_month and source != "claims"):
                planned[m] += v
    series = []
    for m in grid:
        a = actual.get(m, 0.0) if m <= M else 0.0
        series.append(dict(month=m, actual=a, planned=planned.get(m, 0.0) if (m > M or (m == M and not claim_in_month)) else 0.0))
    return {"source": source, "series": series, "claimed_to_date": sum(actual.get(m, 0) for m in actual if m <= M),
            "future_planned": sum(planned.values())}


# ---- the claim schedule grid: type a $ or % in a month, drag a value to a later month ---------------------------
TOL = 0.005


def _mlabel(m):
    return f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][int(m[5:7]) - 1]}-{m[2:4]}"


def claim_months(con, pid):
    """Every claim by month: issued ones (submitted, certified, paid) lock their month, a draft keeps in step with the grid."""
    out = {}
    for c in db.rows(con, "SELECT id, claim_no, period, status FROM claim WHERE project_id=? ORDER BY period, id", (pid,)):
        out[c["period"][:7]] = dict(id=c["id"], claim_no=c["claim_no"], status=c["status"], issued=c["status"] != "draft")
    return out


def _editable_item(con, pid, iid):
    it = db.one(con, "SELECT * FROM contract_item WHERE id=? AND project_id=?", (iid, pid))
    if not it:
        raise ValueError("That claim item was not found")
    if db.scalar(con, "SELECT COUNT(*) FROM contract_item WHERE parent_id=?", (iid,)):
        raise ValueError("That row is a group. Type in the lines under it.")
    if not item_counts(it):
        raise ValueError("This optional price or variation does not count in the contract value yet (not confirmed or approved), so it has no schedule.")
    return it


def _state(con, pid, it):
    """What the item stands at: months already claimed (locked), and the scheduled amount in every other month."""
    cm = claim_months(con, pid)
    locked = {m for m, c in cm.items() if c["issued"]}
    claimed = {}
    for r in con.execute("SELECT c.period, SUM(COALESCE(cl.certified, cl.amount)) a FROM claim_line cl JOIN claim c ON c.id=cl.claim_id "
                         "WHERE c.project_id=? AND c.status!='draft' AND cl.item_id=? GROUP BY c.period", (pid, it["id"])):
        claimed[r["period"][:7]] = r["a"] or 0
    if (it.get("method") or "even") == "manual":
        plan = {r["month"][:7]: r["amount"] for r in con.execute("SELECT month, amount FROM revenue_plan WHERE item_id=?", (it["id"],))}
    else:
        sm = ((db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,)) or {}).get("status_date") or "")[:7] or None
        plan = {m: round(v, 2) for m, v in plan_series(it, None, sum(claimed.values()), locked, sm).items()}
    return cm, locked, claimed, plan


def _total(claimed, plan, locked):
    return sum(claimed.values()) + sum(a for m, a in plan.items() if m not in locked)


def _write_plan(con, it, plan):
    con.execute("DELETE FROM revenue_plan WHERE item_id=?", (it["id"],))
    for m, a in sorted(plan.items()):
        if abs(a) > TOL:
            db.insert(con, "revenue_plan", dict(item_id=it["id"], month=m, amount=round(a, 2)))
    if (it.get("method") or "even") != "manual":
        db.update(con, "contract_item", it["id"], {"method": "manual"})


def _sync_draft(con, pid, iid, month, amount):
    """A draft claim for that month follows the grid, so the claim is what you typed."""
    c = db.one(con, "SELECT id FROM claim WHERE project_id=? AND period=? AND status='draft'", (pid, month))
    if not c:
        return
    con.execute("DELETE FROM claim_line WHERE claim_id=? AND item_id=?", (c["id"], iid))
    if abs(amount) > TOL:
        db.insert(con, "claim_line", dict(claim_id=c["id"], item_id=iid, amount=round(amount, 2)))


def set_cell(con, pid, iid, month, amount=None, pct=None, rest=False):
    """Set one month of one claim item, as a dollar amount, a percentage of the item's price, or 'rest' (whatever is left).
    The item can never be scheduled for more than its price in total, claims already issued included."""
    month = (month or "")[:7]
    if len(month) != 7:
        raise ValueError("Choose a month")
    it = _editable_item(con, pid, iid)
    value = _num(it["value"])
    cm, locked, claimed, plan = _state(con, pid, it)
    if month in locked:
        c = cm[month]
        raise ValueError(f"{_mlabel(month)} is already claimed ({c['claim_no']}, {c['status']}), so it cannot be changed.")
    old_total = _total(claimed, plan, locked)
    others = old_total - plan.get(month, 0.0)
    if rest:
        amount = value - others
    elif pct is not None:
        amount = value * float(pct) / 100.0
    amount = round(float(amount or 0), 2)
    if (value >= 0 and amount < -TOL) or (value < 0 and amount > TOL):
        raise ValueError("A month cannot be negative." if value >= 0 else "This is a credit line, so its months are credits.")
    new_total = others + amount
    if 0 < abs(new_total - value) < 0.0105:
        amount = round(amount + (value - new_total), 2)         # a rounded percentage that lands on the price takes the last cent
        new_total = others + amount
    grows = new_total > old_total + TOL if value >= 0 else new_total < old_total - TOL
    over = new_total > value + TOL if value >= 0 else new_total < value - TOL
    if over and grows:
        avail = round(value - others, 2)
        pct_av = f" ({avail / value:.1%})" if value else ""
        raise ValueError(f"That would schedule {new_total:,.2f} in total, more than the item's price of {value:,.2f}. "
                         f"The most you can enter in {_mlabel(month)} is {max(avail, 0) if value >= 0 else min(avail, 0):,.2f}{pct_av}.")
    plan[month] = amount
    _write_plan(con, it, plan)
    _sync_draft(con, pid, iid, month, amount)
    total = _total(claimed, plan, locked)
    return dict(month=month, amount=amount, total=round(total, 2), left=round(value - total, 2), value=value)


def move_cell(con, pid, iid, src, dst):
    """Drag a month's value to another month of the same item, later or earlier but never before the status month. Nothing is lost: the target adds to what is already there."""
    src, dst = (src or "")[:7], (dst or "")[:7]
    if not src or not dst or dst == src:
        raise ValueError("Drop the value on another month of the same line.")
    from . import engine
    M = engine.project_status_month(db.one(con, "SELECT * FROM project WHERE id=?", (pid,)))
    if dst < M:
        raise ValueError(f"A value can only move to {_mlabel(M)} (the status month) or a later month, not into the past.")
    it = _editable_item(con, pid, iid)
    cm, locked, claimed, plan = _state(con, pid, it)
    for m in (src, dst):
        if m in locked:
            raise ValueError(f"{_mlabel(m)} is already claimed ({cm[m]['claim_no']}, {cm[m]['status']}), so it cannot change.")
    amount = plan.get(src, 0.0)
    if abs(amount) < TOL:
        raise ValueError(f"There is nothing in {_mlabel(src)} to move.")
    plan[dst] = round(plan.get(dst, 0.0) + amount, 2)
    plan[src] = 0.0
    _write_plan(con, it, plan)
    _sync_draft(con, pid, iid, src, 0.0)
    _sync_draft(con, pid, iid, dst, plan[dst])
    return dict(moved=amount, src=src, dst=dst, dst_amount=plan[dst])


def claim_sheet(con, pid, cid):
    """The claim as the client sees it: every group and line in schedule order with this month, to date and remaining.
    Group rows add up the lines below them; the grand total adds the lines only."""
    d = claim_detail(con, pid, cid)
    if not d:
        return None
    items = items_tree(con, pid)
    by_item = {l["item_id"]: l for l in d["lines"]}
    kids = defaultdict(list)
    for i in items:
        kids[i["parent_id"]].append(i)

    def sums(i):
        if i["is_leaf"]:
            l = by_item.get(i["id"])
            return (l["value"], l["prior"], l["amount"], l["remaining"]) if l else None
        tot = None
        for c in kids.get(i["id"], []):
            s = sums(c)
            if s:
                tot = s if tot is None else tuple(a + b for a, b in zip(tot, s))
        return tot

    rows = []

    def walk(i, depth):
        s = sums(i)
        if not s:
            return
        value, prior, amount, remaining = s
        rows.append(dict(ref=i["ref"] or "", stage=i.get("stage") or "", description=i["description"], depth=depth, leaf=bool(i["is_leaf"]), value=value, prior=prior,
                         this=amount, to_date=prior + amount, pct=(prior + amount) / value if value else 0.0, remaining=remaining))
        for c in kids.get(i["id"], []):
            walk(c, depth + 1)
    for top in kids.get(None, []):
        walk(top, 0)
    leaves = [r for r in rows if r["leaf"]]
    totals = dict(value=sum(r["value"] for r in leaves), prior=sum(r["prior"] for r in leaves), this=sum(r["this"] for r in leaves),
                  remaining=sum(r["remaining"] for r in leaves))
    totals["to_date"] = totals["prior"] + totals["this"]
    totals["pct"] = totals["to_date"] / totals["value"] if totals["value"] else 0.0
    return dict(claim=d, rows=rows, totals=totals)


def trim_excess(con, pid):
    """Lines scheduled for more than their price (claims issued plus months still to claim): take the excess off the latest
    months first. Claimed months are never touched. Returns what was trimmed and what could not be."""
    trimmed, stuck = [], []
    for it in db.rows(con, "SELECT * FROM contract_item WHERE project_id=? ORDER BY sort_order, id", (pid,)):
        if db.scalar(con, "SELECT COUNT(*) FROM contract_item WHERE parent_id=?", (it["id"],)) or _num(it["value"]) < 0:
            continue
        if not item_counts(it):
            continue
        cm, locked, claimed, plan = _state(con, pid, it)
        value = _num(it["value"])
        excess = _total(claimed, plan, locked) - value
        if excess <= TOL:
            continue
        removed, changed = 0.0, []
        for m in sorted(plan, reverse=True):
            if m in locked or plan[m] <= TOL:
                continue
            take = min(excess - removed, plan[m])
            plan[m] = round(plan[m] - take, 2)
            removed += take
            changed.append(m)
            if removed >= excess - TOL:
                break
        if removed > TOL:
            _write_plan(con, it, plan)
            for m in changed:
                _sync_draft(con, pid, it["id"], m, plan[m])
            trimmed.append(dict(id=it["id"], ref=it["ref"], description=it["description"], removed=round(removed, 2)))
        if removed < excess - 0.01:
            stuck.append(dict(id=it["id"], ref=it["ref"], description=it["description"], over=round(excess - removed, 2)))
    return dict(trimmed=trimmed, total=round(sum(t["removed"] for t in trimmed), 2), stuck=stuck)


def review_deadline(con, p, submitted):
    """The date by which the client must review a claim submitted on `submitted`: the contract's review period counted in business days
    (not weekends or the project's public holidays) or calendar days. None when the contract's period is not set or there is no date."""
    from datetime import date, timedelta
    n = int(p.get("review_days") or 0)
    if not n or not submitted:
        return None
    d = date.fromisoformat(db.iso(submitted)[:10])
    if (p.get("review_basis") or "business") == "calendar":
        return (d + timedelta(days=n)).isoformat()
    hol = {r["day"][:10] for r in db.rows(con, "SELECT day FROM holiday WHERE project_id=?", (p["id"],))}
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in hol:
            n -= 1
    return d.isoformat()


def _month_end(m):
    y, mo = int(m[:4]), int(m[5:7])
    nxt = date(y + (mo == 12), mo % 12 + 1, 1)
    return (nxt - timedelta(days=1)).isoformat()


def set_item_window(con, pid, iid, start=None, stop=None, months=None):
    """Give a claim line a window (Start, End, months): its price not yet claimed is spread over the window's open months, like cost to
    complete on Cost control. Any two of start, end and months work it out. Typing a window takes the line off the client schedule."""
    it = _editable_item(con, pid, iid)
    s, e = (start or "")[:7] or None, (stop or "")[:7] or None
    m = int(months) if months else None
    if m and m < 1:
        raise ValueError("Months must be 1 or more")
    if s and m and not e:
        e = db.month_range(s, s)[0]
        y, mo = int(s[:4]), int(s[5:7]) + m - 1
        e = f"{y + (mo - 1) // 12}-{(mo - 1) % 12 + 1:02d}"
    elif e and m and not s:
        y, mo = int(e[:4]), int(e[5:7]) - m + 1
        s = f"{y + (mo - 1) // 12}-{(mo - 1) % 12 + 1:02d}"
    if s and e and e < s:
        raise ValueError("The end is before the start")
    patch = {"start_date": (s + "-01") if s else None, "end_date": _month_end(e) if e else None}
    if s:
        patch["method"] = "window"
    db.update(con, "contract_item", iid, patch)
    n = con.execute("UPDATE programme_task SET link_item_id=NULL WHERE project_id=? AND link_item_id=?", (pid, iid)).rowcount
    db.bump(con, pid)
    return {"unlinked": n}
