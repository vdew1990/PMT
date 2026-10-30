"""The EPEC Classification Framework (ECF): job families, roles, levels 1 to 11, allowable business titles and job profiles.

Source: EPEC Classification Framework, document EPEC-HR-FW-0001_0 (inside the document EPEC-GR-FW-0001_0), revision 0, published 1 October 2026,
approved by the Chief Operating Officer. Levelling table page 5; profile tables pages 6 to 46; allowable business titles under each family; definitions page 52.
The framework is owned by HR: PMT keeps a copy as reference data (table ecf_role, seeded here, editable on the Classification page when HR revises it)
and records which ECF role each person holds. It does not decide anyone's classification, and every business title needs HR approval (page 52).

Two additions of Vincent's, marked in the data: the Senior Construction Manager is level 8 (it is in the Technicians allowable titles but not in the levelling table).
"""
import json

from . import db

META = dict(number="EPEC-HR-FW-0001_0", inside_number="EPEC-GR-FW-0001_0", revision="0", published="2026-10-01", approved_by="Chief Operating Officer",
            titles_note="All business titles require HR approval (framework, Definitions, page 52).")
FAMILIES = [("mgmt", "Management"), ("eng", "Engineering"), ("design", "Design"), ("model", "Modelling"), ("pm", "Project Management"), ("tech", "Technicians"), ("draft", "Drafting")]
FAMILY_NAME = dict(FAMILIES)


def _p(objectives, experience, leadership, autonomy, dimensions, qualifications):
    return dict(key_objectives=objectives, experience=experience, leadership=leadership, autonomy=autonomy, dimensions=dimensions, qualifications=qualifications)


