"""The project team against what the project's complexity band asks for.

Requirements are the EPEC Project Complexity Matrix (sheet "Project Resourcing Requirement"): seven roles by band, each with a seniority.
Seniority is 1 to 4 for every role except the Project Manager, who keeps the PM level 1 to 5 of EPEC-PM-FW-0002 (Level 5 is the project director).
For the other roles the four band columns are also the four steps, so a person's level for a role reads the same as the requirement text
(for the Project Engineer: 1 Shared / Junior PE, 2 Dedicated / Competent PE, 3 Senior / Lead PE, 4 Principal / Portfolio Engineer).

A role is filled by the people in `team_slot` with status "selected" who are in post on the project's status date. The Project Manager and
the Project Director are the project's own fields (epec_pm, project_director). Fit per role: meets, above, below, vacant, unrated, or not_required.

The risk rating is a first rule (Vincent, 29/10/2026): Red when the PM or a mandatory role is vacant or below the level asked for, or the PM's
latest complexity assessment is in a higher band than the director's baseline; Amber when another dedicated role is vacant, below or unrated;
Green otherwise. A shared role, or one marked "if applicable", is not a gap when nobody holds it.
"""
from . import complexity, db, ecf
from .services import Problem
from .workload import _norm

ROLES = [("pm", "Project Manager"), ("pe", "Project Engineer"), ("dm", "Design Manager"), ("cm", "Construction Manager"),
         ("tc", "Test & Commissioning"), ("ct", "Project Controls (Cost & Schedule)"), ("co", "Project Coordinator")]
ROLE_KEYS = [r[0] for r in ROLES]
ROLE_NAME = dict(ROLES)
STATUS = {"selected": "Selected", "recruitment": "Recruitment", "tbc": "To be confirmed"}


def _r(label, level, mode="dedicated", mandatory=False):
    return dict(label=label, level=level, mode=mode, mandatory=mandatory)


# role -> band code -> what is asked (labels as written in the workbook)
REQ = {
    "pm": {"C1": _r("PM Level 1 / Junior", 1), "C2": _r("PM Level 2–3", 2), "C3": _r("Senior PM / Program Manager (L4)", 4), "C4": _r("Project / Portfolio Director (L4–5)", 5)},
    "pe": {"C1": _r("Shared / Junior PE", 1, "shared"), "C2": _r("Dedicated / Competent PE", 2), "C3": _r("Senior / Lead PE (Mandatory)", 3, mandatory=True), "C4": _r("Principal / Portfolio Engineer", 4)},
    "dm": {"C1": _r("Shared / Design Coordinator", 1, "shared"), "C2": _r("Design Manager (Dedicated)", 2), "C3": _r("Senior / Lead Design Manager", 3), "C4": _r("Design / Engineering Director", 4)},
    "cm": {"C1": _r("Shared Supervisor", 1, "shared"), "C2": _r("Project Construction Manager", 2), "C3": _r("Senior Construction Manager", 3), "C4": _r("Construction Director", 4)},
    "tc": {"C1": _r("Not normally required", None, "none"), "C2": _r("Commissioning Engineer (if applicable)", 2, "if_applicable"), "C3": _r("Lead Test & Commissioning Manager", 3), "C4": _r("Commissioning Director", 4)},
    "ct": {"C1": _r("Shared", 1, "shared"), "C2": _r("Dedicated Cost / Scheduler", 2), "C3": _r("Controls Lead", 3), "C4": _r("Portfolio Controls", 4)},
    "co": {"C1": _r("Shared / Part-time", 1, "shared"), "C2": _r("Dedicated Project Coordinator", 2), "C3": _r("Senior Project Coordinator", 3), "C4": _r("Portfolio PMO Analyst", 4)},
}
PM_LEVEL_LABEL = {1: "PM Level 1 (junior PM)", 2: "PM Level 2 (PM)", 3: "PM Level 3 (senior PM)", 4: "PM Level 4 (senior PM / program manager)", 5: "PM Level 5 (project director)"}


def level_labels(role):
    """{level: text} for a role: the PM levels, or the four band columns of the requirement table."""
    if role == "pm":
        return PM_LEVEL_LABEL
    return {i + 1: REQ[role][c]["label"] for i, c in enumerate(("C1", "C2", "C3", "C4")) if REQ[role][c]["level"]}


