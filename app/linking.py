"""Linked projects: a parent project over two or more child projects.

Order of levels: child project (what a project manager runs) -> parent project (the children together) -> portfolio
(the projects a PM manages) -> program (what a project director directs for their clients).

A parent project holds no data of its own. Its figures are the children's, each computed by the engine as the child
shows it (own status month, own data), merged CBS code by CBS code: a line coded 1.2.3 in both children is one line in
the parent with both amounts added; a code only one child has is carried as it is. Groups are summed again from the
merged lines below them, so the parent always ties to the sum of its children. Every merged row keeps `by_project`:
what each child contributes, for the breakdown and to jump into the child. A parent is read-only (main.py refuses any
change under /api/p/{parent}); changes are made in the child projects.
"""
from collections import defaultdict

from . import db

SUMS = ("orig_budget", "orig_risk", "budget", "risk", "allowance", "variations", "cont_earmark", "risk_cover", "po_committed", "po_received",
        "outstanding", "ctd", "ctd_journal", "acc", "acc_pm", "acc_ts", "acc_claim", "ctc", "eac", "eac_cmt_style", "remaining", "contingency",
        "po_count", "po_open", "tx_rows", "fc_hours", "uncommitted", "pool_drawn", "drawn")
TOTALS = ("orig_budget", "orig_risk", "budget", "risk", "allowance", "variations", "cont_earmark", "risk_cover", "po_committed", "outstanding",
          "ctd", "ctd_journal", "acc", "ctc", "eac", "eac_cmt_style", "contingency", "remaining")


def is_parent(con, pid):
    return bool(db.scalar(con, "SELECT COALESCE(is_parent,0) FROM project WHERE id=?", (pid,)))


def children(con, pid):
    return db.rows(con, "SELECT * FROM project WHERE parent_project_id=? ORDER BY name", (pid,))


def scope_ids(con, pid):
    """The projects whose data a page shows: the project itself, or a parent's children."""
    kids = [c["id"] for c in children(con, pid)] if is_parent(con, pid) else []
    return kids or [pid]


def cache_key(con, pid):
    return tuple((c["id"], c["version"]) for c in children(con, pid))


def _span(values, pick):
    vals = [v for v in values if v]
    return pick(vals) if vals else None


def link(con, name, child_ids, director=None, parent_id=None):
    """Create a parent project over these projects (or add them to an existing parent). Returns the parent id."""
    child_ids = [int(c) for c in dict.fromkeys(child_ids or [])]
    if parent_id is None and len(child_ids) < 2:
        raise ValueError("Pick at least two projects to link")
    kids = [db.one(con, "SELECT * FROM project WHERE id=?", (c,)) for c in child_ids]
    for k, c in zip(kids, child_ids):
        if not k:
            raise ValueError(f"Project {c} not found")
        if k.get("is_parent"):
            raise ValueError(f"{k['name']} is itself a parent project: link its child projects instead")
        if k.get("is_template") or k.get("archived_at"):
            raise ValueError(f"{k['name']} is a template or archived: it cannot be linked")
        if k.get("parent_project_id") and k["parent_project_id"] != parent_id:
            other = db.one(con, "SELECT name FROM project WHERE id=?", (k["parent_project_id"],))
            raise ValueError(f"{k['name']} is already linked under {other['name'] if other else 'another parent'}: unlink it first")
    if parent_id is None:
        if not (name or "").strip():
            raise ValueError("Give the parent project a name")
        clients = sorted({k["client_name"] for k in kids if k.get("client_name")})
        directors = sorted({k["project_director"] for k in kids if k.get("project_director")})
        parent_id = db.insert(con, "project", dict(
            name=name.strip(), is_parent=1, initialised=1, client_name=", ".join(clients) or None,
            project_director=(director or "").strip() or (directors[0] if len(directors) == 1 else None),
            project_start=_span([k.get("project_start") for k in kids], min), project_end=_span([k.get("project_end") for k in kids], max),
            status_date=_span([k.get("status_date") for k in kids], max), grid_start=_span([k.get("grid_start") for k in kids], min),
            grid_end=_span([k.get("grid_end") for k in kids], max),
            notes="Parent project: the figures are its child projects' added together."))
    elif not is_parent(con, parent_id):
        raise ValueError("That project is not a parent project")
    for c in child_ids:
        con.execute("UPDATE project SET parent_project_id=? WHERE id=?", (parent_id, c))
    refresh(con, parent_id)
    return parent_id


