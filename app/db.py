"""SQLite access. One database file; every table carries project_id so several contracts can live side by side."""
import hashlib
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from . import changelog

APP_ROOT = Path(__file__).resolve().parent.parent
# Shared mode: the program folder sits in a synced SharePoint library and holds a "shared" folder for the change
# journals. The database itself is then a private replica on this PC, never inside the synced folder.
SHARED_DIR = Path(os.environ["PMT_SHARED"]) if os.environ.get("PMT_SHARED") else None


def _default_db():
    if SHARED_DIR:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "PMT" / "replicas"
        key = hashlib.sha1(str(SHARED_DIR.resolve()).lower().encode()).hexdigest()[:10]
        return base / key / "pmt.db"
    return APP_ROOT / "data" / "pmt.db"


DB_PATH = Path(os.environ.get("PMT_DB") or _default_db())
SCHEMA = Path(__file__).with_name("schema.sql")

# New row ids: writer slot * 2^40 + n, so users sharing a project never hand out the same id (slot 0 = plain
# SQLite numbering, used when not sharing). Set by sync.start().
ID_SLOT = 0
ID_SPAN = 1 << 40
_next_id = {}
_id_lock = threading.Lock()


def connect(path=None, logging=True):
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    changelog.register(con, logging)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    return con


# Columns added after first release: (table, column, DDL). Lets an existing database pick up new fields.
MIGRATIONS = [
    ("person", "leaving_date", "TEXT"), ("person", "employment_status", "TEXT"), ("person", "engagement", "TEXT"), ("person", "aliases_json", "TEXT"),   # leaving, serving notice, contractor / secondee, other spellings of the name
    ("person", "ecf_role", "TEXT"), ("person", "ecf_level", "INTEGER"), ("person", "business_title", "TEXT"),   # the person's EPEC Classification Framework role, level and business title
    ("assessment", "scores_json", "TEXT"), ("assessment", "total", "INTEGER"), ("assessment", "band", "TEXT"),   # the PM's monthly ten-dimension complexity score (complexity.py)
    ("forecast_item", "h1", "TEXT"), ("forecast_item", "h2", "TEXT"), ("forecast_item", "h3", "TEXT"),   # the Ground-Up register's own three nested groups (labels chosen by the PM, not CBS)
    ("variation", "schedule_item_id", "INTEGER"),               # the contract (claim schedule) item this register entry stands for: its revenue stays on that item
    ("phase_log", "end_date", "TEXT"),                           # when the delivery stage ended
    ("revert_mark", "rev_id", "INTEGER"),                        # change_log id after the revert, for Redo
    ("cbs_node", "window_months", "INTEGER"),                  # typed duration (months) when the window is driven by a start or stop anchor plus a duration
    ("cbs_node", "window_manual", "INTEGER DEFAULT 0"),   # 1 = the activity window (start, end) was set by hand and ignores schedule updates
    ("cbs_node", "schedule_link_lost", "TEXT"),   # JSON list [{date, task, wbs, role}]: schedule items this line followed that a re-upload no longer has (Q13); cleared on a new link or dismiss
    ("project", "archived_at", "TEXT"), ("project", "archived_by", "TEXT"),   # archived: in the project library, data kept
    ("project", "archive_summary", "TEXT"), ("project", "location", "TEXT"), ("project", "project_director", "TEXT"),
    # accruals: what kind, who for, every reference that can match the invoice, and how it was matched
    ("accrual", "kind", "TEXT"), ("accrual", "supplier_code", "TEXT"), ("accrual", "supplier_name", "TEXT"), ("accrual", "quote_ref", "TEXT"),
    ("accrual", "matched_via", "TEXT"), ("accrual", "matched_month", "TEXT"), ("accrual", "matched_refs", "TEXT"), ("accrual", "resolution", "TEXT"),
    ("project", "project_type", "TEXT"), ("project", "capacity_mw", "REAL"), ("project", "storage_mwh", "REAL"),   # asset
    ("project", "voltage", "TEXT"), ("project", "lat", "REAL"), ("project", "lon", "REAL"), ("project", "complexity", "INTEGER"),   # figures saved on archiving; site location
    ("pronto_tx", "cat_desc", "TEXT"), ("client", "knowledge", "INTEGER"),
    ("variation_line", "item_count", "REAL"), ("variation_line", "hrs_day", "REAL"), ("variation_line", "days_wk", "REAL"),
    ("variation_line", "wks", "REAL"), ("variation_line", "price_override", "REAL"),
    ("sub_claim", "retention_release", "REAL DEFAULT 0"), ("sub_claim", "received_date", "TEXT"),
    ("sub_claim", "approved_date", "TEXT"), ("sub_claim", "paid_date", "TEXT"),
    ("claim_line", "certified", "REAL"), ("snapshot_line", "months_json", "TEXT"),
    ("subcontract", "supplier_name", "TEXT"),
    ("variation_line", "price_id", "INTEGER"), ("variation_line", "extra_qty", "REAL"), ("variation_line", "contract_rate", "REAL"),
    ("variation_line", "note", "TEXT"), ("variation", "detail_level", "TEXT DEFAULT 'scope'"), ("variation", "funding", "TEXT DEFAULT 'topup'"),
    ("variation", "exclusions", "TEXT"), ("cbs_node", "variation_id", "INTEGER"), ("cbs_node", "copied_from", "INTEGER"),
    ("accrual", "risk_id", "INTEGER"), ("forecast_item", "risk_id", "INTEGER"),
    ('risk', 'kind', "TEXT DEFAULT 'Risk'"),
    ('risk', 'category', 'TEXT'),
    ('risk', 'area', 'TEXT'),
    ('risk', 'consequences', 'TEXT'),
    ('risk', 'basis', 'TEXT'),
    ('risk', 'trigger_event', 'TEXT'),
    ('risk', 'controls', 'TEXT'),
    ('risk', 'treatment', 'TEXT'),
    ('risk', 'estimate', 'REAL DEFAULT 0'),
    ('risk', 'likelihood', 'REAL DEFAULT 0'),
    ('risk', 'control_cost', 'REAL DEFAULT 0'),
    ('risk', 'effectiveness', 'REAL DEFAULT 0'),
    ('risk', 'last_reviewed', 'TEXT'),
    ('risk', 'retire_date', 'TEXT'),
    ('risk', 'comment', 'TEXT'),
    ('risk', 'delay_days', 'REAL DEFAULT 0'), ('risk', 'delay_actual', 'REAL DEFAULT 0'),
    ('risk', 'revenue_impact', 'REAL DEFAULT 0'), ('risk', 'revenue_actual', 'REAL DEFAULT 0'),
    ('allowance_ledger', 'contingency', 'REAL DEFAULT 0'), ('allowance_ledger', 'risk_cover', 'REAL DEFAULT 0'),
    ('risk_release', 'kind', "TEXT DEFAULT 'release'"), ('risk_release', 'forced', 'INTEGER DEFAULT 0'),
    # forecast sub-methods (Calendar, Milestones, Roster) and labour in hours
    ("forecast_item", "basis", "TEXT"),            # dollars | hours | units (how day-grid values are read)
    ("forecast_item", "resource_id", "INTEGER"),   # who: employee, or supplier (with role)
    ("forecast_item", "role", "TEXT"),
    ("forecast_item", "rate_mode", "TEXT"),        # auto = follow the rate card / supplier rates; fixed = the typed rate
    ("forecast_item", "hours_day", "REAL"), ("forecast_item", "headcount", "REAL"),
    ("forecast_item", "pattern", "TEXT"),          # roster: 10:4, 5:2, 7:7, WEEKDAYS, DAILY
    ("forecast_item", "swings", "INTEGER"), ("forecast_item", "skip_holidays", "INTEGER"),
    ("forecast_item", "from_pool", "INTEGER"),     # 1 = allocated out of the (Unallocated) pool above, not in addition
    ("accrual", "role", "TEXT"),
    ("accrual", "ot_hours", "REAL"),               # overtime part of the hours, when typed as NT + OT
    ("forecast_day", "ot", "REAL"),
    # what each month-end close keeps per line, for the forecast history page
    ("snapshot_line", "method", "TEXT"), ("snapshot_line", "a_json", "TEXT"), ("snapshot_line", "x_json", "TEXT"), ("snapshot_line", "f_json", "TEXT"),
    ("snapshot_line", "kind", "TEXT"), ("snapshot_line", "parent_ref", "TEXT"),                # overtime part of a day's hours, when typed as NT + OT                  # supplier hour accruals: the role on the supplier's rates
    ("contract_item", "in_original", "INTEGER"),   # in the original contract value (NULL: base and optional yes, variation no)
    ("accrual", "hours", "REAL"), ("accrual", "rate", "REAL"), ("accrual", "resource_id", "INTEGER"), ("accrual", "day", "TEXT"),
    ("project", "is_parent", "INTEGER DEFAULT 0"),     # a parent project: its child projects' figures together (linking.py)
    ("project", "parent_project_id", "INTEGER"),       # the parent project this one is linked under
    ("programme_task", "layer", "TEXT DEFAULT 'internal'"),   # internal (drives dates) or upstream (the client or head contract schedule, for reference)
    ("sub_claim", "cert_no", "TEXT"), ("sub_claim", "cert_date", "TEXT"), ("sub_claim", "cert_by", "TEXT"), ("sub_claim", "cert_note", "TEXT"),   # the payment certificate issued when EPEC approves a subcontractor claim
    ("claim", "client_claim_no", "TEXT"), ("claim", "revision", "INTEGER"), ("claim", "revision_date", "TEXT"), ("claim", "client_cert_no", "TEXT"),   # revision of the claim; the client's payment certificate number
    ("project", "review_days", "INTEGER"), ("project", "review_basis", "TEXT"),   # the client's time to review a payment claim, from the contract: days, business or calendar
    ("project", "contract_law", "TEXT"),   # the state or territory whose law governs the contract
    ("project", "claim_act", "TEXT"),    # payment claim legislation: qld (BIF Act) | none | empty = from the site location   # the client's own number for the claim, when it differs from EPEC's
    ("kb_doc", "project_type", "TEXT"),   # library document meant for one kind of project (NULL: all types)
    ("person", "employee_code", "TEXT"), ("person", "function", "TEXT"), ("person", "phone", "TEXT"),   # employees in the directory
    # the CRM opportunity this project was started from (crm_link.py): one way copy, the CRM is never written to
    ("project", "crm_opportunity_id", "INTEGER"), ("project", "crm_record_id", "INTEGER"),
    ("project", "crm_linked_at", "TEXT"), ("project", "crm_snapshot_json", "TEXT"),   # snapshot of the mapped fields as the CRM said then
]


