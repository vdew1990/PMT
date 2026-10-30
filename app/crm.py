"""Client CRM and the people who run projects: company-wide records, shared with the team like everything else.

Clients are matched to projects by name (project.client_name), people by name (project.epec_pm / project_director),
ignoring case and spaces, so a client or PM named on a project shows up even before anyone fills in their card.
"""
from . import challenge, db, library, portfolio, workload
from .workload import _norm

CLIENT_COLS = ("name", "sector", "abn", "website", "hq", "contacts", "risk", "complexity", "knowledge", "payment_terms", "relationship", "notes")
PERSON_COLS = ("name", "role", "pm_level", "fte", "base", "lat", "lon", "reports_to", "email", "notes", "active", "employee_code", "function", "phone", "ecf_role", "ecf_level", "business_title", "leaving_date", "employment_status", "engagement")


def _clean(body, cols):
    d = {k: body.get(k) for k in cols if k in body}
    for k in ("complexity", "knowledge", "pm_level", "ecf_level"):
        if k in d:
            d[k] = int(float(d[k])) if d[k] not in (None, "") else None
    for k in ("fte", "lat", "lon"):
        if k in d:
            d[k] = float(d[k]) if d[k] not in (None, "") else None
    for k, v in list(d.items()):
        if isinstance(v, str):
            d[k] = v.strip() or None
    return d


# ---- clients --------------------------------------------------------------------------------------------------------
def clients(con, pf=None):
    """Every client: the CRM card (if any) plus what the projects say: running and archived projects, contract value,
    margin, and who manages them."""
    pf = pf or portfolio.run(con)
    lib = library.listing(con)
    cards = {_norm(c["name"]): c for c in db.rows(con, "SELECT * FROM client ORDER BY name")}
    out = {}
    for k, c in cards.items():
        out[k] = dict(c, running=[], archived=[])
    for p in pf["projects"]:
        k = _norm(p["client"])
        if not k:
            continue
        out.setdefault(k, dict(id=None, name=p["client"].strip(), running=[], archived=[]))["running"].append(
            dict(id=p["id"], name=p["name"], pm=p["pm"], director=p["director"], contract_value=p["contract_value"], margin_pct=p["margin_pct"],
                 erosion=p["erosion"], type=p.get("project_type"), status_date=p["status_date"],
                 lat=p.get("lat"), lon=p.get("lon"), location=p.get("location"), project_type=p.get("project_type"), start=p.get("start"), end=p.get("end")))
    for p in lib:
        k = _norm(p.get("client_name"))
        if not k:
            continue
        out.setdefault(k, dict(id=None, name=p["client_name"].strip(), running=[], archived=[]))["archived"].append(
            dict(id=p["id"], name=p["name"], pm=p.get("epec_pm"), contract_value=p.get("contract_value"), margin_pct=p.get("margin_pct"), end=p.get("project_end"),
                 start=p.get("project_start"), lat=p.get("lat"), lon=p.get("lon"), location=p.get("location"), project_type=p.get("project_type")))
    summ, per_project = challenge.summaries(con)
    for k, c in out.items():
        c["challenge"] = summ.get(k) or dict(score=None, band=None, client_pms=[], projects={}, position=None, evidence=None)
        for x in c["running"] + c["archived"]:
            x["assessment"] = per_project.get(x["id"])
    for c in out.values():
        allp = c["running"] + c["archived"]
        cv = sum(x.get("contract_value") or 0 for x in allp)
        c["projects"] = len(allp)
        c["contract_value"] = cv
        c["running_value"] = sum(x.get("contract_value") or 0 for x in c["running"])
        # margin across their projects, weighted by contract value
        w = [(x.get("contract_value") or 0, x.get("margin_pct")) for x in allp if x.get("margin_pct") is not None]
        c["margin_pct"] = (sum(v * m for v, m in w) / sum(v for v, _ in w)) if w and sum(v for v, _ in w) else None
        c["erosion"] = sum(x.get("erosion") or 0 for x in c["running"])
        c["pms"] = sorted({x["pm"] for x in allp if x.get("pm")})
    return sorted(out.values(), key=lambda c: -(c["running_value"] or 0))


def save_client(con, body, cid=None):
    d = _clean(body, CLIENT_COLS)
    if not cid:
        if not d.get("name"):
            raise ValueError("Enter the client's name")
        same = next((c for c in db.rows(con, "SELECT id, name FROM client") if _norm(c["name"]) == _norm(d["name"])), None)
        if same:
            cid = same["id"]
        else:
            return db.insert(con, "client", d)
    db.update(con, "client", cid, d)
    return cid