# ---- people's levels ---------------------------------------------------------------------------------------------------
def set_levels(con, person_id, levels):
    """levels: {role_key: 1..4 or blank}. The Project Manager's level is the person's pm_level (1 to 5)."""
    for k, v in (levels or {}).items():
        if k not in ROLE_KEYS:
            raise Problem("Unknown role " + str(k))
        if k == "pm":
            db.update(con, "person", person_id, {"pm_level": int(v) if v not in (None, "") else None})
            continue
        con.execute("DELETE FROM person_role WHERE person_id=? AND role_key=?", (person_id, k))
        if v not in (None, "", 0):
            v = int(v)
            if not 1 <= v <= 4:
                raise Problem("Levels run from 1 to 4")
            db.insert(con, "person_role", dict(person_id=person_id, role_key=k, level=v))


def levels_of(con, person_id):
    out = {r["role_key"]: r["level"] for r in db.rows(con, "SELECT role_key, level FROM person_role WHERE person_id=?", (person_id,))}
    pm = (db.one(con, "SELECT pm_level FROM person WHERE id=?", (person_id,)) or {}).get("pm_level")
    if pm:
        out["pm"] = pm
    return out


def all_levels(con):
    """{person_id: {role_key: level}} for everyone (used by the people list)."""
    out = {}
    for r in db.rows(con, "SELECT person_id, role_key, level FROM person_role"):
        out.setdefault(r["person_id"], {})[r["role_key"]] = r["level"]
    return out


# ---- the team of one project -----------------------------------------------------------------------------------------------
def _person(con, name):
    name = (name or "").strip()
    if not name:
        return None
    from . import org_load
    return org_load.find(db.rows(con, "SELECT * FROM person"), name)


def _in_post(slot, on):
    return (not slot.get("start_date") or slot["start_date"] <= on) and (not slot.get("end_date") or slot["end_date"] >= on)


def save_slot(con, pid, body):
    role = body.get("role_key")
    if role not in ROLE_KEYS or role == "pm":
        raise Problem("Choose a role. The Project Manager is set on Project setup.")
    status = body.get("status") or "selected"
    if status not in STATUS:
        raise Problem("Status is Selected, Recruitment or To be confirmed")
    person_id = None
    name = (body.get("person_name") or "").strip()
    if name:
        from . import directory
        person_id = directory.add(con, "employee", name)["id"]
        if body.get("level") not in (None, ""):
            set_levels(con, person_id, {role: body["level"]})
    elif status == "selected":
        raise Problem("Name the person, or set the status to Recruitment or To be confirmed")
    d = dict(project_id=pid, role_key=role, person_id=person_id, status=status, start_date=db.iso(body.get("start_date")) if body.get("start_date") else None,
             end_date=db.iso(body.get("end_date")) if body.get("end_date") else None, note=(body.get("note") or "").strip() or None)
    if d["start_date"] and d["end_date"] and d["end_date"] < d["start_date"]:
        raise Problem("The end date is before the start date")
    if person_id and not body.get("id") and db.one(con, "SELECT id FROM team_slot WHERE project_id=? AND role_key=? AND person_id=?", (pid, role, person_id)):
        raise Problem(name + " is already on this project in that role")
    if body.get("id"):
        if not db.one(con, "SELECT id FROM team_slot WHERE id=? AND project_id=?", (body["id"], pid)):
            raise Problem("That team entry is not on this project")
        db.update(con, "team_slot", int(body["id"]), {k: v for k, v in d.items() if k != "project_id"})
        return int(body["id"])
    return db.insert(con, "team_slot", d)


def delete_slot(con, pid, sid):
    con.execute("DELETE FROM team_slot WHERE id=? AND project_id=?", (sid, pid))