def unlink(con, child_id):
    """Take a project out of its parent. A parent left with no children stays (empty) until it is deleted."""
    pid = db.scalar(con, "SELECT parent_project_id FROM project WHERE id=?", (child_id,), None)
    con.execute("UPDATE project SET parent_project_id=NULL WHERE id=?", (child_id,))
    if pid:
        refresh(con, pid)
    return pid


def release(con, parent_id):
    """Before a parent is deleted: its children become stand-alone projects again (their data is untouched)."""
    con.execute("UPDATE project SET parent_project_id=NULL WHERE parent_project_id=?", (parent_id,))


def refresh(con, parent_id):
    """Dates of the parent follow its children; bump its version so cached figures are recomputed."""
    kids = children(con, parent_id)
    if kids:
        con.execute("UPDATE project SET project_start=?, project_end=?, status_date=?, grid_start=?, grid_end=? WHERE id=?",
                    (_span([k.get("project_start") for k in kids], min), _span([k.get("project_end") for k in kids], max),
                     _span([k.get("status_date") for k in kids], max), _span([k.get("grid_start") for k in kids], min),
                     _span([k.get("grid_end") for k in kids], max), parent_id))
    db.bump(con, parent_id)


# ---- the parent's figures -------------------------------------------------------------------------------------------
def merged(con, p, status_month=None):
    """The engine result of a parent project: its children's results merged by CBS code (same shape as engine.compute)."""
    return combine(con, children(con, p["id"]), status_month, p)


