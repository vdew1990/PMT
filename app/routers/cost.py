"""Cost and Forecast routes: cost control and CBS, allowance, ledger, pools, forecast items, accruals, labour calendar, risk, programme and month-end."""
import json
import mimetypes
import base64
import secrets
import shutil
from datetime import datetime
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from .. import (groundup, checklists, revert as revert_mod, allowance, pools, invoices as invoices_mod, accruals,
                activity, review, site_files, timeline, changelog, db, forecast, holidays, identity,
                drill as drill_mod, engine, exporters, programme, pronto, risk as risk_mod, revenue, services,
                subcontracts)
from ..taxonomy import METHODS

from ._shared import J, UPLOADS, _rm, _xlsx, get_con, need_project

router = APIRouter(default_response_class=J)


@router.get("/api/p/{pid}/month-end")
def month_end(pid: int, month: str = None, con=Depends(get_con)):
    need_project(con, pid)
    return checklists.month_end(con, pid, month)


# ---------------------------------------------------------------------------
# CBS and allowance
# ---------------------------------------------------------------------------
@router.get("/api/p/{pid}/cost-control")
def cost_control(pid: int, months: int = 1, status_month: str = None, merge: int = 0, con=Depends(get_con)):
    """merge=1: a CBS line and its variation copies show as one row with a base / variation breakdown (cost control)."""
    need_project(con, pid)
    res = engine.compute(con, pid, status_month)
    rows = res["rows"]
    if not months:
        rows = [{k: v for k, v in r.items() if k not in ("a", "x", "f")} for r in rows]
    # risk cost that has occurred (tagged to a risk event), rolled up the tree
    byid = {str(r["id"]): r for r in rows}
    for r in rows:
        r["risk_cost"] = 0.0
    for t in risk_mod.tagged_costs(con, pid, res["status_month"]):
        if t["kind"] == "forecast":
            continue
        cur = byid.get(str(t["node_id"]))
        # the amount belongs to the line, or to the group's unallocated pot when the node is a group
        leaf = byid.get(str(t["node_id"])) if byid.get(str(t["node_id"])) and byid[str(t["node_id"])]["kind"] == "line" else byid.get("p" + str(t["node_id"]))
        x = leaf
        while x is not None:
            x["risk_cost"] += t["amount"]
            x = byid.get(str(x["parent_id"])) if x["parent_id"] is not None else None
    p = db.one(con, "SELECT initialised, status_date, project_start, project_end FROM project WHERE id=?", (pid,))
    # the current month as it was forecast at the last month-end close (shown next to what landed)
    snap, plan = review.planned(con, pid, res["status_month"])
    if merge:
        rows = engine.merge_variation_copies(con, pid, rows, res.get("tolerance") or 1.0)
    # which lines have Start and/or Stop driven by a schedule item (for the Start / Stop cells of Cost control)
    wins = {}
    linked = {r["node_id"] for r in db.rows(con, "SELECT node_id FROM window_link WHERE project_id=?", (pid,))} | \
             {r["link_node_id"] for r in db.rows(con, "SELECT link_node_id FROM programme_task WHERE project_id=? AND link_node_id IS NOT NULL", (pid,))}
    for nid in linked:
        _n, st = programme.window_state(con, pid, nid)
        wins[str(nid)] = {k: ({kk: v[kk] for kk in ("task_id", "task", "edge", "suspended", "date")} if v else None) for k, v in st.items()}
    return dict(status_month=res["status_month"], grid=res["grid"], rows=rows, planned=plan, planned_from=snap["label"] if snap else None, windows=wins,
                total={k: v for k, v in res["total"].items() if months or k not in ("a", "x", "f")},
                unplaced=res["unplaced"], initialised=bool(p["initialised"]), project=p, claim_nodes=sorted(subcontracts.claim_nodes(con, pid)),
                is_parent=bool(res.get("is_parent")), children=res.get("children"))


@router.get("/api/p/{pid}/drill")
def drill(pid: int, node: str, metric: str, month: str = None, con=Depends(get_con)):
    """The records behind an amount in cost control (a row's CTD, open POs, accruals, forecast, allowance, risk), optionally for one month."""
    need_project(con, pid)
    return drill_mod.drill(con, pid, node, metric, month)


