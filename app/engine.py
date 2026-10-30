"""Cost control engine.

One pass over the project produces a row per CBS node with allowance, commitments, actuals, accruals, cost to
complete, EAC and the monthly grid, then rolls the leaf rows up through the tree.

EAC = CTD + ACC + CTC. This is deliberately not the CMT's cost-to-date + cost-to-complete; accruals are included
(see the known CMT issue). `eac_cmt_style` is exposed so the Reconcile page can show the difference.
"""
import json
from collections import defaultdict
from datetime import date, timedelta

from . import accruals as _accr, db, forecast as _fc, subcontracts

ZERO_TOL = 0.005


def _fnum(x):
    return float(x or 0)


def project_status_month(p):
    return (p.get("status_date") or date.today().isoformat())[:7]


def grid_for(p, extra_months=()):
    """Month grid: explicit grid dates if set, else widened to cover project dates, status date and data."""
    lo = [m for m in [(p.get("grid_start") or "")[:7], (p.get("project_start") or "")[:7], *extra_months] if m]
    hi = [m for m in [(p.get("grid_end") or "")[:7], (p.get("project_end") or "")[:7], project_status_month(p)] if m]
    if not lo:
        lo = [project_status_month(p)]
    a = min(lo)
    b = max(hi + [max(extra_months)] if extra_months else hi)
    if p.get("grid_end") is None and p.get("project_end"):
        b = db.add_months(max(b, p["project_end"][:7]), 2)
    return db.month_range(a, b)


# --------------------------------------------------------------------------
# Forecast item series
# --------------------------------------------------------------------------
def _occurrences(item):
    start = db.to_date(item["start_date"])
    if not start:
        return []
    end = db.to_date(item["end_date"])
    freq = (item.get("freq") or "Monthly")
    n = item.get("occurrences")
    out = []
    d = start
    cap = 3000
    while cap:
        cap -= 1
        if n and len(out) >= n:
            break
        if not n and end and d > end:
            break
        if not n and not end and len(out) >= 1:
            break
        if freq == "Daily":
            if d.weekday() < 5:
                out.append(d)
            d += timedelta(days=1)
        elif freq == "Weekly":
            out.append(d); d += timedelta(days=7)
        elif freq == "Fortnightly":
            out.append(d); d += timedelta(days=14)
        else:
            out.append(d)
            m = db.add_months(d.strftime("%Y-%m"), 1)
            d = date(int(m[:4]), int(m[5:7]), min(start.day, 28))
    return out


def item_series(item, manual=None, ctx=None, notes=None):
    """month -> amount for one forecast item (whole life; the caller trims to the forecast window).
    Calendar, Milestones and Roster need the project context (forecast.Ctx) for day grids, milestones and rates."""
    if item.get("spread") in _fc.DETAIL_SPREADS:
        return _fc.series(item, ctx, notes) if ctx is not None else defaultdict(float)
    total = _fnum(item["qty"]) * _fnum(item["rate"]) * (1 if item.get("pct") in (None, "") else _fnum(item["pct"]))
    sp = item.get("spread") or "Linear"
    out = defaultdict(float)
    if sp == "Manual":
        for m, a in (manual or {}).items():
            out[m] += a
        return out
    s, e = db.month_of(item.get("start_date")), db.month_of(item.get("end_date"))
    if not s:
        return out
    if sp == "Lump":
        out[s] += total
    elif sp == "Linear":
        e = e or s
        months = db.month_range(s, e) or [s]
        for m in months:
            out[m] += total / len(months)
    elif sp == "Recurring":
        per = _fnum(item["qty"]) * _fnum(item["rate"]) * (1 if item.get("pct") in (None, "") else _fnum(item["pct"]))
        for d in _occurrences(item):
            out[d.strftime("%Y-%m")] += per
    return out


def _drawdown(series, draws):
    """Take allocated forecast out of a pool's forecast: same month first, then the pool's earliest months.
    Reduces both the pool series and what is left to draw. Returns the amount taken."""
    taken = 0.0
    for d in draws:
        for m in sorted(d):
            need = d[m]
            if need <= ZERO_TOL:
                continue
            for pm in [m] + sorted(k for k in series if k != m):
                if need <= ZERO_TOL:
                    break
                have = series.get(pm, 0.0)
                if have <= ZERO_TOL:
                    continue
                t = min(have, need)
                series[pm] = have - t
                need -= t
                taken += t
            d[m] = need
    return taken


