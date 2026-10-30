"""Unallocated allowance (a group's own allowance, shown as its "(Unallocated)" pool) and the lines beneath it.

The engine already counts the costs on those lines as drawn from the pool (see engine.leaf_row, covered). This module is the
fix that makes it permanent: transfer allowance from the pool to the lines whose cost it is covering, so each line carries
the allowance it needs. Nearest pool first; what a pool cannot cover stays an overrun, or goes up to the pool above.
"""
from . import db, engine, services


def plan(con, pid, only_groups=None):
    res = engine.compute(con, pid)
    rows = res["rows"]
    by_id = {r["id"]: r for r in rows}
    kids = {}
    for r in rows:
        if r["kind"] in ("line", "group") and r.get("parent_id") is not None:
            kids.setdefault(r["parent_id"], []).append(r)
    pots = {r["node_id"]: r for r in rows if r["kind"] == "pot"}
    over = {r["id"]: max(0.0, r["eac"] - r["allowance"]) for r in rows if r["kind"] == "line" and r.get("origin") not in ("ctc", "wip")}
    out, order = [], sorted((g for g in rows if g["kind"] == "group" and g["node_id"] in pots), key=lambda g: -g["level"])
    tol = max(1.0, (db.one(con, "SELECT tolerance FROM project WHERE id=?", (pid,)) or {}).get("tolerance") or 1.0)

    def lines_under(gid):
        found = []
        for c in kids.get(gid, []):
            if c["kind"] == "line":
                found.append(c)
            else:
                found.extend(lines_under(c["id"]))
        return found
    for g in order:
        pot = pots[g["node_id"]]
        avail = max(0.0, pot["allowance"] - pot["ctd"] - pot["acc"])
        if only_groups is not None and g["node_id"] not in only_groups:
            continue
        for ln in sorted(lines_under(g["id"]), key=lambda r: r["code"]):
            o = over.get(ln["id"], 0.0)
            if o <= tol or avail <= tol:
                continue
            amt = round(min(o, avail), 2)
            out.append(dict(group_id=g["node_id"], group=f"{g['code']} {g['name']}", line_id=ln["node_id"], line=f"{ln['code']} {ln['name']}", over=round(o, 2), amount=amt))
            avail -= amt
            over[ln["id"]] = o - amt
    return out


def allocate(con, pid, only_groups=None, who=None):
    moves = plan(con, pid, only_groups)
    for m in moves:
        services.transfer(con, pid, m["group_id"], m["line_id"], budget=m["amount"], ref="POOL", note="Allocated from the unallocated allowance to cover costs")
    return moves
