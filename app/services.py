"""Core domain operations: projects, CBS, resources, allowance ledger, initialisation."""
import json
import re
import uuid

from . import db
from .taxonomy import DEFAULT_METHOD_BY_GP, GRANDPARENTS, PARENTS


class Problem(Exception):
    """A user-correctable problem; surfaced as HTTP 400."""


# --------------------------------------------------------------------------
# Projects
# --------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "default_methods": DEFAULT_METHOD_BY_GP,
    "accrual_auto_reverse": True,
    "accrual_tolerance": 1.0,
    "stages": ["Early Works", "EPC"],
    "ctd_includes_journals": True,
    "allowance_view": "pm",        # pm: the allowance is the budget; company: budget plus the risk bucket the company holds
}


def load_standard_cbs(con, pid):
    gp_ids = {}
    order = 0
    for gp, name in GRANDPARENTS.items():
        order += 1
        gp_ids[gp] = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=None, code=gp, name=name,
                                                    kind="group", gp=gp, sort_order=order, origin="standard"))
    for code, name in PARENTS:
        order += 1
        db.insert(con, "cbs_node", dict(project_id=pid, parent_id=gp_ids[code[:2]], code=code, name=name,
                                        kind="group", gp=code[:2], category=code, sort_order=order,
                                        origin="standard"))


def create_project(con, data, from_template=None, include=None):
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    data = dict(data)
    data.setdefault("default_risk_pct", 0.07)
    pid = db.insert(con, "project", {**data, "settings_json": json.dumps(settings)})
    if from_template:
        clone_structure(con, from_template, pid, include or {})
    else:
        load_standard_cbs(con, pid)
    db.log(con, pid, "project.create", data.get("name", ""))
    db.bump(con, pid)
    return pid


def clone_structure(con, src, dst, include):
    """Copy the reusable skeleton of one project into another. Never copies Pronto data, claims or history.

    include keys: lines (CBS lines + intermediate groups), allowances (estimate entries), resources,
    rate_card (with the supplier rates and public holidays), milestones, contract_items.
    """
    s = db.one(con, "SELECT settings_json FROM project WHERE id=?", (src,))
    con.execute("UPDATE project SET settings_json=? WHERE id=?", (s["settings_json"], dst))
    if include.get("resources"):
        for r in db.rows(con, "SELECT * FROM resource WHERE project_id=?", (src,)):
            r.pop("id"); r["project_id"] = dst
            db.insert(con, "resource", r)
    res_map = {(r["kind"], r["code"]): r["id"] for r in db.rows(con, "SELECT * FROM resource WHERE project_id=?", (dst,))}
    src_res = {r["id"]: (r["kind"], r["code"]) for r in db.rows(con, "SELECT * FROM resource WHERE project_id=?", (src,))}
    nodes = db.rows(con, "SELECT * FROM cbs_node WHERE project_id=? ORDER BY id", (src,))
    idmap = {}
    for n in nodes:
        if n["kind"] == "line" and not include.get("lines"):
            continue
        if n["origin"] not in ("standard",) and not include.get("lines") and n["kind"] == "group":
            # custom groups below parents are structure too, keep them when lines are kept only
            continue
        old = n["id"]
        n = {k: v for k, v in n.items() if k != "id"}
        n["project_id"] = dst
        n["parent_id"] = idmap.get(n["parent_id"]) if n["parent_id"] else None
        rid = src_res.get(n.get("resource_id"))
        n["resource_id"] = res_map.get(rid) if rid else None
        idmap[old] = db.insert(con, "cbs_node", n)
    if include.get("allowances"):
        for e in db.rows(con, "SELECT * FROM allowance_ledger WHERE project_id=? AND kind='estimate'", (src,)):
            if e["node_id"] in idmap:
                e.pop("id"); e["project_id"] = dst; e["node_id"] = idmap[e["node_id"]]
                db.insert(con, "allowance_ledger", e)
    if include.get("rate_card"):
        for r in db.rows(con, "SELECT * FROM rate_card WHERE project_id=?", (src,)):
            r.pop("id"); r["project_id"] = dst
            db.insert(con, "rate_card", r)
        # the subcontractors' rates go with the rate card, on the copied supplier (a rate whose supplier was not copied is left out)
        for r in db.rows(con, "SELECT * FROM supplier_rate WHERE project_id=? ORDER BY id", (src,)):
            if r["resource_id"] and not res_map.get(src_res.get(r["resource_id"])):
                continue
            r.pop("id"); r["project_id"] = dst
            r["resource_id"] = res_map.get(src_res.get(r["resource_id"])) if r["resource_id"] else None
            db.insert(con, "supplier_rate", r)
        # and so do the public holidays the labour calendar skips
        have = {h["day"] for h in db.rows(con, "SELECT day FROM holiday WHERE project_id=?", (dst,))}
        for r in db.rows(con, "SELECT * FROM holiday WHERE project_id=? ORDER BY day", (src,)):
            if r["day"] not in have:
                r.pop("id"); r["project_id"] = dst
                db.insert(con, "holiday", r)
    if include.get("milestones"):
        for r in db.rows(con, "SELECT * FROM milestone WHERE project_id=?", (src,)):
            r.pop("id"); r["project_id"] = dst
            for k in ("baseline_start", "baseline_end", "forecast_start", "forecast_end", "actual_date"):
                r[k] = None
            r["pct"] = 0
            db.insert(con, "milestone", r)
    if include.get("contract_items"):
        cmap = {}
        for r in db.rows(con, "SELECT * FROM contract_item WHERE project_id=? AND kind!='variation' ORDER BY id", (src,)):
            old = r.pop("id"); r["project_id"] = dst
            r["parent_id"] = cmap.get(r["parent_id"]) if r["parent_id"] else None
            cmap[old] = db.insert(con, "contract_item", r)
    # the standard CBS must exist even when nothing else was copied
    if not db.scalar(con, "SELECT COUNT(*) FROM cbs_node WHERE project_id=?", (dst,)):
        load_standard_cbs(con, dst)