def combine(con, kids, status_month=None, p=None):
    """Several projects' engine results merged by CBS code: a parent project's children, or a portfolio / program."""
    from . import engine
    p = p or (kids[0] if kids else {})
    results = []
    for k in kids:
        try:
            results.append((k, engine.compute(con, k["id"], status_month)))
        except Exception as e:   # a half set-up child must not break the parent
            results.append((k, {"error": str(e)}))
    good = [(k, r) for k, r in results if "rows" in r]
    months = sorted({m for _, r in good for m in r["grid"]})
    grid = db.month_range(months[0], months[-1]) if months else (engine.grid_for(p) if p else [])
    gidx = {m: i for i, m in enumerate(grid)}
    G = len(grid)
    M = max([r["status_month"] for _, r in good], default=None) or (engine.project_status_month(p) if p else None)

    merged_rows = {}          # key -> row
    kids_of = defaultdict(list)   # parent key -> [keys] in first-seen order
    roots = []
    for k, r in good:
        key_of = {}
        for row in r["rows"]:
            key_of[row["id"]] = ("p:" if row["kind"] == "pot" else "") + row["code"]
        for row in r["rows"]:
            key = key_of[row["id"]]
            pkey = key_of.get(row["parent_id"]) if row["parent_id"] is not None else None
            m = merged_rows.get(key)
            if m is None:
                m = {kk: vv for kk, vv in row.items() if not kk.startswith("_") and kk not in ("a", "x", "f", "parts")}
                for kk in SUMS:
                    m[kk] = 0.0
                m["a"], m["x"], m["f"] = [0.0] * G, [0.0] * G, [0.0] * G
                m["by_project"] = []
                m["note"] = ""
                m["_pkey"] = pkey
                merged_rows[key] = m
                (kids_of[pkey] if pkey is not None else roots).append(key)
            elif row["kind"] == "group" and m["kind"] != "group":
                m["kind"] = "group"   # a line in one child and a group in another: a group here
            if row["kind"] in ("line", "pot"):
                for kk in SUMS:
                    m[kk] += row.get(kk) or 0
                for kk in ("a", "x", "f"):
                    arr = m[kk]
                    for i, v in enumerate(row[kk]):
                        if v:
                            arr[gidx[r["grid"][i]]] += v
                if row.get("po_status") == "SHORT":
                    m["po_status"] = "SHORT"
                if row.get("method") and m.get("method") and row["method"] != m["method"]:
                    m["method"] = "MIXED"
            m["by_project"].append(dict(project_id=k["id"], project=k["name"], id=row["id"], node_id=row["node_id"], kind=row["kind"],
                                        allowance=row.get("allowance") or 0, ctd=row.get("ctd") or 0, acc=row.get("acc") or 0,
                                        ctc=row.get("ctc") or 0, eac=row.get("eac") or 0, contingency=row.get("contingency") or 0,
                                        method=row.get("method"), budget_status=row.get("budget_status")))

    # number the merged rows, sum groups from their merged leaves, presentation order depth first
    from .engine import _status
    tol = max([r.get("tolerance") or 1 for _, r in good], default=1.0)
    ids = {}
    n = 0
    for key in merged_rows:
        if not key.startswith("p:"):
            n += 1
            ids[key] = n
    for key, m in merged_rows.items():
        if key.startswith("p:"):
            gid = ids.get(m["_pkey"])
            m["id"], m["node_id"] = f"p{gid}", gid
        else:
            m["id"] = m["node_id"] = ids[key]
        m["parent_id"] = ids.get(m["_pkey"]) if m["_pkey"] is not None else None

    out = []

    def walk(key, level):
        m = merged_rows[key]
        m["level"] = level
        out.append(m)
        kids = kids_of.get(key, [])
        # pots last, as the engine shows them
        kids = [c for c in kids if not c.startswith("p:")] + [c for c in kids if c.startswith("p:")]
        if m["kind"] == "group":
            m["n_lines"] = 0
            for c in kids:
                walk(c, level + 1)
            leaves = [merged_rows[c] for c in kids]
            for kk in SUMS:
                m[kk] = sum(c.get(kk) or 0 for c in leaves)
            for kk in ("a", "x", "f"):
                m[kk] = [sum(c[kk][i] for c in leaves) for i in range(G)]
            m["n_lines"] = sum(1 if c["kind"] in ("line", "pot") else c.get("n_lines", 0) for c in leaves)
            m["po_status"] = "SHORT" if any(c.get("po_status") == "SHORT" for c in leaves) else ("OK" if m["outstanding"] > 0 else "")
            m["method"] = None
        m["budget_status"] = _status(m["allowance"], m["eac"], m["ctd"] + m["acc"], tol)
        m.pop("_pkey", None)
    for key in roots:
        walk(key, 1)

    total = {kk: sum(merged_rows[r].get(kk) or 0 for r in roots) for kk in TOTALS}
    for kk in ("a", "x", "f"):
        total[kk] = [sum(merged_rows[r][kk][i] for r in roots) for i in range(G)]
    unplaced = [dict(u, category=f"{k['name']}: {u['category'] or '(none)'}") for k, r in good for u in r.get("unplaced") or []]
    return {"project_id": p.get("id"), "status_month": M, "allowance_view": good[0][1]["allowance_view"] if good else "pm", "grid": grid,
            "rows": out, "total": total, "unplaced": unplaced, "tolerance": tol, "is_parent": True,
            "children": [dict(id=k["id"], name=k["name"], status_month=r.get("status_month"), error=r.get("error"),
                              **({kk: r["total"][kk] for kk in ("allowance", "ctd", "acc", "ctc", "eac", "contingency")} if "rows" in r else {}))
                         for k, r in results]}


def sum_dicts(parts):
    """Add up dicts of numbers (nested dicts added key by key; anything else taken from the first that has it)."""
    out = {}
    for d in parts:
        for k, v in d.items():
            if isinstance(v, bool):
                out[k] = out.get(k, False) or v
            elif isinstance(v, (int, float)):
                out[k] = (out.get(k) or 0) + v
            elif isinstance(v, dict):
                out[k] = sum_dicts([out.get(k) or {}, v])
            elif k not in out:
                out[k] = v
    return out