def team(con, pid):
    proj = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    on = (proj.get("status_date") or "")[:10] or "9999-12-31"
    base, _ = complexity.baseline(con, pid)
    band = complexity.band_of(base["total"]) if base else None
    code = band["code"] if band else None
    names = {p["id"]: p for p in db.rows(con, "SELECT * FROM person")}
    lv = all_levels(con)
    rolemap = {r["key"]: r for r in ecf.roles(con)}
    slots = [dict(s) for s in db.rows(con, "SELECT * FROM team_slot WHERE project_id=? ORDER BY role_key, id", (pid,))]
    members = []
    for s in slots:
        p = names.get(s["person_id"])
        ends = [x for x in (s["end_date"], (p or {}).get("leaving_date")) if x]
        members.append(dict(id=s["id"], role_key=s["role_key"], role=ROLE_NAME[s["role_key"]], person_id=s["person_id"], person=p["name"] if p else None, status=s["status"],
                            status_label=STATUS[s["status"]], start_date=s["start_date"], end_date=min(ends) if ends else None, slot_end_date=s["end_date"], note=s["note"],
                            leaving_date=(p or {}).get("leaving_date"), serving_notice=bool(p and p.get("employment_status") == "serving notice"),
                            level=(ecf.effective(p, rolemap, s["role_key"], lv.get(s["person_id"], {}))[0] if p else None),
                            level_source=(ecf.effective(p, rolemap, s["role_key"], lv.get(s["person_id"], {}))[1] if p else None),
                            ecf=(ecf.person_view(p, rolemap) if p else None), in_post=_in_post(dict(start_date=s["start_date"], end_date=(min(ends) if ends else None)), on)))
    # the Project Manager and Project Director come from the project
    pm_p = _person(con, proj.get("epec_pm"))
    pm = dict(role_key="pm", role=ROLE_NAME["pm"], person=(proj.get("epec_pm") or "").strip() or None, person_id=pm_p["id"] if pm_p else None, status="selected" if (proj.get("epec_pm") or "").strip() else "tbc",
              status_label="Selected" if (proj.get("epec_pm") or "").strip() else "To be confirmed",
              level=ecf.effective(pm_p, rolemap, "pm", {})[0] if pm_p else None, level_source=ecf.effective(pm_p, rolemap, "pm", {})[1] if pm_p else None,
              ecf=ecf.person_view(pm_p, rolemap) if pm_p else None, in_post=True, id=None, start_date=None, end_date=(pm_p or {}).get("leaving_date"),
              leaving_date=(pm_p or {}).get("leaving_date"), serving_notice=bool(pm_p and pm_p.get("employment_status") == "serving notice"))
    director = (proj.get("project_director") or "").strip() or None
    rows = _rows(members, pm, code, on)
    assessed = complexity.assessments(con, pid)
    return dict(project=dict(id=pid, name=proj["name"], pm=pm["person"], director=director, status_date=proj.get("status_date")), band=band, rows=rows,
                extra=[m for m in members], risk=risk(rows, band, base, assessed), requirement=REQ_TABLE(code), ahead=ahead(members, pm, band, code, on, base, assessed),
                reviews=[dict(r) for r in db.rows(con, "SELECT month, rating, note, by, created_at FROM team_review WHERE project_id=? ORDER BY month DESC", (pid,))])


def _rows(members, pm, code, on):
    """Each role against the band on one date: who is in post then, the best level among them, and the fit."""
    rows = []
    for key, label in ROLES:
        req = REQ[key].get(code) if code else None
        mem = [pm] if key == "pm" else [m for m in members if m["role_key"] == key]
        active = [m for m in mem if m["status"] == "selected" and m["person"] and _in_post(m, on)]
        lvls = [m["level"] for m in active if m["level"]]
        best = max(lvls) if lvls else None
        if not req:
            fit = "no_band"
        elif req["mode"] == "none":
            fit = "not_required"
        elif not active:
            fit = "vacant"
        elif best is None:
            fit = "unrated"
        else:
            fit = "below" if best < req["level"] else ("meets" if best == req["level"] else "above")
        rows.append(dict(role_key=key, role=label, required=req, members=mem, fit=fit, best_level=best, level_labels=level_labels(key)))
    return rows


def _add_months(ym, n):
    y, m = int(ym[:4]), int(ym[5:7]) - 1 + n
    return f"{y + m // 12}-{m % 12 + 1:02d}"


def ahead(members, pm, band, code, on, base, assessed, months=6):
    """The team's rating for each of the next months (judged on the 15th of each): a leaver or a joiner with a date changes it.
    Returns { months: [{month, rating, issues}], first_gap: {...} or None }."""
    start = on[:7] if on[:4].isdigit() else None
    if not start:
        return dict(months=[], first_gap=None)
    out, first = [], None
    now = risk(_rows(members, pm, code, on), band, base, assessed)
    for i in range(months + 1):
        m = _add_months(start, i)
        d = f"{m}-15"
        rows = _rows(members, pm, code, d)
        r = risk(rows, band, base, assessed)
        issues = [x for x in r["reasons"] if x not in now["reasons"]] if i else r["reasons"]
        out.append(dict(month=m, rating=r["rating"], reasons=r["reasons"], new_issues=issues))
        if i and not first and band and issues:        # the first month with a problem the team does not have today
            first = dict(month=m, rating=r["rating"], reasons=issues)
    return dict(months=out, first_gap=first)