def init_db(path=None):
    con = connect(path)
    con.executescript(SCHEMA.read_text())
    for table, col, ddl in MIGRATIONS:
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        if have and col not in have:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    # optional prices: offered / confirmed / cancelled (older copies stored taken / declined / pending, or a template's words)
    con.execute("UPDATE contract_item SET optional_status=CASE WHEN lower(trim(optional_status)) IN ('confirmed','taken','accepted','approved','awarded','exercised','yes','y','included') "
                "THEN 'confirmed' WHEN lower(trim(optional_status)) IN ('cancelled','canceled','declined','rejected','withdrawn','not taken','deleted','no','n','excluded') "
                "THEN 'cancelled' ELSE 'offered' END WHERE kind='optional' AND COALESCE(optional_status,'') NOT IN ('offered','confirmed','cancelled')")
    from . import ecf
    ecf.seed(con)             # the EPEC Classification Framework as reference data
    from . import directory
    directory.backfill(con)   # the directory picks up the names the projects already use (once each; never overwrites)
    changelog.install_triggers(con)
    con.commit()
    con.close()


@contextmanager
def session():
    con = connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def one(con, sql, args=()):
    r = con.execute(sql, args).fetchone()
    return dict(r) if r else None


def scalar(con, sql, args=(), default=0):
    r = con.execute(sql, args).fetchone()
    return default if r is None or r[0] is None else r[0]