WIPE_SCOPES = {
    "pronto": ["pronto_tx", "pronto_labour", "pronto_po", "pronto_claim", "pronto_variation", "pronto_ctd", "import_batch"],
    "forecast": ["forecast_day", "forecast_ms", "forecast_item", "forecast_manual", "accrual"],
    "revenue": ["claim", "contract_item"],
    "variations": ["variation"],
    "subcontracts": ["subcontract"],
    "history": ["snapshot", "cmt_entry", "audit_log"],
    "programme": ["milestone", "programme_task"],
    "risk": ["risk", "risk_alloc", "risk_tag", "risk_release"],
}


def wipe_project(con, pid, scopes):
    """Irreversible. Removes the chosen data groups; identity, standard CBS and settings are kept."""
    done = []
    for sc in scopes:
        if sc == "allowances":
            con.execute("DELETE FROM allowance_ledger WHERE project_id=?", (pid,)); done.append(sc); continue
        if sc == "structure":
            con.execute("DELETE FROM cbs_node WHERE project_id=? AND origin!='standard'", (pid,))
            con.execute("DELETE FROM resource WHERE project_id=?", (pid,))
            con.execute("UPDATE cbs_node SET method=NULL, unalloc_method=NULL, unalloc_eac=NULL WHERE project_id=?", (pid,))
            done.append(sc); continue
        for t in WIPE_SCOPES.get(sc, []):
            con.execute(f"DELETE FROM {t} WHERE project_id=?", (pid,))
        done.append(sc)
    if "structure" in scopes or "allowances" in scopes:
        con.execute("UPDATE project SET initialised=0, initialised_at=NULL WHERE id=?", (pid,))
    db.log(con, pid, "project.wipe", ",".join(done))
    db.bump(con, pid)
    return done


# --------------------------------------------------------------------------
# Resources
# --------------------------------------------------------------------------
def upsert_resource(con, pid, kind, code, name=None, function=None, **extra):
    code = (code or "").strip()
    if not code:
        raise Problem("Resource code is required")
    r = db.one(con, "SELECT * FROM resource WHERE project_id=? AND kind=? AND code=?", (pid, kind, code))
    data = {k: v for k, v in dict(name=name, function=function, **extra).items() if v not in (None, "")}
    if r:
        db.update(con, "resource", r["id"], data)
        return r["id"]
    return db.insert(con, "resource", dict(project_id=pid, kind=kind, code=code, **data))