# ---- people and workload --------------------------------------------------------------------------------------------
def people(con, pf=None):
    """Everyone who manages or directs a running project, plus everyone with a card."""
    pf = pf or portfolio.run(con)
    cards = {_norm(p["name"]): p for p in db.rows(con, "SELECT * FROM person ORDER BY name")}
    out = {k: dict(v) for k, v in cards.items()}
    for p in pf["projects"]:
        for nm, role in ((p["pm"], "Project Manager"), (p["director"], "Project Director")):
            if nm and _norm(nm) not in out:
                out[_norm(nm)] = dict(id=None, name=nm, role=role, pm_level=5 if role == "Project Director" else None, fte=1.0, active=1)
    from . import ecf, team
    lv = team.all_levels(con)
    dl = team.all_dimension_levels(con)
    rm = {r["key"]: r for r in ecf.roles(con)}
    for v in out.values():
        v["role_levels"] = lv.get(v.get("id"), {})
        v["dimension_levels"] = dl.get(v.get("id"), {})
        v["ecf"] = ecf.person_view(v, rm)
    return sorted(out.values(), key=lambda x: x["name"].lower())


def _check_ecf(con, d):
    """An ECF role must exist and the level lie within its range; a blank role clears the classification."""
    from . import ecf
    if "ecf_role" in d and not d["ecf_role"]:
        d["ecf_role"] = d["ecf_level"] = None
        d["business_title"] = None if "business_title" in d and not d.get("business_title") else d.get("business_title")
    if d.get("ecf_role"):
        r = ecf.get(con, d["ecf_role"])
        if not r:
            raise ValueError("Unknown classification role")
        if d.get("ecf_level") is None:
            d["ecf_level"] = r["level_from"]
        if r["level_from"] and not (r["level_from"] <= d["ecf_level"] <= (r["level_to"] or r["level_from"])):
            raise ValueError(f"{r['name']} is level {r['level_from']}" + (f" to {r['level_to']}" if r["level_to"] != r["level_from"] else ""))


STATUSES = ("active", "serving notice", "left")
ENGAGEMENTS = ("employee", "contractor", "secondment")


def _check_status(d):
    for k, allowed in (("employment_status", STATUSES), ("engagement", ENGAGEMENTS)):
        if k in d and d[k] in ("", None):
            d[k] = None
        elif k in d and d[k] not in allowed:
            raise ValueError(f"{k.replace('_', ' ').capitalize()} is one of: " + ", ".join(allowed))
    if "leaving_date" in d:
        d["leaving_date"] = db.iso(d["leaving_date"]) if d["leaving_date"] else None


def save_person(con, body, pid=None):
    from . import team
    d = _clean(body, PERSON_COLS)
    _check_ecf(con, d)
    _check_status(d)
    levels = {k: v for k, v in (body.get("role_levels") or {}).items() if k != "pm"}     # the PM level is the pm_level field
    dims = body.get("dimension_levels")
    if not pid:
        if not d.get("name"):
            raise ValueError("Enter the person's name")
        same = next((x for x in db.rows(con, "SELECT id, name FROM person") if _norm(x["name"]) == _norm(d["name"])), None)
        if same:
            pid = same["id"]
        else:
            pid = db.insert(con, "person", d)
            team.set_levels(con, pid, levels)
            if dims:
                team.set_dimension_levels(con, pid, dims)
            return pid
    db.update(con, "person", pid, d)
    team.set_levels(con, pid, levels)
    if dims:
        team.set_dimension_levels(con, pid, dims)
    return pid


def team(con, director=None):
    """Workload of each PM: everyone, or the team of one director (PMs on projects they direct, or who report to them)."""
    pf = portfolio.run(con)
    ppl = {_norm(p["name"]): p for p in people(con, pf)}
    cl = {_norm(c["name"]): c for c in db.rows(con, "SELECT * FROM client")}
    by_pm = {}
    for p in pf["projects"]:
        if p["pm"]:
            by_pm.setdefault(_norm(p["pm"]), []).append(p)
    rows = []
    for k, person in ppl.items():
        if (person.get("role") or "").lower().endswith("director") and k not in by_pm:
            continue
        mine = by_pm.get(k, [])      # all their projects, whoever directs them: that is their workload
        if director and not (any(_norm(p["director"]) == _norm(director) for p in mine) or _norm(person.get("reports_to")) == _norm(director)):
            continue
        if not mine and not person.get("id"):
            continue
        r = workload.pm_workload(person, mine, cl)
        r["id"] = person.get("id")
        r["role"] = person.get("role")
        r["lat"], r["lon"] = person.get("lat"), person.get("lon")
        rows.append(r)
    rows.sort(key=lambda r: -(r["pct"] or 0))
    return dict(team=rows, director=director, weights=dict(complexity=workload.COMPLEXITY_LOAD, capacity=workload.LEVEL_CAPACITY,
                required_level=workload.REQUIRED_LEVEL, client=workload.CLIENT_FACTOR, risk=workload.RISK_FACTOR,
                travel=[workload.TRAVEL_MAX, workload.TRAVEL_KM], spread=[workload.SPREAD_MAX, workload.SPREAD_KM],
                bands=workload.BANDS, levels=workload.LEVEL_NAME))