PM_PROFILES = {
    "pd": _p("Provides strategic leadership across multiple projects or programs to ensure successful delivery and alignment with business and client objectives.", "10+ years professional experience.",
             "Leads project managers and teams, including performance, development and resourcing. Provides leadership across multiple projects.", "Works autonomously to set direction and resolve complex and high-impact challenges.",
             "Oversees delivery of multiple large or complex projects or programs with significant commercial and client impact.", "Relevant degree in Engineering, Project Management or related field."),
    "spm": _p("Leads the delivery of large or complex projects, ensuring alignment with client, commercial and business objectives.", "6+ years professional experience.",
              "Provides leadership to project teams and mentors less experienced project managers.", "Works autonomously with accountability for project outcomes.",
              "Leads delivery of large or complex projects with significant risk, budget and stakeholder complexity.", "Relevant degree in Engineering, Project Management or related field."),
    "pm": _p("Manages the successful delivery of projects, ensuring they are completed on time, within budget and to required quality standards.", "3+ years professional experience.",
             "Leads project teams and provides direction to project support staff.", "Operates with autonomy in managing projects, with guidance available for complex issues.",
             "Leads delivery of small to medium projects or contributes to larger projects.", "Relevant degree in Engineering, Project Management or related field."),
    "ps": _p("Provides coordination and / or administrative support to ensure effective project delivery.", "3+ years professional experience.", "N/A",
             "Works under direction, supporting project delivery activities.", "Supports delivery across multiple projects.", "Relevant qualification or experience in supporting project delivery."),
    "pa": _p("Provides administrative support to enable efficient and accurate project delivery.", "Experience in administrative or project support roles.", "N/A",
             "Works under direction to complete defined administrative tasks.", "Supports project teams through documentation and administrative activities.", "Relevant qualification or experience in project administration."),
}
ENG_PROFILES = {
    "tech_dir": _p("This role provides technical leadership for their specialist domain of engineering, to assist teams in providing effective delivery of services for clients. Uses expertise to shape and challenge standards.", "Degree and 15+ years professional experience.",
                   "Technical and people leadership across a specialist domain and within complex works. Demonstrates technical eminence by leading, shaping and developing the technical capability of others across the Company whilst contributing to industry practice.",
                   "Establishes technical approaches/methodologies for solving highly complex, novel and strategically significant problems and serves as the ultimate technical authority within their specialist domain.",
                   "Acts as final authority for technical assurance for their specialist domain of engineering. Provides support and expertise at a Company-wide level.", "Bachelor of Engineering; Relevant Post-Graduate; Registered Professional Engineer; CPEng"),
    "sr_principal": _p("This role leads team/s and provides technical leadership to complex problems to assist in the delivery of services to clients, utilising a specialist skillset.", "Degree and 10 - 15 years professional experience.",
                       "Technical and people leadership within a Discipline/Team and across multiple complex projects or scope of work. Recognised as a trusted authority for complex matters, mentors others and contributes to the development of technical capability across the Company.",
                       "Develops technical approaches/methodologies to lead problem solving strategies for complex and challenging problems across multiple projects or scope of work.",
                       "Accountable for the approval of project or scope of work in their specialist domain of engineering or design. Provides support and expertise at a Business Unit level.", "Bachelor of Engineering; Relevant Post-Graduate (working towards); Registered Professional Engineer; CPEng"),
    "principal": _p("This role leads and manages team/s to provide effective and efficient delivery of services for clients. Has a specialised skillset.", "Degree and 8 - 12 years professional experience.",
                    "Technical and people leadership within a Team and across multiple complex projects or scope of work.", "Leads problem solving strategies for complex and challenging problems across multiple projects or scope of works.",
                    "Accountable for the approval of project or scope of work in specialist domain of engineering or design. Provides support and expertise at a Discipline or Team level.", "Bachelor of Engineering; Registered Professional Engineer; CPEng"),
    "sr_eng": _p("This role provides technical leadership to ensure effective and efficient delivery of engineering or design services for clients, in accordance with industry standards, project/scope of work time frames and budgets.", "Degree and 4 - 8 years professional experience.",
                 "Provides technical guidance to more junior staff.", "Works within leadership direction with work reviewed on an exception basis. Delivers problem solving solutions for complex and challenging problems.",
                 "Leads technical delivery of a project or scope of work of medium complexity. Provides support and expertise for a project or scope of work.", "Bachelor of Engineering; Registered Professional Engineer; CPEng"),
    "engineer": _p("This role provides accurate and efficient engineering or design services in accordance with project/scope of work time frames and budgets.", "Degree and 1 - 5 years professional experience.",
                   "Provides limited technical guidance to more junior staff.", "A fully functioning professional who has demonstrated technical competence and is expected to operate with minimal supervision.",
                   "Leads or contributes to technical elements projects or scope of work.", "Bachelor of Engineering; working towards achievement of CPEng"),
    "grad_eng": _p("Under the guidance of senior roles, this role develops technical skills and contributes to the delivery of projects.", "Degree and 0 - 2 years professional experience.", "N/A",
                   "Procedures cover most circumstances with the role holder identifying which procedures to apply. In circumstances which are not covered by procedure, guidance is available.", "Contributes to projects or scope of work.", "Bachelor of Engineering"),
    "cadet_eng": _p("Under the guidance of engineers, this role develops technical skills and supports project delivery.", "Study underway and limited professional experience.", "N/A",
                    "Procedures cover most circumstances with the role holder directed what procedure to apply. In circumstances which are not covered by procedure, guidance is available.", "May contribute to limited tasks on projects.", "Undergoing studies in Engineering."),
}
TECH_PROFILES = {
    "cm": _p("Leads construction activities across projects to ensure safe, efficient and high-quality delivery of field and site-based works.", "Extensive & demonstrated experience in construction management and field services delivery environments.",
             "Provides leadership and direction to supervisors, site teams and subcontractors to coordinate activities to ensure safe and effective delivery of construction works.", "Works autonomously to plan and manage construction activities, resolve complex issues and ensure delivery outcomes are met.",
             "Oversees all construction activities across projects, including safety, quality, design reviews. Responsible for schedule and resource management.", "Relevant trade or technical qualification and required licences."),
    "sup": _p("Leads site teams to ensure the safe, efficient and high-quality delivery of field-based activities within projects.", "Demonstrated experience in a relevant field-based, construction environment.",
              "Leads teams, subcontractors and site activities, including performance, safety and coordination.", "Works collaboratively with CMs to plan, coordinate and resolve complex on-site challenges.",
              "Leads delivery of site based activities within projects and provides leadership and mentoring to site based teams.", "Relevant trade or technical qualification and required licences."),
    "tech": _p("Delivers installation, maintenance, testing activities to support project outcomes.", "Trade-qualified with experience in relevant technical field.", "Provides informal guidance and support to less experienced staff.",
               "Works with direction, applying technical judgement in dynamic environments.", "Contributes to delivery of projects through technical execution.", "Trade qualification and relevant licences."),
}

