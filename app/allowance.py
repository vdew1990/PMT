"""Linking a resource to an allowance bucket: the starting point of the allowance ledger.

A bucket is a CBS group and the allowance it holds itself (its "(Unallocated)" pool). Linking gives a resource a CBS line under the
bucket and moves allowance from the bucket to that line as a ledger transfer (ref LINK); later movements are ordinary transfers.

Three options, by what the resource has already cost (CTD + accruals + open commitment, once its Pronto rows sit on the line):
  1  no cost yet: the user sets the initial budget, which cannot exceed what the bucket has left.
  2  cost already: the line is given enough to cover it; if the bucket cannot, only what is left is assigned.
  3  cost already: the line is given enough to cover it (a floor) plus an extra amount for future costs; the total cannot exceed the bucket.
"""
from . import db, engine, pronto, services
from .services import Problem

OPTIONS = (1, 2, 3)


def _rows(con, pid):
    res = engine.compute(con, pid)
    return {r["node_id"]: r for r in res["rows"] if r["kind"] == "pot"}, {r["id"]: r for r in res["rows"] if r["kind"] == "line"}


def overview(con, pid):
    pots, lines = _rows(con, pid)
    groups = db.rows(con, "SELECT id, code, name, category, parent_id FROM cbs_node WHERE project_id=? AND kind='group' ORDER BY code", (pid,))
    has_lines = {r["parent_id"] for r in lines.values()}
    buckets = []
    for g in groups:
        pot = pots.get(g["id"])
        if not pot and g["id"] not in has_lines:
            continue
        budget = (pot or {}).get("budget", 0.0)
        parked = ((pot or {}).get("ctd", 0.0) + (pot or {}).get("acc", 0.0))
        # where the money in the pool came from: the estimate, approved variations, risk released or infused by the company, adjustments
        src = {}
        for e in db.rows(con, "SELECT kind, ref, variation_id, SUM(budget) b, SUM(risk) r FROM allowance_ledger WHERE project_id=? AND node_id=? "
                              "AND kind IN ('estimate','variation','release','infuse','adjust','contingency_set') GROUP BY kind, ref, variation_id", (pid, g["id"])):
            if abs(e["b"] or 0) > 0.005 or abs(e["r"] or 0) > 0.005:
                src[(e["kind"], e["ref"])] = dict(kind=e["kind"], ref=e["ref"], budget=round(e["b"] or 0, 2), risk=round(e["r"] or 0, 2))
        buckets.append(dict(id=g["id"], code=g["code"], name=g["name"], category=g["category"], budget=round(budget, 2),
                            risk=round((pot or {}).get("risk", 0.0), 2), parked=round(parked, 2), available=round(max(0.0, budget - parked), 2),
                            sources=sorted(src.values(), key=lambda x: -abs(x["budget"] + x["risk"]))))
    by_cat = {g["category"]: g["id"] for g in groups if g["category"]}
    todo = []
    for s in pronto.suggestions(con, pid):                              # cost with no line: parked on the bucket of its category
        todo.append(dict(state="cost_no_line", kind=s["kind"], code=s["resource_code"], name=s["name"], function=s["function"],
                         cost=s["cost"], bucket_id=by_cat.get(s["category"]), line_id=None))
    for ln in lines.values():                                           # a line the bucket has not funded (or not fully)
        need = ln["ctd"] + ln["acc"] + ln["outstanding"]
        if ln["budget"] < need - 1 or (ln["budget"] <= 0 and ln.get("resource_code")):
            todo.append(dict(state="unfunded_line", kind=ln.get("resource_kind"), code=ln.get("resource_code"), name=ln["name"],
                             function=ln.get("function"), cost=round(need, 2), allowance=round(ln["budget"], 2),
                             bucket_id=ln["parent_id"], line_id=ln["node_id"]))
    return dict(buckets=buckets, resources=todo, options={1: "No cost yet: set the initial budget", 2: "Cover the cost so far", 3: "Cover the cost so far and add an amount for the future"})


def _line_for(con, pid, bucket, kind, code):
    """An existing line for the resource in the bucket's category, else None."""
    cat = bucket["category"] or _category(con, pid, bucket)
    for n in db.rows(con, "SELECT n.id, n.parent_id FROM cbs_node n JOIN resource r ON r.id=n.resource_id WHERE n.project_id=? AND n.kind='line' "
                          "AND r.kind=? AND r.code=? AND n.active=1", (pid, kind, code)):
        if _category(con, pid, services.get_node(con, pid, n["id"])) == cat:
            return n["id"]
    return None


def _category(con, pid, n):
    while n:
        if n["category"]:
            return n["category"]
        n = db.one(con, "SELECT * FROM cbs_node WHERE id=?", (n["parent_id"],)) if n["parent_id"] else None
    return None