@router.post("/api/p/{pid}/nodes")
def add_node(pid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    keys = ("parent_id", "name", "kind", "code", "resource_kind", "resource_code", "resource_name", "function", "scope",
            "method", "start_date", "end_date", "po_no", "budget", "risk", "category", "notes")
    d = {k: body.get(k) for k in keys if k in body}
    for k in ("start_date", "end_date"):
        if d.get(k):
            d[k] = db.iso(d[k])
    if d.get("kind") is None:
        d["kind"] = "line"
    nid = services.add_node(con, pid, **d)
    return {"id": nid}


@router.put("/api/p/{pid}/nodes/{nid}")
def edit_node(pid: int, nid: int, body: dict, con=Depends(get_con)):
    for k in ("start_date", "end_date"):
        if body.get(k):
            body[k] = db.iso(body[k])
    services.update_node(con, pid, nid, body)
    return {"ok": True}


@router.post("/api/p/{pid}/nodes/{nid}/window")
def node_window(pid: int, nid: int, body: dict, con=Depends(get_con)):
    """Save a line's activity window: Start and Stop each typed, driven by a schedule task (start or finish), or worked out from the duration."""
    services.get_node(con, pid, nid)
    for k in ("start", "stop"):
        if (body.get(k) or {}).get("date"):
            body[k]["date"] = db.iso(body[k]["date"])
    return {"warnings": programme.set_window(con, pid, nid, body.get("start"), body.get("stop"), body.get("months"))}


@router.post("/api/p/{pid}/nodes/{nid}/window-reset")
def node_window_reset(pid: int, nid: int, body: dict = None, con=Depends(get_con)):
    """Hand the line's Start and/or Stop back to the project schedule (the links typed over are switched on again)."""
    services.get_node(con, pid, nid)
    return {"warnings": programme.reset_window(con, pid, nid, (body or {}).get("role"))}


@router.get("/api/p/{pid}/programme/links")
def programme_links(pid: int, con=Depends(get_con)):
    """Both directions: which CBS lines each schedule task drives (as the whole span, or as Start and/or Stop)."""
    span = db.rows(con, "SELECT t.id task_id, n.id node_id, n.code, n.name FROM programme_task t JOIN cbs_node n ON n.id=t.link_node_id "
                        "WHERE t.project_id=? AND COALESCE(t.layer,'internal')='internal'", (pid,))
    anchors = db.rows(con, "SELECT w.task_id, w.node_id, n.code, n.name, w.role, w.edge, w.suspended FROM window_link w JOIN cbs_node n ON n.id=w.node_id WHERE w.project_id=?", (pid,))
    return {"span": span, "anchors": anchors}


@router.post("/api/p/{pid}/programme/links")
def programme_link_add(pid: int, body: dict, con=Depends(get_con)):
    nid, tid, role = int(body["node_id"]), int(body["task_id"]), body.get("role") or "span"
    services.get_node(con, pid, nid)
    if role == "span":
        db.update(con, "programme_task", tid, {"link_node_id": nid})
    else:
        for r in (("start", "stop") if role == "both" else (role,)):
            row = db.one(con, "SELECT * FROM window_link WHERE node_id=? AND role=?", (nid, r))
            vals = dict(task_id=tid, edge=body.get("edge") or ("start" if r == "start" else "finish"), suspended=0)
            if row:
                db.update(con, "window_link", row["id"], vals)
            else:
                db.insert(con, "window_link", dict(project_id=pid, node_id=nid, role=r, **vals))
    return {"warnings": programme.apply(con, pid, targets=("costs",)).get("warnings", [])}


@router.delete("/api/p/{pid}/programme/links")
def programme_link_del(pid: int, task_id: int, node_id: int, role: str = "span", con=Depends(get_con)):
    if role == "span":
        con.execute("UPDATE programme_task SET link_node_id=NULL WHERE id=? AND link_node_id=? AND project_id=?", (task_id, node_id, pid))
    else:
        con.execute("DELETE FROM window_link WHERE task_id=? AND node_id=? AND project_id=?" + ("" if role == "both" else " AND role=?"),
                    (task_id, node_id, pid) + (() if role == "both" else (role,)))
    db.bump(con, pid)
    return {"ok": True}


@router.post("/api/p/{pid}/nodes/{nid}/move")
def move_node(pid: int, nid: int, body: dict, con=Depends(get_con)):
    services.move_node(con, pid, nid, body["parent_id"])
    return {"ok": True}


@router.get("/api/p/{pid}/revert")
def revert_preview(pid: int, con=Depends(get_con)):
    return revert_mod.preview(con, pid)


@router.post("/api/p/{pid}/revert")
def revert_last(pid: int, con=Depends(get_con)):
    """Put back the last action this user made on the project."""
    need_project(con, pid)
    return revert_mod.revert(con, pid)


@router.post("/api/p/{pid}/redo")
def redo_last(pid: int, con=Depends(get_con)):
    """Apply again what Revert last put back."""
    need_project(con, pid)
    return revert_mod.redo(con, pid)


@router.post("/api/p/{pid}/nodes/{nid}/reorder")
def node_reorder(pid: int, nid: int, body: dict, con=Depends(get_con)):
    """Reorder a CBS group or line among its siblings: {dir: -1 | 1}."""
    need_project(con, pid)
    return {"moved": services.reorder_node(con, pid, nid, -1 if int(body.get("dir") or 0) < 0 else 1)}


@router.delete("/api/p/{pid}/nodes/{nid}")
def delete_node(pid: int, nid: int, con=Depends(get_con)):
    services.delete_node(con, pid, nid)
    return {"ok": True}


@router.post("/api/p/{pid}/methods")
def set_methods(pid: int, body: dict, con=Depends(get_con)):
    method = body.get("method")
    if method not in METHODS:
        raise services.Problem("Unknown forecast method")
    ids = services.subtree_ids(con, pid, int(body["node_id"]))
    n = 0
    claimable = subcontracts.claim_nodes(con, pid) if method == "CLAIM" else None
    for i in ids:
        node = services.get_node(con, pid, i)
        if claimable is not None and i not in claimable:
            continue  # CLAIM only where a subcontract with a claim schedule is linked
        if node["kind"] == "line":
            db.update(con, "cbs_node", i, {"method": method})
            n += 1
        elif body.get("include_pots"):
            db.update(con, "cbs_node", i, {"unalloc_method": method})
    return {"updated": n}


@router.get("/api/p/{pid}/nodes/{nid}/what-if")
def node_what_if(pid: int, nid: int, pot: int = 0, eac: float = None, uncommitted: float = None, con=Depends(get_con)):
    """Monthly CTC of this line under each forecast method (or the fields given), next to the saved one."""
    n = services.get_node(con, pid, nid)
    pot = bool(pot)
    base = engine.what_if(con, pid, nid, pot)
    out = {"current": base, "methods": {}}
    keys = ("unalloc_method", "unalloc_eac") if pot else ("method", "eac_override", "uncommitted")
    extra = {}
    if eac is not None:
        extra[keys[1]] = eac
    if uncommitted is not None and not pot:
        extra["uncommitted"] = uncommitted
    for m in METHODS:
        out["methods"][m] = engine.what_if(con, pid, nid, pot, **{keys[0]: m, **extra})
    return out


@router.get("/api/p/{pid}/nodes/{nid}/budget-buildup")
def node_budget(pid: int, nid: int, own: int = 0, con=Depends(get_con)):
    """Original budget, movements and each variation that make up a CBS item's budget (cost control drawer)."""
    need_project(con, pid)
    return engine.budget_buildup(con, pid, nid, bool(own))


@router.get("/api/p/{pid}/nodes/{nid}")
def node_detail(pid: int, nid: int, con=Depends(get_con)):
    n = services.get_node(con, pid, nid)
    n["resource"] = db.one(con, "SELECT * FROM resource WHERE id=?", (n["resource_id"],)) if n["resource_id"] else None
    ids = services.subtree_ids(con, pid, nid)
    q = ",".join("?" * len(ids))
    n["ancestors"] = [dict(id=a["id"], code=a["code"], name=a["name"]) for a in reversed(services.ancestors(con, pid, nid))]
    n["ledger"] = db.rows(con, "SELECT * FROM allowance_ledger WHERE project_id=? AND node_id=? ORDER BY id DESC", (pid, nid))
    n["items"] = db.rows(con, "SELECT * FROM forecast_item WHERE project_id=? AND node_id=? ORDER BY id", (pid, nid))
    n["manual"] = db.rows(con, "SELECT item_id, month, amount FROM forecast_manual WHERE project_id=? AND node_id=? ORDER BY month", (pid, nid))
    n["accruals"] = db.rows(con, "SELECT * FROM accrual WHERE project_id=? AND node_id=? ORDER BY month DESC", (pid, nid))
    st = activity.stamps(con, "accrual", [a["id"] for a in n["accruals"]])
    for a in n["accruals"]:
        a.update(st.get(a["id"], {}))
    n["pos"] = db.rows(con, f"SELECT order_no, supplier_name, status, SUM(committed) committed, SUM(received) received, MAX(is_open) is_open "
                            f"FROM pronto_po WHERE project_id=? AND node_id IN ({q}) GROUP BY order_no, supplier_name, status ORDER BY order_no", [pid, *ids])
    n["subcontracts"] = db.rows(con, f"SELECT id, name, contract_value FROM subcontract WHERE project_id=? AND node_id IN ({q})", [pid, *ids])
    # for a group: the forecast items below it that are taken out of its pool
    n["allocations"] = db.rows(con, f"SELECT i.id item_id, i.node_id, i.scope, i.spread, c.code, c.name FROM forecast_item i JOIN cbs_node c ON c.id=i.node_id "
                                    f"WHERE i.project_id=? AND i.from_pool=1 AND i.node_id IN ({q}) AND i.node_id!=? ORDER BY c.code", [pid, *ids, nid]) if n["kind"] == "group" else []
    # pools above this item: unassigned forecast still left on each parent's (Unallocated) line, nearest first
    res = engine.compute(con, pid)
    by = {str(r["id"]): r for r in res["rows"]}
    _n, wst = programme.window_state(con, pid, nid)
    n["window"] = dict(start=wst["start"], stop=wst["stop"], months=n.get("window_months"), manual=any(v and v["suspended"] for v in wst.values()),
                       tasks=[v for v in wst.values() if v])
    n["pools"] = []
    for a in reversed(n["ancestors"][:-1]):  # ancestors runs from the root to this node
        pr = by.get(f"p{a['id']}")
        if pr:
            n["pools"].append(dict(node_id=a["id"], code=pr["code"], name=a["name"], method=pr["method"], ctc=pr["ctc"], drawn=pr.get("pool_drawn", 0), allowance=pr["allowance"]))
    return n


@router.put("/api/p/{pid}/nodes/{nid}/estimate")
def node_estimate(pid: int, nid: int, body: dict, con=Depends(get_con)):
    services.set_estimate(con, pid, nid, body.get("budget") or 0, body.get("risk"), body.get("note"))
    return {"ok": True}


@router.post("/api/p/{pid}/allowance/bulk")
def allowance_bulk(pid: int, body: dict, con=Depends(get_con)):
    n = 0
    for r in body.get("rows", []):
        services.set_estimate(con, pid, int(r["node_id"]), r.get("budget") or 0, r.get("risk"))
        n += 1
    return {"updated": n}


@router.post("/api/p/{pid}/ledger/transfer")
def ledger_transfer(pid: int, body: dict, con=Depends(get_con)):
    services.transfer(con, pid, int(body["from_id"]), int(body["to_id"]), float(body.get("budget") or 0), float(body.get("risk") or 0),
                      body.get("ref"), body.get("note"), db.iso(body.get("date")))
    return {"ok": True}


@router.post("/api/p/{pid}/ledger/spread")
def ledger_spread(pid: int, body: dict, con=Depends(get_con)):
    """Spread a group's own allowance over lines beneath it (the drag on Cost control)."""
    need_project(con, pid)
    return allowance.spread(con, pid, int(body["from_id"]), body.get("moves"), "SPREAD", body.get("note"))


@router.post("/api/p/{pid}/ledger/spread/undo")
def ledger_spread_undo(pid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    allowance.undo_spread(con, pid, body.get("pairs"))
    return {"ok": True}


@router.post("/api/p/{pid}/ledger/risk-release")
def ledger_risk(pid: int, body: dict, con=Depends(get_con)):
    services.release_risk(con, pid, int(body["node_id"]), float(body["amount"]), body.get("ref"), body.get("note"), db.iso(body.get("date")))
    return {"ok": True}


@router.post("/api/p/{pid}/ledger/adjust")
def ledger_adjust(pid: int, body: dict, con=Depends(get_con)):
    services.post_ledger(con, pid, "adjustment", [(int(body["node_id"]), float(body.get("budget") or 0), float(body.get("risk") or 0))],
                         body.get("ref"), body.get("note"), db.iso(body.get("date")))
    return {"ok": True}


def _reason(v):
    v = (v or "").strip()
    if len(v) < 3:
        raise services.Problem("Give a reason for the change (at least a few words): it is kept with the entry for traceability.")
    return v


def _ledger_log(con, pid, e, action, new, reason):
    keep = ("date", "kind", "budget", "risk", "contingency", "risk_cover", "ref", "note")
    code = db.scalar(con, "SELECT code FROM cbs_node WHERE id=?", (e["node_id"],))
    db.insert(con, "ledger_edit", dict(project_id=pid, ledger_id=e["id"], node_code=code, action=action, reason=reason,
                                       old_json=json.dumps({k: e.get(k) for k in keep}), new_json=json.dumps(new) if new is not None else None,
                                       by=(identity.current() or {}).get("name")))


@router.get("/api/p/{pid}/ledger")
def ledger(pid: int, all: int = 0, con=Depends(get_con)):
    """Allowance movements, newest first. all=1: every row including the original estimate (the full ledger per CBS),
    with who made each movement (from the change log), where the line sits in the CBS (ord = position in CBS order, anc = its
    ancestors from the top), the other side of a transfer (counter: which pot funded it, or which line a pot funded) and
    how many corrections the entry has had (edits)."""
    rows = db.rows(con, "SELECT l.*, n.code, n.name, n.parent_id FROM allowance_ledger l JOIN cbs_node n ON n.id=l.node_id WHERE l.project_id=?"
                        + ("" if all else " AND l.kind!='estimate'") + " ORDER BY l.id DESC" + ("" if all else " LIMIT 1000"), (pid,))
    if all and rows:
        who = {r["row_id"]: r["user_name"] for r in con.execute("SELECT row_id, user_name FROM change_log WHERE tbl='allowance_ledger' AND op='I' AND project_id=?", (pid,))}
        nodes = {n["id"]: n for n in db.rows(con, "SELECT id, parent_id, code, name FROM cbs_node WHERE project_id=? ORDER BY sort_order, id", (pid,))}
        kids = {}
        for n in nodes.values():
            kids.setdefault(n["parent_id"], []).append(n["id"])
        order, stack = {}, list(reversed(kids.get(None, [])))
        while stack:
            i = stack.pop()
            order[i] = len(order)
            stack.extend(reversed(kids.get(i, [])))

        def anc(i):
            out, p = [], nodes[i]["parent_id"]
            while p in nodes:
                out.append({"id": p, "code": nodes[p]["code"], "name": nodes[p]["name"]})
                p = nodes[p]["parent_id"]
            return out[::-1]

        by_pair = {}
        for r in rows:
            if r["pair_id"]:
                by_pair.setdefault(r["pair_id"], []).append(r)
        edits = {r["ledger_id"]: r["n"] for r in con.execute("SELECT ledger_id, COUNT(*) n FROM ledger_edit WHERE project_id=? GROUP BY ledger_id", (pid,))}
        for r in rows:
            r["by"] = who.get(r["id"])
            r["ord"] = order.get(r["node_id"], 1 << 30)
            r["anc"] = anc(r["node_id"]) if r["node_id"] in nodes else []
            r["counter"] = [{"node_id": o["node_id"], "code": o["code"], "name": o["name"], "budget": o["budget"], "risk": o["risk"]}
                            for o in by_pair.get(r["pair_id"], []) if o["id"] != r["id"]]
            r["edits"] = edits.get(r["id"], 0)
    return rows


@router.get("/api/p/{pid}/ledger/{lid}/edits")
def ledger_edits(pid: int, lid: int, con=Depends(get_con)):
    """Corrections and deletions of one entry (and of the other side of its move), newest first, each with its reason."""
    e = db.one(con, "SELECT pair_id FROM allowance_ledger WHERE id=? AND project_id=?", (lid, pid))
    ids = [lid]
    if e and e["pair_id"]:
        ids = [r["id"] for r in db.rows(con, "SELECT id FROM allowance_ledger WHERE project_id=? AND pair_id=?", (pid, e["pair_id"]))]
    return db.rows(con, f"SELECT * FROM ledger_edit WHERE project_id=? AND ledger_id IN ({','.join('?' * len(ids))}) ORDER BY id DESC", (pid, *ids))


@router.put("/api/p/{pid}/ledger/{lid}")
def ledger_edit(pid: int, lid: int, body: dict, con=Depends(get_con)):
    """Correct a ledger entry: amounts, date, reference, reason. The other leg of a two-sided move follows with the opposite sign so the
    move stays balanced; a move with more than two legs (a spread) can only have its text and date changed. A reason for the change
    is required and kept (ledger_edit). Undo reverses it."""
    e = db.one(con, "SELECT * FROM allowance_ledger WHERE id=? AND project_id=?", (lid, pid))
    if not e:
        raise HTTPException(404)
    why = _reason(body.get("reason"))
    amt = {k: round(float(body[k] or 0), 2) for k in ("budget", "risk", "contingency", "risk_cover") if k in body}
    changed = {k: v for k, v in amt.items() if abs(v - (e[k] or 0)) > 0.004}
    legs = db.rows(con, "SELECT * FROM allowance_ledger WHERE project_id=? AND pair_id=? AND id!=?", (pid, e["pair_id"], lid)) if e["pair_id"] else []
    if changed and e["pair_id"] and len(legs) != 1:
        raise services.Problem("This move has more than two sides. Change its date and reason here, or delete it and enter it again.")
    text = {k: (body.get(k) or None) for k in ("date", "ref", "note") if k in body}
    db.update(con, "allowance_ledger", lid, {**changed, **text})
    if legs:
        db.update(con, "allowance_ledger", legs[0]["id"], {**{k: -v for k, v in changed.items()}, **text})
    _ledger_log(con, pid, e, "edit", {**changed, **text}, why)
    db.bump(con, pid)
    return {"ok": True}


@router.delete("/api/p/{pid}/ledger/{lid}")
def ledger_delete(pid: int, lid: int, reason: str = "", con=Depends(get_con)):
    e = db.one(con, "SELECT * FROM allowance_ledger WHERE id=? AND project_id=?", (lid, pid))
    if not e:
        raise HTTPException(404)
    if e["kind"] in ("estimate", "variation"):
        raise services.Problem("Estimate and variation entries are managed from their own screens.")
    why = _reason(reason)
    _ledger_log(con, pid, e, "delete", None, why)
    if e["pair_id"]:
        con.execute("DELETE FROM allowance_ledger WHERE project_id=? AND pair_id=?", (pid, e["pair_id"]))
    else:
        con.execute("DELETE FROM allowance_ledger WHERE id=?", (lid,))
    db.bump(con, pid)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Forecast items, manual months, accruals
# ---------------------------------------------------------------------------
FORECAST_ITEM_COLS = ("risk_id", "scope", "note", "spread", "unit", "qty", "rate", "pct", "start_date", "end_date", "freq", "occurrences", "po_no", "milestone",
             "basis", "resource_id", "role", "rate_mode", "hours_day", "headcount", "pattern", "swings", "skip_holidays", "from_pool", "h1", "h2", "h3")


@router.get("/api/p/{pid}/groundup")
def groundup_register(pid: int, con=Depends(get_con)):
    need_project(con, pid)
    return groundup.register(con, pid)


@router.post("/api/p/{pid}/groundup/group")
def groundup_group(pid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    return {"updated": groundup.group(con, pid, body.get("ids") or [], body.get("h1"), body.get("h2"), body.get("h3"))}


@router.post("/api/p/{pid}/groundup/rename")
def groundup_rename(pid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    return {"updated": groundup.rename(con, pid, body.get("level"), body.get("old"), body.get("new"))}


@router.post("/api/p/{pid}/nodes/{nid}/items")
def item_save(pid: int, nid: int, body: dict, con=Depends(get_con)):
    n = services.get_node(con, pid, nid)
    d = {k: body.get(k) for k in FORECAST_ITEM_COLS if k in body}
    for k in ("start_date", "end_date"):
        if d.get(k):
            d[k] = db.iso(d[k])
    if body.get("id"):
        db.update(con, "forecast_item", body["id"], d)
        iid = body["id"]
    else:
        if "from_pool" not in body:  # by default a new item is allocated out of a pool above it when one has forecast left
            d["from_pool"] = 1 if _pools_left(con, pid, nid) > 0.5 else 0
        iid = db.insert(con, "forecast_item", dict(project_id=pid, node_id=nid, **d))
    if d.get("spread") == "Roster" and d.get("pattern"):
        forecast.parse_pattern(d["pattern"])  # a clear message for a pattern that cannot be read
    if body.get("days") is not None:
        forecast.save_days(con, pid, iid, body["days"])
    if body.get("milestones") is not None:
        forecast.save_milestones(con, pid, iid, body["milestones"])
    if body.get("months") is not None:
        con.execute("DELETE FROM forecast_manual WHERE node_id=? AND item_id=?", (nid, iid))
        for m, a in body["months"].items():
            if a not in (None, "", 0):
                db.insert(con, "forecast_manual", dict(project_id=pid, node_id=nid, item_id=iid, month=m[:7], amount=float(a)))
    if body.get("set_method", True):
        # items on a group forecast its (Unallocated) pool
        col = "method" if n["kind"] == "line" else "unalloc_method"
        if n.get(col) != "GROUND-UP":
            db.update(con, "cbs_node", nid, {col: "GROUND-UP"})
    return {"id": iid}


@router.get("/api/p/{pid}/items/{iid}")
def item_get(pid: int, iid: int, con=Depends(get_con)):
    it = db.one(con, "SELECT * FROM forecast_item WHERE id=? AND project_id=?", (iid, pid))
    if not it:
        raise HTTPException(404)
    ctx = forecast.load_ctx(con, pid)
    it["days"] = ctx.days.get(iid, {})
    it["milestones"] = ctx.ms.get(iid, [])
    it["rate_used"] = forecast.rate_for(ctx, it)
    it["node"] = db.one(con, "SELECT id, code, name, start_date, end_date FROM cbs_node WHERE id=?", (it["node_id"],))
    return it


@router.put("/api/p/{pid}/items/{iid}/days")
def item_days(pid: int, iid: int, body: dict, con=Depends(get_con)):
    if not db.one(con, "SELECT id FROM forecast_item WHERE id=? AND project_id=?", (iid, pid)):
        raise HTTPException(404)
    return {"days": forecast.save_days(con, pid, iid, body.get("days") or {})}


@router.post("/api/p/{pid}/items/{iid}/accrue-past")
def item_accrue_past(pid: int, iid: int, con=Depends(get_con)):
    return {"accrued_days": forecast.accrue_past(con, pid, iid)}


@router.post("/api/p/{pid}/forecast/preview")
def item_preview(pid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    item = {k: body.get(k) for k in FORECAST_ITEM_COLS + ("id", "node_id")}
    for k in ("start_date", "end_date"):
        item[k] = db.iso(item.get(k))
    if item.get("spread") == "Roster" and item.get("pattern"):
        forecast.parse_pattern(item["pattern"])
    return forecast.preview(con, pid, item, body.get("days"), body.get("milestones"))


@router.get("/api/p/{pid}/history/{metric}")
def metric_history(pid: int, metric: str, as_at: str = "live", node: str = None, con=Depends(get_con)):
    if metric not in timeline.METRICS:
        raise HTTPException(404)
    need_project(con, pid)
    return timeline.grid(con, pid, metric, as_at, node)


@router.get("/api/p/{pid}/history/{metric}/track")
def metric_track(pid: int, metric: str, node: str = None, con=Depends(get_con)):
    if metric not in timeline.METRICS:
        raise HTTPException(404)
    need_project(con, pid)
    return timeline.track(con, pid, metric, node)


@router.get("/api/p/{pid}/month-review")
def month_review(pid: int, month: str = None, con=Depends(get_con)):
    need_project(con, pid)
    return review.month_review(con, pid, month)


@router.post("/api/p/{pid}/month-review")
def month_review_decide(pid: int, body: dict, con=Depends(get_con)):
    return {"id": review.decide(con, pid, body["node_ref"], body["month"], body.get("decision"), body.get("note"))}


@router.get("/api/p/{pid}/calendar")
def labour_calendar(pid: int, start: str = None, days: int = 42, kind: str = None, node: str = None, con=Depends(get_con)):
    need_project(con, pid)
    ids = set(services.subtree_ids(con, pid, int(node))) if node and node not in ("root", "") else None
    out = forecast.calendar(con, pid, start, max(7, min(days, 1500)), kind or None, ids)  # up to the whole project (by month)
    # unassigned pools (a group's Unallocated line) with forecast left or already allocated, so they can be tied out here
    res = engine.compute(con, pid)
    out["pools"] = [dict(id=r["id"], node_id=r["node_id"], code=r["code"], name=next((g["name"] for g in res["rows"] if g["id"] == r["node_id"]), r["name"]),
                         method=r["method"], ctc=r["ctc"], drawn=r.get("pool_drawn", 0), hours=r.get("fc_hours", 0), gp=r["gp"])
                    for r in res["rows"] if r["kind"] == "pot" and (ids is None or r["node_id"] in ids) and (r["ctc"] > 0.5 or r.get("pool_drawn", 0) > 0.5)
                    and r["gp"] in ("PL", "PS")]
    return out


@router.post("/api/p/{pid}/accruals/hours")
def accrual_hours(pid: int, body: dict, con=Depends(get_con)):
    services.get_node(con, pid, int(body["node_id"]))
    n = forecast.save_hour_accruals(con, pid, int(body["resource_id"]), int(body["node_id"]), body.get("days") or {},
                                    rate=body.get("rate"), role=body.get("role"), reason=body.get("reason"), note=body.get("note"),
                                    heads=body.get("workers") or 1)
    accruals.match(con, pid)
    return {"days": n}


@router.post("/api/p/{pid}/accruals/invoice-ref")
def accrual_invoice_ref(pid: int, body: dict, con=Depends(get_con)):
    """Give a subcontractor's open hour accruals for a month (one role or all) the invoice reference that will reverse them."""
    q = "UPDATE accrual SET inv_ref=? WHERE project_id=? AND resource_id=? AND month=? AND hours IS NOT NULL AND status IN ('open','investigate')"
    args = [body.get("inv_ref") or None, pid, int(body["resource_id"]), body["month"][:7]]
    if body.get("role"):
        q += " AND COALESCE(role,'')=?"
        args.append(body["role"])
    n = con.execute(q, args).rowcount
    accruals.match(con, pid)
    return {"accruals": n}


@router.get("/api/p/{pid}/sub-timesheets/template.xlsx")
def sub_ts_template(pid: int, con=Depends(get_con)):
    need_project(con, pid)
    return _xlsx(site_files.timesheet_template(con, pid), "subcontractor-timesheets.xlsx")


@router.post("/api/p/{pid}/sub-timesheets")
async def sub_ts_upload(pid: int, file: UploadFile = File(...), replace: str = Form("0"), con=Depends(get_con)):
    need_project(con, pid)
    return site_files.import_timesheets(con, pid, await file.read(), file.filename or "", replace == "1")


@router.get("/api/p/{pid}/lookahead/template.xlsx")
def lookahead_template(pid: int, start: str = None, con=Depends(get_con)):
    need_project(con, pid)
    data, d0 = site_files.lookahead_template(con, pid, start)
    return _xlsx(data, f"3-week-lookahead-{d0}.xlsx")


@router.post("/api/p/{pid}/lookahead")
async def lookahead_upload(pid: int, file: UploadFile = File(...), con=Depends(get_con)):
    need_project(con, pid)
    return site_files.import_lookahead(con, pid, await file.read(), file.filename or "")


@router.get("/api/p/{pid}/sub-timesheets")
def sub_ts_list(pid: int, month: str = None, con=Depends(get_con)):
    q = ("SELECT t.*, r.code, r.name, n.code ncode FROM sub_timesheet t LEFT JOIN resource r ON r.id=t.resource_id LEFT JOIN cbs_node n ON n.id=t.node_id "
         "WHERE t.project_id=?")
    args = [pid]
    if month:
        q += " AND t.day LIKE ?"
        args.append(month[:7] + "%")
    return db.rows(con, q + " ORDER BY t.day DESC, r.name, t.worker LIMIT 2000", args)


@router.get("/api/p/{pid}/rate")
def rate_lookup(pid: int, resource_id: int = None, role: str = None, con=Depends(get_con)):
    return forecast.rate_for(forecast.load_ctx(con, pid), dict(resource_id=resource_id, role=role, rate_mode="auto"))


@router.get("/api/p/{pid}/supplier-rates")
def srates(pid: int, con=Depends(get_con)):
    return db.rows(con, "SELECT s.*, r.code, r.name FROM supplier_rate s LEFT JOIN resource r ON r.id=s.resource_id WHERE s.project_id=? ORDER BY r.name, s.role", (pid,))


@router.post("/api/p/{pid}/supplier-rates")
def srate_save(pid: int, body: dict, con=Depends(get_con)):
    d = {k: body.get(k) for k in ("resource_id", "role", "unit", "rate", "ot_rate", "nt_hours", "allowance", "ref", "valid_from", "note")}
    if not d.get("role"):
        raise services.Problem("Enter the role, for example Electrician")
    if not d.get("resource_id"):
        raise services.Problem("Choose the supplier")
    d["valid_from"] = db.iso(d.get("valid_from"))
    for k in ("rate", "ot_rate", "nt_hours", "allowance"):
        d[k] = None if d.get(k) in (None, "") else float(d[k])
    if body.get("id"):
        db.update(con, "supplier_rate", int(body["id"]), d)
        return {"id": body["id"]}
    return {"id": db.insert(con, "supplier_rate", dict(project_id=pid, **d))}


@router.delete("/api/p/{pid}/supplier-rates/{sid}")
def srate_del(pid: int, sid: int, con=Depends(get_con)):
    con.execute("DELETE FROM supplier_rate WHERE id=? AND project_id=?", (sid, pid))
    return {"ok": True}


@router.get("/api/p/{pid}/holidays")
def hol_list(pid: int, con=Depends(get_con)):
    return db.rows(con, "SELECT * FROM holiday WHERE project_id=? ORDER BY day", (pid,))


@router.post("/api/p/{pid}/holidays")
def hol_save(pid: int, body: dict, con=Depends(get_con)):
    """One holiday, or a range of years: source "internet" pulls them from the Nager.Date public holiday API (needs internet),
    "standard" uses the built-in Queensland list (2024 to 2035, works offline). Days already in the project are kept, not doubled."""
    src = "internet" if body.get("internet") else "standard" if body.get("standard") else None
    if src:
        try:
            y0, y1 = holidays.check_range(body.get("from_year") or 2024, body.get("to_year") or 2035)
        except (ValueError, TypeError) as e:
            raise services.Problem(str(e))
        found, errors, years = [], [], []
        if src == "internet":
            for y in range(y0, y1 + 1):
                try:
                    found += holidays.fetch_year(y)
                    years.append(y)
                except Exception as e:  # noqa: BLE001  (no internet, a blocked address, a year the service does not have)
                    errors.append(f"{y}: {str(e)[:80]}")
            if not years:
                raise services.Problem("Could not reach the public holiday service (" + (errors[0] if errors else "no answer") + "). Check the internet connection, or use the built-in list.")
        else:
            found, years = holidays.bundled(y0, y1), list(range(y0, y1 + 1))
        have = {r["day"] for r in con.execute("SELECT day FROM holiday WHERE project_id=?", (pid,))}
        n = 0
        for d, name in found:
            if d not in have:
                db.insert(con, "holiday", dict(project_id=pid, day=d, name=name))
                have.add(d)
                n += 1
        return {"added": n, "years": years, "errors": errors, "source": src}
    d = db.iso(body.get("day"))
    if not d:
        raise services.Problem("Enter a date")
    return {"id": db.insert(con, "holiday", dict(project_id=pid, day=d, name=body.get("name")))}


@router.delete("/api/p/{pid}/holidays/{hid}")
def hol_del(pid: int, hid: int, con=Depends(get_con)):
    con.execute("DELETE FROM holiday WHERE id=? AND project_id=?", (hid, pid))
    return {"ok": True}


def _pools_left(con, pid, nid):
    res = engine.compute(con, pid)
    by = {str(r["id"]): r for r in res["rows"]}
    return sum(by[f"p{a['id']}"]["ctc"] for a in services.ancestors(con, pid, nid)[1:] if f"p{a['id']}" in by)


@router.delete("/api/p/{pid}/items/{iid}")
def item_delete(pid: int, iid: int, con=Depends(get_con)):
    con.execute("DELETE FROM forecast_manual WHERE item_id=? AND project_id=?", (iid, pid))
    con.execute("DELETE FROM forecast_item WHERE id=? AND project_id=?", (iid, pid))
    return {"ok": True}


@router.put("/api/p/{pid}/nodes/{nid}/manual")
def manual_save(pid: int, nid: int, body: dict, con=Depends(get_con)):
    services.get_node(con, pid, nid)
    con.execute("DELETE FROM forecast_manual WHERE node_id=? AND item_id IS NULL", (nid,))
    for m, a in (body.get("months") or {}).items():
        if a not in (None, "", 0):
            db.insert(con, "forecast_manual", dict(project_id=pid, node_id=nid, item_id=None, month=m[:7], amount=float(a)))
    if body.get("set_method", True):
        db.update(con, "cbs_node", nid, {"method": "MANUAL"})
    return {"ok": True}


@router.post("/api/p/{pid}/nodes/{nid}/forecast-move")
def forecast_move(pid: int, nid: int, body: dict, con=Depends(get_con)):
    """Drag a month's forecast to another month, earlier or later but not before the status month. The line must forecast from typed
    months (MANUAL); with convert=true a BURN-RATE, AT-BUDGET, AT-COMMIT or TOP-DOWN line is first turned into typed months at its current forecast."""
    node = services.get_node(con, pid, nid)
    if node["kind"] != "line":
        raise services.Problem("Only a CBS line can be moved")
    res = engine.compute(con, pid)
    M, grid = res["status_month"], res["grid"]
    src, dst = (body.get("src") or "")[:7], (body.get("dst") or "")[:7]
    if not src or not dst or src == dst:
        raise services.Problem("Drop the amount on another month")
    if src < M or dst < M:
        raise services.Problem(f"Forecast can only move between the status month ({M}) and later months, not the past")
    method = node["method"] or "AT-BUDGET"
    if method in ("GROUND-UP", "CLAIM"):
        raise services.Problem(f"{method} lines are built from their items or the claim schedule: change them there, or switch the line to MANUAL first")
    if method != "MANUAL":
        if not body.get("convert"):
            raise services.Problem(f"This line forecasts by {method}. Moving an amount turns it into typed months (MANUAL).")
        row = next((r for r in res["rows"] if r["id"] == nid), None)
        con.execute("DELETE FROM forecast_manual WHERE node_id=? AND item_id IS NULL", (nid,))
        for i, m in enumerate(grid):
            if m >= M and row and abs(row["f"][i]) > 0.005:
                db.insert(con, "forecast_manual", dict(project_id=pid, node_id=nid, item_id=None, month=m, amount=round(row["f"][i], 2)))
        db.update(con, "cbs_node", nid, {"method": "MANUAL"})
    cur = {r["month"]: r["amount"] for r in db.rows(con, "SELECT month, amount FROM forecast_manual WHERE node_id=? AND item_id IS NULL", (nid,))}
    amount = cur.get(src, 0.0)
    if abs(amount) < 0.005:
        raise services.Problem(f"There is no forecast in {src} to move")
    cur[dst] = round(cur.get(dst, 0.0) + amount, 2)
    cur[src] = 0.0
    con.execute("DELETE FROM forecast_manual WHERE node_id=? AND item_id IS NULL", (nid,))
    for m, a in cur.items():
        if abs(a) > 0.005:
            db.insert(con, "forecast_manual", dict(project_id=pid, node_id=nid, item_id=None, month=m, amount=a))
    return {"moved": amount, "src": src, "dst": dst, "converted": method != "MANUAL"}


@router.post("/api/p/{pid}/nodes/{nid}/forecast-set")
def forecast_set(pid: int, nid: int, body: dict, con=Depends(get_con)):
    """Type, change or clear one month of a line's forecast, as $ or as a % of what is left to forecast (a % only where the method has
    such a pool: AT-BUDGET = allowance less spent and accrued, AT-COMMIT = outstanding commitment plus uncommitted). Other methods are
    turned into typed months (MANUAL) first, with convert=true. Returns what was there before, so the page can undo it."""
    node = services.get_node(con, pid, nid)
    if node["kind"] != "line":
        raise services.Problem("Only a CBS line has a monthly forecast")
    res = engine.compute(con, pid)
    M, grid = res["status_month"], res["grid"]
    month = (body.get("month") or "")[:7]
    if month not in grid or month < M:
        raise services.Problem(f"Forecast can be typed from the status month ({M}) onwards")
    method = node["method"] or "AT-BUDGET"
    row = next((r for r in res["rows"] if r["id"] == nid), None) or {}
    unit = body.get("unit") or "$"
    if body.get("clear"):
        amount = 0.0
    elif unit == "%":
        pool = {"AT-BUDGET": max(0.0, (row.get("allowance") or 0) - (row.get("ctd") or 0) - (row.get("acc") or 0)),
                "AT-COMMIT": (row.get("outstanding") or 0) + (node.get("uncommitted") or 0)}.get(method)
        if pool is None:
            raise services.Problem(f"A % only makes sense on AT-BUDGET and AT-COMMIT lines (a share of what is left to forecast). This line forecasts by {method}: type a $ amount.")
        amount = round(pool * float(body.get("value") or 0) / 100.0, 2)
    else:
        amount = round(float(body.get("value") or 0), 2)
    before = {"method": method, "months": {r["month"]: r["amount"] for r in db.rows(con, "SELECT month, amount FROM forecast_manual WHERE node_id=? AND item_id IS NULL", (nid,))}}
    if method != "MANUAL":
        if not body.get("convert"):
            raise services.Problem(f"This line forecasts by {method}. Typing a month turns it into typed months (MANUAL).")
        cur = {m: round(row["f"][i], 2) for i, m in enumerate(grid) if m >= M and row.get("f") and abs(row["f"][i]) > 0.005}
        db.update(con, "cbs_node", nid, {"method": "MANUAL"})
    else:
        cur = {m: a for m, a in before["months"].items() if m >= M}
    cur[month] = amount
    con.execute("DELETE FROM forecast_manual WHERE node_id=? AND item_id IS NULL AND month>=?", (nid, M))
    for m, a in cur.items():
        if abs(a) > 0.005:
            db.insert(con, "forecast_manual", dict(project_id=pid, node_id=nid, item_id=None, month=m, amount=a))
    return {"amount": amount, "before": before, "converted": method != "MANUAL"}


@router.post("/api/p/{pid}/nodes/{nid}/forecast-restore")
def forecast_restore(pid: int, nid: int, body: dict, con=Depends(get_con)):
    """Put a line's typed forecast back as it was (what forecast-set returned in 'before')."""
    services.get_node(con, pid, nid)
    before = body.get("before") or {}
    con.execute("DELETE FROM forecast_manual WHERE node_id=? AND item_id IS NULL", (nid,))
    for m, a in (before.get("months") or {}).items():
        db.insert(con, "forecast_manual", dict(project_id=pid, node_id=nid, item_id=None, month=str(m)[:7], amount=float(a)))
    if before.get("method"):
        db.update(con, "cbs_node", nid, {"method": before["method"]})
    return {"ok": True}


@router.get("/api/p/{pid}/accruals")
def accrual_list(pid: int, con=Depends(get_con)):
    accruals.match(con, pid)
    rows = db.rows(con, "SELECT a.*, n.code, n.name FROM accrual a JOIN cbs_node n ON n.id=a.node_id WHERE a.project_id=? ORDER BY a.month DESC, a.id DESC", (pid,))
    st = activity.stamps(con, "accrual", [r["id"] for r in rows])
    for r in rows:
        r.update(st.get(r["id"], {}))
    ts = db.rows(con, f"SELECT l.node_id, n.code, n.name, l.month, l.resource_code, l.name AS person, SUM(l.hours) hours, SUM({accruals.UNPOSTED_COST}) amount, MIN(l.status) status "
                      f"FROM pronto_labour l LEFT JOIN cbs_node n ON n.id=l.node_id WHERE l.project_id=? AND l.posted=0 AND {accruals.UNPOSTED_NOT_ACCRUED} "
                      "GROUP BY l.node_id, l.month, l.resource_code", (pid,))
    claims = subcontracts.claim_accruals(con, pid, accruals.landed_refs(con, pid))
    nodes = {r["id"]: r for r in db.rows(con, "SELECT id, code, name FROM cbs_node WHERE project_id=?", (pid,))}
    for c in claims:
        c["code"], c["name"] = nodes[c["node_id"]]["code"], nodes[c["node_id"]]["name"]
    for r in rows:
        r["kind"] = accruals._kind(r)
        r["cover"] = 0.0
    cover = accruals.pronto_cover(con, pid)
    for r in rows:
        r["cover"] = round(cover.get(r["id"], 0.0), 2)
    unp, reqs = accruals.unposted(con, pid)
    pr = accruals.pronto_accruals(con, pid)
    hints = accruals.estimate_hints(con, pid, rows)
    for r in rows:
        r["hint"] = hints.get(r["id"], "")
    return dict(manual=rows, timesheets=ts, claims=claims, pronto=pr, unposted=unp, requests=reqs, kinds=accruals.KINDS,
                landings=accruals.claim_landings(con, pid))


def _accrual_checks(con, pid, body, aid=None):
    """Warnings before saving an accrual; raises when there is nothing to accrue (the invoice is already in Pronto)."""
    warn = []
    nid = int(body["node_id"])
    if body.get("inv_ref"):
        landed = accruals.already_landed(con, pid, body["inv_ref"])
        if landed and not body.get("force"):
            i = landed[0]
            raise services.Problem(f"Invoice {body['inv_ref']} is already in Pronto ({i['ref']}, {i['date']}, {i['amount']:,.2f}): it counts as an actual, nothing to accrue.")
        dup = [a for a in db.rows(con, "SELECT * FROM accrual WHERE project_id=? AND status IN ('open','partial') AND id!=?", (pid, aid or 0))
               if accruals._n(a["inv_ref"]) and accruals._n(a["inv_ref"]) == accruals._n(body["inv_ref"])]
        if dup:
            warn.append(f"Invoice {body['inv_ref']} is already accrued ({len(dup)} open accrual(s), {sum(a['amount'] for a in dup):,.2f}).")
    for p in accruals.overlaps(con, pid, nid, body.get("po_no"), body.get("inv_ref"), body.get("supplier_name")):
        warn.append(f"Finance already accrued {p['open']:,.2f} for {p['supplier']} ({p['reference'] or 'no reference'}, {p['month']}) in Pronto on this line. "
                    "PMT counts only the part of your accrual above it.")
    return warn


@router.get("/api/p/{pid}/accruals/master")
def accrual_master(pid: int, con=Depends(get_con)):
    """Every accrual from every source in one list, with the parties (companies and employees) to filter by."""
    need_project(con, pid)
    accruals.match(con, pid)
    return accruals.master(con, pid)


@router.get("/api/p/{pid}/accruals/people")
def accrual_people(pid: int, category: str = "", month: str = "", resource_code: str = "", con=Depends(get_con)):
    """The people behind a payroll accrual or an unposted timesheet line: hours, posted cost and unposted cost for the category and month."""
    need_project(con, pid)
    rows = accruals.timesheet_people(con, pid, category, month[:7])
    if resource_code:
        rows = [r for r in rows if r["resource_code"] == resource_code]
    return rows


@router.post("/api/p/{pid}/accruals/check")
def accrual_check(pid: int, body: dict, con=Depends(get_con)):
    try:
        return {"warnings": _accrual_checks(con, pid, body, body.get("id")), "error": None}
    except services.Problem as e:
        return {"warnings": [], "error": str(e)}


@router.post("/api/p/{pid}/accruals")
def accrual_save(pid: int, body: dict, con=Depends(get_con)):
    services.get_node(con, pid, int(body["node_id"]))
    d = dict(node_id=int(body["node_id"]), month=(body.get("month") or "")[:7], amount=float(body.get("amount") or 0),
             source=body.get("source") or "PM", po_no=body.get("po_no") or None, inv_ref=body.get("inv_ref") or None, reason=body.get("reason"),
             note=body.get("note"), status=body.get("status") or "open", risk_id=body.get("risk_id") or None,
             kind=body.get("kind") or ("invoice" if body.get("inv_ref") or body.get("quote_ref") else "work"),
             supplier_code=body.get("supplier_code") or None, supplier_name=body.get("supplier_name") or None, quote_ref=body.get("quote_ref") or None)
    if not d["month"]:
        raise services.Problem("Month is required")
    if d["kind"] == "invoice" and not (d["inv_ref"] or d["po_no"] or d["quote_ref"]):
        raise services.Problem("An invoice accrual needs its invoice, PO or quote number, so it can match the invoice when it lands in Pronto")
    warn = _accrual_checks(con, pid, body, body.get("id"))
    if body.get("id"):
        why = _reason(body.get("change_reason"))   # a correction needs its reason: it shows in the accrual's history and in Activity and history
        d.pop("status")
        with changelog.via(f"Reason: {why}"):
            db.update(con, "accrual", body["id"], d)
        aid = body["id"]
    else:
        aid = db.insert(con, "accrual", dict(project_id=pid, **d))
    accruals.match(con, pid)
    return {"id": aid, "warnings": warn}


@router.post("/api/p/{pid}/accruals/{aid}/resolve")
def accrual_resolve(pid: int, aid: int, body: dict, con=Depends(get_con)):
    """The invoice landed for a different amount: accept it (the accrual is trued up to the invoice) or keep the rest of
    the work accrued (it is still to be invoiced)."""
    res = body.get("resolution")
    if res not in ("accept", "rest_open", None):
        raise services.Problem("Choose accept or rest_open")
    db.update(con, "accrual", aid, {"resolution": res})
    accruals.match(con, pid)
    return {"ok": True}


@router.post("/api/p/{pid}/timesheet-requests")
def timesheet_request(pid: int, body: dict, con=Depends(get_con)):
    """Ask for unposted hours to be journalled to another project: they stop accruing here while the request is open."""
    if not body.get("resource_code") or not body.get("date_from") or not body.get("date_to"):
        raise services.Problem("Person and dates are required")
    rid = db.insert(con, "timesheet_request", dict(project_id=pid, resource_code=body["resource_code"], person=body.get("person"), date_from=body["date_from"][:10],
                                                  date_to=body["date_to"][:10], hours=body.get("hours"), target=body.get("target"), note=body.get("note")))
    db.bump(con, pid)
    return {"id": rid}


@router.put("/api/p/{pid}/timesheet-requests/{rid}")
def timesheet_request_status(pid: int, rid: int, body: dict, con=Depends(get_con)):
    st = body.get("status")
    if st not in ("requested", "done", "withdrawn"):
        raise services.Problem("Unknown status")
    db.update(con, "timesheet_request", rid, {"status": st})
    db.bump(con, pid)
    return {"ok": True}


@router.post("/api/p/{pid}/accruals/unposted")
def accrue_unposted(pid: int, body: dict, con=Depends(get_con)):
    """Accrue a person's unposted timesheet hours for a month on their line (hours x their rate), day by day."""
    res = db.one(con, "SELECT * FROM resource WHERE project_id=? AND kind='employee' AND code=?", (pid, body["resource_code"]))
    if not res:
        raise services.Problem("This person is not in the resources yet: add them (Resources and rates) with a cost rate")
    days = defaultdict(float)
    for r in con.execute("SELECT date_worked, SUM(hours) h FROM pronto_labour WHERE project_id=? AND posted=0 AND resource_code=? AND month=? AND node_id IS ? GROUP BY date_worked",
                         (pid, body["resource_code"], body["month"][:7], body.get("node_id"))):
        days[r["date_worked"]] += r["h"] or 0
    if not days:
        raise services.Problem("No unposted hours left for that month")
    n = forecast.save_hour_accruals(con, pid, res["id"], int(body["node_id"]), dict(days), reason="Unposted timesheet", note=body.get("note"))
    accruals.match(con, pid)
    return {"days": n}


@router.get("/api/p/{pid}/accruals/timelines")
def accrual_timelines(pid: int, group: str = "", con=Depends(get_con)):
    """Cost by month three ways: work performed, billed, paid (see accruals.timelines)."""
    accruals.match(con, pid)
    return accruals.timelines(con, pid, group or None)


@router.delete("/api/p/{pid}/accruals/{aid}")
def accrual_delete(pid: int, aid: int, reason: str = "", con=Depends(get_con)):
    why = _reason(reason)
    with changelog.via(f"Reason: {why}"):
        con.execute("DELETE FROM accrual WHERE id=? AND project_id=?", (aid, pid))
    return {"ok": True}


@router.get("/api/p/{pid}/commitments")
def commitments(pid: int, open_only: int = 0, con=Depends(get_con)):
    q = ("SELECT p.order_no, MAX(p.supplier_name) supplier, MAX(p.supplier_code) supplier_code, MAX(p.status) status, MAX(p.order_type) order_type, "
         "MIN(p.ordered) ordered, MAX(p.category) category, SUM(p.committed) committed, SUM(p.received) received, "
         "SUM(CASE WHEN p.is_open THEN MAX(0, p.committed - p.received) ELSE 0 END) outstanding, MAX(p.is_open) is_open, "
         "MIN(p.node_id) node_id, MAX(n.code) node_code, MAX(n.name) node_name, MAX(n.kind) node_kind "
         "FROM pronto_po p LEFT JOIN cbs_node n ON n.id=p.node_id WHERE p.project_id=? GROUP BY p.order_no")
    rows = db.rows(con, q, (pid,))
    if open_only:
        rows = [r for r in rows if r["is_open"]]
    return rows


# ---------------------------------------------------------------------------
# Risk: register, buckets, tagging, releases, close-out
# ---------------------------------------------------------------------------
@router.get("/api/p/{pid}/risk")
def risk_list(pid: int, con=Depends(get_con)):
    need_project(con, pid)
    res = engine.compute(con, pid)
    pos = risk_mod.positions(con, pid, res)
    sm = lambda k: sum(x[k] for x in pos)
    return dict(risks=risk_mod.register(con, pid, res), positions=pos, summary=risk_mod.summary(con, pid, res), view=res["allowance_view"],
                totals=dict(orig_risk=sm("orig_risk"), bucket=sm("bucket"), released=sm("released"), remaining=sm("bucket_remaining"), occurred=sm("occurred"),
                            tagged=sm("tagged"), uncovered=sm("uncovered"), uncovered_landed=sm("uncovered_landed"), saved=sm("over_covered"), contingency=sm("contingency"), cover=sm("cover"), infused=sm("infused"),
                            from_contingency=sm("from_contingency"), step_contingency=sm("step_contingency"), step_release=sm("step_release"), step_infuse=sm("step_infuse")))


@router.post("/api/p/{pid}/risk")
def risk_save(pid: int, body: dict, con=Depends(get_con)):
    d = {k: body.get(k) for k in ("ref", "title", "description", "cause", "owner", "status", "raised_date", "note", "kind", "category", "area", "consequences", "basis",
                                  "trigger_event", "controls", "treatment", "estimate", "likelihood", "control_cost", "effectiveness", "last_reviewed", "retire_date", "comment", "delay_days", "delay_actual", "revenue_impact", "revenue_actual") if k in body}
    for k in ("raised_date", "last_reviewed", "retire_date"):
        if d.get(k):
            d[k] = db.iso(d[k])
    for k in ("estimate", "likelihood", "control_cost", "effectiveness", "delay_days", "delay_actual", "revenue_impact", "revenue_actual"):
        if k in d:
            d[k] = float(d[k] or 0)
    if d.get("status") and d["status"] not in ("open", "materialised", "ceased"):
        raise services.Problem("Status must be open, materialised or ceased")
    if body.get("id"):
        db.update(con, "risk", body["id"], d)
        return {"id": body["id"]}
    if not d.get("title"):
        raise services.Problem("Give the risk a title")
    d["ref"] = (d.get("ref") or risk_mod.next_ref(con, pid)).strip().upper()
    if db.one(con, "SELECT 1 x FROM risk WHERE project_id=? AND ref=?", (pid, d["ref"])):
        raise services.Problem(f"{d['ref']} already exists")
    return {"id": db.insert(con, "risk", dict(project_id=pid, **d)), "ref": d["ref"]}


@router.post("/api/p/{pid}/risk/import")
async def risk_import(pid: int, file: UploadFile = File(...), con=Depends(get_con)):
    need_project(con, pid)
    tmp = UPLOADS / f"risk-{secrets.token_hex(6)}{Path(file.filename or '').suffix.lower() or '.xlsx'}"
    with open(tmp, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        return risk_mod.import_register(con, pid, tmp)
    finally:
        _rm(tmp)


@router.delete("/api/p/{pid}/risk/{rid}")
def risk_delete(pid: int, rid: int, con=Depends(get_con)):
    con.execute("UPDATE accrual SET risk_id=NULL WHERE risk_id=?", (rid,))
    con.execute("UPDATE forecast_item SET risk_id=NULL WHERE risk_id=?", (rid,))
    con.execute("DELETE FROM risk WHERE id=? AND project_id=?", (rid, pid))
    return {"ok": True}


@router.get("/api/p/{pid}/risk/buckets")
def risk_buckets(pid: int, con=Depends(get_con)):
    return dict(rows=risk_mod.buckets(con, pid), risks=db.rows(con, "SELECT id, ref, title, status FROM risk WHERE project_id=? ORDER BY ref", (pid,)))


@router.put("/api/p/{pid}/risk/alloc")
def risk_alloc(pid: int, body: dict, con=Depends(get_con)):
    amt = float(body.get("amount") or 0)
    con.execute("DELETE FROM risk_alloc WHERE risk_id=? AND node_id=?", (body["risk_id"], body["node_id"]))
    if amt:
        db.insert(con, "risk_alloc", dict(project_id=pid, risk_id=int(body["risk_id"]), node_id=int(body["node_id"]), amount=amt))
    return {"ok": True}


@router.get("/api/p/{pid}/risk/transactions")
def risk_transactions(pid: int, node: str = None, q: str = None, tagged: str = None, limit: int = 300, con=Depends(get_con)):
    where, args = ["x.project_id=?", "x.class IN ('actual','journal')"], [pid]
    if node:
        ids = services.subtree_ids(con, pid, int(node))
        where.append(f"x.node_id IN ({','.join('?' * len(ids))})")
        args += ids
    if q:
        where.append("(x.description LIKE ? OR x.reference LIKE ? OR x.account_desc LIKE ? OR x.doc_no LIKE ?)")
        args += [f"%{q}%"] * 4
    if tagged == "yes":
        where.append("EXISTS (SELECT 1 FROM risk_tag g WHERE g.project_id=x.project_id AND g.row_hash=x.row_hash)")
    elif tagged == "no":
        where.append("NOT EXISTS (SELECT 1 FROM risk_tag g WHERE g.project_id=x.project_id AND g.row_hash=x.row_hash)")
    w = " AND ".join(where)
    rows = db.rows(con, f"SELECT x.id, x.row_hash, x.tx_date, x.doc_type, x.reference, x.description, x.account_desc, x.cost, x.node_id, n.code node_code FROM pronto_tx x "
                        f"LEFT JOIN cbs_node n ON n.id=x.node_id WHERE {w} ORDER BY x.tx_date DESC, x.id DESC LIMIT ?", args + [limit])
    tags = {}
    for t in db.rows(con, "SELECT g.id, g.row_hash, g.risk_id, g.amount, r.ref FROM risk_tag g JOIN risk r ON r.id=g.risk_id WHERE g.project_id=?", (pid,)):
        tags.setdefault(t["row_hash"], []).append(t)
    for r in rows:
        r["tags"] = tags.get(r["row_hash"], [])
    return rows


@router.post("/api/p/{pid}/risk/tag")
def risk_tag(pid: int, body: dict, con=Depends(get_con)):
    rid = int(body["risk_id"])
    for h in body.get("row_hashes") or [body.get("row_hash")]:
        if not h:
            continue
        con.execute("DELETE FROM risk_tag WHERE project_id=? AND row_hash=? AND risk_id=?", (pid, h, rid))
        db.insert(con, "risk_tag", dict(project_id=pid, risk_id=rid, row_hash=h, amount=body.get("amount"), note=body.get("note")))
    return {"ok": True}


@router.delete("/api/p/{pid}/risk/tag/{tid}")
def risk_untag(pid: int, tid: int, con=Depends(get_con)):
    con.execute("DELETE FROM risk_tag WHERE id=? AND project_id=?", (tid, pid))
    return {"ok": True}


@router.get("/api/p/{pid}/risk/tagged")
def risk_tagged(pid: int, risk_id: int = None, con=Depends(get_con)):
    res = engine.compute(con, pid)
    names = {r["id"]: f"{r['code']} {r['name']}" for r in res["rows"] if isinstance(r["id"], int)}
    out = [t for t in risk_mod.tagged_costs(con, pid, res["status_month"]) if not risk_id or t["risk_id"] == risk_id]
    for t in out:
        t["node"] = names.get(t["node_id"], "")
    return sorted(out, key=lambda t: (t["month"], t["kind"]))


@router.get("/api/p/{pid}/risk/releases")
def risk_releases(pid: int, con=Depends(get_con)):
    return db.rows(con, "SELECT r.*, s.code source_code, s.name source_name, t.code target_code, t.name target_name FROM risk_release r "
                        "LEFT JOIN cbs_node s ON s.id=r.source_node_id JOIN cbs_node t ON t.id=r.target_node_id WHERE r.project_id=? ORDER BY r.id DESC", (pid,))


@router.post("/api/p/{pid}/risk/fund")
def risk_fund(pid: int, body: dict, con=Depends(get_con)):
    """Fund materialised risk cost: kind = contingency (PM transfer) | release (company bucket) | infuse (new company funds)."""
    kind, target, amt = body.get("kind"), int(body["target_node_id"]), body.get("amount")
    d, by, ref, note, force = db.iso(body.get("date")), body.get("approved_by"), body.get("ref"), body.get("note"), bool(body.get("force"))
    if kind == "contingency":
        rid = risk_mod.contingency_to_risk(con, pid, int(body.get("source_node_id") or target), target, amt, d, by, ref, note, force)
    elif kind == "release":
        rid = risk_mod.release(con, pid, target, amt, body.get("source_node_id"), d, by, ref, note, force)
    elif kind == "infuse":
        rid = risk_mod.infuse(con, pid, target, amt, d, by, ref, note, force)
    else:
        raise services.Problem("Unknown funding type")
    return {"id": rid}


@router.post("/api/p/{pid}/risk/contingency")
def risk_contingency(pid: int, body: dict, con=Depends(get_con)):
    risk_mod.set_contingency(con, pid, int(body["node_id"]), body.get("amount"))
    return {"ok": True}


@router.delete("/api/p/{pid}/risk/releases/{rid}")
def risk_release_undo(pid: int, rid: int, con=Depends(get_con)):
    risk_mod.reverse_release(con, pid, rid)
    return {"ok": True}


@router.get("/api/p/{pid}/risk/closeout")
def risk_closeout(pid: int, con=Depends(get_con)):
    co = risk_mod.closeout(con, pid)
    return dict(**co, by_risk=risk_mod.closeout_by_event(con, pid, None, co))


@router.get("/api/p/{pid}/risk/closeout.xlsx")
def risk_closeout_xlsx(pid: int, con=Depends(get_con)):
    return _xlsx(exporters.risk_closeout_xlsx(con, pid), "risk-closeout-estimator-feedback.xlsx")


@router.get("/api/p/{pid}/pools/allocation")
def pools_preview(pid: int, con=Depends(get_con)):
    """Transfers that would move allowance from each unallocated pool to the lines whose cost it is covering (nothing is changed)."""
    need_project(con, pid)
    moves = pools.plan(con, pid)
    return {"moves": moves, "total": round(sum(m["amount"] for m in moves), 2)}


@router.post("/api/p/{pid}/pools/method")
def pools_method(pid: int, body: dict, con=Depends(get_con)):
    """Set the forecast method of every unallocated pool at once (NONE keeps them out of the forecast)."""
    need_project(con, pid)
    method = body.get("method") or "NONE"
    if method not in METHODS:
        raise services.Problem("Unknown forecast method")
    n = con.execute("UPDATE cbs_node SET unalloc_method=? WHERE project_id=? AND kind='group' AND COALESCE(unalloc_method,'')!=?", (method, pid, method)).rowcount
    db.bump(con, pid)
    return {"updated": n}


@router.post("/api/p/{pid}/ctc-lines")
def ctc_lines(pid: int, con=Depends(get_con)):
    need_project(con, pid)
    made = services.ensure_ctc_lines(con, pid)
    if made:
        pronto.resolve_all(con, pid)
    return {"created": made}


@router.post("/api/p/{pid}/pools/allocation")
def pools_allocate(pid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    groups = body.get("groups")
    moves = pools.allocate(con, pid, set(int(x) for x in groups) if groups is not None else None)
    return {"moves": moves, "total": round(sum(m["amount"] for m in moves), 2)}


@router.get("/api/p/{pid}/allowance/overview")
def allowance_overview(pid: int, con=Depends(get_con)):
    need_project(con, pid)
    return allowance.overview(con, pid)


def _link_args(body):
    return dict(bucket_id=body.get("bucket_id"), kind=body.get("kind") or "supplier", code=body.get("code"), option=int(body.get("option") or 0),
                amount=body.get("amount") or 0, name=body.get("name"), function=body.get("function"), line_id=body.get("line_id"))


@router.get("/api/p/{pid}/allowance/preview")
def allowance_preview(pid: int, bucket_id: int = None, kind: str = "supplier", code: str = None, option: int = 0, amount: float = 0,
                      name: str = None, line_id: int = None, con=Depends(get_con)):
    """What a link would do (nothing is changed)."""
    need_project(con, pid)
    return allowance.link(con, pid, bucket_id, kind, code, option, amount, name=name, line_id=line_id, dry=True)


@router.post("/api/p/{pid}/allowance/link-many")
def allowance_link_many(pid: int, body: dict, con=Depends(get_con)):
    """One action on several resources: option 2 (cover the cost so far) into each resource's own suggested bucket, or the one given."""
    need_project(con, pid)
    return allowance.link_many(con, pid, body.get("rows") or [], int(body.get("option") or 2), body.get("bucket_id"))


@router.post("/api/p/{pid}/allowance/link")
def allowance_link(pid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    return allowance.link(con, pid, **_link_args(body))


@router.get("/api/p/{pid}/review-deadline")
def review_deadline_get(pid: int, submitted: str = "", con=Depends(get_con)):
    """The client's review deadline for a claim submitted on `submitted`, from the contract's review period (on the project card)."""
    p = need_project(con, pid)
    return {"deadline": revenue.review_deadline(con, p, submitted or None), "days": p.get("review_days"), "basis": p.get("review_basis") or "business"}


# ---------------------------------------------------------------------------
# Optional programme: MS Project XML, Excel/CSV or PDF
# ---------------------------------------------------------------------------
@router.post("/api/p/{pid}/programme/upload")
async def programme_upload(pid: int, file: UploadFile = File(...), layer: str = "internal", con=Depends(get_con)):
    need_project(con, pid)
    if layer not in ("internal", "upstream"):
        raise HTTPException(400, "layer must be internal or upstream")
    suffix = Path(file.filename or "").suffix.lower()
    tmp = UPLOADS / f"prog-{secrets.token_hex(6)}{suffix}"
    with open(tmp, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        raw = tmp.read_bytes()
        source, tasks = programme.parse(tmp, file.filename or "")
    finally:
        _rm(tmp)
    con.execute("DELETE FROM programme_file WHERE project_id=? AND layer=?", (pid, layer))
    if len(raw) <= 15 * 1024 * 1024:
        db.insert(con, "programme_file", dict(project_id=pid, layer=layer, filename=file.filename, mime=mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream",
                                              size=len(raw), data=base64.b64encode(raw).decode(), uploaded_by=(identity.current() or {}).get("name"), uploaded_at=datetime.now().isoformat(timespec="seconds")))
    # links to CBS lines and claim items survive a new upload: matched by WBS and name, else by name alone
    keep, keep_name = {}, {}
    for o in db.rows(con, "SELECT wbs, name, link_item_id, link_node_id FROM programme_task WHERE project_id=? AND COALESCE(layer,'internal')=? "
                          "AND (link_item_id IS NOT NULL OR link_node_id IS NOT NULL)", (pid, layer)):
        keep[(o["wbs"], o["name"])] = o
        keep_name.setdefault(o["name"], o)
    con.execute("DELETE FROM programme_task WHERE project_id=? AND COALESCE(layer,'internal')=?", (pid, layer))
    relinked = 0
    for i, t in enumerate(tasks):
        old = keep.get((t.get("wbs"), t.get("name"))) or keep_name.get(t.get("name"))
        extra = dict(link_item_id=old["link_item_id"], link_node_id=old["link_node_id"]) if old else {}
        relinked += 1 if old else 0
        db.insert(con, "programme_task", dict(project_id=pid, source=source, seq=i, layer=layer, **t, **extra))
    s = db.project_settings(con, pid)
    s["programme_file" if layer == "internal" else "programme_file_upstream"] = dict(name=file.filename, source=source, tasks=len(tasks))
    db.update(con, "project", pid, {"settings_json": json.dumps(s)})
    linked = programme.suggest(con, pid) if layer == "internal" else 0
    windows = programme.apply(con, pid, targets=("costs",)) if layer == "internal" else {}     # the activity windows follow the schedule
    programme.apply(con, pid, targets=("claims",))                                              # and so do claim lines linked to tasks
    return {"tasks": len(tasks), "source": source, "auto_linked": linked, "relinked": relinked,
            "windows": windows.get("nodes", 0), "windows_kept": windows.get("kept", 0), "warnings": windows.get("warnings", [])}


@router.get("/api/p/{pid}/programme/file")
def programme_file(pid: int, layer: str = "internal", info: int = 0, con=Depends(get_con)):
    """The schedule file as it was uploaded (info=1: just whether there is one)."""
    f = db.one(con, "SELECT filename, mime, size, data, uploaded_by, uploaded_at FROM programme_file WHERE project_id=? AND layer=?", (pid, layer))
    if info:
        return {"has_file": bool(f), **({k: f[k] for k in ("filename", "size", "uploaded_by", "uploaded_at")} if f else {})}
    if not f:
        raise HTTPException(404, "No file was kept for this schedule: upload it again to be able to download it")
    return Response(base64.b64decode(f["data"] or ""), media_type=f["mime"] or "application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{f["filename"]}"'})


@router.get("/api/p/{pid}/programme/tasks")
def programme_tasks(pid: int, con=Depends(get_con)):
    return db.rows(con, "SELECT t.*, i.ref AS item_ref, i.description AS item_desc, n.code AS node_code, n.name AS node_name "
                        "FROM programme_task t LEFT JOIN contract_item i ON i.id=t.link_item_id "
                        "LEFT JOIN cbs_node n ON n.id=t.link_node_id WHERE t.project_id=? ORDER BY COALESCE(t.layer,'internal')='upstream', t.seq", (pid,))


@router.put("/api/p/{pid}/programme/tasks/{tid}")
def programme_task_link(pid: int, tid: int, body: dict, con=Depends(get_con)):
    d = {k: body.get(k) for k in ("link_item_id", "link_node_id", "start_date", "finish_date", "name") if k in body}
    db.update(con, "programme_task", tid, d)
    out = {"ok": True, "warnings": []}
    if "link_node_id" in d or "start_date" in d or "finish_date" in d:      # the linked line's activity window follows the schedule
        out["warnings"] = programme.apply(con, pid, targets=("costs",)).get("warnings", [])
    if "link_item_id" in d or "start_date" in d or "finish_date" in d:      # a linked claim line follows the (client facing) schedule
        programme.apply(con, pid, targets=("claims",))
    return out


@router.post("/api/p/{pid}/programme/auto-link")
def programme_autolink(pid: int, con=Depends(get_con)):
    return {"linked": programme.suggest(con, pid)}


@router.post("/api/p/{pid}/programme/apply")
def programme_apply(pid: int, body: dict, con=Depends(get_con)):
    return programme.apply(con, pid, body.get("targets") or ["claims", "costs"], bool(body.get("only_empty")))


@router.post("/api/p/{pid}/programme/to-milestones")
def programme_to_ms(pid: int, body: dict, con=Depends(get_con)):
    """Copy chosen schedule tasks (default: milestones and summary phases) into the project milestone list."""
    ids = body.get("ids")
    q = "SELECT * FROM programme_task WHERE project_id=? AND COALESCE(layer,'internal')='internal' AND (milestone=1 OR summary=1)" if not ids else f"SELECT * FROM programme_task WHERE project_id=? AND id IN ({','.join('?' * len(ids))})"
    n = 0
    for t in db.rows(con, q, [pid, *(ids or [])]):
        db.insert(con, "milestone", dict(project_id=pid, phase=None, name=t["name"], type="Milestone" if t["milestone"] else "Phase",
                                         baseline_start=t["start_date"], baseline_end=t["finish_date"], forecast_start=t["start_date"],
                                         forecast_end=t["finish_date"], pmr_row=t["wbs"], sort_order=t["seq"]))
        n += 1
    return {"created": n}


@router.delete("/api/p/{pid}/programme")
def programme_clear(pid: int, layer: str = "internal", con=Depends(get_con)):
    con.execute("DELETE FROM programme_task WHERE project_id=? AND COALESCE(layer,'internal')=?", (pid, layer))
    con.execute("DELETE FROM programme_file WHERE project_id=? AND layer=?", (pid, layer))
    s = db.project_settings(con, pid)
    s.pop("programme_file" if layer == "internal" else "programme_file_upstream", None)
    db.update(con, "project", pid, {"settings_json": json.dumps(s)})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Dashboard and reports
# ---------------------------------------------------------------------------
@router.get("/api/p/{pid}/invoices")
def supplier_invoices(pid: int, con=Depends(get_con)):
    """Every supplier invoice in the Pronto GL (PO receipts, direct invoices, supplier journals), grouped per supplier."""
    need_project(con, pid)
    return invoices_mod.listing(con, pid)


@router.get("/api/p/{pid}/invoices.xlsx")
def supplier_invoices_xlsx(pid: int, con=Depends(get_con)):
    p = need_project(con, pid)
    return Response(invoices_mod.xlsx(con, pid), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="Invoices_{(p.get("code") or "project")}.xlsx"'})