# --------------------------------------------------------------------------
# Main computation
# --------------------------------------------------------------------------
_cache = {}


def compute(con, pid, status_month=None):
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    if not p:
        raise KeyError("project")
    key = (str(db.DB_PATH), pid, p["version"], status_month)  # path included so separate databases never share a cached result
    if p.get("is_parent"):   # a parent project: its children merged by CBS code (cached on the children's versions)
        from . import linking
        key = key + linking.cache_key(con, pid)
    if key in _cache:
        return _cache[key]
    if p.get("is_parent"):
        res = linking.merged(con, p, status_month)
    else:
        res = _compute(con, p, status_month)
    if len(_cache) > 24:
        _cache.clear()
    _cache[key] = res
    return res


def what_if(con, pid, nid, pot=False, **fields):
    """The line's monthly cost to complete if it used other method fields (nothing is saved)."""
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    res = _compute(con, p, None, overrides={nid: fields})
    key = f"p{nid}" if pot else nid
    r = next((x for x in res["rows"] if x["id"] == key), None)
    if r is None:
        return None
    return dict(grid=res["grid"], status_month=res["status_month"], f=r["f"], ctc=r["ctc"], eac=r["eac"], contingency=r["contingency"], note=r["note"],
                method=r["method"])


def _compute(con, p, status_month=None, overrides=None):
    pid = p["id"]
    M = status_month or project_status_month(p)
    settings = db.project_settings(con, pid)
    tol = _fnum(p["tolerance"]) or 1.0
    company_view = settings.get("allowance_view", "pm") == "company"
    nodes = db.rows(con, "SELECT n.*, r.code AS resource_code, r.name AS resource_name, r.kind AS resource_kind, "
                         "r.function AS res_function FROM cbs_node n LEFT JOIN resource r ON r.id=n.resource_id "
                         "WHERE n.project_id=? ORDER BY n.sort_order, n.id", (pid,))
    by_id = {n["id"]: n for n in nodes}
    for k, v in (overrides or {}).items():
        if k in by_id:
            by_id[k].update(v)
    kids = defaultdict(list)
    for n in nodes:
        kids[n["parent_id"]].append(n["id"])

    # ledger
    led = defaultdict(lambda: defaultdict(float))
    for r in con.execute("SELECT node_id, kind, SUM(budget) b, SUM(risk) k, SUM(contingency) c, SUM(risk_cover) rc FROM allowance_ledger WHERE project_id=? GROUP BY node_id, kind", (pid,)):
        led[r["node_id"]][r["kind"] + "_b"] += r["b"] or 0
        led[r["node_id"]][r["kind"] + "_r"] += r["k"] or 0
        led[r["node_id"]]["_c"] += r["c"] or 0
        led[r["node_id"]]["_rc"] += r["rc"] or 0

    # actuals by node and month
    act = defaultdict(lambda: defaultdict(float))
    jour = defaultdict(float)
    ntx = defaultdict(int)
    for r in con.execute("SELECT node_id, month, class, SUM(cost) c, COUNT(*) n FROM pronto_tx WHERE project_id=? AND class IN ('actual','journal') "
                         "AND node_id IS NOT NULL GROUP BY node_id, month, class", (pid,)):
        act[r["node_id"]][r["month"]] += r["c"] or 0
        ntx[r["node_id"]] += r["n"]
        if r["class"] == "journal":
            jour[r["node_id"]] += r["c"] or 0

    # accruals: PM accruals still open + timesheets not yet posted
    accr = defaultdict(lambda: defaultdict(float))
    accr_src = defaultdict(lambda: defaultdict(float))
    # (accruals.counted: open PM accruals above what finance already accrued in Pronto, matched invoices in the month the
    # work was done and reversed when they land, unposted timesheets, subcontract claims not yet invoiced)
    for nid, m, amt, src in _accr.counted(con, pid):
        accr[nid][m] += amt
        accr_src[nid]["PM" if src == "Matched" else src] += amt

    # commitments
    po = defaultdict(lambda: {"committed": 0.0, "received": 0.0, "outstanding": 0.0, "open": 0, "n": set()})
    for r in con.execute("SELECT node_id, order_no, committed, received, is_open FROM pronto_po WHERE project_id=? AND node_id IS NOT NULL", (pid,)):
        d = po[r["node_id"]]
        # a closed PO commits only what was received; the rest of its original value is released
        d["committed"] += (r["committed"] or 0) if r["is_open"] else (r["received"] or 0)
        d["received"] += r["received"] or 0
        d["n"].add(r["order_no"])
        if r["is_open"]:
            d["outstanding"] += max(0.0, (r["committed"] or 0) - (r["received"] or 0))
            d["open"] += 1

    items = defaultdict(list)
    for r in db.rows(con, "SELECT * FROM forecast_item WHERE project_id=? ORDER BY id", (pid,)):
        items[r["node_id"]].append(r)
    manual = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for r in con.execute("SELECT node_id, item_id, month, amount FROM forecast_manual WHERE project_id=?", (pid,)):
        manual[r["node_id"]][r["item_id"]][r["month"]] += r["amount"]
    claim_sched = subcontracts.node_schedule(con, pid, M)
    fctx = _fc.load_ctx(con, pid, p)

    all_months = set()
    for d in (act, accr):
        for nid in d:
            all_months.update(d[nid])
    grid = grid_for(p, sorted(all_months))
    gidx = {m: i for i, m in enumerate(grid)}
    G = len(grid)
    proj_end = (p.get("project_end") or "")[:7] or grid[-1]
    proj_start = (p.get("project_start") or "")[:7] or grid[0]

    eff = {}

    def effd(n):
        """Own start/end, else inherited from the nearest ancestor that has them."""
        if n["id"] in eff:
            return eff[n["id"]]
        s0, e0 = n.get("start_date"), n.get("end_date")
        if (not s0 or not e0) and n["parent_id"]:
            ps, pe = effd(by_id[n["parent_id"]])
            s0, e0 = s0 or ps, e0 or pe
        eff[n["id"]] = (s0, e0)
        return eff[n["id"]]

    def level_of(n):
        lv = 1
        while n["parent_id"]:
            n = by_id[n["parent_id"]]
            lv += 1
        return lv

    def zeros():
        return [0.0] * G

    rows = {}

    def leaf_row(nid, n, is_pot, draws=None, covered=0.0):
        a_m, x_m = act.get(nid, {}), accr.get(nid, {})
        ctd = sum(a_m.values())
        acc = sum(x_m.values())
        L = led.get(nid, {})
        orig_b, orig_r = L.get("estimate_b", 0), L.get("estimate_r", 0)
        budget = sum(v for k, v in L.items() if k.endswith("_b"))
        risk = sum(v for k, v in L.items() if k.endswith("_r"))
        var_b, var_r = L.get("variation_b", 0), L.get("variation_r", 0)
        # the PM works to the budget; the risk bucket is held by the company and only counts in the company view
        allowance = budget + (risk if company_view else 0.0)
        pod = po.get(nid)
        outstanding = pod["outstanding"] if pod else 0.0
        method = (n.get("unalloc_method") or "NONE") if is_pot else (n.get("method") or "AT-BUDGET")
        es, ee = effd(n)
        start = (es or "")[:7] or proj_start
        end = (ee or "")[:7] or proj_end
        if not is_pot and not es and (a_m or x_m):
            start = min(list(a_m) + list(x_m))
        fc_from = max(M, start)
        fc_to = max(M, end, fc_from)
        fmonths = [m for m in db.month_range(fc_from, fc_to) if m in gidx]
        if not fmonths:
            fmonths = [M] if M in gidx else []
        series = defaultdict(float)
        draw = defaultdict(float)   # forecast on this line that is allocated out of a pool above it, by month
        note = ""
        fc_hours = 0.0
        ctc = 0.0
        eac_top = None

        # a line only forecasts cost to complete once it has a window: its own or its group's start and end (typed, from a duration or
        # linked to the project schedule). Before that it sits at cost to date and accruals, so a new project starts with zero CTC.
        has_window = bool(es or ee)
        if not is_pot and not has_window and method in ("AT-BUDGET", "AT-COMMIT", "BURN-RATE", "TOP-DOWN") and \
                (n.get("origin") not in ("ctc", "wip")):
            fmonths = []
            note = "Set a start and end, or link to the project schedule, to forecast"

        def spread(amount):
            if amount <= 0 or not fmonths:
                return
            for m in fmonths:
                series[m] += amount / len(fmonths)

        if method == "AT-BUDGET":
            # an unallocated pool forecasts only what is left of it after the costs beneath it that its allowance has to cover
            spread(max(0.0, allowance - ctd - acc - (covered if is_pot else 0.0)))
        elif method == "NONE":
            pass                                   # not forecast: cost to date and accruals only
        elif method == "BURN-RATE":
            hist = {m: v for m, v in {**{m: a_m.get(m, 0) + x_m.get(m, 0) for m in set(a_m) | set(x_m)}}.items() if m < M}
            if hist:
                first = min(hist)
                nmonths = max(1, db.month_diff(first, M))  # first spend month up to, not including, the status month
                avg = sum(hist.values()) / nmonths
                if avg > 0:
                    spread(avg * len(fmonths))
            else:
                note = "No spend history to burn from"
        elif method == "AT-COMMIT":
            spread(outstanding + _fnum(n.get("uncommitted")))
        elif method == "TOP-DOWN":
            e = n.get("unalloc_eac") if is_pot else n.get("eac_override")
            if e is None:
                note = "Enter a top-down EAC"
            else:
                eac_top = _fnum(e)
                spread(max(0.0, eac_top - ctd - acc))
        elif method == "GROUND-UP":
            its = items.get(nid, [])
            if not its:
                note = "No forecast items"
            notes = []
            for it in its:
                it = dict(it)
                # an item with no dates of its own follows the line's window (from the schedule or typed on the line)
                it["start_date"] = it.get("start_date") or (start + "-01")
                it["end_date"] = it.get("end_date") or (db.month_end(end) if it.get("spread") != "Roster" or not it.get("swings") else None)
                s = item_series(it, manual.get(nid, {}).get(it["id"]), fctx, notes)
                for m, v in s.items():
                    if m >= M and m in gidx:
                        series[m] += v
                        if it.get("from_pool") and not is_pot:
                            draw[m] += v
                if it.get("spread") in _fc.DAY_SPREADS:
                    fc_hours += _fc.forecast_hours(it, fctx)
            if notes and not note:
                note = "; ".join(notes[:2]) + (f" (+{len(notes) - 2} more)" if len(notes) > 2 else "")
        elif method == "CLAIM":
            cs = claim_sched.get(nid)
            if not cs:
                note = "No subcontract schedule linked"
            else:
                for m, v in cs.get("direct", {}).items():  # the PM's own forecast on the claim sheet
                    if m >= M and m in gidx:
                        series[m] += v
                remaining = max(0.0, cs["net_total"] - cs["net_claimed"])
                fut = {m: v for m, v in cs["net_by_month"].items() if m >= M}
                tot = sum(fut.values())
                if remaining > 0:
                    if tot > 0:
                        for m, v in fut.items():
                            if m in gidx:
                                series[m] += remaining * v / tot
                    else:
                        spread(remaining)
        elif method == "MANUAL":
            for m, v in manual.get(nid, {}).get(None, {}).items():
                if m >= M and m in gidx:
                    series[m] += v
        pool_drawn = 0.0
        if is_pot and draws and method != "AT-BUDGET":     # AT-BUDGET has already netted what the lines below take
            pool_drawn = _drawdown(series, draws)
            if pool_drawn > 0.5 and not note:
                note = f"Pool reduced by {pool_drawn:,.0f} allocated to resources below"
        ctc = sum(series.values())
        eac = ctd + acc + ctc
        row = dict(
            id=f"p{nid}" if is_pot else nid, node_id=nid, parent_id=nid if is_pot else n["parent_id"],
            code=(n["code"] + ".U") if is_pot else n["code"],
            name="(Unallocated)" if is_pot else n["name"],
            kind="pot" if is_pot else "line", gp=n["gp"], category=None,
            resource_code=None if is_pot else n.get("resource_code"),
            resource_kind=None if is_pot else n.get("resource_kind"),
            function=None if is_pot else (n.get("function") or n.get("res_function")),
            scope=None if is_pot else n.get("scope"), method=method, start=start, end=end,
            po_no=n.get("po_no"), active=n.get("active", 1), origin=n.get("origin"),
            start_own=n.get("start_date"), end_own=n.get("end_date"),
            orig_budget=orig_b, orig_risk=orig_r, budget=budget, risk=risk, allowance=allowance, cont_earmark=L.get("_c", 0.0), risk_cover=L.get("_rc", 0.0),
            variations=var_b + var_r, po_committed=pod["committed"] if pod else 0.0,
            po_received=pod["received"] if pod else 0.0, po_open=pod["open"] if pod else 0,
            po_count=len(pod["n"]) if pod else 0, outstanding=outstanding,
            ctd=ctd, ctd_journal=jour.get(nid, 0.0), acc=acc, acc_pm=accr_src[nid].get("PM", 0.0),
            acc_ts=accr_src[nid].get("Timesheet", 0.0), acc_claim=accr_src[nid].get("Claim", 0.0), ctc=ctc, eac=eac, eac_top=eac_top,
            eac_cmt_style=ctd + ctc, remaining=allowance - ctd - acc, contingency=allowance - eac,
            note=note, tx_rows=ntx.get(nid, 0),
            uncommitted=_fnum(n.get("uncommitted")), fc_hours=fc_hours, pool_drawn=pool_drawn, pool_covered=covered if is_pot else 0.0,
            drawn=sum(draw.values()), _draw=draw,
        )
        a = zeros(); x = zeros(); f = zeros()
        for m, v in a_m.items():
            if m in gidx:
                a[gidx[m]] += v
        for m, v in x_m.items():
            if m in gidx:
                x[gidx[m]] += v
        for m, v in series.items():
            f[gidx[m]] += v
        row["a"], row["x"], row["f"] = a, x, f
        # checks
        row["po_status"] = ("SHORT" if ctc + 0.5 < outstanding else ("OK" if outstanding > 0 else ""))
        row["budget_status"] = _budget_status(allowance, eac, ctd + acc, tol)
        row["burn_avg"] = None
        return row

    def _budget_status(allowance, eac, spent, tol):
        if allowance <= tol and eac <= tol and spent <= tol:
            return ""
        if allowance <= tol and eac > tol:
            return "NO ALLOWANCE"
        if eac > allowance + tol:
            return "OVERRUN"
        if eac < allowance - tol:
            return "UNDERRUN"
        return "ON BUDGET"

    category_cache = {}

    def category_of(nid):
        if nid in category_cache:
            return category_cache[nid]
        n = by_id[nid]
        c = n["category"] or (category_of(n["parent_id"]) if n["parent_id"] else None)
        category_cache[nid] = c
        return c

    order = []

    def build(nid, level):
        n = by_id[nid]
        n["level"] = level
        if n["kind"] == "line":
            r = leaf_row(nid, n, False)
            r["level"] = level
            r["category"] = category_of(nid)
            rows[nid] = r
            order.append(nid)
            return r
        child_rows = [build(c, level + 1) for c in kids.get(nid, [])]
        # a group may hold its own allowance, unresolved actuals, accruals or PO: those form the (Unallocated) pot
        has_own = (nid in led and any(abs(v) > ZERO_TOL for v in led[nid].values())) or nid in act or nid in accr or nid in po \
            or n.get("unalloc_eac") is not None or nid in items
        pot = None
        # what the lines and groups beneath take from this group's unallocated allowance: a line's overspend (its EAC beyond its own
        # allowance), and what the groups below could not cover from their own pools (nearest pool first, the rest goes up a level)
        claimed = sum((0.0 if r.get("origin") == "ctc" else max(0.0, r["eac"] - r["allowance"])) if r["kind"] == "line" else r.get("_unmet", 0.0) for r in child_rows if r)
        unmet = claimed
        if has_own and level >= 2:
            # resources below that take their forecast out of this pool (nearest pool first; what is left goes up a level)
            pot = leaf_row(nid, n, True, draws=[d for d in _draws_below(nid) if d], covered=claimed)
            pot["level"] = level + 1
            pot["category"] = category_of(nid)
            avail = max(0.0, pot["allowance"] - pot["ctd"] - pot["acc"])
            unmet = max(0.0, claimed - avail)
            left = avail                            # lines whose overspend the pool covers are marked COVERED instead of OVERRUN
            for r in child_rows:
                if r and r["kind"] == "line" and r.get("origin") != "ctc":     # a CTC (Unallocated) line is never covered by the pool
                    over = max(0.0, r["eac"] - r["allowance"])
                    if over > tol and over <= left + tol:
                        r["budget_status"] = "COVERED"; r["covered_by_pool"] = over; left -= over
        g = _group_row(n, level, child_rows + ([pot] if pot else []), category_of(nid), tol)
        g["_unmet"] = unmet
        rows[nid] = g
        order.append(nid)
        if pot:
            rows[pot["id"]] = pot
            order.append(pot["id"])
        return g

    def _draws_below(nid):
        out = []
        for c in kids.get(nid, []):
            r = rows.get(c)
            if r is None:
                continue
            if r["kind"] == "line":
                out.append(r["_draw"])
            else:
                out.extend(_draws_below(c))
        return out

    def _group_row(n, level, kids_rows, cat, tol):
        g = dict(id=n["id"], node_id=n["id"], parent_id=n["parent_id"], code=n["code"], name=n["name"], kind="group",
                 gp=n["gp"], category=cat, level=level, method=None, active=n.get("active", 1), origin=n.get("origin"),
                 note="", function=None, resource_code=None, resource_kind=None, scope=None, po_no=None,
                 start=(effd(n)[0] or "")[:7] or None, end=(effd(n)[1] or "")[:7] or None,
                 start_own=n.get("start_date"), end_own=n.get("end_date"))
        for k in ("orig_budget", "orig_risk", "budget", "risk", "allowance", "variations", "cont_earmark", "risk_cover", "po_committed", "po_received",
                  "outstanding", "ctd", "ctd_journal", "acc", "acc_pm", "acc_ts", "acc_claim", "ctc", "eac", "eac_cmt_style",
                  "remaining", "contingency", "po_count", "po_open", "tx_rows", "fc_hours"):
            g[k] = sum(c.get(k, 0) or 0 for c in kids_rows)
        for k in ("a", "x", "f"):
            arr = zeros()
            for c in kids_rows:
                ca = c[k]
                for i in range(G):
                    arr[i] += ca[i]
            g[k] = arr
        g["n_lines"] = sum((1 if c["kind"] in ("line", "pot") else c.get("n_lines", 0)) for c in kids_rows)
        g["budget_status"] = _budget_status(g["allowance"], g["eac"], g["ctd"] + g["acc"], tol)
        g["po_status"] = "SHORT" if any(c.get("po_status") == "SHORT" for c in kids_rows) else ("OK" if g["outstanding"] > 0 else "")
        g["eac_top"] = None
        return g

    roots = [n["id"] for n in nodes if n["parent_id"] is None]
    for r in roots:
        build(r, 1)
    for r in rows.values():
        left = sum((r.pop("_draw", None) or {}).values())
        if left > 0.5:
            r["note"] = (r["note"] + "; " if r["note"] else "") + \
                f"{left:,.0f} is marked as taken from the pool above, but no pool forecast is left to take it from: it counts in addition"

    out_rows = []
    # depth-first presentation order with children after the group
    def emit(nid):
        out_rows.append(rows[nid])
        n = by_id.get(nid) if isinstance(nid, int) else None
        if n and n["kind"] == "group":
            for c in kids.get(nid, []):
                emit(c)
            if f"p{nid}" in rows:
                out_rows.append(rows[f"p{nid}"])
    for r in roots:
        emit(r)

    total = {k: sum(rows[r].get(k, 0) for r in roots) for k in
             ("orig_budget", "orig_risk", "budget", "risk", "allowance", "variations", "cont_earmark", "risk_cover", "po_committed", "outstanding",
              "ctd", "ctd_journal", "acc", "ctc", "eac", "eac_cmt_style", "contingency", "remaining")}
    for k in ("a", "x", "f"):
        arr = zeros()
        for r in roots:
            for i in range(G):
                arr[i] += rows[r][k][i]
        total[k] = arr

    # data not placed on any node (category missing from the CBS)
    unplaced = db.rows(con, "SELECT category, COUNT(*) n, SUM(cost) cost FROM pronto_tx WHERE project_id=? AND class IN ('actual','journal') "
                            "AND node_id IS NULL GROUP BY category", (pid,))
    return {"project_id": pid, "status_month": M, "allowance_view": "company" if company_view else "pm", "grid": grid, "rows": out_rows, "total": total,
            "unplaced": unplaced, "tolerance": tol}