def link(con, pid, bucket_id, kind, code, option, amount=0.0, name=None, function=None, line_id=None, dry=False):
    """Link a resource to a bucket. dry=True works everything out and changes nothing."""
    if option not in OPTIONS:
        raise Problem("Choose option 1, 2 or 3")
    amount = float(amount or 0)
    if amount < 0:
        raise Problem("The amount cannot be negative")
    if line_id:
        line_id = int(line_id)
        bucket_id = services.get_node(con, pid, line_id)["parent_id"]
    bucket = services.get_node(con, pid, bucket_id)
    if bucket["kind"] != "group":
        raise Problem("Choose an allowance bucket (a CBS group)")
    if not (line_id or code):
        raise Problem("Choose or type the resource")
    con.execute("SAVEPOINT alw")
    try:
        if not line_id:
            line_id = _line_for(con, pid, bucket, kind, code)
        if not line_id:
            line_id = services.add_node(con, pid, bucket_id, name or code, kind="line", resource_kind=kind, resource_code=code,
                                        resource_name=name, function=function, origin="allowance")
        pronto.resolve_all(con, pid)                                    # the resource's cost moves from the bucket onto its line
        pots, lines = _rows(con, pid)
        ln, pot = lines[line_id], pots.get(bucket_id)
        cost = round(ln["ctd"] + ln["acc"] + ln["outstanding"], 2)
        have = ln["budget"]
        left = max(0.0, ((pot or {}).get("budget", 0.0)) - ((pot or {}).get("ctd", 0.0) + (pot or {}).get("acc", 0.0)))
        floor = max(0.0, cost - have)
        if option == 1:
            if cost > 1:
                raise Problem(f"This resource already has {cost:,.2f} of cost. Use option 2 or 3.")
            draw = amount
        elif option == 2:
            draw = min(floor, left)
        else:
            if cost <= 1:
                raise Problem("This resource has no cost yet. Use option 1.")
            draw = min(floor, left) + amount
        if option != 2 and draw > left + 0.005:
            raise Problem(f"The bucket has {left:,.2f} left, so no more than that can be drawn (asked for {draw:,.2f}).")
        draw = round(draw, 2)
        out = dict(line_id=line_id, bucket_id=bucket_id, option=option, cost=cost, floor=round(min(floor, left), 2), uncovered=round(max(0.0, floor - left), 2),
                   bucket_left=round(left, 2), draw=draw, bucket_after=round(left - draw, 2), line_allowance_after=round(have + draw, 2))
        if dry:
            con.execute("ROLLBACK TO alw")
        elif draw > 0:
            services.transfer(con, pid, bucket_id, line_id, budget=draw, ref="LINK", note=f"Linked to the allowance bucket (option {option})")
        con.execute("RELEASE alw")
        return out
    except BaseException:
        con.execute("ROLLBACK TO alw")
        con.execute("RELEASE alw")
        raise


def link_many(con, pid, rows, option=2, bucket_id=None):
    """Link several resources at once. Each row is { kind, code, name, function, line_id, bucket_id }; a row with no bucket takes `bucket_id`.
    Only options 2 (cover the cost so far) and 1 with no amount (no cost yet, nothing drawn) make sense in bulk. Rows that cannot be linked are listed, not fatal."""
    if option not in (1, 2):
        raise Problem("Several at once can cover the cost so far (option 2) or link with no budget (option 1)")
    done, skipped, draw = 0, [], 0.0
    for r in rows:
        b = r.get("bucket_id") or bucket_id
        if not b:
            skipped.append(dict(code=r.get("code"), name=r.get("name"), why="No bucket chosen or suggested"))
            continue
        try:
            o = link(con, pid, int(b), r.get("kind") or "supplier", r.get("code"), option, 0, name=r.get("name"), function=r.get("function"), line_id=r.get("line_id"))
        except Problem as e:
            skipped.append(dict(code=r.get("code"), name=r.get("name"), why=str(e)))
            continue
        done += 1
        draw += float((o or {}).get("draw") or 0)
    return dict(linked=done, skipped=skipped, draw=round(draw, 2))


def spread(con, pid, from_id, moves, ref="SPREAD", note=None):
    """Spread allowance from a group's own pool (its "(Unallocated)" line) to lines beneath it, in one go. moves = [{to_id, budget}].
    Nothing moves unless the whole spread fits in what the pool has left (its allowance less the cost parked on it)."""
    from . import services
    group = services.get_node(con, pid, from_id)
    if group["kind"] != "group":
        raise Problem("Allowance is spread from a group's pool")
    below = set(services.subtree_ids(con, pid, from_id))
    moves = [m for m in (moves or []) if float(m.get("budget") or 0) > 0.004]
    if not moves:
        raise Problem("Enter an amount for at least one line")
    for m in moves:
        n = services.get_node(con, pid, int(m["to_id"]))
        if n["kind"] != "line" or n["id"] not in below or n["id"] == from_id:
            raise Problem(f"{n['code']} is not a line under {group['code']}")
    pots, _lines = _rows(con, pid)
    pot = pots.get(from_id)
    left = max(0.0, ((pot or {}).get("budget", 0.0)) - ((pot or {}).get("ctd", 0.0) + (pot or {}).get("acc", 0.0)))
    total = round(sum(float(m["budget"]) for m in moves), 2)
    if total > left + 0.005:
        raise Problem(f"The pool has {left:,.2f} left, so {total:,.2f} cannot be spread.")
    pairs = []
    for m in moves:
        pairs.append(services.transfer(con, pid, from_id, int(m["to_id"]), budget=round(float(m["budget"]), 2), ref=ref, note=note or "Spread from the unallocated allowance"))
    return dict(pairs=pairs, total=total, left_after=round(left - total, 2))


def undo_spread(con, pid, pairs):
    for pr in pairs or []:
        con.execute("DELETE FROM allowance_ledger WHERE project_id=? AND pair_id=? AND kind='transfer' AND ref='SPREAD'", (pid, pr))
    db.bump(con, pid)
