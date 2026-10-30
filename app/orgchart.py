"""The project's parties and how they communicate: who the owner, developer, builder, principal contractor, contractor and the
network service provider (NSP: Transgrid, Powerlink and so on) are, and the contract, reporting and communication lines between them.

EPEC is always on the chart, as either the Contractor or the Principal Contractor. The chart is one JSON document per project
(parties with a position on the canvas, links with a kind), edited on the Project org chart page and saved whole.
"""
import json
import uuid

from . import db

ROLES = ("Owner", "Developer", "Builder", "Principal Contractor", "Contractor", "NSP", "Subcontractor", "Consultant", "Other")
EPEC_ROLES = ("Contractor", "Principal Contractor")
KINDS = ("contract", "reporting", "communication")
NSPS = ["Transgrid", "Powerlink", "Ausgrid", "Endeavour Energy", "Essential Energy", "Energex", "Ergon Energy", "AusNet", "Jemena", "CitiPower",
        "Powercor", "United Energy", "SA Power Networks", "ElectraNet", "Evoenergy", "TasNetworks", "Western Power", "AEMO"]


def _id():
    return uuid.uuid4().hex[:8]


def default_chart(epec_role="Principal Contractor"):
    return dict(epec_role=epec_role, parties=[dict(id="epec", role=epec_role, name="EPEC", epec=True, note="", x=420, y=260)], links=[])


def load(con, pid):
    r = db.one(con, "SELECT data FROM project_org WHERE project_id=?", (pid,))
    if not r:
        return dict(default_chart(), saved=False)
    try:
        return dict(clean(json.loads(r["data"])), saved=True)
    except ValueError:
        return dict(default_chart(), saved=False)


def clean(body):
    """Keep only what a chart may hold: known roles and link kinds, links between parties that exist, exactly one EPEC party."""
    epec_role = body.get("epec_role") if body.get("epec_role") in EPEC_ROLES else "Principal Contractor"
    parties, seen = [], set()
    for p in body.get("parties") or []:
        pid = str(p.get("id") or _id())[:24]
        if pid in seen:
            continue
        seen.add(pid)
        is_epec = bool(p.get("epec")) or pid == "epec"
        role = epec_role if is_epec else (p.get("role") if p.get("role") in ROLES else "Other")
        parties.append(dict(id=pid, role=role, name=(p.get("name") or "EPEC" if is_epec else p.get("name") or "").strip()[:120], epec=is_epec,
                            note=(p.get("note") or "").strip()[:300], x=int(float(p.get("x") or 0)), y=int(float(p.get("y") or 0))))
    epecs = [p for p in parties if p["epec"]]
    for extra in epecs[1:]:
        extra["epec"] = False
        extra["role"] = "Other"
    if not epecs:
        parties.insert(0, dict(id="epec", role=epec_role, name="EPEC", epec=True, note="", x=420, y=260))
    ids = {p["id"] for p in parties}
    links, lseen = [], set()
    for l in body.get("links") or []:
        a, b = str(l.get("from") or ""), str(l.get("to") or "")
        k = l.get("kind") if l.get("kind") in KINDS else "communication"
        if a in ids and b in ids and a != b and (a, b, k) not in lseen:
            lseen.add((a, b, k))
            links.append(dict(id=str(l.get("id") or _id())[:24], **{"from": a, "to": b}, kind=k, label=(l.get("label") or "").strip()[:80]))
    return dict(epec_role=epec_role, parties=parties, links=links)


def save(con, pid, body, who=None):
    data = clean(body)
    con.execute("DELETE FROM project_org WHERE project_id=?", (pid,))
    con.execute("INSERT INTO project_org (project_id, data, updated_by) VALUES (?,?,?)", (pid, json.dumps(data), who))
    return data
