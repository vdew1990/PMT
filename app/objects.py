"""The objects PMT holds and the properties of each (the data model Vincent asked for, 31/10/2026): people (EPEC employees; client and subcontractor people),
organisations (clients, subcontractors and suppliers), and projects. Each property says where it lives, how sensitive it is and whether it is held yet.

sensitivity: open (anyone on the project), internal (EPEC staff), personal (personal data: keep to those who need it), restricted (pay, home address: not held until
the role-based access design, agreed with HR and IT, exists: PMT has no sign-in and its database file can be read by anyone with the shared folder).
status: live (stored and used), derived (worked out from another property), planned (agreed, not built), deferred (agreed, waiting for the access design).
Age is not a property of an employee object (Vincent, 31/10/2026).
"""
from . import db


def _p(key, label, kind, where, sensitivity="internal", status="live", note=""):
    return dict(key=key, label=label, type=kind, where=where, sensitivity=sensitivity, status=status, note=note)


TYPES = [
    dict(key="employee", name="EPEC employee", table="person", props=[
        _p("name", "Name", "text", "person.name", "open", note="Other spellings are kept in aliases"),
        _p("aliases", "Other spellings of the name", "list", "person.aliases_json", "open", note="Added when two records are merged"),
        _p("role", "Role (PMT)", "text", "person.role", "internal", note="Project Manager, Project Director or Employee: used for lookups"),
        _p("business_title", "Business title", "text", "person.business_title", "open", note="Every business title needs HR approval (framework p.52)"),
        _p("ecf_role", "ECF role", "choice", "person.ecf_role", "internal", note="EPEC Classification Framework"),
        _p("ecf_level", "ECF level (1 to 11)", "number", "person.ecf_level", "internal", note="Ties to the pay band; the role's level unless the role spans two"),
        _p("job_family", "Job family", "derived", "ecf_role.family", "internal", "derived", "From the ECF role"),
        _p("pm_level", "Competency: PM level (1 to 5)", "number", "person.pm_level", "internal", note="EPEC-PM-FW-0002; a different level from the ECF level"),
        _p("role_levels", "Competency: level per project role (1 to 4)", "numbers", "person_role", "internal", note="Overrides what the ECF classification gives"),
        _p("dimension_levels", "Competency: PM level per complexity dimension", "numbers", "person_dimension", "internal"),
        _p("work_rate", "Work rate / cost rate", "money", "rate_card / resource.cost_rate", "restricted", "live", "Held in the rate card and on the resource (cost to EPEC); not shown on the person"),
        _p("pay_band", "Pay band level", "choice", "person.pay_band", "restricted", "deferred", "Not held until the role-based access design exists; ties to the ECF level"),
        _p("pronto_code", "Pronto resource code", "text", "person.employee_code", "internal"),
        _p("home_base", "Home base (town, for travel; with its map position)", "text", "person.base", "personal", note="A town, not an address"),
        _p("home_address", "Home address", "text", "person.home_address", "restricted", "deferred", "Not held until the role-based access design exists"),
        _p("email", "Email", "text", "person.email", "internal"),
        _p("phone", "Phone", "text", "person.phone", "internal"),
        _p("engagement", "Engagement (employee, contractor, secondment)", "choice", "person.engagement", "internal"),
        _p("employment_status", "Status (active, serving notice, left)", "choice", "person.employment_status", "internal"),
        _p("leaving_date", "Leaving date", "date", "person.leaving_date", "internal", note="Ends every project role the person holds"),
        _p("reports_to", "Reports to", "text", "person.reports_to", "internal", note="Interim lines after the 21/10/2026 re-organisation are not all stated"),
        _p("fte", "Time available (FTE)", "number", "person.fte", "internal"),
    ]),
    dict(key="external_person", name="Client or subcontractor person", table=None, props=[
        _p("name", "Name", "text", "contacts (free text today)", "internal", "planned", "Today a contact is text on the client or company"),
        _p("organisation", "Organisation", "link", "", "internal", "planned"),
        _p("role", "Role", "text", "", "internal", "planned", "For example client PM, site manager, HSE officer"),
        _p("email", "Email", "text", "", "personal", "planned"),
        _p("phone", "Phone", "text", "", "personal", "planned"),
        _p("difficulty", "Difficulty to work with (1 to 5)", "number", "assessment.pm_difficulty", "internal", "live", "Recorded monthly per project by the PM, for the client PM"),
    ]),
    dict(key="client", name="Client", table="client", props=[
        _p(k, label, kind, f"client.{k}", "internal", note=n) for k, label, kind, n in [
            ("name", "Name", "text", ""), ("sector", "Sector", "text", ""), ("abn", "ABN", "text", ""), ("website", "Website", "text", ""), ("hq", "Head office", "text", ""),
            ("contacts", "Contacts", "text", "Free text"), ("risk", "Risk", "choice", ""), ("complexity", "Difficulty (1 to 5)", "number", "The client's difficulty on the challenge grid"),
            ("knowledge", "Knowledge (1 to 5)", "number", ""), ("payment_terms", "Payment terms", "text", ""), ("relationship", "Relationship", "text", "")]]),
    dict(key="company", name="Subcontractor, supplier or consultant", table="company", props=[
        _p(k, label, kind, f"company.{k}", "internal") for k, label, kind in [
            ("kind", "Kind", "choice"), ("name", "Name", "text"), ("code", "Pronto code", "text"), ("abn", "ABN", "text"), ("trade", "Trade", "text"), ("contacts", "Contacts", "text"),
            ("email", "Email", "text"), ("phone", "Phone", "text"), ("address", "Address", "text")]]),
    dict(key="project", name="Project", table="project", props=[
        _p(k, label, kind, f"project.{k}", "open") for k, label, kind in [
            ("name", "Name", "text"), ("code", "Code", "text"), ("number", "Number", "text"), ("client_name", "Client", "link"), ("epec_pm", "EPEC project manager", "link"),
            ("project_director", "EPEC project director", "link"), ("status_date", "Status date", "date"), ("project_start", "Start", "date"), ("project_end", "End", "date"),
            ("project_type", "Type", "choice"), ("capacity_mw", "Capacity (MW)", "number"), ("voltage", "Voltage", "text"), ("location", "Location", "text"), ("complexity", "Complexity (1 to 5)", "number")]]
        + [_p("complexity_band", "Complexity band (C1 to C4)", "derived", "cx_baseline", "internal", "derived", "From the director's baseline score; the PM does not see it")]),
]