def new_id(con, table):
    """Next id in this writer's block (None when not sharing: SQLite numbers the row)."""
    if not ID_SLOT:
        return None
    base = ID_SLOT * ID_SPAN
    key = (str(DB_PATH), table, ID_SLOT)
    with _id_lock:
        n = _next_id.get(key)
        if n is None:
            n = (con.execute(f"SELECT MAX(id) FROM {table} WHERE id>=? AND id<?", (base, base + ID_SPAN)).fetchone()[0] or base) + 1
        _next_id[key] = n + 1
    return n


def insert(con, table, data):
    if "id" not in data or data["id"] is None:
        rid = new_id(con, table)
        if rid is not None:
            data = {"id": rid, **{k: v for k, v in data.items() if k != "id"}}
    cols = list(data)
    cur = con.execute(
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [data[c] for c in cols],
    )
    return cur.lastrowid


def update(con, table, row_id, data, where="id"):
    if not data:
        return
    cols = list(data)
    con.execute(f"UPDATE {table} SET {','.join(c + '=?' for c in cols)} WHERE {where}=?",
                [data[c] for c in cols] + [row_id])


def bump(con, pid):
    con.execute("UPDATE project SET version = COALESCE(version,0)+1 WHERE id=?", (pid,))


def log(con, pid, action, detail=""):
    con.execute("INSERT INTO audit_log(project_id, action, detail) VALUES (?,?,?)", (pid, action, detail))


def project_settings(con, pid):
    r = one(con, "SELECT settings_json FROM project WHERE id=?", (pid,))
    try:
        return json.loads((r or {}).get("settings_json") or "{}")
    except ValueError:
        return {}


# ---- month helpers ---------------------------------------------------------
def to_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def iso(v):
    d = to_date(v)
    return d.isoformat() if d else None


def month_of(v):
    d = to_date(v)
    return d.strftime("%Y-%m") if d else None


def add_months(m, n):
    y, mo = int(m[:4]), int(m[5:7])
    t = y * 12 + (mo - 1) + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def month_diff(a, b):
    return (int(b[:4]) * 12 + int(b[5:7])) - (int(a[:4]) * 12 + int(a[5:7]))


def month_range(a, b):
    if not a or not b or a > b:
        return []
    return [add_months(a, i) for i in range(month_diff(a, b) + 1)]


def month_end(m):
    y, mo = int(m[:4]), int(m[5:7])
    nxt = date(y + (mo == 12), 1 if mo == 12 else mo + 1, 1)
    return (nxt - date.resolution).isoformat()