# key, family, track, name, level_from, level_to, allowable business titles, profile
_R = [
    ("coo", "mgmt", "", "Chief Operating Officer", 11, 11, [], None),
    ("gm", "mgmt", "", "General Manager", 10, 10, ["General Manager – Engineering", "General Manager – Projects"], None),
    ("bum", "mgmt", "", "Business Unit Manager", 9, 9, ["Head of Engineering", "Head of Technology", "Head of Commissioning", "Head of SCADA & Controls", "Project Director", "Substation Commissioning Manager", "New Projects – Director",
                                                          "Operations Manager – Projects", "Field Services Superintendent", "Technical Director – Electricity Market & Network Modelling"], None),
    ("dl", "mgmt", "", "Discipline Lead", 8, 8, [], None),
    ("head_tech", "eng", "", "Head of Technical", 9, 9, ["Head of Technical"], None),
    ("tech_dir", "eng", "", "Technical Director", 8, 8, ["Technical Director"], ENG_PROFILES["tech_dir"]),
    ("design_dir", "design", "", "Design Director", 8, 8, ["Design Director"], ENG_PROFILES["tech_dir"]),
    ("sr_principal", "eng", "", "Senior Principal Engineer", 7, 7, ["Senior Principal Engineer"], ENG_PROFILES["sr_principal"]),
    ("design_mgr", "design", "", "Design Manager", 6, 7, ["Design Manager"], ENG_PROFILES["principal"]),
    ("principal", "eng", "", "Principal Engineer", 6, 6, ["Principal Power Systems Engineer", "Substation Principal Engineer", "Principal SCADA Engineer", "Lead Power Systems Engineer"], ENG_PROFILES["principal"]),
    ("sr_eng", "eng", "", "Senior Engineer", 5, 5, ["Senior Power Systems Engineer", "Senior Product Engineer", "Senior Electrical Engineer", "Senior SCADA Engineer", "Senior Design Engineer", "Senior Project Engineer",
                                                      "Senior Commissioning Engineer", "Lead Commissioning Engineer"], ENG_PROFILES["sr_eng"]),
    ("sr_designer", "design", "", "Senior Designer", 5, 5, ["Senior Designer"], ENG_PROFILES["sr_eng"]),
    ("engineer", "eng", "", "Engineer", 4, 4, ["Power Systems Engineer", "Electrical Engineer", "SCADA Engineer", "Project Engineer", "Design Engineer", "Commissioning Engineer", "Technologies Engineer", "Software Engineer"], ENG_PROFILES["engineer"]),
    ("designer", "design", "", "Designer", 4, 4, ["Designer"], ENG_PROFILES["engineer"]),
    ("grad_eng", "eng", "", "Graduate Engineer", 3, 3, ["Graduate Power Systems Engineer", "Graduate SCADA Engineer", "Graduate Commissioning Engineer", "Graduate Technologies Engineer", "Graduate Design Engineer"], ENG_PROFILES["grad_eng"]),
    ("cadet_eng", "eng", "", "Cadet Engineer", 2, 2, ["Cadet Engineer", "Cadet Power Systems Engineer", "Cadet Electrical Engineer", "Cadet SCADA Engineer", "Cadet Technologies Engineer"], ENG_PROFILES["cadet_eng"]),
    ("tech_dir_model", "model", "", "Technical Director (Modelling)", 8, 8, [], None),
    ("principal_modeller", "model", "", "Principal Modeller", 6, 6, ["Principal Electricity Market Modeller"], None),
    ("sr_modeller", "model", "", "Senior Modeller", 5, 5, ["Senior Electricity Market Modeller"], None),
    ("modeller", "model", "", "Modeller", 4, 4, ["Electricity Market Modeller"], None),
    ("grad_modeller", "model", "", "Graduate Modeller", 3, 3, ["Graduate Electricity Market Modeller"], None),
    ("cadet_modeller", "model", "", "Cadet Modeller", None, None, ["Cadet Electricity Market Modeller"], None),
    ("pd", "pm", "", "Project Director", 8, 8, ["Project Director", "Program Manager - Engineering"], PM_PROFILES["pd"]),
    ("spm", "pm", "", "Senior Project Manager", 7, 7, ["Senior Project Manager", "Program Manager – SCADA and Controls"], PM_PROFILES["spm"]),
    ("pm", "pm", "", "Project Manager", 6, 6, ["Project Manager"], PM_PROFILES["pm"]),
    ("ps", "pm", "", "Project Support", 4, 5, ["Project Coordinator", "Senior Project Administrator", "Project Scheduler"], PM_PROFILES["ps"]),
    ("pa", "pm", "", "Project Administration", 3, 3, ["Project Administrator", "Document Controller"], PM_PROFILES["pa"]),
    ("sr_cm", "tech", "", "Senior Construction Manager", 8, 8, ["Senior Construction Manager"], None),     # level 8 per Vincent (28/10/2026): not in the framework's levelling table
    ("cm", "tech", "", "Construction Manager", 7, 7, ["Construction Manager"], TECH_PROFILES["cm"]),
    ("sup", "tech", "", "Supervisor", 5, 5, ["Site Supervisor – Electrical", "Site Supervisor – Civil", "Substation Supervisor", "Electrical Supervisor", "Warehouse Supervisor"], TECH_PROFILES["sup"]),
    ("tech", "tech", "", "Technician", 4, 4, ["Electrician", "Substation Technician"], TECH_PROFILES["tech"]),
    ("sup_tech", "tech", "", "Support Technician", 3, 3, ["Store person", "Trades Assistant"], None),
    ("apprentice", "tech", "", "Apprentice", 1, 2, ["Apprentice"], None),
    ("sr_drafter", "draft", "", "Senior Drafter", 4, 4, ["Senior Drafter"], None),
    ("drafter", "draft", "", "Drafter", 3, 3, ["SCADA Drafter", "Drafter"], None),
    ("design_support", "draft", "", "Design Support Administrator", 2, 2, [], None),
]
ROLE_ROWS = _R


