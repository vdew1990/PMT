"""History of one metric (forecast, accruals or actuals) through the month-end closes.

Every month-end close stores, per CBS line, the actual, accrued and forecast cost by month as it stood then
(reports.create_snapshot). This module lines those up so a page can answer "what did I forecast for Sep-25 back in
Jul-25", show how a line's method and value moved from close to close, and replay the cost curve over time.
Closes made before the split was stored keep only the monthly total: their forecast is taken as the months from the
close's status month on, and the earlier months as actual.
"""
import json

from . import db, engine

METRICS = {"f": "forecast", "x": "accrual", "a": "actual"}


def _closes(con, pid):
    # the baseline is day zero, whatever period it was stamped with
    return db.rows(con, "SELECT id, label, period, kind, status_date, curve_json FROM snapshot WHERE project_id=? ORDER BY kind<>'baseline', period, id", (pid,))


def _snap_rows(con, s):
    months = (json.loads(s["curve_json"] or "{}") or {}).get("months") or []
    out = []
    codes = []
    for r in db.rows(con, "SELECT * FROM snapshot_line WHERE snapshot_id=?", (s["id"],)):
        tot = json.loads(r["months_json"] or "[]")
        if r.get("f_json"):
            a, x, f = (json.loads(r[k] or "[]") for k in ("a_json", "x_json", "f_json"))
        else:  # an older close: only the total by month was kept
            cut = s["period"] or ""
            a = [v if m < cut else 0.0 for m, v in zip(months, tot)]
            x = [0.0] * len(tot)
            f = [v if m >= cut else 0.0 for m, v in zip(months, tot)]
        out.append(dict(ref=r["node_ref"], code=r["code"], name=r["name"], level=r["level"], gp=r["gp"], kind=r.get("kind"), method=r.get("method"),
                        allowance=r["allowance"], ctd=r["ctd"], acc=r["acc"], ctc=r["ctc"], eac=r["eac"],
                        m={k: dict(zip(months, v)) for k, v in (("a", a), ("x", x), ("f", f))}))
        codes.append(r["code"])
    cs = set(codes)
    for r in out:  # older closes do not say which rows are leaves: a leaf has no row below it
        if not r["kind"]:
            r["kind"] = "group" if any(c != r["code"] and c.startswith(r["code"] + ".") for c in cs) else "line"
    return dict(id=s["id"], label=s["label"], period=s["period"], kind=s["kind"], months=months, rows=out)


def _live(con, pid):
    res = engine.compute(con, pid)
    rows = [dict(ref=str(r["id"]), code=r["code"], name=r["name"], level=r["level"], gp=r["gp"], kind=r["kind"], method=r.get("method"),
                 allowance=r["allowance"], ctd=r["ctd"], acc=r["acc"], ctc=r["ctc"], eac=r["eac"],
                 m={k: dict(zip(res["grid"], r[k])) for k in ("a", "x", "f")}) for r in res["rows"]]
    return dict(id="live", label="Now (live)", period=res["status_month"], kind="live", months=res["grid"], rows=rows)


def _in_scope(rows, code):
    """Leaf rows (lines and unallocated pools) at or below a CBS code; every leaf when code is None."""
    leaves = [r for r in rows if r["kind"] in ("line", "pot")]
    if not code:
        return leaves
    return [r for r in leaves if r["code"] == code or r["code"].startswith(code + ".")]


def _scope_code(con, pid, node):
    if node in (None, "", "root"):
        return None, "Whole project"
    nid = int(str(node).lstrip("p"))
    n = db.one(con, "SELECT code, name FROM cbs_node WHERE id=? AND project_id=?", (nid, pid))
    if not n:
        raise ValueError("CBS item not found")
    return (n["code"] + ".U" if str(node).startswith("p") else n["code"]), f"{n['code']} {n['name']}"


def grid(con, pid, metric, as_at="live", node=None):
    """One close (or now): every leaf in scope with its metric by month, method, EAC and the change since the close before."""
    closes = _closes(con, pid)
    code, label = _scope_code(con, pid, node)
    snaps = [_snap_rows(con, s) for s in closes] + [_live(con, pid)]
    sel = next((s for s in snaps if str(s["id"]) == str(as_at)), snaps[-1])
    i = snaps.index(sel)
    prev = snaps[i - 1] if i > 0 else None
    prev_by = {r["code"]: r for r in (prev["rows"] if prev else [])}
    months = sorted(set().union(*[set(s["months"]) for s in snaps]))
    rows = []
    for r in sorted(_in_scope(sel["rows"], code), key=lambda r: r["code"]):
        vals = [r["m"][metric].get(m, 0.0) for m in months]
        p = prev_by.get(r["code"])
        ptot = sum(p["m"][metric].values()) if p else None
        rows.append(dict(ref=r["ref"], code=r["code"], name=r["name"], gp=r["gp"], kind=r["kind"], method=r["method"], eac=r["eac"], allowance=r["allowance"],
                         values=vals, total=sum(vals), prev_total=ptot, prev_method=p["method"] if p else None, prev_eac=p["eac"] if p else None))
    return dict(metric=metric, scope=label, as_at=dict(id=sel["id"], label=sel["label"], period=sel["period"]), prev=dict(id=prev["id"], label=prev["label"]) if prev else None,
                closes=[dict(id=s["id"], label=s["label"], period=s["period"]) for s in snaps], months=months, rows=rows,
                total=[sum(r["values"][j] for r in rows) for j in range(len(months))])


def track(con, pid, metric, node=None):
    """Close by close for one CBS item (or the whole project): the metric by month, the method, the EAC and allowance.
    Answers "what did I forecast for Sep-25 back in Jul-25" and drives the chart that moves over time."""
    code, label = _scope_code(con, pid, node)
    snaps = [_snap_rows(con, s) for s in _closes(con, pid)] + [_live(con, pid)]
    months = sorted(set().union(*[set(s["months"]) for s in snaps]))
    out = []
    for s in snaps:
        leaves = _in_scope(s["rows"], code)
        if not leaves:
            continue
        vals = {k: [sum(r["m"][k].get(m, 0.0) for r in leaves) for m in months] for k in ("a", "x", "f")}
        methods = sorted({r["method"] or "AT-BUDGET" for r in leaves})
        out.append(dict(id=s["id"], label=s["label"], period=s["period"], kind=s["kind"], values=vals[metric], a=vals["a"], x=vals["x"], f=vals["f"],
                        total=sum(vals[metric]), eac=sum(r["eac"] or 0 for r in leaves), allowance=sum(r["allowance"] or 0 for r in leaves),
                        ctd=sum(r["ctd"] or 0 for r in leaves), acc=sum(r["acc"] or 0 for r in leaves), ctc=sum(r["ctc"] or 0 for r in leaves),
                        method=methods[0] if len(methods) == 1 else f"{len(methods)} methods"))
    return dict(metric=metric, scope=label, months=months, closes=out)