def review(con, pid, month, note, by):
    """The PM confirms the team for a month (joiners, leavers and what it means for the project). The rating at that moment is kept with it."""
    month = (month or "")[:7]
    if len(month) != 7 or month[4] != "-":
        raise Problem("Choose the month")
    rating = team(con, pid)["risk"]["rating"]
    con.execute("DELETE FROM team_review WHERE project_id=? AND month=?", (pid, month))
    db.insert(con, "team_review", dict(project_id=pid, month=month, rating=rating, note=(note or "").strip() or None, by=by))
    return team(con, pid)


def overview(con, director=None):
    """Every running project's team against its band, for the director: one row per project with each role's fit."""
    from .workload import _norm as nn
    out = []
    for p in db.rows(con, "SELECT id, name, project_director, epec_pm FROM project WHERE archived_at IS NULL AND COALESCE(is_template,0)=0 AND COALESCE(is_parent,0)=0 ORDER BY name"):
        if director and nn(p["project_director"]) != nn(director):
            continue
        t = team(con, p["id"])
        comp = competency(con, p["id"])
        out.append(dict(id=p["id"], name=p["name"], pm=p["epec_pm"], director=p["project_director"], pm_dimension_gaps=comp["gaps"] if comp["ready"] else None, band=t["band"]["name"] if t["band"] else None, band_code=t["band"]["code"] if t["band"] else None,
                        rating=t["risk"]["rating"], reasons=t["risk"]["reasons"], first_gap=t["ahead"]["first_gap"],
                        roles={r["role_key"]: dict(fit=r["fit"], asked=r["required"]["label"] if r["required"] else None,
                                                   who=", ".join(dict.fromkeys(m["person"] for m in r["members"] if m["person"] and m["status"] == "selected")) or None, status=(r["members"][0]["status_label"] if r["members"] and not any(m["person"] for m in r["members"]) else None))
                               for r in t["rows"]}))
    order = {"red": 0, "amber": 1, "unknown": 2, "green": 3}
    out.sort(key=lambda r: (order.get(r["rating"], 4), r["name"]))
    return dict(projects=out, roles=[dict(key=k, name=n) for k, n in ROLES])


def REQ_TABLE(code):
    return {k: REQ[k][code]["label"] for k in ROLE_KEYS} if code else None


def risk(rows, band, base, assessed):
    """(rating, reasons) by the rule in the module note."""
    if not band:
        return dict(rating="unknown", reasons=["The project director has not set the complexity baseline yet, so there is nothing to compare the team with."])
    red, amber = [], []
    for r in rows:
        req = r["required"]
        critical = r["role_key"] == "pm" or (req and req["mandatory"])
        shared_ok = req and req["mode"] in ("shared", "if_applicable", "none")
        who = f"{r['role']}: asked for {req['label']}" if req else r["role"]
        if r["fit"] == "below":
            (red if critical else amber).append(f"{who}; the person in the role is below that level")
        elif r["fit"] == "vacant" and not shared_ok:
            (red if critical else amber).append(f"{who}; nobody is in the role yet")
        elif r["fit"] == "unrated":
            (red if critical else amber).append(f"{who}; the person's level for this role is not recorded")
    for r in rows:                                    # someone serving notice with no last day recorded: the role may empty at any time
        for m in r["members"]:
            if m.get("serving_notice") and not m.get("leaving_date") and m.get("person") and m.get("status", "selected") == "selected":
                amber.append(f"{m['person']} ({r['role']}) is serving notice and the last day is not recorded")
    last = next((a for a in reversed(assessed) if a.get("total") is not None), None)
    if last and complexity.band_of(last["total"])["code"] > band["code"]:
        red.append(f"The PM's latest complexity assessment ({fmt_m(last['month'])}) is {complexity.band_of(last['total'])['code']}, above the baseline {band['code']}: the director should review the requirement")
    return dict(rating="red" if red else "amber" if amber else "green", reasons=red + amber)