# --------------------------------------------------------------------------
# Helpers for views
# --------------------------------------------------------------------------
def descendants_map(rows):
    """Map node/row id -> list of leaf rows (line or pot) below it."""
    by_parent = defaultdict(list)
    for r in rows:
        by_parent[r["parent_id"]].append(r)
    out = {}

    def walk(r):
        if r["kind"] in ("line", "pot"):
            out[r["id"]] = [r]
            return [r]
        acc = []
        for c in by_parent.get(r["node_id"], []):
            acc.extend(walk(c))
        # pots are children via parent_id == node_id; they are included above
        out[r["id"]] = acc
        return acc
    for r in rows:
        if r["parent_id"] is None:
            walk(r)
    return out


def scope_leaves(res, node_id=None):
    """Leaf rows (lines and pots) under a node; whole project when node_id is None."""
    rows = res["rows"]
    if node_id in (None, "", 0, "0", "root"):
        return [r for r in rows if r["kind"] in ("line", "pot")]
    dm = descendants_map(rows)
    key = node_id if str(node_id).startswith("p") else int(node_id)
    return dm.get(key, [])


def aggregate(leaves, keys=("allowance", "budget", "risk", "ctd", "acc", "ctc", "eac", "outstanding", "po_committed")):
    out = {k: sum(r.get(k, 0) or 0 for r in leaves) for k in keys}
    out["contingency"] = out["allowance"] - out["eac"]
    return out


