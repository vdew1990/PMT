"""Read-only link to the MM_CRM opportunity database, so a new project starts from the opportunity.

The CRM (a SQLite file, `inputs/crm.db` in the MM_CRM repository) is never written to: it is opened with `mode=ro`
and `query_only`. Point PMT at it with `crm_link.txt` next to PMT.exe (one line: the full path of crm.db) or the environment variable PMT_CRM_DB, which wins if both are set.

The CRM keeps history as versions: an opportunity has one row per version, and only `record_status='A'` with
`hidden=0` is current. Accounts, contacts and the CRM project (technical data) are versioned the same way.

The copy is one way. At creation the opportunity's mapped fields are copied into the project and a snapshot of what
the CRM said is stored on the project (`crm_snapshot_json`). Later, `drift()` compares the CRM now with that snapshot
and lists what changed; `resolve()` copies chosen fields into the project (still PMT only) or acknowledges them.
"""
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from . import db

ENV = "PMT_CRM_DB"
PROJECT_TYPES = ("Solar farm", "BESS", "Hybrid (solar + BESS)", "Wind farm", "Substation / transmission", "Other")

# project field -> label shown to the person
LABELS = {
    "name": "Project name", "client_name": "Client", "client_pm": "Client contact", "location": "Location (state)",
    "lat": "Latitude", "lon": "Longitude", "project_start": "Project start", "project_end": "Project end",
    "project_type": "Project type", "capacity_mw": "Capacity (MW)", "storage_mwh": "Storage (MWh)", "voltage": "Voltage (kV)",
}
FIELDS = tuple(LABELS)

_OPP_SQL = """
SELECT o.opportunity_id, o.record_id, o.opportunity_name, o.opportunity_status, o.pipeline_stage, o.assigned_to,
       o.estimated_value, o.contract_model, o.expected_gross_margin, o.location_state, o.opportunity_lat, o.opportunity_lon,
       o.expected_commencement_date, o.expected_completion_date, o.expected_award_date, o.url, o.business_unit,
       o.project_owner, o.opportunity_services, o.modified_datetime, o.project_id,
       a.account_name, a.account_abn, k.contact_name,
       p.voltage_kv, p.voltage_secondary_kv, p.capacity_mw_primary, p.capacity_mw_secondary, p.capacity_mwh,
       p.generation_model, p.transformer_type
FROM opportunities o
LEFT JOIN accounts a ON a.account_id = o.account_id AND a.record_status = 'A' AND COALESCE(a.hidden, 0) = 0
LEFT JOIN contacts k ON k.contact_id = o.contact_id AND k.record_status = 'A' AND COALESCE(k.hidden, 0) = 0
LEFT JOIN projects p ON p.project_id = o.project_id AND p.record_status = 'A' AND COALESCE(p.hidden, 0) = 0
WHERE o.record_status = 'A' AND COALESCE(o.hidden, 0) = 0
"""


class CrmUnavailable(Exception):
    """The CRM database is not set, cannot be found or cannot be read. The message is fit to show the person."""


SETTINGS_FILE = "crm_link.txt"   # next to PMT.exe; one line: the full path of the CRM database (crm.db). Not shipped, so updates never overwrite it.


def _settings_path():
    return Path(db.APP_ROOT) / SETTINGS_FILE


def _from_file():
    """First line of crm_link.txt that is not blank or a # comment; quotes around the path are dropped."""
    try:
        for line in _settings_path().read_text(encoding="utf-8-sig").splitlines():
            line = line.strip().strip('"').strip("'").strip()
            if line and not line.startswith("#"):
                return line
    except OSError:
        pass
    return ""


def db_path():
    """The CRM database path: the environment variable PMT_CRM_DB if set, else crm_link.txt next to PMT.exe, else None."""
    v = (os.environ.get(ENV) or "").strip() or _from_file()
    return Path(v) if v else None


def source():
    """Where the path comes from, for the status text: 'environment variable', 'crm_link.txt' or None."""
    if (os.environ.get(ENV) or "").strip():
        return "environment variable " + ENV
    return SETTINGS_FILE if _from_file() else None


def _connect():
    path = db_path()
    if path is None:
        raise CrmUnavailable(f"The CRM link is not set up. Create the file {SETTINGS_FILE} next to PMT.exe (copy crm_link.example.txt) with the full path of the CRM database (crm.db) on one line, then reopen this window.")
    if not path.is_file():
        raise CrmUnavailable(f"The CRM database was not found at the path in {source()}: {path}")
    try:
        con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only = ON")
        con.execute("SELECT 1 FROM opportunities LIMIT 1")
        return con
    except sqlite3.Error as e:   # a WAL database needs its folder readable (the -shm file) by the account PMT runs as
        raise CrmUnavailable(f"The CRM database could not be read ({e}). The account PMT runs as needs read access to the file and its folder.")


