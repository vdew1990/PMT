"""The Ground-Up register: every forecast item of the project in one list, grouped the way the PM chooses (H1 > H2 > H3), not in CBS order.

An item is still a forecast item on a CBS line (it rolls up to Cost control by CBS line and month as before); H1, H2 and H3 are only labels for
looking at them together, for example everything for one person on site (LAHA, vehicle, labour). Nothing here changes a figure.
An item counts in the forecast only while its line's method is GROUND-UP; `live` says whether it does.
"""
from collections import defaultdict

from . import db, engine, forecast
from .services import Problem

LEVELS = ("h1", "h2", "h3")


def _clean(v):
    v = (v or "").strip() if isinstance(v, str) else v
    return v or None


def _shown(start, end, start_own, end_own):
    """The start and end the register shows, never an end before the start. When an inherited date contradicts the
    item's own date (an own start after the inherited end, or an own end before the inherited start), the inherited
    one is left blank rather than shown; if both are the item's own, the end is left blank (start_own and end_own still
    carry them). Display only: the months and totals are not touched. Which window should win when an item's own
    dates fall outside the line window is open question Q14 for Vincent."""
    if start and end and end < start:
        if end_own and not start_own:
            start = None
        else:
            end = None
    return dict(start=start, end=end)


def register(con, pid):
    res = engine.compute(con, pid)
    grid, M = res["grid"], res["status_month"]
    ctx = forecast.load_ctx(con, pid)
    manual = defaultdict(lambda: defaultdict(dict))
    for r in db.rows(con, "SELECT node_id, item_id, month, amount FROM forecast_manual WHERE project_id=? AND item_id IS NOT NULL", (pid,)):
        manual[r["node_id"]][r["item_id"]][r["month"]] = r["amount"]
    rows = db.rows(con, "SELECT i.*, n.code node_code, n.name node_name, n.kind node_kind, n.method node_method, n.unalloc_method, n.start_date node_start, n.end_date node_end, "
                        "COALESCE(r.name, r.code, rn.name, rn.code) who, COALESCE(r.kind, rn.kind) who_kind "
                        "FROM forecast_item i JOIN cbs_node n ON n.id=i.node_id LEFT JOIN resource r ON r.id=i.resource_id LEFT JOIN resource rn ON rn.id=n.resource_id "
                        "WHERE i.project_id=? ORDER BY i.id", (pid,))
    # the effective window Cost control uses for each line and pool: its own start/end, else the nearest group's, else the project's
    win = {(r["node_id"], r["kind"] == "pot"): (r["start"], r["end"]) for r in res["rows"] if r.get("kind") in ("line", "pot")}
    items = []
    for it in rows:
        s = dict(it)
        w = win.get((it["node_id"], it["node_kind"] != "line"))
        if w:                                                # an item with no dates of its own follows that window, as in engine.compute
            s["start_date"] = it["start_date"] or (w[0] + "-01")
            s["end_date"] = it["end_date"] or (db.month_end(w[1]) if it.get("spread") != "Roster" or not it.get("swings") else None)
        else:
            s["start_date"] = it["start_date"] or it["node_start"] or (M + "-01")
            s["end_date"] = it["end_date"] or it["node_end"] or (grid[-1] + "-28" if grid else None)
        try:
            ser = engine.item_series(s, manual[it["node_id"]].get(it["id"]), ctx, [])
        except Exception:                                    # an item that cannot be worked out shows with no months, not a broken page
            ser = {}
        months = {m: round(v, 2) for m, v in ser.items() if m >= M and m in grid and abs(v) > 0.005}
        method = it["node_method"] if it["node_kind"] == "line" else it["unalloc_method"]
        items.append(dict(id=it["id"], node_id=it["node_id"], code=it["node_code"], line=it["node_name"], pool=it["node_kind"] != "line", who=it["who"], who_kind=it["who_kind"],
                          role=it["role"], scope=it["scope"], spread=it["spread"], **_shown(s["start_date"], s["end_date"], it["start_date"], it["end_date"]),
                          start_own=it["start_date"], end_own=it["end_date"], note=it["note"],
                          h1=it["h1"], h2=it["h2"], h3=it["h3"], from_pool=bool(it["from_pool"]), method=method or "AT-BUDGET", live=method == "GROUND-UP",
                          months=months, total=round(sum(months.values()), 2)))
    names = {k: sorted({i[k] for i in items if i[k]}) for k in LEVELS}
    return dict(month=M, grid=[m for m in grid if m >= M], items=items, names=names, total=round(sum(i["total"] for i in items if i["live"]), 2),
                not_live=sum(1 for i in items if not i["live"]), ungrouped=sum(1 for i in items if not i["h1"]))


def group(con, pid, ids, h1=None, h2=None, h3=None, clear_below=True):
    """Put items under H1 > H2 > H3. A blank level clears it; a blank H1 clears the lot (a lower level cannot exist without the one above)."""
    vals = [_clean(h1), _clean(h2), _clean(h3)]
    if not vals[0]:
        vals = [None, None, None]
    elif not vals[1]:
        vals[2] = None
    n = 0
    for iid in ids:
        if not db.one(con, "SELECT id FROM forecast_item WHERE id=? AND project_id=?", (int(iid), pid)):
            raise Problem("An item in the selection does not belong to this project")
        db.update(con, "forecast_item", int(iid), dict(zip(LEVELS, vals)))
        n += 1
    return n


def rename(con, pid, level, old, new):
    """Rename a group label everywhere it is used (H1, H2 or H3)."""
    if level not in LEVELS:
        raise Problem("Level must be h1, h2 or h3")
    new = _clean(new)
    if not new:
        raise Problem("Give the group a name")
    cur = con.execute(f"UPDATE forecast_item SET {level}=? WHERE project_id=? AND {level}=?", (new, pid, old))
    return cur.rowcount