# --------------------------------------------------------------------------
# CBS
# --------------------------------------------------------------------------
def get_node(con, pid, nid):
    n = db.one(con, "SELECT * FROM cbs_node WHERE id=? AND project_id=?", (nid, pid))
    if not n:
        raise Problem("CBS node not found")
    return n


def ancestors(con, pid, nid):
    out = []
    n = get_node(con, pid, nid)
    while n:
        out.append(n)
        n = db.one(con, "SELECT * FROM cbs_node WHERE id=?", (n["parent_id"],)) if n["parent_id"] else None
    return out


def next_code(con, pid, parent):
    base = parent["code"]
    taken = {r["code"] for r in db.rows(con, "SELECT code FROM cbs_node WHERE project_id=? AND code LIKE ?", (pid, base + ".%"))}
    n = 1
    while f"{base}.{n:03d}" in taken:
        n += 1
    return f"{base}.{n:03d}"


def add_node(con, pid, parent_id, name, kind="line", code=None, resource_kind=None, resource_code=None,
             resource_name=None, function=None, scope=None, method=None, start_date=None, end_date=None,
             po_no=None, budget=None, risk=None, category=None, origin="manual", notes=None):
    parent = get_node(con, pid, parent_id) if parent_id else None
    if parent and parent["kind"] == "line":
        raise Problem("A CBS line cannot have children. Choose a group as the parent.")
    if kind not in ("group", "line"):
        raise Problem("kind must be group or line")
    if not parent:
        if not code or code in {r["code"] for r in db.rows(con, "SELECT code FROM cbs_node WHERE project_id=?", (pid,))}:
            raise Problem("A top-level node needs a unique code")
    rid = None
    if resource_code:
        rk = resource_kind or ("employee" if parent and parent["gp"] == "PL" else "supplier")
        rid = upsert_resource(con, pid, rk, resource_code, resource_name or name, function)
        if not name or name == resource_code:
            name = resource_name or resource_code
        res = db.one(con, "SELECT * FROM resource WHERE id=?", (rid,))
        function = function or res.get("function")
        name = name or res["name"]
    if not name:
        raise Problem("Name is required")
    code = code or next_code(con, pid, parent)
    if db.one(con, "SELECT 1 x FROM cbs_node WHERE project_id=? AND code=?", (pid, code)):
        raise Problem(f"CBS code {code} already exists")
    gp = parent["gp"] if parent else code[:2]
    sort = db.scalar(con, "SELECT COALESCE(MAX(sort_order),0)+1 FROM cbs_node WHERE project_id=?", (pid,))
    nid = db.insert(con, "cbs_node", dict(
        project_id=pid, parent_id=parent_id, code=code, name=name, kind=kind, gp=gp, category=category,
        resource_id=rid, function=function, scope=scope, method=method, start_date=start_date,
        end_date=end_date, po_no=po_no, sort_order=sort, origin=origin, notes=notes))
    if budget or risk:
        set_estimate(con, pid, nid, budget or 0, risk if risk is not None else None)
    if kind == "group" and parent and parent["parent_id"] is None and origin not in ("ctc", "wip"):
        ensure_ctc_lines(con, pid)                  # a new CBS parent gets its CTC (Unallocated) line
    db.bump(con, pid)
    return nid