def status():
    """Is the link set up and readable, and how many current opportunities there are."""
    if db_path() is None:
        return dict(configured=False, ok=False, message=f"Not set up. Create {SETTINGS_FILE} next to PMT.exe (copy crm_link.example.txt) with the full path of the CRM database on one line, or set {ENV}. Then reopen this window.")
    try:
        con = _connect()
    except CrmUnavailable as e:
        return dict(configured=True, ok=False, message=str(e))
    try:
        n = con.execute("SELECT COUNT(*) FROM opportunities WHERE record_status='A' AND COALESCE(hidden,0)=0").fetchone()[0]
        return dict(configured=True, ok=True, file=db_path().name, source=source(), opportunities=n, message="")
    finally:
        con.close()


# ---- parsing ----------------------------------------------------------------------------------------------------
def _iso(v):
    """The CRM stores dates as DD/MM/YYYY (with or without a time) or as ISO; PMT stores ISO."""
    s = str(v or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    return None


def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _kv(*vals):
    """33 and 330 -> '33/330' (lower voltage first), the way PMT's voltage field is written."""
    xs = sorted({x for x in (_num(v) for v in vals) if x})
    return "/".join(str(int(x)) if x == int(x) else str(x) for x in xs) or None


def _infer_type(text):
    t = (text or "").lower()
    solar, bess = bool(re.search(r"solar|\bpv\b", t)), bool(re.search(r"bess|batter|storage", t))
    if solar and bess:
        return "Hybrid (solar + BESS)"
    if re.search(r"substation|transmission|switchyard|switching station", t):
        return "Substation / transmission"
    if bess:
        return "BESS"
    if solar:
        return "Solar farm"
    if "wind" in t:
        return "Wind farm"
    return None


# ---- reading ----------------------------------------------------------------------------------------------------
def list_opportunities(search="", status_contains="", limit=300):
    """Current opportunities, newest id first, for the picker. `status_contains` is matched against the CRM status text."""
    con = _connect()
    try:
        sql, args = _OPP_SQL, []
        if search.strip():
            sql += " AND (o.opportunity_name LIKE ? OR a.account_name LIKE ?)"
            args += [f"%{search.strip()}%"] * 2
        if status_contains.strip():
            sql += " AND o.opportunity_status LIKE ?"
            args.append(f"%{status_contains.strip()}%")
        sql += " ORDER BY o.opportunity_id DESC LIMIT ?"
        args.append(int(limit))
        return [dict(id=r["opportunity_id"], name=r["opportunity_name"], client=r["account_name"], status=r["opportunity_status"],
                     stage=r["pipeline_stage"], value=_num(r["estimated_value"]), state=r["location_state"],
                     has_crm_project=r["project_id"] is not None) for r in con.execute(sql, args)]
    finally:
        con.close()


def get_opportunity(opportunity_id):
    """The current version of one opportunity with its account, contact and CRM project joined in, or None."""
    con = _connect()
    try:
        r = con.execute(_OPP_SQL + " AND o.opportunity_id = ?", (int(opportunity_id),)).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def map_to_project(opp):
    """What the opportunity gives a new project: `fields` (project columns), `inferred` (field names PMT guessed, to be
    checked), and `reference` (CRM figures PMT has no project field for: shown, and written into the notes)."""
    ptype = _infer_type(" ".join(str(opp.get(k) or "") for k in ("opportunity_name", "opportunity_services", "generation_model")))
    mw = _num(opp.get("capacity_mw_primary"))
    fields = {
        "name": (opp.get("opportunity_name") or "").strip() or None,
        "client_name": opp.get("account_name"),
        "client_pm": opp.get("contact_name"),
        "location": opp.get("location_state"),
        "lat": _num(opp.get("opportunity_lat")), "lon": _num(opp.get("opportunity_lon")),
        "project_start": _iso(opp.get("expected_commencement_date")),
        "project_end": _iso(opp.get("expected_completion_date")),
        "project_type": ptype,
        "capacity_mw": mw,
        "storage_mwh": _num(opp.get("capacity_mwh")),
        "voltage": _kv(opp.get("voltage_secondary_kv"), opp.get("voltage_kv")),
    }
    fields = {k: v for k, v in fields.items() if v not in (None, "")}
    reference = {
        "CRM opportunity": opp.get("opportunity_id"), "CRM status": opp.get("opportunity_status"), "CRM stage": opp.get("pipeline_stage"),
        "Contract model": (opp.get("contract_model") or "").strip() or None, "Estimated value (AUD)": _num(opp.get("estimated_value")),
        "Expected gross margin": _num(opp.get("expected_gross_margin")), "CRM owner": opp.get("assigned_to"),
        "Expected award": _iso(opp.get("expected_award_date")), "SharePoint": opp.get("url"), "Client ABN": opp.get("account_abn"),
    }
    reference = {k: v for k, v in reference.items() if v not in (None, "")}
    return dict(fields=fields, inferred=["project_type"] if ptype else [], reference=reference,
                notes=_notes(reference), crm=dict(opportunity_id=opp.get("opportunity_id"), record_id=opp.get("record_id"),
                                                  modified=opp.get("modified_datetime"), has_crm_project=opp.get("project_id") is not None))


def _notes(reference):
    lines = [f"{k}: {v:,.0f}" if k == "Estimated value (AUD)" else f"{k}: {v}" for k, v in reference.items()]
    return ("From the CRM on " + datetime.now().strftime("%d/%m/%Y") + "\n" + "\n".join(lines)) if lines else ""


# ---- the link on a project --------------------------------------------------------------------------------------
def linked_projects(con, opportunity_id):
    """Names of PMT projects already created from this opportunity."""
    return [r["name"] for r in db.rows(con, "SELECT name FROM project WHERE crm_opportunity_id=?", (int(opportunity_id),))]


def attach(con, pid, opportunity_id):
    """Store the link and the snapshot of what the CRM said, on a project just created from the opportunity."""
    opp = get_opportunity(opportunity_id)
    if not opp:
        raise CrmUnavailable("That opportunity is no longer current in the CRM.")
    m = map_to_project(opp)
    db.update(con, "project", pid, dict(crm_opportunity_id=int(opportunity_id), crm_record_id=opp.get("record_id"),
                                       crm_linked_at=datetime.now().isoformat(timespec="seconds"),
                                       crm_snapshot_json=json.dumps(dict(fields=m["fields"], modified=opp.get("modified_datetime")))))
    return m


def drift(con, pid):
    """Compare the CRM now with what it said when the project was created or last resolved. `changed` lists each mapped
    field that moved, with the project's own value beside it (the PM may have edited it since)."""
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    if not p or not p.get("crm_opportunity_id"):
        return dict(linked=False)
    snap = json.loads(p.get("crm_snapshot_json") or "{}").get("fields", {})
    out = dict(linked=True, opportunity_id=p["crm_opportunity_id"], linked_at=p.get("crm_linked_at"), changed=[], reachable=True)
    try:
        opp = get_opportunity(p["crm_opportunity_id"])
    except CrmUnavailable as e:
        return dict(out, reachable=False, message=str(e))
    if not opp:
        return dict(out, reachable=True, gone=True, message="This opportunity is no longer current in the CRM.")
    now = map_to_project(opp)
    out.update(crm_status=opp.get("opportunity_status"), crm_stage=opp.get("pipeline_stage"))
    for f in FIELDS:
        if snap.get(f) != now["fields"].get(f):
            out["changed"].append(dict(field=f, label=LABELS[f], was=snap.get(f), now=now["fields"].get(f), project_has=p.get(f)))
    return out


def resolve(con, pid, accept=(), ignore=()):
    """`accept`: copy the CRM's current value of these fields into the project. `ignore`: keep the project's value and stop
    flagging the change. Both move the stored snapshot forward for those fields. Nothing is ever written to the CRM."""
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    if not p or not p.get("crm_opportunity_id"):
        raise CrmUnavailable("This project is not linked to a CRM opportunity.")
    opp = get_opportunity(p["crm_opportunity_id"])
    if not opp:
        raise CrmUnavailable("This opportunity is no longer current in the CRM.")
    now = map_to_project(opp)
    snap = json.loads(p.get("crm_snapshot_json") or "{}")
    fields = snap.setdefault("fields", {})
    accept, ignore = [f for f in accept if f in FIELDS], [f for f in ignore if f in FIELDS]
    if accept:
        db.update(con, "project", pid, {f: now["fields"].get(f) for f in accept})
    for f in accept + ignore:
        if f in now["fields"]:
            fields[f] = now["fields"][f]
        else:
            fields.pop(f, None)
    snap["modified"] = opp.get("modified_datetime")
    db.update(con, "project", pid, dict(crm_snapshot_json=json.dumps(snap)))
    return dict(accepted=accept, ignored=ignore)
