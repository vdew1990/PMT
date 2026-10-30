"""Company-wide database of clients and resources: clients (crm.client), suppliers, subcontractors and consultants
(company), and employees (person, which also holds the project managers and directors).

Fields that ask for a name (client, project manager, project director, supplier...) look names up here and accept free
text: names(kind, q) is what the lookup lists, add(kind, name) puts a new name in the database. backfill() fills the
database once from the names the projects already use, so nothing has to be typed twice.
"""
from . import db
from .workload import _norm

ORG_KINDS = ("supplier", "subcontractor", "consultant")
COMPANY_COLS = ("kind", "name", "code", "abn", "trade", "contacts", "email", "phone", "address", "notes", "active")
EMPLOYEE_ROLES = {"pm": "Project Manager", "director": "Project Director", "employee": "Employee"}


def _find(rows, name):
    """A row with this name, or (people) one of their other spellings kept after a merge."""
    import json
    n = _norm(name)
    for r in rows:
        if _norm(r["name"]) == n:
            return r
        try:
            if any(_norm(a) == n for a in json.loads(r.get("aliases_json") or "[]")):
                return r
        except (ValueError, AttributeError):
            continue
    return None


def names(con, kind, q=""):
    """[{name, sub, kind}] for a lookup. kind: client | pm | director | employee | person | supplier | subcontractor |
    consultant | company (any organisation) | resource (organisations and employees)."""
    out = []
    if kind == "client":
        seen = {}
        for c in db.rows(con, "SELECT name, sector, hq FROM client"):
            seen[_norm(c["name"])] = dict(name=c["name"], sub=" · ".join(x for x in (c["sector"], c["hq"]) if x), kind="client")
        for r in db.rows(con, "SELECT DISTINCT client_name n FROM project WHERE client_name IS NOT NULL AND trim(client_name)!='' AND COALESCE(is_parent,0)=0"):
            for n in r["n"].split(","):   # a parent lists its children's clients, comma separated
                if n.strip() and _norm(n) not in seen:
                    seen[_norm(n)] = dict(name=n.strip(), sub="on a project", kind="client")
        out = list(seen.values())
    if kind in ("pm", "director", "employee", "person", "resource"):
        seen = {}
        for p in db.rows(con, "SELECT name, role, pm_level, function, employee_code FROM person WHERE COALESCE(active,1)=1"):
            seen[_norm(p["name"])] = dict(name=p["name"], kind="employee", role=p["role"],
                                          sub=" · ".join(x for x in (p["role"], p["function"], p["employee_code"], f"PM level {p['pm_level']}" if p["pm_level"] else None) if x))
        for col, role in (("epec_pm", "Project Manager"), ("project_director", "Project Director")):
            for r in db.rows(con, f"SELECT DISTINCT {col} n FROM project WHERE {col} IS NOT NULL AND trim({col})!=''"):
                seen.setdefault(_norm(r["n"]), dict(name=r["n"].strip(), kind="employee", role=role, sub=f"{role} on a project"))
        rows = list(seen.values())
        if kind == "pm":   # managers first, then everyone else (a PM can be anyone in the team)
            rows.sort(key=lambda x: 0 if "manager" in (x.get("role") or "").lower() else 1)
        if kind == "director":
            rows.sort(key=lambda x: 0 if "director" in (x.get("role") or "").lower() else 1)
        out += rows
    if kind in ORG_KINDS + ("company", "resource"):
        ks = ORG_KINDS if kind in ("company", "resource") else (kind,)
        q_ = ",".join("?" * len(ks))
        out += [dict(name=c["name"], kind=c["kind"], sub=" · ".join(x for x in (c["kind"], c["trade"], c["code"]) if x))
                for c in db.rows(con, f"SELECT name, kind, trade, code FROM company WHERE kind IN ({q_}) AND COALESCE(active,1)=1", ks)]
    if q:
        nq = _norm(q)
        out = [x for x in out if nq in _norm(x["name"]) or nq in _norm(x.get("sub"))]
    if kind not in ("pm", "director"):
        out.sort(key=lambda x: x["name"].lower())
    return out[:300]


