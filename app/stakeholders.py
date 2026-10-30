"""COMMUNICATION > Stakeholders: who matters to this one project. (OVERVIEW > Stakeholders is the company-wide directory.)"""
import json

from . import db, orgchart

LEVELS = ("High", "Medium", "Low")


def rows(con, pid):
    return db.rows(con, "SELECT * FROM project_stakeholder WHERE project_id=? ORDER BY name", (pid,))


def clean(b):
    name = (b.get("name") or "").strip()
    if not name:
        raise ValueError("Name is required")
    pick = lambda v: v if v in LEVELS else None
    return dict(name=name, organisation=(b.get("organisation") or "").strip() or None, role=(b.get("role") or "").strip() or None, contact=(b.get("contact") or "").strip() or None,
                interest=pick(b.get("interest")), influence=pick(b.get("influence")), notes=(b.get("notes") or "").strip() or None)


def save(con, pid, b, sid=None):
    d = clean(b)
    if sid:
        db.update(con, "project_stakeholder", sid, d)
        return sid
    return db.insert(con, "project_stakeholder", dict(project_id=pid, source=b.get("source") or "manual", **d))


def import_known(con, pid):
    """Add the org chart parties and the project's named people that are not listed yet. Returns how many were added."""
    have = {(r["name"].lower()) for r in rows(con, pid)}
    cand = []
    for p in (orgchart.load(con, pid) or {}).get("parties", []):
        if p.get("name") and not p.get("epec"):
            cand.append((p["name"], p["name"], p["role"], "org chart"))
    proj = db.one(con, "SELECT client_name, client_pm, epec_pm, project_director FROM project WHERE id=?", (pid,)) or {}
    for who, role, org in ((proj.get("client_pm"), "Client project manager", proj.get("client_name")), (proj.get("epec_pm"), "EPEC project manager", "EPEC"),
                           (proj.get("project_director"), "EPEC project director", "EPEC")):
        if who:
            cand.append((who, org, role, "project team"))
    n = 0
    for name, org, role, src in cand:
        if name.lower() in have:
            continue
        have.add(name.lower())
        db.insert(con, "project_stakeholder", dict(project_id=pid, name=name, organisation=org if org != name else None, role=role, source=src))
        n += 1
    return n