# ---- cost control: base scope and variation scope of a CBS line together ---------------------------------------------
SUM_KEYS = ("orig_budget", "orig_risk", "budget", "risk", "allowance", "variations", "cont_earmark", "risk_cover", "po_committed", "po_received",
            "outstanding", "ctd", "ctd_journal", "acc", "acc_pm", "acc_ts", "acc_claim", "ctc", "eac", "eac_cmt_style", "remaining", "contingency",
            "po_count", "po_open", "tx_rows", "fc_hours", "n_lines", "risk_cost", "uncommitted", "pool_drawn", "drawn")


def merge_variation_copies(con, pid, rows, tol=1.0):
    """A variation tracked on its own copy of the CBS (variations.duplicate_cbs) shows on the original line: amounts and
    months added together, and `parts` = the base row and each variation's row for the breakdown. Parents are
    unchanged (the copies sit under the same parent). Rows not copied are returned as they are."""
    copies = {r["id"]: r for r in db.rows(con, "SELECT n.id, n.copied_from, n.variation_id, v.ref, v.title FROM cbs_node n "
                                                "LEFT JOIN variation v ON v.id=n.variation_id WHERE n.project_id=? AND n.variation_id IS NOT NULL", (pid,))}
    if not copies:
        return rows
    by_id = {str(r["id"]): r for r in rows}

    def original_key(r):
        c = copies.get(r["node_id"])
        if not c or not c["copied_from"]:
            return None
        return ("p" if r["kind"] == "pot" else "") + str(c["copied_from"])
    out = []
    for r in rows:
        k = original_key(r)
        o = by_id.get(k) if k else None
        if o is None:
            out.append(r)
            continue
        c = copies[r["node_id"]]
        if "parts" not in o:
            base = {kk: (list(vv) if isinstance(vv, list) else vv) for kk, vv in o.items() if not kk.startswith("_")}
            o["parts"] = [dict(base, part="base", label="Base scope")]
        o["parts"].append(dict({kk: vv for kk, vv in r.items() if not kk.startswith("_")}, part="variation", label=f"{c['ref']} {c['title'] or ''}".strip(),
                               variation_id=c["variation_id"], variation_ref=c["ref"]))
        for kk in SUM_KEYS:
            if isinstance(r.get(kk), (int, float)) or isinstance(o.get(kk), (int, float)):
                o[kk] = (o.get(kk) or 0) + (r.get(kk) or 0)
        for kk in ("a", "x", "f"):
            if isinstance(o.get(kk), list) and isinstance(r.get(kk), list):
                o[kk] = [p + q for p, q in zip(o[kk], r[kk])]
        if r.get("po_status") == "SHORT":
            o["po_status"] = "SHORT"
        o["budget_status"] = _status(o["allowance"], o["eac"], o["ctd"] + o["acc"], tol)
    return out