def fmt_m(m):
    try:
        y, mo = m.split("-")
        return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(mo) - 1] + "-" + y[2:]
    except (ValueError, IndexError, AttributeError):
        return m


# ---- the PM's competency by dimension against what the project's dimensions ask ----------------------------------------------------
def set_dimension_levels(con, person_id, levels):
    """levels: {dimension key: 1..5 or blank}. Blank clears it (the person's overall PM level is used)."""
    for k, v in (levels or {}).items():
        if k not in complexity.KEYS:
            raise Problem("Unknown dimension " + str(k))
        con.execute("DELETE FROM person_dimension WHERE person_id=? AND dim_key=?", (person_id, k))
        if v not in (None, "", 0):
            v = int(v)
            if not 1 <= v <= 5:
                raise Problem("Levels run from 1 to 5")
            db.insert(con, "person_dimension", dict(person_id=person_id, dim_key=k, level=v))


def all_dimension_levels(con):
    out = {}
    for r in db.rows(con, "SELECT person_id, dim_key, level FROM person_dimension"):
        out.setdefault(r["person_id"], {})[r["dim_key"]] = r["level"]
    return out


def competency(con, pid):
    """The Project Manager's level in each dimension against what the director's baseline asks of it (Complexity Matrix levels).
    Holds the director's dimension scores in disguise, so it is for director roles only (the caller checks)."""
    base, _ = complexity.baseline(con, pid)
    proj = db.one(con, "SELECT epec_pm FROM project WHERE id=?", (pid,))
    pm = _person(con, proj.get("epec_pm"))
    if not base or not pm:
        return dict(ready=False, reason="The baseline and the project manager are needed" if not base or not pm else "", rows=[], gaps=0, pm=pm["name"] if pm else None)
    rolemap = {r["key"]: r for r in ecf.roles(con)}
    overall = ecf.effective(pm, rolemap, "pm", {})[0]
    own = all_dimension_levels(con).get(pm["id"], {})
    rows, gaps = [], 0
    for key, label, _d in complexity.DIMENSIONS:
        score = base["scores"][key]["score"]; band = complexity.dimension_band(score)
        ask = complexity.MATRIX_LEVELS[key][band]
        lvl, src = (own[key], "set") if key in own else (overall, "overall PM level" if overall else None)
        if not ask:
            fit = "no_level"
        elif lvl is None:
            fit = "unrated"
        else:
            fit = "below" if lvl < ask[0] else ("meets" if lvl <= ask[1] else "above")
        gaps += fit == "below"
        rows.append(dict(key=key, label=label, score=score, band=band, asked=list(ask) if ask else None, level=lvl, source=src, fit=fit))
    return dict(ready=True, pm=pm["name"], overall=overall, rows=rows, gaps=gaps)


def impact(con, person_id):
    """Where a person holds a role, with what their leaving does to each team: the rating now and the first month it gets worse."""
    p = db.one(con, "SELECT * FROM person WHERE id=?", (person_id,))
    if not p:
        raise Problem("No such person")
    from .workload import _norm as nn
    out = []
    for proj in db.rows(con, "SELECT id, name, epec_pm, project_director FROM project WHERE archived_at IS NULL AND COALESCE(is_template,0)=0 AND COALESCE(is_parent,0)=0 ORDER BY name"):
        roles = [ROLE_NAME[s["role_key"]] for s in db.rows(con, "SELECT role_key FROM team_slot WHERE project_id=? AND person_id=?", (proj["id"], person_id))]
        if nn(proj["epec_pm"]) == nn(p["name"]):
            roles.insert(0, "Project Manager")
        director = nn(proj["project_director"]) == nn(p["name"])
        if not roles and not director:
            continue
        t = team(con, proj["id"])
        out.append(dict(project_id=proj["id"], project=proj["name"], roles=roles, as_director=director, rating=t["risk"]["rating"], first_gap=t["ahead"]["first_gap"]))
    return dict(person=p["name"], leaving_date=p.get("leaving_date"), employment_status=p.get("employment_status"), projects=out)


def leavers(con):
    """Everyone with a leaving date or serving notice, with the projects affected."""
    out = []
    for p in db.rows(con, "SELECT id, name, leaving_date, employment_status FROM person WHERE (leaving_date IS NOT NULL AND leaving_date<>'') OR employment_status='serving notice' ORDER BY leaving_date, name"):
        out.append(impact(con, p["id"]))
    return out