def seed(con):
    """Put the framework in the database (once; the rows can then be edited on the Classification page)."""
    for i, (key, fam, track, name, lo, hi, titles, prof) in enumerate(_R):
        if db.one(con, "SELECT id FROM ecf_role WHERE role_key=?", (key,)):
            continue
        con.execute("INSERT INTO ecf_role(role_key, family, name, level_from, level_to, titles_json, profile_json, sort_order) VALUES (?,?,?,?,?,?,?,?)",
                    (key, fam, name, lo, hi, json.dumps(titles), json.dumps(prof) if prof else None, i))


def roles(con):
    out = []
    edits = {x["role_key"]: x for x in db.rows(con, "SELECT * FROM ecf_edit")}
    for r in db.rows(con, "SELECT * FROM ecf_role ORDER BY sort_order, id"):
        e = edits.get(r["role_key"])
        out.append(dict(key=r["role_key"], family=r["family"], family_name=FAMILY_NAME.get(r["family"], r["family"]), name=r["name"],
                        level_from=e["level_from"] if e else r["level_from"], level_to=e["level_to"] if e else r["level_to"],
                        titles=json.loads((e["titles_json"] if e else r["titles_json"]) or "[]"), profile=json.loads(r["profile_json"]) if r["profile_json"] else None, revised=bool(e)))
    return out


