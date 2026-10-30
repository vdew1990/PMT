"""Change log: every insert, update and delete, with who made it and when.

SQLite triggers on every data table write one `change_log` row per changed record, so nothing that writes through
any code path can skip it. The rows are both the audit trail (who changed what, old and new values) and the
payload the shared-folder sync sends to the other users (see sync.py).

Timestamps come from a hybrid logical clock: wall-clock microseconds, but never behind the newest change already
seen from anyone, so "later" always means later in cause and effect even when PC clocks drift.
"""
import json
import threading
import time
import uuid
from contextvars import ContextVar

from . import identity

# Tables that are local machinery, not project data.
NOT_LOGGED = {"change_log", "sync_state", "sync_file", "audit_log", "sqlite_sequence", "ecf_role"}   # ecf_role is the framework seeded identically on every PC; HR's revisions go in ecf_edit, which is logged
# Columns whose changes are bookkeeping, not edits.
IGNORED_COLS = {"project": {"version"}}
# Bulk landing tables: a delete keeps no copy of the old row (re-importing Pronto deletes thousands of rows).
LEAN_DELETE = {"pronto_tx", "pronto_labour", "pronto_po", "pronto_claim", "pronto_variation", "pronto_ctd", "snapshot_line"}
# How a table without project_id finds its project.
PARENT_PROJECT = {
    "claim_line": "(SELECT project_id FROM claim WHERE id={r}.claim_id)",
    "revenue_plan": "(SELECT project_id FROM contract_item WHERE id={r}.item_id)",
    "variation_rev": "(SELECT project_id FROM variation WHERE id={r}.variation_id)",
    "variation_line": "(SELECT project_id FROM variation WHERE id={r}.variation_id)",
    "variation_price": "(SELECT project_id FROM variation WHERE id={r}.variation_id)",
    "variation_event": "(SELECT project_id FROM variation WHERE id={r}.variation_id)",
    "sub_milestone": "(SELECT project_id FROM subcontract WHERE id={r}.subcontract_id)",
    "sub_claim": "(SELECT project_id FROM subcontract WHERE id={r}.subcontract_id)",
    "sub_claim_line": "(SELECT s.project_id FROM sub_claim c JOIN subcontract s ON s.id=c.subcontract_id WHERE c.id={r}.claim_id)",
    "snapshot_line": "(SELECT project_id FROM snapshot WHERE id={r}.snapshot_id)",
}

txn_id: ContextVar = ContextVar("pmt_txn", default=None)
via_note: ContextVar = ContextVar("pmt_via", default=None)

_clock_lock = threading.Lock()
_last_ts = 0


def now_ts():
    """Hybrid clock tick in microseconds (a bulk load of thousands of rows moves it ahead of real time by
    milliseconds only, so a colleague's later edit still counts as later)."""
    global _last_ts
    with _clock_lock:
        t = int(time.time() * 1_000_000)
        _last_ts = max(t, _last_ts + 1)
        return _last_ts


def observe_ts(ts):
    """Move the clock past a timestamp seen from another user."""
    global _last_ts
    with _clock_lock:
        if ts and ts > _last_ts:
            _last_ts = int(ts)


class via:
    """Label changes the app makes by itself, e.g. `with changelog.via("Automatic: invoice landed in Pronto"):`."""
    def __init__(self, note):
        self.note = note

    def __enter__(self):
        self.tok = via_note.set(self.note)

    def __exit__(self, *a):
        via_note.reset(self.tok)


def new_txn():
    t = uuid.uuid4().hex[:12]
    txn_id.set(t)
    return t


def _diff(tbl, old, new):
    o, n = json.loads(old), json.loads(new)
    skip = IGNORED_COLS.get(tbl, ())
    d = {k: [o.get(k), v] for k, v in n.items() if k not in skip and o.get(k) != v}
    return json.dumps(d, separators=(",", ":")) if d else None


def register(con, logging=True):
    """Install the SQL functions the triggers call. Every connection needs them; db.connect does this."""
    con.create_function("pmt_on", 0, (lambda: 1) if logging else (lambda: 0))
    con.create_function("pmt_ts", 0, now_ts)
    con.create_function("pmt_upn", 0, lambda: identity.current()["upn"])
    con.create_function("pmt_name", 0, lambda: identity.current()["name"])
    con.create_function("pmt_txn", 0, lambda: txn_id.get())
    con.create_function("pmt_via", 0, lambda: via_note.get())
    con.create_function("pmt_diff", 3, _diff, deterministic=True)


def _cols(con, table):
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


def data_tables(con):
    names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return [t for t in names if t not in NOT_LOGGED and not t.startswith("sqlite_") and "id" in _cols(con, t)]


def install_triggers(con):
    """(Re)create the three triggers per data table. Run at start-up, after migrations, so new columns are covered."""
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'pmtlog_%'").fetchall():
        con.execute(f"DROP TRIGGER IF EXISTS {name}")
    for t in data_tables(con):
        cols = _cols(con, t)

        def obj(ref):
            return "json_object(" + ",".join(f"'{c}',{ref}.{c}" for c in cols) + ")"

        def pid(ref):
            if t == "project":
                return f"{ref}.id"
            if "project_id" in cols:
                return f"{ref}.project_id"
            return PARENT_PROJECT.get(t, "NULL").format(r=ref)
        head = "INSERT INTO change_log(ts, at, user_upn, user_name, via, txn, project_id, tbl, row_id, op, data) "
        meta = "pmt_ts(), strftime('%Y-%m-%dT%H:%M:%fZ','now'), pmt_upn(), pmt_name(), pmt_via(), pmt_txn()"
        con.execute(f"CREATE TRIGGER pmtlog_{t}_i AFTER INSERT ON {t} WHEN pmt_on() BEGIN {head}"
                    f"VALUES ({meta}, {pid('NEW')}, '{t}', NEW.id, 'I', {obj('NEW')}); END")
        con.execute(f"CREATE TRIGGER pmtlog_{t}_u AFTER UPDATE ON {t} WHEN pmt_on() BEGIN {head}"
                    f"SELECT {meta}, {pid('NEW')}, '{t}', NEW.id, 'U', d FROM (SELECT pmt_diff('{t}', {obj('OLD')}, {obj('NEW')}) AS d) WHERE d IS NOT NULL; END")
        old = "NULL" if t in LEAN_DELETE else obj("OLD")
        con.execute(f"CREATE TRIGGER pmtlog_{t}_d AFTER DELETE ON {t} WHEN pmt_on() BEGIN {head}"
                    f"VALUES ({meta}, {pid('OLD')}, '{t}', OLD.id, 'D', {old}); END")