def add(con, kind, name, extra=None):
    """Put a name in the database (no duplicate: the same name, case and spaces ignored, returns the existing one)."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Type a name first")
    extra = {k: v for k, v in (extra or {}).items() if v not in (None, "")}
    if kind == "client":
        same = _find(db.rows(con, "SELECT id, name FROM client"), name)
        return dict(table="client", id=same["id"] if same else db.insert(con, "client", dict(name=name, **{k: v for k, v in extra.items() if k in ("sector", "hq", "abn")})), name=name)
    if kind in ("pm", "director", "employee", "person"):
        same = _find(db.rows(con, "SELECT id, name, aliases_json FROM person"), name)
        if same:
            return dict(table="person", id=same["id"], name=same["name"])
        role = EMPLOYEE_ROLES.get(kind, "Employee")
        return dict(table="person", id=db.insert(con, "person", dict(name=name, role=role, pm_level=5 if kind == "director" else None, fte=1.0, active=1,
                                                                      **{k: v for k, v in extra.items() if k in ("employee_code", "function", "email", "phone")})), name=name)
    if kind in ORG_KINDS or kind in ("company", "resource"):
        k = kind if kind in ORG_KINDS else extra.get("kind") if extra.get("kind") in ORG_KINDS else "supplier"
        same = _find(db.rows(con, "SELECT id, name FROM company"), name)
        if same:
            return dict(table="company", id=same["id"], name=same["name"])
        return dict(table="company", id=db.insert(con, "company", dict(kind=k, name=name, **{x: v for x, v in extra.items() if x in ("code", "trade", "email", "phone", "abn")})), name=name)
    raise ValueError(f"Unknown list: {kind}")


# ---- the directory page ------------------------------------------------------------------------------------------------
def companies(con, kind=None):
    rows = db.rows(con, "SELECT * FROM company" + (" WHERE kind=?" if kind else "") + " ORDER BY name", (kind,) if kind else ())
    # where each one is used: projects with it as a resource or a subcontract
    used = {}
    for r in db.rows(con, "SELECT r.name, p.name pn FROM resource r JOIN project p ON p.id=r.project_id WHERE r.kind='supplier' "
                          "UNION SELECT s.supplier_name, p.name FROM subcontract s JOIN project p ON p.id=s.project_id"):
        if r["name"]:
            used.setdefault(_norm(r["name"]), set()).add(r["pn"])
    for c in rows:
        c["projects"] = sorted(used.get(_norm(c["name"]), []))
    return rows


def save_company(con, body, cid=None):
    d = {k: (body[k].strip() or None) if isinstance(body.get(k), str) else body.get(k) for k in COMPANY_COLS if k in body}
    if d.get("kind") and d["kind"] not in ORG_KINDS:
        raise ValueError("Kind is supplier, subcontractor or consultant")
    if cid:
        db.update(con, "company", cid, d)
        return cid
    if not d.get("name"):
        raise ValueError("Enter the name")
    same = _find(db.rows(con, "SELECT id, name FROM company"), d["name"])
    if same:
        db.update(con, "company", same["id"], d)
        return same["id"]
    return db.insert(con, "company", d)


def backfill(con):
    """Names the projects use and the database does not have yet: clients, suppliers (project resources), subcontractors
    (subcontracts), employees (project resources). Runs at start-up; adds only, never changes a record."""
    have = {_norm(c["name"]) for c in db.rows(con, "SELECT name FROM company")}
    # a subcontractor: the subcontract's supplier name, else the Pronto supplier on its supplier code (not the title)
    for r in db.rows(con, "SELECT DISTINCT COALESCE(NULLIF(trim(s.supplier_name),''), (SELECT r.name FROM resource r WHERE r.project_id=s.project_id "
                          "AND r.kind='supplier' AND r.code=s.supplier_code LIMIT 1)) n FROM subcontract s"):
        if r["n"] and _norm(r["n"]) not in have:
            db.insert(con, "company", dict(kind="subcontractor", name=r["n"].strip()))
            have.add(_norm(r["n"]))
    for r in db.rows(con, "SELECT code, name, MAX(function) f FROM resource WHERE kind='supplier' AND name IS NOT NULL GROUP BY lower(trim(name))"):
        if _norm(r["name"]) not in have:
            kind = "consultant" if "consult" in r["name"].lower() else "supplier"
            db.insert(con, "company", dict(kind=kind, name=r["name"].strip(), code=r["code"], trade=r["f"]))
            have.add(_norm(r["name"]))
    people = {_norm(p["name"]) for p in db.rows(con, "SELECT name FROM person")}
    for r in db.rows(con, "SELECT code, name, MAX(function) f FROM resource WHERE kind='employee' AND name IS NOT NULL GROUP BY lower(trim(name))"):
        if _norm(r["name"]) not in people:
            db.insert(con, "person", dict(name=r["name"].strip(), role="Employee", employee_code=r["code"], function=r["f"], fte=1.0, active=1))
            people.add(_norm(r["name"]))
    clients = {_norm(c["name"]) for c in db.rows(con, "SELECT name FROM client")}
    for r in db.rows(con, "SELECT DISTINCT client_name n FROM project WHERE client_name IS NOT NULL AND COALESCE(is_parent,0)=0 AND COALESCE(is_template,0)=0"):
        if _norm(r["n"]) and _norm(r["n"]) not in clients:
            db.insert(con, "client", dict(name=r["n"].strip()))
            clients.add(_norm(r["n"]))