# What a person sees of their own record on My profile (a view, not a lock: PMT has no sign-in). edit = they can change it, view = they can read it,
# hidden = only HR and their project director see it. A first proposal for the role-based design session (Vincent, 31/10/2026): home address and phone they can change.
SELF = {"aliases": "hidden", "work_rate": "hidden", "pay_band": "hidden", "dimension_levels": "hidden", "phone": "edit", "home_base": "edit", "home_address": "edit"}
SELF_COLUMN = {"phone": "phone", "home_base": "base", "home_address": "home_address"}


def self_access(prop):
    return SELF.get(prop["key"], "view")


def catalogue(con):
    """The types with each property's status checked against the database: a live property whose column does not exist is reported as missing."""
    out = []
    for t in TYPES:
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({t['table']})")} if t["table"] else set()
        props = []
        for p in t["props"]:
            q = dict(p)
            if t["key"] == "employee":
                q["self"] = self_access(p)
            if t["table"] and p["where"].startswith(t["table"] + ".") and p["status"] == "live":
                q["status"] = "live" if p["where"].split(".", 1)[1] in cols else "missing"
            props.append(q)
        out.append(dict(key=t["key"], name=t["name"], properties=props))
    return dict(types=out, sensitivity={"open": "Anyone on the project", "internal": "EPEC staff", "personal": "Personal data: keep to those who need it",
                                        "restricted": "Not held until the role-based access design exists"},
                note="Age is not held. Pay band and home address wait for the role-based access design agreed with HR and IT.")


def my_record(con, name):
    """The signed-in person's own employee record as they may see it: what is hidden is left out (and said to exist), what they may change is marked."""
    from . import ecf, org_load
    people = db.rows(con, "SELECT * FROM person")
    p = org_load.find(people, name)
    if not p:
        return dict(found=False, name=name, message="No employee record matches your profile name. Ask HR to add you, or check the name in your profile.")
    rm = {r["key"]: r for r in ecf.roles(con)}
    view = ecf.person_view(p, rm)
    from . import team
    levels = team.all_levels(con).get(p["id"], {})
    fields, hidden = [], 0
    emp = next(t for t in TYPES if t["key"] == "employee")
    for prop in emp["props"]:
        acc = self_access(prop)
        if acc == "hidden":
            hidden += 1
            continue
        if prop["status"] in ("deferred", "planned") and acc != "edit":
            continue
        k = prop["key"]
        if k == "ecf_role":
            v = view["role"] if view else None
        elif k == "ecf_level":
            v = view["level"] if view else None
        elif k == "job_family":
            v = view["family_name"] if view else None
        elif k == "role_levels":
            v = ", ".join(f"{team.ROLE_NAME[r]} {l}" for r, l in levels.items() if r in team.ROLE_NAME) or None
        elif k == "home_base":
            v = p.get("base")
        elif k == "home_address":
            v = p.get("home_address") if "home_address" in p else None
        else:
            v = p.get(SELF_COLUMN.get(k, {"pronto_code": "employee_code"}.get(k, k)))
        fields.append(dict(key=k, label=prop["label"], value=v, access=acc if prop["status"] in ("live", "derived") else "unavailable", note=prop.get("note", ""),
                           status=prop["status"]))
    return dict(found=True, person_id=p["id"], name=p["name"], fields=fields, hidden=hidden,
                note="Some information about you is held by HR and your project director and is not shown here.")


def update_my_record(con, name, changes):
    from . import org_load
    from .services import Problem
    p = org_load.find(db.rows(con, "SELECT * FROM person"), name)
    if not p:
        raise Problem("No employee record matches your profile name")
    emp = {x["key"]: x for x in next(t for t in TYPES if t["key"] == "employee")["props"]}
    data = {}
    for k, v in (changes or {}).items():
        prop = emp.get(k)
        if not prop or self_access(prop) != "edit":
            raise Problem(f"You cannot change {prop['label'] if prop else k} here")
        if prop["status"] != "live":
            raise Problem(f"{prop['label']} is not held yet")
        data[SELF_COLUMN[k]] = (str(v).strip() or None) if v is not None else None
    if data:
        db.update(con, "person", p["id"], data)
    return my_record(con, name)