def revise(con, key, level_from, level_to, titles):
    """HR's revision of a role: its levels and allowable titles (the published seed is kept underneath)."""
    row = db.one(con, "SELECT id FROM ecf_edit WHERE role_key=?", (key,))
    data = dict(level_from=level_from, level_to=level_to, titles_json=json.dumps(titles))
    if row:
        db.update(con, "ecf_edit", row["id"], data)
    else:
        db.insert(con, "ecf_edit", dict(role_key=key, **data))


def get(con, key):
    return next((r for r in roles(con) if r["key"] == key), None)


def label(role, level=None):
    lv = level or role["level_from"]
    return f"{role['name']} (level {lv})" if lv else role["name"]


# ---- how an ECF classification reads in the project team (confirmed by Vincent, 28/10/2026) ---------------------------------------
def _band(level, cuts):
    for upto, v in cuts:
        if level <= upto:
            return v
    return None


# seniority 1 to 4 of the team roles, by ECF level
ENGINEERING = [(3, 1), (4, 2), (6, 3), (99, 4)]          # Project Engineer, and Test & Commissioning for engineers
DESIGN = [(5, 1), (6, 2), (7, 3), (99, 4)]               # Design Manager
CONSTRUCTION = [(4, None), (6, 1), (7, 2), (8, 3), (99, None)]
SUPPORT = [(3, 1), (5, 2), (99, None)]                    # Project Controls and Project Coordinator, from Project Support


def seniority(team_role, family, level):
    """The 1 to 4 step a person's ECF level gives for a project team role, or None where the framework says nothing."""
    if not level:
        return None
    if team_role in ("pe", "tc") and family in ("eng",):
        return _band(level, ENGINEERING)
    if team_role == "dm" and family in ("eng", "design"):
        return _band(level, DESIGN)
    if team_role == "cm" and family == "tech":
        return _band(level, CONSTRUCTION)
    if team_role in ("ct", "co") and family == "pm":
        return _band(level, SUPPORT) if level <= 5 else None
    return None


def effective(person, rolemap, team_role, overrides):
    """(level, source) for one person in one team role: a level set on the person wins; otherwise the ECF classification; otherwise none."""
    if team_role == "pm":          # the PM level (EPEC-PM-FW-0002) is a competency level, not the ECF level (which ties to pay band): it is set per person
        return (person["pm_level"], "set") if person.get("pm_level") else (None, None)
    if overrides.get(team_role):
        return overrides[team_role], "set"
    r = rolemap.get(person.get("ecf_role"))
    if r:
        v = seniority(team_role, r["family"], person.get("ecf_level") or r["level_from"])
        if v:
            return v, "ECF"
    return None, None


def person_view(person, rolemap):
    """How a person's classification reads on a card or in the team: role, level, family, business title (and whether it is on the allowed list)."""
    r = rolemap.get(person.get("ecf_role"))
    if not r:
        return None
    lv = person.get("ecf_level") or r["level_from"]
    t = (person.get("business_title") or "").strip()
    short = " ".join(f"{k}: {r['profile'][k]}" for k in ("experience", "leadership", "autonomy") if r.get("profile") and r["profile"].get(k) and r["profile"][k] != "N/A")
    return dict(role=r["name"], family=r["family"], family_name=r["family_name"], level=lv, title=t or None, title_ok=(not t) or t in r["titles"], text=f"{r['name']}, level {lv}. {short}".strip())
