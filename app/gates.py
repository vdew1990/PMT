"""EPEC's project gates, 1 to 7, and where a project stands on them.

From EPEC's gate forms and Project Lifecycle Management overview: Gate 1 approves going after an opportunity (EPEC-OP-FR-0001),
Gate 2 approves creating the proposal (EPEC-OP-FR-0002), Gate 5 is the handover from the proposal team to the delivery team once
the contract is won (EPEC-OP-FR-0005), Gate 6 approves delivering the project after Setup (EPEC-PD-FR-0001) and Gate 7 approves
Practical Completion at the end of Close Out (EPEC-PD-FR-0004). Between Gates 6 and 7 the Delivery phase ends with the Ready to
Close Out Project Review; after Gate 7 the project is in Warranty (the defect liability period). Gates 3 (Approval to submit proposal,
EPEC-OP-FR-0003) and 4 (Approval to sign contract, EPEC-OP-FR-0004) are the last two Tender gates. Gate 8 is not defined yet.

PMs join at Gate 3 at the earliest and set the project up in Pronto, SharePoint and PMT around Gates 4 and 5. A project with an Early
Works award and then an EPC award goes round Gates 3 to 5 twice, so a gate can move back as well as forward: the log keeps every
change with its date and the stage (Early Works, EPC or the whole project), and the latest entry is where the project stands.
"""
from pathlib import Path

from . import db

FORMS = Path(__file__).resolve().parent / "gate_forms"   # EPEC's gate papers (Word), one per gate that has a form

GATES = {
    1: dict(name="Approval to proceed with opportunity", form="EPEC-OP-FR-0001", phase="Tender"),
    2: dict(name="Approval to create proposal", form="EPEC-OP-FR-0002", phase="Tender"),
    3: dict(name="Approval to submit proposal", form="EPEC-OP-FR-0003", phase="Tender"),
    4: dict(name="Approval to sign contract", form="EPEC-OP-FR-0004", phase="Tender"),
    5: dict(name="Handover to Delivery", form="EPEC-OP-FR-0005", phase="Setup"),
    6: dict(name="Approval to Deliver Project", form="EPEC-PD-FR-0001", phase="Delivery"),
    7: dict(name="Approval of Project Completion", form="EPEC-PD-FR-0004", phase="Warranty"),
}
STAGES = ("Whole project", "Early Works", "EPC")


def form_file(g):
    """The Word file of a gate's paper, or None (every gate defined so far has one)."""
    f = GATES.get(g, {}).get("form")
    return next(iter(sorted(FORMS.glob(f"{f}_*.docx"))), None) if f else None


def label(g):
    if g not in GATES:
        return None
    n = GATES[g]["name"]
    return f"Gate {g}" + (f": {n}" if n else "")


def catalogue():
    return [dict(gate=g, **v, label=label(g), has_form=form_file(g) is not None) for g, v in GATES.items()]


def log(con, pid):
    return db.rows(con, "SELECT * FROM gate_log WHERE project_id=? ORDER BY date, id", (pid,))


def current(rows):
    """The latest entry (by date, then entry order) as the project's standing, or None."""
    if not rows:
        return None
    last = sorted(rows, key=lambda r: (r["date"] or "", r["id"]))[-1]
    return dict(gate=last["gate"], label=label(last["gate"]), phase=GATES[last["gate"]]["phase"], stage=last.get("stage"), date=last["date"], note=last.get("note"))


def standings(con):
    """project id -> current standing, for the Portfolio."""
    by = {}
    for r in db.rows(con, "SELECT * FROM gate_log ORDER BY date, id"):
        by.setdefault(r["project_id"], []).append(r)
    return {pid: current(rs) for pid, rs in by.items()}


def add(con, pid, gate, date, stage=None, note=None, by=None):
    gate = int(gate)
    if gate not in GATES:
        raise ValueError("A gate is 1 to 7")
    if not date or len(date) < 10:
        raise ValueError("Enter the date the project reached this gate")
    if stage and stage not in STAGES:
        raise ValueError("Stage is Whole project, Early Works or EPC")
    return db.insert(con, "gate_log", dict(project_id=pid, gate=gate, date=date[:10], stage=stage or None, note=(note or "").strip() or None, by=by))