def update_node(con, pid, nid, data):
    n = get_node(con, pid, nid)
    allowed = {"name", "function", "scope", "po_no", "method", "start_date", "end_date", "eac_override",
               "uncommitted", "unalloc_method", "unalloc_eac", "notes", "active", "sort_order", "code", "window_manual"}
    patch = {k: v for k, v in data.items() if k in allowed}
    if "code" in patch and patch["code"] != n["code"]:
        if n["origin"] == "standard":
            raise Problem("Standard CBS codes cannot be renamed")
        if db.one(con, "SELECT 1 x FROM cbs_node WHERE project_id=? AND code=? AND id!=?", (pid, patch["code"], nid)):
            raise Problem("That CBS code already exists")
    if "method" in patch and patch["method"] and patch["method"] not in __import__("app.taxonomy", fromlist=["METHODS"]).METHODS:
        raise Problem("Unknown forecast method")
    for k in ("method", "unalloc_method"):
        if patch.get(k) == "CLAIM" and nid not in __import__("app.subcontracts", fromlist=["claim_nodes"]).claim_nodes(con, pid):
            raise Problem("CLAIM needs a subcontract with a claim schedule linked to this line (Subcontracts)")
    if "window_manual" not in patch and ("start_date" in patch or "end_date" in patch):
        s1, e1 = patch.get("start_date", n["start_date"]), patch.get("end_date", n["end_date"])
        if not s1 and not e1:
            patch["window_manual"] = 0                      # dates cleared: the window is inherited again
        elif s1 != n["start_date"] or e1 != n["end_date"]:
            patch["window_manual"] = 1                      # changed by hand: schedule updates leave this line alone
    db.update(con, "cbs_node", nid, patch)
    db.bump(con, pid)


def move_node(con, pid, nid, new_parent_id):
    n = get_node(con, pid, nid)
    p = get_node(con, pid, new_parent_id)
    if p["kind"] == "line":
        raise Problem("Target must be a group")
    if n["origin"] == "standard":
        raise Problem("Standard CBS nodes cannot be moved")
    if nid in [a["id"] for a in ancestors(con, pid, new_parent_id)]:
        raise Problem("Cannot move a node under itself")
    if n["kind"] == "line" and p["gp"] != n["gp"]:
        raise Problem("A line must stay inside its grandparent category")
    db.update(con, "cbs_node", nid, {"parent_id": new_parent_id, "code": next_code(con, pid, p)})
    db.bump(con, pid)


def delete_node(con, pid, nid):
    n = get_node(con, pid, nid)
    if n["origin"] == "standard":
        raise Problem("Standard CBS nodes cannot be deleted. Deactivate it instead.")
    ids = _subtree(con, pid, nid)
    q = ",".join("?" * len(ids))
    used = (db.scalar(con, f"SELECT COUNT(*) FROM pronto_tx WHERE node_id IN ({q})", ids)
            or db.scalar(con, f"SELECT COUNT(*) FROM accrual WHERE node_id IN ({q})", ids)
            or db.scalar(con, f"SELECT COUNT(*) FROM allowance_ledger WHERE node_id IN ({q}) AND kind!='estimate'", ids))
    if used:
        raise Problem("This node has actuals, accruals or allowance movements. Deactivate it instead of deleting.")
    con.execute(f"DELETE FROM cbs_node WHERE id IN ({q})", ids)
    db.bump(con, pid)


def _subtree(con, pid, nid):
    out, stack = [], [nid]
    kids = {}
    for r in db.rows(con, "SELECT id,parent_id FROM cbs_node WHERE project_id=?", (pid,)):
        kids.setdefault(r["parent_id"], []).append(r["id"])
    while stack:
        x = stack.pop()
        out.append(x)
        stack.extend(kids.get(x, []))
    return out


def subtree_ids(con, pid, nid):
    return _subtree(con, pid, nid)


# --------------------------------------------------------------------------
# Allowance ledger
# --------------------------------------------------------------------------
def set_estimate(con, pid, nid, budget, risk=None, note=None, date=None):
    """Original estimate (proposal allowance) for a node. Replaces any earlier estimate entry.

    risk=None applies the project default risk % to the budget.
    """
    n = get_node(con, pid, nid)
    p = db.one(con, "SELECT default_risk_pct, initialised FROM project WHERE id=?", (pid,))
    budget = float(budget or 0)
    if risk is None:
        risk = round(budget * (p["default_risk_pct"] or 0), 2)
    if p["initialised"]:
        raise Problem("Cost control is initialised, so the original estimate is locked. "
                      "Use a budget transfer or adjustment to change the allowance.")
    con.execute("DELETE FROM allowance_ledger WHERE project_id=? AND node_id=? AND kind='estimate'", (pid, nid))
    if budget or risk:
        db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=nid, date=date, kind="estimate",
                                                budget=budget, risk=float(risk), note=note or "Proposal allowance"))
    db.bump(con, pid)