def _status(allowance, eac, spent, tol):
    """Same rule as the engine's budget status (see _compute)."""
    if allowance <= tol and eac <= tol and spent <= tol:
        return ""
    if allowance <= tol and eac > tol:
        return "NO ALLOWANCE"
    if eac > allowance + tol:
        return "OVERRUN"
    if eac < allowance - tol:
        return "UNDERRUN"
    return "ON BUDGET"


def budget_buildup(con, pid, nid, own=False):
    """How a CBS line's (or group's) budget is made up: the original estimate, transfers and other movements, then one
    entry per variation, whether it topped the line up or is tracked on the line's variation copy. own=True: only the
    node's own ledger (a group's unallocated pot), plus its copies' own."""
    from . import services
    if own:
        originals = {nid}
    else:
        originals = {i for i in services.subtree_ids(con, pid, nid)
                     if not db.scalar(con, "SELECT variation_id FROM cbs_node WHERE id=?", (i,), None)}
    copies = {r["id"] for r in db.rows(con, f"SELECT id FROM cbs_node WHERE project_id=? AND variation_id IS NOT NULL AND copied_from IN ({','.join('?' * len(originals))})",
                                       [pid, *originals])} if originals else set()
    ids = originals | copies
    q = ",".join("?" * len(ids))
    led = db.rows(con, f"SELECT l.kind, l.budget, l.risk, l.ref, l.variation_id, l.node_id, v.title FROM allowance_ledger l LEFT JOIN variation v ON v.id=l.variation_id "
                       f"WHERE l.project_id=? AND l.node_id IN ({q})", [pid, *ids])
    labels = {"estimate": "Original budget", "transfer": "Transfers in and out", "risk_release": "Risk released by the company",
              "infuse": "New funds from the company", "contingency_set": "Contingency set aside", "contingency_to_risk": "Contingency moved to risk cover"}
    order = list(labels)
    rows = {}
    for e in led:
        if e["kind"] == "variation" or e["variation_id"]:
            k = ("variation", e["variation_id"] or e["ref"])
            r = rows.setdefault(k, dict(kind="variation", label=f"{e['ref'] or ''} {e['title'] or ''}".strip(), ref=e["ref"], variation_id=e["variation_id"],
                                        budget=0.0, risk=0.0, tracked=set()))
            r["tracked"].add("copy" if e["node_id"] in copies else "topup")
        else:
            k = (e["kind"], None)
            r = rows.setdefault(k, dict(kind=e["kind"], label=labels.get(e["kind"], e["kind"]), budget=0.0, risk=0.0))
        r["budget"] += e["budget"] or 0
        r["risk"] += e["risk"] or 0
    out = sorted((r for r in rows.values() if r["kind"] != "variation"), key=lambda r: order.index(r["kind"]) if r["kind"] in order else 99)
    out = [r for r in out if r["kind"] == "estimate" or abs(r["budget"]) > 0.005 or abs(r["risk"]) > 0.005]
    if not any(r["kind"] == "estimate" for r in out):
        out.insert(0, dict(kind="estimate", label="Original budget", budget=0.0, risk=0.0))
    for r in sorted((r for r in rows.values() if r["kind"] == "variation"), key=lambda r: r.get("ref") or ""):
        r["tracked"] = "tracked on its own CBS copy" if r["tracked"] == {"copy"} else ("topped up this line" if r["tracked"] == {"topup"} else "topped up and tracked on a copy")
        out.append(r)
    return dict(rows=out, total=dict(budget=sum(r["budget"] for r in out), risk=sum(r["risk"] for r in out)))