# ---- delivery phases and their readiness reviews ---------------------------------------------------------------------
# The Delivery phase runs through four stages (Project Delivery Procedure EPEC-PM-PR-0003: Design, Procure, Construct, Commission),
# then Close Out. Table 3 of the Project Set Up Procedure (EPEC-PM-PR-0002) lists the reviews that go with them; when the PM moves the
# project to a new stage PMT shows what to look for and offers the paper. Only the checklists EPEC has supplied carry items; the rest are
# named so the PM knows a review exists, with no paper yet.
import json

LIFECYCLE_FORMS = Path(__file__).resolve().parent / "lifecycle_forms"
CHECKLISTS = json.loads((Path(__file__).resolve().parent / "lifecycle_checklists.json").read_text(encoding="utf8"))

REVIEWS = {
    "EPEC-PD-FR-0011": dict(name="Preliminary Detailed Design Review (Phase 1) Checklist", status="Optional", when="4 to 6 weeks after design starts; recommended where the design component is over $250k", reviewer="Project Manager"),
    "EPEC-PD-FR-0010": dict(name="Site Start Up Planning Meeting", status="Agenda", when="Before work starts on site", reviewer="Chaired by the project"),
    "EPEC-PD-FR-0009": dict(name="Construction Readiness Review (Phase 2) Checklist", status="Optional", when="Before construction starts; recommended where construction is over $1M", reviewer="General Manager, Projects (over $10M to $25M) or Project Director (under $10M)"),
    "EPEC-PD-FR-0012": dict(name="Commissioning Readiness Review (Phase 3) Checklist", status="Optional", when="Before commissioning; recommended where commissioning is in scope", reviewer="Project Manager or nominated delegate"),
    "EPEC-PD-FR-0014": dict(name="Ready to Close Out Project Review", status="Mandatory", when="Before substantial Close Out activities start", reviewer="Project Manager and their line manager"),
}
PHASES = {
    "Design": dict(reviews=["EPEC-PD-FR-0011"], remind="Design is under way. A preliminary detailed design review (Phase 1) is optional 4 to 6 weeks in, and worth doing where the design component is over $250k. Check the Design Management Plan and that the client's design requirements are being met."),
    "Procure": dict(reviews=[], remind="Procurement. No readiness review is defined for this stage in the procedures supplied. Make sure the Procurement Plan, commitments and long lead items are on track in Pronto; the Construction Readiness review later checks materials, long lead items and FAT."),
    "Construct": dict(reviews=["EPEC-PD-FR-0010", "EPEC-PD-FR-0009"], remind="Entering construction: hold the Site Start Up Planning Meeting and consider the Construction Readiness Review (Phase 2), ideally before construction starts. Check permits, plans and registers, subcontracts, materials, site possession and mobilisation, the cost system, commercial, engineering, communication, people and safety."),
    "Commission": dict(reviews=["EPEC-PD-FR-0012"], remind="Entering commissioning: consider the Commissioning Readiness Review (Phase 3). Check approvals (permit to work, licence to operate, network outage and client LOTO / HVIA), inspection and test plans, that construction defects and the punch list are cleared, staffing, spares and test equipment, and safety."),
    "Close Out": dict(reviews=["EPEC-PD-FR-0014"], remind="Entering Close Out: the Ready to Close Out Project Review is mandatory before substantial close out work starts. Gate 7, Approval of Project Completion, follows (its paper is under Project gate)."),
}


def review_form(code):
    return next(iter(sorted(LIFECYCLE_FORMS.glob(f"{code}_*.docx"))), None)


def phase_catalogue():
    out = []
    for key, ph in PHASES.items():
        revs = []
        for code in ph["reviews"]:
            r = REVIEWS[code]
            revs.append(dict(code=code, **r, has_form=review_form(code) is not None, sections=CHECKLISTS.get(code, [])))
        out.append(dict(phase=key, remind=ph["remind"], reviews=revs))
    return out


def phase_log(con, pid):
    return db.rows(con, "SELECT * FROM phase_log WHERE project_id=? ORDER BY date, id", (pid,))


