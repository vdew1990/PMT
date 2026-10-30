"""Ground-up forecast detail: day grids, payment milestones and rosters, priced from the rates on file.

Three item spreads extend the ground-up method (engine.py handles Lump, Linear, Recurring and Manual):

Calendar    one resource on one CBS line, a value per day. The item's basis says what the value is: hours
            (x rate, overtime above the normal hours if the rate has it), units (days, nights, ea x rate) or dollars.
Milestones  the item value (qty x rate x share, typically the PO value) split over payment milestones, each with a
            % and the month the supplier is expected to reach it. Invoiced milestones are in actuals, so they leave
            the forecast; a milestone still open in a past month rolls into the status month (it has slipped).
Roster      a pattern (10:4 = ten days on, four off) from a start date for a number of swings, x headcount x hours a
            shift, priced from the supplier's schedule of rates for the role (normal time, overtime, daily allowance).

Forecast days count from the day after the project status date; earlier days belong to timesheets and accruals.
"""
from collections import defaultdict
from datetime import date, timedelta

from . import db

DAY_SPREADS = ("Calendar", "Roster")
DETAIL_SPREADS = ("Calendar", "Milestones", "Roster")


def _f(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


class Ctx:
    """Everything the detail spreads need for one project, loaded once per computation."""

    def __init__(self, con, pid, p=None):
        p = p or db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
        self.pid = pid
        sd = db.to_date(p.get("status_date")) or date.today()
        self.cutoff = sd                      # forecast days are strictly after this
        self.M = sd.strftime("%Y-%m")
        self.holidays = {r["day"]: r["name"] for r in db.rows(con, "SELECT day, name FROM holiday WHERE project_id=?", (pid,))}
        self.resources = {r["id"]: r for r in db.rows(con, "SELECT * FROM resource WHERE project_id=?", (pid,))}
        self.res_by_code = {(r["kind"], r["code"]): r for r in self.resources.values()}
        self.rate_card = db.rows(con, "SELECT * FROM rate_card WHERE project_id=?", (pid,))
        self.srates = defaultdict(list)
        for r in db.rows(con, "SELECT * FROM supplier_rate WHERE project_id=? ORDER BY COALESCE(valid_from,''), id", (pid,)):
            self.srates[r["resource_id"]].append(r)
        self.days = defaultdict(dict)
        self.days_ot = defaultdict(dict)   # overtime part of a day's hours, where it was typed as NT + OT
        # highest id wins when two people filled the same cell on their own copies
        for r in con.execute("SELECT item_id, day, qty, ot FROM forecast_day WHERE project_id=? ORDER BY id", (pid,)):
            if r["qty"] is None:
                self.days[r["item_id"]].pop(r["day"], None)
                self.days_ot[r["item_id"]].pop(r["day"], None)
            else:
                self.days[r["item_id"]][r["day"]] = r["qty"]
                if r["ot"] is not None:
                    self.days_ot[r["item_id"]][r["day"]] = r["ot"]
                else:
                    self.days_ot[r["item_id"]].pop(r["day"], None)
        self.ms = defaultdict(list)
        for r in db.rows(con, "SELECT * FROM forecast_ms WHERE project_id=? ORDER BY seq, id", (pid,)):
            self.ms[r["item_id"]].append(r)


def load_ctx(con, pid, p=None):
    return Ctx(con, pid, p)


# ---------------------------------------------------------------------------------------------------------------
# Rates
# ---------------------------------------------------------------------------------------------------------------
def rate_for(ctx, item):
    """{rate, ot_rate, nt_hours, allowance, unit, source} for an item: typed, or looked up when rate_mode is auto."""
    typed = item.get("rate")
    if item.get("rate_mode") != "auto" and typed not in (None, ""):
        return dict(rate=_f(typed), ot_rate=None, nt_hours=None, allowance=None, unit="hr", source="typed on the item")
    res = ctx.resources.get(item.get("resource_id"))
    if res and res["kind"] == "employee":
        if res.get("cost_rate"):
            return dict(rate=_f(res["cost_rate"]), ot_rate=None, nt_hours=None, allowance=None, unit="hr", source=f"{res['name'] or res['code']} cost rate")
        wrc = (res.get("work_rate_code") or "").strip().upper()
        fn = (res.get("function") or "").strip().lower()
        for rc in ctx.rate_card:
            if (wrc and (rc.get("work_rate_code") or "").strip().upper() == wrc) or (fn and (rc.get("role") or "").strip().lower() == fn):
                return dict(rate=_f(rc["cost_rate"]), ot_rate=None, nt_hours=None, allowance=None, unit="hr", source=f"rate card {rc['role']}")
    if not res and item.get("role"):  # a pool forecast by role, before anyone is named: the rate card for the role
        role = item["role"].strip().lower()
        for rc in ctx.rate_card:
            if (rc.get("role") or "").strip().lower() == role:
                return dict(rate=_f(rc["cost_rate"]), ot_rate=None, nt_hours=None, allowance=None, unit="hr", source=f"rate card {rc['role']}")
    if res and res["kind"] == "supplier":
        rates = ctx.srates.get(res["id"], [])
        role = (item.get("role") or "").strip().lower()
        pick = [r for r in rates if (r["role"] or "").strip().lower() == role] if role else rates[:1]
        if pick:
            r = pick[-1]  # latest valid_from
            return dict(rate=_f(r["rate"]), ot_rate=r.get("ot_rate"), nt_hours=r.get("nt_hours"), allowance=r.get("allowance"),
                        unit=r.get("unit") or "hr", source=f"{res['name'] or res['code']} rates, {r['role']}")
    return dict(rate=_f(typed), ot_rate=None, nt_hours=None, allowance=None, unit="hr", source="typed on the item" if typed else "no rate found")


def split_cost(total, ot, r, heads=1.0):
    """Cost of a day typed as normal time + overtime: `total` hours of which `ot` are overtime (for `heads` people
    together), plus each person's daily allowance. Overtime uses the OT rate (normal rate if the rates have none)."""
    if total <= 0:
        return 0.0
    heads = heads or 1.0
    if (r.get("unit") or "hr") in ("day", "shift"):
        return (_f(r["rate"]) + _f(r.get("allowance"))) * heads
    ot = min(max(0.0, _f(ot)), total)
    return (total - ot) * _f(r["rate"]) + ot * (_f(r.get("ot_rate")) or _f(r["rate"])) + _f(r.get("allowance")) * heads


def auto_ot(hours, r):
    """Overtime hours of one person's day when it was not typed: the hours above the normal hours a day."""
    nt = r.get("nt_hours")
    return max(0.0, hours - nt) if nt and r.get("ot_rate") and (r.get("unit") or "hr") not in ("day", "shift") else 0.0


def labour_cost(hours, r, heads=1.0):
    """Cost of `hours` a person a day for `heads` people, with overtime and daily allowance if the rate has them."""
    if hours <= 0 or heads <= 0:
        return 0.0
    if (r.get("unit") or "hr") in ("day", "shift"):
        per = _f(r["rate"])
    else:
        nt = r.get("nt_hours")
        if nt and r.get("ot_rate"):
            per = min(hours, nt) * _f(r["rate"]) + max(0.0, hours - nt) * _f(r["ot_rate"])
        else:
            per = hours * _f(r["rate"])
    per += _f(r.get("allowance"))
    return per * heads


# ---------------------------------------------------------------------------------------------------------------
# Day values
# ---------------------------------------------------------------------------------------------------------------
def parse_pattern(p):
    p = (p or "").strip().upper()
    if p in ("DAILY", "WEEKDAYS"):
        return p, None
    if ":" in p:
        a, b = p.split(":", 1)
        try:
            on, off = int(a), int(b)
            if on > 0 and off >= 0:
                return "CYCLE", (on, off)
        except ValueError:
            pass
    raise ValueError(f"Roster pattern '{p}' not understood. Use days on:days off such as 10:4, or WEEKDAYS or DAILY.")


def roster_days(item, holidays=()):
    """Working days of a roster: pattern from the start date for `swings` cycles (or weeks), stopping at the end date."""
    start = db.to_date(item.get("start_date"))
    if not start:
        return []
    end = db.to_date(item.get("end_date"))
    swings = int(item.get("swings") or 0)
    kind, cyc = parse_pattern(item.get("pattern") or "WEEKDAYS")
    out = []
    if kind == "CYCLE":
        on, off = cyc
        n = swings or (10_000 if end else 1)
        for s in range(n):
            base = start + timedelta(days=s * (on + off))
            if end and base > end:
                break
            for i in range(on):
                d = base + timedelta(days=i)
                if end and d > end:
                    break
                out.append(d)
    else:
        last = end or (start + timedelta(days=7 * (swings or 1) - 1))
        d = start
        while d <= last and len(out) < 4000:
            if kind == "DAILY" or d.weekday() < 5:
                out.append(d)
            d += timedelta(days=1)
    if item.get("skip_holidays"):
        out = [d for d in out if d.isoformat() not in holidays]
    return out


def day_values(item, ctx):
    """day (ISO) -> (hours, cost) for Calendar and Roster items, past and future."""
    sp = item.get("spread")
    out = {}
    if sp == "Calendar":
        r = rate_for(ctx, item)
        basis = item.get("basis") or "hours"
        typed_ot = ctx.days_ot.get(item.get("id"), {})
        for d, q in ctx.days.get(item.get("id"), {}).items():
            q = _f(q)
            if basis == "people":  # headcount that day, each working the item's hours a shift
                hd = _f(item.get("hours_day")) or _f(r.get("nt_hours")) or 10.0
                out[d] = (q * hd, split_cost(q * hd, typed_ot[d], r, q) if d in typed_ot else labour_cost(hd, r, q))
            elif basis == "dollars":
                out[d] = (0.0, q)
            elif basis == "units":
                out[d] = (0.0, q * _f(r["rate"]))
            else:
                out[d] = (q, split_cost(q, typed_ot[d], r) if d in typed_ot else labour_cost(q, r))
    elif sp == "Roster":
        r = rate_for(ctx, item)
        heads = _f(item.get("headcount")) or 1.0
        hrs = _f(item.get("hours_day")) or _f(r.get("nt_hours")) or 10.0
        for d in roster_days(item, ctx.holidays):
            out[d.isoformat()] = (hrs * heads, labour_cost(hrs, r, heads))
    return out


def day_ot(item, ctx):
    """day -> overtime hours in a Calendar or Roster item's day: as typed (NT + OT), else worked out from the rates."""
    out = {}
    r = rate_for(ctx, item)
    if item.get("spread") == "Calendar":
        basis = item.get("basis") or "hours"
        typed = ctx.days_ot.get(item.get("id"), {})
        hd = _f(item.get("hours_day")) or _f(r.get("nt_hours")) or 10.0
        for d, q in ctx.days.get(item.get("id"), {}).items():
            if d in typed:
                out[d] = _f(typed[d])
            elif basis == "people":
                out[d] = _f(q) * auto_ot(hd, r)
            elif basis == "hours":
                out[d] = auto_ot(_f(q), r)
    elif item.get("spread") == "Roster":
        heads = _f(item.get("headcount")) or 1.0
        hrs = _f(item.get("hours_day")) or _f(r.get("nt_hours")) or 10.0
        for d in roster_days(item, ctx.holidays):
            out[d.isoformat()] = heads * auto_ot(hrs, r)
    return out


def milestone_series(item, ctx, notes=None):
    total = _f(item.get("qty")) * _f(item.get("rate")) * (1 if item.get("pct") in (None, "") else _f(item.get("pct")))
    out = defaultdict(float)
    ms = ctx.ms.get(item.get("id"), [])
    if not ms:
        m = db.month_of(item.get("start_date")) or ctx.M
        out[max(m, ctx.M)] += total
        return out
    for x in ms:
        if x.get("status") == "invoiced":
            continue
        m = (x.get("month") or "")[:7] or ctx.M
        if m < ctx.M:
            if notes is not None:
                notes.append(f"{x.get('name') or 'Milestone'} was due {m} and is not invoiced: moved to {ctx.M}")
            m = ctx.M
        out[m] += total * _f(x.get("pct"))
    return out


def series(item, ctx, notes=None):
    """month -> forecast amount for a detail spread. Day spreads count only days after the status date."""
    sp = item.get("spread")
    if sp == "Milestones":
        return milestone_series(item, ctx, notes)
    out = defaultdict(float)
    cut = ctx.cutoff.isoformat()
    for d, (_, cost) in day_values(item, ctx).items():
        if d > cut:
            out[d[:7]] += cost
    return out


def forecast_hours(item, ctx):
    cut = ctx.cutoff.isoformat()
    return sum(h for d, (h, _) in day_values(item, ctx).items() if d > cut)


def preview(con, pid, item, days=None, ms=None):
    """What an item (saved or not) would forecast: by month, total, hours, rate used."""
    ctx = load_ctx(con, pid)
    iid = item.get("id") or -1
    item = dict(item, id=iid)
    if days is not None:
        ctx.days[iid] = {d: q for d, q in days.items() if q not in (None, "")}
    if ms is not None:
        ctx.ms[iid] = ms
    notes = []
    if item.get("spread") in DETAIL_SPREADS:
        ser = series(item, ctx, notes)
    else:
        from . import engine
        ser = engine.item_series(item, None, ctx)
    dv = day_values(item, ctx) if item.get("spread") in DAY_SPREADS else {}
    return dict(months={m: v for m, v in sorted(ser.items())}, total=sum(ser.values()), hours=forecast_hours(item, ctx) if dv else 0.0,
                days=len([d for d in dv if d > ctx.cutoff.isoformat()]), all_days=sorted(dv), rate=rate_for(ctx, item) if item.get("spread") != "Milestones" else None,
                notes=notes, status_date=ctx.cutoff.isoformat())


# ---------------------------------------------------------------------------------------------------------------
# Labour calendar: timesheet, accrued and forecast hours per resource per day
# ---------------------------------------------------------------------------------------------------------------
def day_state(v):
    """The workbook's colour logic for one person-day (Cost Control sheet, at hours level):
    actual  posted timesheet with no accrual, or an accrual it matched exactly          (pink)
    hybrid  posted timesheet and an accrual that differs from it on the same day          (purple)
    accrual hours accrued, or a timesheet entered but not yet posted                    (light blue)
    v: a posted hours, t unposted hours, acc hours accrued (any status), x accrued hours still counting."""
    posted, unposted, acc = v.get("a", 0), v.get("t", 0), v.get("acc", 0)
    if v.get("inv_diff"):
        return "hybrid"
    if posted > 0.005:
        return "hybrid" if acc > 0.005 and abs(acc - (posted + unposted)) > 0.01 else "actual"
    if unposted > 0.005 or acc > 0.005:
        return "accrual"
    return ""


def calendar(con, pid, start, ndays=42, kind=None, node_ids=None):
    ctx = load_ctx(con, pid)
    d0 = db.to_date(start) or (ctx.cutoff - timedelta(days=ctx.cutoff.weekday() + 14))
    d1 = d0 + timedelta(days=int(ndays) - 1)
    a, b = d0.isoformat(), d1.isoformat()
    nodes = {r["id"]: r for r in db.rows(con, "SELECT id, code, name FROM cbs_node WHERE project_id=?", (pid,))}
    rows = {}

    def row(res_id, code, name, rkind, role=None, function=None):
        key = f"{res_id or code}|{(role or '').lower()}"
        r = rows.get(key)
        if r is None:
            r = rows[key] = dict(key=key, resource_id=res_id, code=code, name=name, kind=rkind, role=role, function=function,
                                 d=defaultdict(lambda: dict(a=0.0, t=0.0, x=0.0, acc=0.0, f=0.0, fc=0.0)), lines={}, items=[], accruals={})
        return r

    def in_scope(nid):
        return node_ids is None or nid in node_ids

    # forecast items with a resource
    for it in db.rows(con, "SELECT * FROM forecast_item WHERE project_id=? AND spread IN ('Calendar','Roster') "
                           "AND (resource_id IS NOT NULL OR COALESCE(role,'')!='')", (pid,)):
        if not in_scope(it["node_id"]):
            continue
        res = ctx.resources.get(it["resource_id"])
        if res is None:  # a pool forecast by role, nobody named yet
            if kind == "supplier":
                continue
            r = row(None, f"pool:{it['node_id']}", f"{it['role']} (unallocated)", "pool", it["role"], None)
        else:
            if kind and res["kind"] != kind:
                continue
            role = it.get("role") if res["kind"] == "supplier" else None
            r = row(res["id"], res["code"], res["name"], res["kind"], role, res.get("function"))
        rt = rate_for(ctx, it)
        r["items"].append(dict(item_id=it["id"], node_id=it["node_id"], code=nodes.get(it["node_id"], {}).get("code"), spread=it["spread"],
                               basis=it.get("basis") or "hours", scope=it.get("scope"), rate=rt["rate"], headcount=it.get("headcount"),
                               hours_day=it.get("hours_day") or rt.get("nt_hours") or 10,
                               from_pool=it.get("from_pool")))
        r["lines"][it["node_id"]] = nodes.get(it["node_id"], {}).get("code")
        ots = day_ot(it, ctx)
        for d, (hrs, cost) in day_values(it, ctx).items():
            if a <= d <= b:
                r["d"][d]["f"] += hrs
                r["d"][d]["fc"] += cost
                r["d"][d]["f_ot"] = r["d"][d].get("f_ot", 0.0) + ots.get(d, 0.0)
    # timesheets from Pronto
    for t in db.rows(con, "SELECT resource_code, MAX(name) name, date_worked, posted, node_id, SUM(hours) h FROM pronto_labour "
                          "WHERE project_id=? AND date_worked BETWEEN ? AND ? GROUP BY resource_code, date_worked, posted, node_id", (pid, a, b)):
        if not in_scope(t["node_id"]):
            continue
        res = ctx.res_by_code.get(("employee", t["resource_code"]))
        if kind and kind != "employee":
            continue
        r = row(res["id"] if res else None, t["resource_code"], (res or {}).get("name") or t["name"], "employee", None, (res or {}).get("function"))
        r["d"][t["date_worked"]]["a" if t["posted"] else "t"] += _f(t["h"])
        if t["node_id"] in nodes:
            r["lines"][t["node_id"]] = nodes[t["node_id"]]["code"]
    # schedule-of-rates subcontractor timesheets (uploaded from the template): what the subby says was worked
    if kind in (None, "supplier"):
        for t in db.rows(con, "SELECT resource_id, role, day, node_id, SUM(hours) h, COUNT(DISTINCT worker) w FROM sub_timesheet WHERE project_id=? AND day BETWEEN ? AND ? "
                              "GROUP BY resource_id, role, day, node_id", (pid, a, b)):
            if node_ids is not None and t["node_id"] not in node_ids:
                continue
            res = ctx.resources.get(t["resource_id"])
            if not res:
                continue
            r = row(res["id"], res["code"], res["name"], "supplier", t["role"], res.get("function"))
            r["sub"] = True
            r["d"][t["day"]]["t"] += _f(t["h"])
            r["d"][t["day"]]["w"] = r["d"][t["day"]].get("w", 0) + (t["w"] or 0)
            if t["node_id"] in nodes:
                r["lines"][t["node_id"]] = nodes[t["node_id"]]["code"]
    # hour accruals
    for x in db.rows(con, "SELECT * FROM accrual WHERE project_id=? AND hours IS NOT NULL AND day BETWEEN ? AND ? AND status IN ('open','partial','matched','investigate')", (pid, a, b)):
        if not in_scope(x["node_id"]):
            continue
        res = ctx.resources.get(x["resource_id"])
        if not res or (kind and res["kind"] != kind):
            continue
        role = (x.get("role") or "") if res["kind"] == "supplier" else ""
        r = (next((y for y in rows.values() if y["resource_id"] == res["id"] and (y["role"] or "").lower() == role.lower()), None)
             or next((y for y in rows.values() if y["resource_id"] == res["id"]), None)
             or row(res["id"], res["code"], res["name"], res["kind"], role or None, res.get("function")))
        cell = r["d"][x["day"]]
        if res["kind"] == "supplier" and x["status"] in ("matched", "investigate"):
            # a subcontractor's hours become actual when their invoice lands (matched on the invoice reference)
            cell["a"] += _f(x["hours"])
            cell["inv"] = x["inv_ref"]
            if x["status"] == "investigate":
                cell["inv_diff"] = True  # the invoice differs from the accruals it covers: purple
            r["accruals"].setdefault(x["day"], []).append(dict(id=x["id"], node_id=x["node_id"], hours=x["hours"], amount=x["amount"], status=x["status"]))
            continue
        # acc: hours accrued (whatever happened since); x: the part still counting (no timesheet has covered it)
        cell["acc"] = cell.get("acc", 0.0) + _f(x["hours"])
        if x["status"] in ("open", "partial"):
            cell["acc_ot"] = cell.get("acc_ot", 0.0) + _f(x.get("ot_hours"))
        if x["status"] == "open":
            cell["x"] += _f(x["hours"])
        elif x["status"] == "partial":
            cell["x"] += max(0.0, _f(x["hours"]) - _f(x["matched_amount"]) / (_f(x["rate"]) or 1))
        r["accruals"].setdefault(x["day"], []).append(dict(id=x["id"], node_id=x["node_id"], hours=x["hours"], amount=x["amount"], status=x["status"]))
        if x["node_id"] in nodes:
            r["lines"][x["node_id"]] = nodes[x["node_id"]]["code"]
    out = []
    for r in sorted(rows.values(), key=lambda r: (r["kind"], r["name"] or r["code"] or "", r["role"] or "")):
        for v in r["d"].values():
            v["st"] = day_state(v)
        r["d"] = {k: v for k, v in r["d"].items()}
        r["lines"] = [dict(node_id=k, code=v) for k, v in r["lines"].items()]
        r["tot"] = {k: sum(v[k] for v in r["d"].values()) for k in ("a", "t", "x", "f", "fc")}
        r["from_pool"] = any(i.get("from_pool") for i in r["items"])
        out.append(r)
    hol = {d: n for d, n in ctx.holidays.items() if a <= d <= b}
    return dict(start=a, end=b, status_date=ctx.cutoff.isoformat(), status_month=ctx.M, holidays=hol, rows=out)


# ---------------------------------------------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------------------------------------------
def _nt_ot(v):
    """A typed day: a number of hours, or {nt, ot}. Returns (total, ot or None)."""
    if isinstance(v, dict):
        nt, ot = _f(v.get("nt")), _f(v.get("ot"))
        total = _f(v["qty"]) if v.get("qty") not in (None, "") else nt + ot   # qty: people a day for a people calendar
        return (total or None), (ot if v.get("ot") not in (None, "") else None)
    return (None if v in (None, "") else _f(v)), None


def save_days(con, pid, item_id, days):
    """Set day values on a Calendar item: a number, or {nt, ot} for normal time and overtime. None, '' or 0 clears a
    day. Existing cells are updated in place (history)."""
    have = {}
    for r in con.execute("SELECT id, day FROM forecast_day WHERE item_id=? ORDER BY id", (item_id,)):
        have.setdefault(r["day"], []).append(r["id"])
    n = 0
    for d, v in days.items():
        d = db.iso(d)
        if not d:
            continue
        q, ot = _nt_ot(v)
        ids = have.get(d, [])
        if q is None or q == 0:
            for i in ids:
                con.execute("DELETE FROM forecast_day WHERE id=?", (i,))
        elif ids:
            for i in ids[:-1]:
                con.execute("DELETE FROM forecast_day WHERE id=?", (i,))
            con.execute("UPDATE forecast_day SET qty=?, ot=? WHERE id=?", (q, ot, ids[-1]))
        else:
            db.insert(con, "forecast_day", dict(project_id=pid, item_id=item_id, day=d, qty=q, ot=ot))
        n += 1
    return n


def save_milestones(con, pid, item_id, rows):
    keep = set()
    for i, r in enumerate(rows):
        d = dict(seq=r.get("seq", i), name=r.get("name"), pct=_f(r.get("pct")), month=(r.get("month") or "")[:7] or None,
                 status=r.get("status") or "forecast", note=r.get("note"))
        if r.get("id"):
            db.update(con, "forecast_ms", int(r["id"]), d)
            keep.add(int(r["id"]))
        else:
            keep.add(db.insert(con, "forecast_ms", dict(project_id=pid, item_id=item_id, **d)))
    for (mid,) in con.execute("SELECT id FROM forecast_ms WHERE item_id=?", (item_id,)).fetchall():
        if mid not in keep:
            con.execute("DELETE FROM forecast_ms WHERE id=?", (mid,))


def save_hour_accruals(con, pid, resource_id, node_id, days, rate=None, role=None, reason=None, note=None, heads=1.0):
    """Accrue hours a day for a resource on a line. One accrual per day; 0 or blank removes that day's accrual.
    `heads` > 1 (a number, or {day: number}) when the hours are a crew's total: overtime is worked out per person."""
    ctx = load_ctx(con, pid)
    res = ctx.resources.get(resource_id)
    if not res:
        raise ValueError("Choose a resource")
    r = rate_for(ctx, dict(resource_id=resource_id, role=role, rate=rate, rate_mode=None if rate not in (None, "") else "auto"))
    role_key = (role or "") if res["kind"] == "supplier" else ""
    if not _f(r["rate"]) and any(_nt_ot(v)[0] for v in days.values()):
        raise ValueError(f"No cost rate found for {res['name'] or res['code']}{' (' + role + ')' if role else ''}, so the hours cannot be priced. "
                         "Add a cost rate on Resources and rates (employee rate, rate card or supplier rates), then accrue again.")
    n = 0
    for d, raw in days.items():
        d = db.iso(d)
        hrs, ot = _nt_ot(raw)
        # the accrual on that day, whatever has happened to it since (a timesheet may have covered part of it)
        ex = db.rows(con, "SELECT id FROM accrual WHERE project_id=? AND resource_id=? AND node_id=? AND day=? AND hours IS NOT NULL AND status!='cancelled' "
                          "AND COALESCE(role,'')=? ORDER BY id", (pid, resource_id, node_id, d, role_key))
        if hrs in (None, "") or _f(hrs) == 0:
            for x in ex:
                con.execute("DELETE FROM accrual WHERE id=?", (x["id"],))
            continue
        hd = (_f(heads.get(d) or heads.get(str(d))) if isinstance(heads, dict) else _f(heads)) or 1.0
        cost = split_cost(_f(hrs), ot, r, hd) if ot is not None else labour_cost(_f(hrs) / hd, r, hd)
        vals = dict(hours=_f(hrs), ot_hours=ot, rate=r["rate"], amount=round(cost, 2), month=d[:7])
        if ex:
            for x in ex[:-1]:
                con.execute("DELETE FROM accrual WHERE id=?", (x["id"],))
            db.update(con, "accrual", ex[-1]["id"], dict(vals, status="open", matched_amount=None, matched_date=None))  # re-matched below
        else:
            db.insert(con, "accrual", dict(project_id=pid, node_id=node_id, resource_id=resource_id, day=d, source="Hours", role=role_key or None,
                                           reason=reason or "Timesheets not yet posted", note=note, status="open", **vals))
        n += 1
    return n


def accrue_past(con, pid, item_id):
    """Turn forecast hours on days up to the status date into hour accruals where no timesheet has landed yet."""
    ctx = load_ctx(con, pid)
    it = db.one(con, "SELECT * FROM forecast_item WHERE id=? AND project_id=?", (item_id, pid))
    if not it or it["spread"] not in DAY_SPREADS or not it.get("resource_id"):
        raise ValueError("Only Calendar or Roster items with a resource can be accrued from the calendar")
    res = ctx.resources[it["resource_id"]]
    cut = ctx.cutoff.isoformat()
    landed = {r["date_worked"] for r in con.execute("SELECT DISTINCT date_worked FROM pronto_labour WHERE project_id=? AND resource_code=?", (pid, res["code"]))}
    have = {r["day"] for r in con.execute("SELECT day FROM accrual WHERE project_id=? AND resource_id=? AND hours IS NOT NULL AND status='open'", (pid, res["id"]))}
    todo = {d: h for d, (h, _) in day_values(it, ctx).items() if d <= cut and h > 0 and d not in landed and d not in have}
    rate = None if it.get("rate_mode") == "auto" else it.get("rate")
    heads = (_f(it.get("headcount")) or 1.0) if it["spread"] == "Roster" else 1.0  # a roster accrues the crew's hours per day
    return save_hour_accruals(con, pid, res["id"], it["node_id"], todo, rate=rate, role=it.get("role"), heads=heads,
                              reason="Work done, invoice not yet received" if res["kind"] == "supplier" else "Timesheets not yet posted",
                              note=f"From forecast item {it.get('scope') or it['id']}")