def post_ledger(con, pid, kind, entries, ref=None, note=None, date=None, variation_id=None):
    """Post a balanced or single-sided ledger movement. entries = [(node_id, budget, risk[, contingency, risk_cover]), ...]."""
    pair = uuid.uuid4().hex[:10]
    for e in entries:
        nid, b, r = e[0], e[1], e[2]
        cont, cover = (e[3], e[4]) if len(e) > 4 else (0, 0)
        get_node(con, pid, nid)
        db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=nid, date=date, kind=kind,
                                                budget=b or 0, risk=r or 0, contingency=cont or 0, risk_cover=cover or 0, ref=ref, note=note,
                                                pair_id=pair, variation_id=variation_id))
    db.bump(con, pid)
    return pair


def transfer(con, pid, from_id, to_id, budget=0, risk=0, ref=None, note=None, date=None):
    if from_id == to_id:
        raise Problem("From and to must differ")
    if not (budget or risk):
        raise Problem("Enter an amount")
    return post_ledger(con, pid, "transfer", [(from_id, -budget, -risk), (to_id, budget, risk)], ref, note, date)


def release_risk(con, pid, nid, amount, ref=None, note=None, date=None):
    """Move risk contingency into budget on the same node (risk allocated to a cost)."""
    return post_ledger(con, pid, "risk_release", [(nid, amount, -amount)], ref, note, date)


# --------------------------------------------------------------------------
# Initialise cost control
# --------------------------------------------------------------------------
def init_checks(con, pid):
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    issues, info = [], {}
    if not p["project_start"] or not p["project_end"]:
        issues.append({"level": "error", "msg": "Set the project start and end dates (Setup, Project)."})
    if not p["status_date"]:
        issues.append({"level": "error", "msg": "Set the status date (Setup, Project)."})
    budget = db.scalar(con, "SELECT SUM(budget) FROM allowance_ledger WHERE project_id=?", (pid,))
    risk = db.scalar(con, "SELECT SUM(risk) FROM allowance_ledger WHERE project_id=?", (pid,))
    n_alw = db.scalar(con, "SELECT COUNT(DISTINCT node_id) FROM allowance_ledger WHERE project_id=?", (pid,))
    from . import revenue                      # imported here: revenue does not depend on services
    rs = revenue.summary(con, pid)             # adds up the claim items under each group, as the Revenue page does
    contract = (rs["base"] + rs["optional_taken"]) or None
    if not budget:
        issues.append({"level": "error", "msg": "No allowances loaded. Enter proposal allowances against the CBS first."})
    if not contract:
        issues.append({"level": "warn", "msg": "No contract value loaded (Revenue, Contract). Planned margin cannot be calculated."})
    lines = db.scalar(con, "SELECT COUNT(*) FROM cbs_node WHERE project_id=? AND kind='line'", (pid,))
    if not lines:
        issues.append({"level": "info", "msg": "No resource lines yet. Allowances will sit as unallocated pots until lines are added."})
    info.update(budget=budget, risk=risk, allowance=budget + risk, nodes_with_allowance=n_alw, contract_value=contract,
                lines=lines,
                planned_margin=(contract - budget) if contract else None,
                planned_margin_pct=((contract - budget) / contract) if contract else None)
    ok = not any(i["level"] == "error" for i in issues)
    return {"ok": ok, "issues": issues, "info": info, "initialised": bool(p["initialised"])}


def initialise(con, pid, force=False):
    chk = init_checks(con, pid)
    if not chk["ok"] and not force:
        raise Problem("Cost control cannot be initialised yet: " + "; ".join(i["msg"] for i in chk["issues"] if i["level"] == "error"))
    s = db.project_settings(con, pid)
    methods = {**DEFAULT_METHOD_BY_GP, **(s.get("default_methods") or {})}
    for n in db.rows(con, "SELECT id, gp, method, kind, unalloc_method FROM cbs_node WHERE project_id=?", (pid,)):
        if n["kind"] == "line" and not n["method"]:
            db.update(con, "cbs_node", n["id"], {"method": methods.get(n["gp"], "AT-BUDGET")})
        if n["kind"] == "group" and not n["unalloc_method"]:
            # an unallocated pot is not forecast until you say so: on a project that is already running its cost is on the lines
            # beneath it, and forecasting the pot as well would count that cost twice
            db.update(con, "cbs_node", n["id"], {"unalloc_method": "NONE"})
    ensure_ctc_lines(con, pid)
    con.execute("UPDATE project SET initialised=1, initialised_at=datetime('now') WHERE id=?", (pid,))
    db.log(con, pid, "project.initialise", json.dumps(chk["info"]))
    db.bump(con, pid)
    return chk