def phase_current(rows):
    if not rows:
        return None
    last = sorted(rows, key=lambda r: (r["date"] or "", r["id"]))[-1]
    return dict(phase=last["phase"], date=last["date"], end_date=last.get("end_date"), note=last.get("note"))


def phase_standings(con):
    by = {}
    for r in db.rows(con, "SELECT * FROM phase_log ORDER BY date, id"):
        by.setdefault(r["project_id"], []).append(r)
    return {pid: phase_current(rs) for pid, rs in by.items()}


def _span(date, end_date, what):
    if not date or len(date) < 10:
        raise ValueError(f"Enter the date {what} started")
    end = (end_date or "")[:10] or None
    if end and end < date[:10]:
        raise ValueError("The end date is before the start date")
    return date[:10], end


def phase_add(con, pid, phase, date, note=None, by=None, end_date=None):
    if phase not in PHASES:
        raise ValueError("Phase is " + ", ".join(PHASES))
    date, end = _span(date, end_date, "this phase")
    sc = stage_current(stage_log(con, pid))
    if phase in DELIVERY_PHASES and not (sc and sc["stage"] == "Delivery"):      # Design to Commission are part of the Delivery stage: the project cannot be in Setup and Commissioning
        stage_add(con, pid, "Delivery", date, f"Started with {phase}", by)
    prev = phase_current(phase_log(con, pid))
    rid = db.insert(con, "phase_log", dict(project_id=pid, phase=phase, date=date, end_date=end, note=(note or "").strip() or None, by=by))
    if prev and prev["phase"] != phase and not prev.get("end_date") and prev["date"] <= date:        # moving on closes the stage before it
        con.execute("UPDATE phase_log SET end_date=? WHERE project_id=? AND date=? AND phase=? AND end_date IS NULL", (date, pid, prev["date"], prev["phase"]))
    return rid


def phase_update(con, pid, rid, date, end_date=None, note=None):
    date, end = _span(date, end_date, "this phase")
    db.update(con, "phase_log", rid, dict(date=date, end_date=end, note=(note or "").strip() or None))


LIFECYCLE_STAGES = ["Handover", "Setup", "Delivery", "Close Out", "Warranty"]
DELIVERY_PHASES = ("Design", "Procure", "Construct", "Commission")


def stage_log(con, pid):
    return db.rows(con, "SELECT * FROM lifecycle_log WHERE project_id=? ORDER BY date, id", (pid,))


def stage_current(rows):
    if not rows:
        return None
    last = sorted(rows, key=lambda r: (r["date"] or "", r["id"]))[-1]
    return dict(stage=last["stage"], date=last["date"], end_date=last.get("end_date"), note=last.get("note"))


def stage_add(con, pid, stage, date, note=None, by=None, end_date=None):
    if stage not in LIFECYCLE_STAGES:
        raise ValueError("Stage is " + ", ".join(LIFECYCLE_STAGES))
    date, end = _span(date, end_date, "this stage")
    prev = stage_current(stage_log(con, pid))
    if stage != "Delivery":                                                         # leaving Delivery ends its open sub-phase
        pc = phase_current(phase_log(con, pid))
        if pc and not pc.get("end_date") and pc["date"] <= date:
            con.execute("UPDATE phase_log SET end_date=? WHERE project_id=? AND date=? AND phase=? AND end_date IS NULL", (date, pid, pc["date"], pc["phase"]))
    rid = db.insert(con, "lifecycle_log", dict(project_id=pid, stage=stage, date=date, end_date=end, note=(note or "").strip() or None, by=by))
    if prev and prev["stage"] != stage and not prev.get("end_date") and prev["date"] <= date:
        con.execute("UPDATE lifecycle_log SET end_date=? WHERE project_id=? AND date=? AND stage=? AND end_date IS NULL", (date, pid, prev["date"], prev["stage"]))
    return rid


def stage_update(con, pid, rid, date, end_date=None, note=None):
    date, end = _span(date, end_date, "this stage")
    db.update(con, "lifecycle_log", rid, dict(date=date, end_date=end, note=(note or "").strip() or None))
