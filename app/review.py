"""Month-end review: for every CBS line, what was forecast to land this month against what landed (actual + accrued),
so the PM can walk the lines and decide: it happened, so accrue what has no invoice yet; or it slipped, so reforecast.

"Planned" is the month as forecast at the last month-end close (the newest month-end snapshot before this month).
"""
import json

from . import activity, db, engine

DECISIONS = {
    "as-planned": "As planned",
    "accrued": "Accrued",
    "delayed": "Slipped, reforecast",
    "partial": "Part accrued, part slipped",
    "not-needed": "No longer needed",
    "noted": "Reviewed, no change",
}


def planned(con, pid, M):
    """{node_ref: amount planned for month M} from the newest month-end snapshot taken before M, and its label."""
    s = db.one(con, "SELECT * FROM snapshot WHERE project_id=? AND kind='eom' AND period<? ORDER BY period DESC, id DESC LIMIT 1", (pid, M))
    if not s:
        return None, {}
    months = (json.loads(s["curve_json"] or "{}") or {}).get("months") or []
    if M not in months:
        return s, {}
    i = months.index(M)
    out = {}
    for r in con.execute("SELECT node_ref, months_json FROM snapshot_line WHERE snapshot_id=?", (s["id"],)):
        try:
            ser = json.loads(r["months_json"] or "[]")
        except ValueError:
            continue
        if i < len(ser):
            out[r["node_ref"]] = ser[i] or 0.0
    return s, out


def month_review(con, pid, month=None):
    res = engine.compute(con, pid)
    grid, M = res["grid"], month or res["status_month"]
    if M not in grid:
        raise ValueError(f"{M} is outside the project months")
    i = grid.index(M)
    snap, plan = planned(con, pid, M)
    dec = {r["node_ref"]: r for r in db.rows(con, "SELECT * FROM month_review WHERE project_id=? AND month=?", (pid, M))}
    st = activity.stamps(con, "month_review", [r["id"] for r in dec.values()])
    subs = {}
    for s in db.rows(con, "SELECT id, node_id, name FROM subcontract WHERE project_id=?", (pid,)):
        subs.setdefault(s["node_id"], s)
    items = {r["node_id"]: r["n"] for r in con.execute("SELECT node_id, COUNT(*) n FROM forecast_item WHERE project_id=? GROUP BY node_id", (pid,))}
    rows = []
    for r in res["rows"]:
        if r["kind"] not in ("line", "pot"):
            continue
        ref = str(r["id"])
        p = plan.get(ref, 0.0)
        a, x, f = r["a"][i], r["x"][i], r["f"][i]
        nxt = r["f"][i + 1] if i + 1 < len(grid) else 0.0
        if not any(abs(v) > 0.5 for v in (p, a, x, f)) and ref not in dec:
            continue
        d = dec.get(ref) or {}
        rows.append(dict(id=ref, node_id=r["node_id"], kind=r["kind"], code=r["code"], name=r["name"], gp=r["gp"], method=r["method"],
                         planned=p, actual=a, accrued=x, landed=a + x, variance=(a + x) - p, forecast_now=f, forecast_next=nxt,
                         state="hybrid" if a > 0.5 and x > 0.5 else "actual" if a > 0.5 else "accrual" if x > 0.5 else "",
                         ctc=r["ctc"], eac=r["eac"], note=r["note"], sub=subs.get(r["node_id"]), items=items.get(r["node_id"], 0),
                         decision=d.get("decision"), decision_note=d.get("note"), review_id=d.get("id"),
                         reviewed_by=st.get(d.get("id"), {}).get("changed_by"), reviewed_at=st.get(d.get("id"), {}).get("changed_at")))
    rows.sort(key=lambda r: r["code"])
    tot = {k: sum(r[k] for r in rows) for k in ("planned", "actual", "accrued", "landed", "variance", "forecast_now", "forecast_next")}
    return dict(month=M, status_month=res["status_month"], grid=grid, snapshot=dict(id=snap["id"], label=snap["label"], period=snap["period"]) if snap else None,
                rows=rows, total=tot, decisions=DECISIONS, reviewed=sum(1 for r in rows if r["decision"]))


def decide(con, pid, node_ref, month, decision, note=None):
    if decision and decision not in DECISIONS:
        raise ValueError("Unknown decision")
    ex = db.one(con, "SELECT id FROM month_review WHERE project_id=? AND node_ref=? AND month=? ORDER BY id DESC LIMIT 1", (pid, str(node_ref), month))
    if ex:
        if decision:
            db.update(con, "month_review", ex["id"], dict(decision=decision, note=note))
        else:
            con.execute("DELETE FROM month_review WHERE id=?", (ex["id"],))
        return ex["id"]
    if not decision:
        return None
    return db.insert(con, "month_review", dict(project_id=pid, node_ref=str(node_ref), month=month, decision=decision, note=note))