CTC_NAME = "CTC (Unallocated)"
WIP_NAME = "WIP (Unallocated CTD)"


def ensure_ctc_lines(con, pid):
    """Three placeholders per CBS parent (PL01, PS02 ...): the allowance pot (the group's own "(Unallocated)" row, which holds the
    estimate's budget and risk and has no forecast method), WIP (code <parent>.998, holds the unallocated cost to date, such as
    Pronto's WIP account) and CTC (Unallocated) (code <parent>.999, somewhere to forecast a cost that has no forecast of its own).
    WIP and CTC have no allowance, start on method NONE and the pool above never allocates to them. Idempotent: a parent that already
    has one is left alone. Returns how many were created."""
    made = 0
    top = {r["id"] for r in db.rows(con, "SELECT id FROM cbs_node WHERE project_id=? AND parent_id IS NULL", (pid,))}
    for g in db.rows(con, "SELECT * FROM cbs_node WHERE project_id=? AND kind='group' AND active=1 AND variation_id IS NULL", (pid,)):
        if g["parent_id"] not in top:
            continue
        for origin, suffix, name, note in (("wip", "998", WIP_NAME, "Cost to date with no resource line to sit on (Pronto's WIP account and anything not yet matched)."),
                                           ("ctc", "999", CTC_NAME, "A forecast with no estimate bucket behind it.")):
            if db.one(con, "SELECT 1 x FROM cbs_node WHERE project_id=? AND parent_id=? AND origin=?", (pid, g["id"], origin)):
                continue
            code = f"{g['code']}.{suffix}"
            if db.one(con, "SELECT 1 x FROM cbs_node WHERE project_id=? AND code=?", (pid, code)):
                continue
            sort = db.scalar(con, "SELECT COALESCE(MAX(sort_order),0)+1 FROM cbs_node WHERE project_id=?", (pid,))
            db.insert(con, "cbs_node", dict(project_id=pid, parent_id=g["id"], code=code, name=name, kind="line", gp=g["gp"], category=None,
                                           method="NONE", sort_order=sort, origin=origin, notes=note))
            made += 1
    if made:
        db.bump(con, pid)
    return made


def reorder_node(con, pid, nid, direction):
    """Move a CBS group or line one place up (-1) or down (+1) among its siblings (same parent), never across parents. Returns True if it moved."""
    n = get_node(con, pid, nid)
    sibs = db.rows(con, "SELECT id, sort_order FROM cbs_node WHERE project_id=? AND parent_id IS ? ORDER BY sort_order, id", (pid, n["parent_id"]))
    ids = [r["id"] for r in sibs]
    i = ids.index(nid)
    j = i + (-1 if direction < 0 else 1)
    if j < 0 or j >= len(ids):
        return False
    ids[i], ids[j] = ids[j], ids[i]
    slots, last = [], None
    for r in sibs:                                   # the same set of sort values, made strictly increasing so ties cannot block a move
        v = r["sort_order"] or 0
        v = v if last is None or v > last else last + 1
        slots.append(v)
        last = v
    for k, sid in enumerate(ids):
        con.execute("UPDATE cbs_node SET sort_order=? WHERE id=?", (slots[k], sid))
    db.bump(con, pid)
    return True


def add_category(con, pid, code, name):
    """A custom Pronto cost category (for example a variation tracker such as PL10) below its grandparent."""
    code = (code or "").strip().upper()
    if not re.match(r"^(PL|PS|PM|PE)\d{2}$", code):
        raise Problem("A category code looks like PL10, PS08, PM09 or PE10")
    gp = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND code=? AND parent_id IS NULL", (pid, code[:2]))
    if not gp:
        raise Problem("Grandparent not found")
    return add_node(con, pid, gp["id"], name or code, kind="group", code=code, category=code, origin="custom")
