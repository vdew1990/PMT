"""Argus: independent checks for Neo's Ground-Up register date display (safe part) and F5, the lasting lost-link flag (Q13).

Expected results come from Neo's test briefs as relayed by Atlas on 31/10/2026, not from the code. Synthetic data only:
the demo seed (`demo` fixture) and fresh databases (`blank` fixture and two temporary synced copies). The Q14 rule (own
dates against the line window) is not decided and is deliberately not tested here.
"""
import json
import sqlite3
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, identity, main, sync


def _client():
    from app.routers import _shared
    _shared.UPLOADS.mkdir(parents=True, exist_ok=True)
    return TestClient(main.app)


def _ok(r):
    assert r.status_code == 200, (r.status_code, r.text)
    return r.json()


# ---------------------------------------------------------------------------
# Ground-Up register date display (safe part only)
# ---------------------------------------------------------------------------
# Expected start/end per item, from the brief (PS04.003 Lump, PM03.002) and, for the rest, the register as served by the
# predecessor commit 00257d8 on the same fresh demo seed (captured by Argus before this change; "unchanged from before").
EXPECTED_ITEMS = [
    ("PM02.002", "Lump", "Retention release", 30000.00, "2026-11-15", "2026-11-30"),
    ("PL04.005", "Recurring", "Site supervision to PC", 49020.00, "2026-10-01", "2026-11-30"),
    ("PS04.003", "Roster", "Bulk earthworks crew", 244320.00, "2026-10-05", None),
    ("PS04.003", "Roster", "Leading hand", 52600.00, "2026-10-05", None),
    ("PS04.003", "Lump", "Demobilisation", 18000.00, "2026-12-10", None),
    ("PM03.002", "Milestones", "33 kV switchboard (PO 1045)", 480000.00, "2025-02-01", "2026-11-30"),
    ("PL05.002", "Calendar", "Commissioning on site", 47320.00, "2025-02-01", "2026-11-30"),
    ("PL03.003", "Calendar", "Protection settings review (from the PL03 pool)", 11400.00, "2025-02-01", "2026-11-30"),
    ("PE05.002", "Lump", "Expedited freight for late switchgear", 22000.00, "2026-10-10", "2026-11-30"),
]


def test_groundup_register_dates_on_demo_seed(demo):
    con, pid = demo
    c = _client()
    reg = _ok(c.get(f"/api/p/{pid}/groundup"))
    assert reg["month"] == "2026-09"
    items = reg["items"]

    # 1. no item shows an end before its start
    bad = [(i["code"], i["scope"], i["start"], i["end"]) for i in items if i["start"] and i["end"] and i["end"] < i["start"]]
    assert bad == []

    # 2. PS04.003 Lump $18,000.00
    lump = [i for i in items if i["code"] == "PS04.003" and i["spread"] == "Lump"]
    assert len(lump) == 1
    lump = lump[0]
    assert lump["total"] == 18000.00
    assert (lump["start"], lump["end"]) == ("2026-12-10", None)
    assert lump["months"] == {"2026-12": 18000.0}
    assert (lump["start_own"], lump["end_own"]) == ("2026-12-10", None)

    # 3. the other items unchanged (and the list of items itself unchanged)
    got = sorted((i["code"], i["spread"], i["scope"], round(i["total"], 2), i["start"], i["end"]) for i in items)
    assert got == sorted(EXPECTED_ITEMS)
    pm = next(i for i in items if i["code"] == "PM03.002")
    assert (pm["start"], pm["end"]) == ("2025-02-01", "2026-11-30")

    # 4. register total, and month-by-month tie to Cost control (oracle: sum of the register's item months per line)
    assert round(reg["total"], 2) == 954660.00
    assert round(sum(i["total"] for i in items), 2) == 954660.00
    cc = _ok(c.get(f"/api/p/{pid}/cost-control"))
    reg_by_line = defaultdict(lambda: defaultdict(float))
    for i in items:
        for m, v in i["months"].items():
            reg_by_line[i["node_id"]][m] += v
    gu_lines = [r for r in cc["rows"] if r.get("method") == "GROUND-UP" and r.get("kind") == "line"]
    assert {r["id"] for r in gu_lines} == set(reg_by_line)
    reg_month, cc_month = defaultdict(float), defaultdict(float)
    for r in gu_lines:
        f = {m: round(v or 0, 2) for m, v in zip(cc["grid"], r["f"]) if abs(v or 0) > 0.005}
        assert f == {m: round(v, 2) for m, v in reg_by_line[r["id"]].items()}, r["code"]
        for m, v in f.items():
            cc_month[m] += v
    for i in items:
        for m, v in i["months"].items():
            reg_month[m] += v
    assert {m: round(v, 2) for m, v in cc_month.items()} == {m: round(v, 2) for m, v in reg_month.items()}


# ---------------------------------------------------------------------------
# F5: the lasting lost-link flag
# ---------------------------------------------------------------------------
CSV_FULL = "WBS,Name,Start,Finish\n1.1,Site start,10/11/2026,10/11/2026\n1.2,Concrete pour,01/12/2026,31/03/2027\n"
CSV_GONE = "WBS,Name,Start,Finish\n1.2,Concrete pour,01/12/2026,31/03/2027\n"


def _upload(c, pid, csv):
    return _ok(c.post(f"/api/p/{pid}/programme/upload", files={"file": ("schedule.csv", csv, "text/csv")}))


def _tasks(c, pid):
    return {t["name"]: t for t in _ok(c.get(f"/api/p/{pid}/programme/tasks"))}


def _row(c, pid, nid):
    return next(r for r in _ok(c.get(f"/api/p/{pid}/cost-control"))["rows"] if str(r["id"]) == str(nid))


def _f5_setup(c, name="F5 synthetic"):
    pid = _ok(c.post("/api/projects", json=dict(name=name, status_date="30/09/2026", project_start="01/01/2026", project_end="30/06/2027")))["id"]
    rows = _ok(c.get(f"/api/p/{pid}/cost-control"))["rows"]
    grp = next(r["id"] for r in rows if r.get("code") == "PS04" and r.get("kind") == "group")
    a = _ok(c.post(f"/api/p/{pid}/nodes", json=dict(parent_id=grp, code="PS04.001", name="Earthworks", kind="line")))["id"]
    b = _ok(c.post(f"/api/p/{pid}/nodes", json=dict(parent_id=grp, code="PS04.002", name="Fencing", kind="line")))["id"]
    _upload(c, pid, CSV_FULL)
    t = _tasks(c, pid)
    _ok(c.post(f"/api/p/{pid}/nodes/{a}/window", json={
        "start": {"mode": "schedule", "task_id": t["Site start"]["id"], "edge": "start"}, "stop": {"mode": "duration"}, "months": 4}))
    return pid, a, b


def _expected_flag():
    return [{"date": date.today().isoformat(), "task": "Site start", "wbs": "1.1", "role": "start"}]


def _flag(c, pid, nid):
    return _row(c, pid, nid).get("schedule_link_lost")


def _lose(c):
    pid, a, b = _f5_setup(c)
    assert _flag(c, pid, a) is None            # nothing lost yet
    _upload(c, pid, CSV_GONE)
    return pid, a, b


def _window_iso(con, nid):
    return tuple(con.execute("SELECT start_date, end_date FROM cbs_node WHERE id=?", (nid,)).fetchone())


def test_f5_flag_set_on_lost_link_and_window_kept(blank):
    c = _client()
    pid, a, b = _lose(c)
    assert _flag(c, pid, a) == _expected_flag()
    assert _flag(c, pid, b) is None
    assert _window_iso(blank, a) == ("2026-11-10", "2027-02-28")


def test_f5_second_identical_upload_keeps_one_entry(blank):
    c = _client()
    pid, a, b = _lose(c)
    _upload(c, pid, CSV_GONE)
    assert _flag(c, pid, a) == _expected_flag()
    assert _flag(c, pid, b) is None
    assert _window_iso(blank, a) == ("2026-11-10", "2027-02-28")


def test_f5_dismiss_clears_then_repeat_is_zero(blank):
    c = _client()
    pid, a, b = _lose(c)
    assert _ok(c.delete(f"/api/p/{pid}/nodes/{a}/schedule-link-lost")) == {"cleared": 1}
    assert _flag(c, pid, a) is None
    assert _ok(c.delete(f"/api/p/{pid}/nodes/{a}/schedule-link-lost")) == {"cleared": 0}
    assert _flag(c, pid, a) is None
    assert _window_iso(blank, a) == ("2026-11-10", "2027-02-28")   # dismissing does not move the window


def test_f5_dismiss_on_unflagged_line_is_zero(blank):
    """Exploratory: dismissing a line that was never flagged."""
    c = _client()
    pid, a, b = _lose(c)
    assert _ok(c.delete(f"/api/p/{pid}/nodes/{b}/schedule-link-lost")) == {"cleared": 0}
    assert _flag(c, pid, a) == _expected_flag()


def test_f5_relink_by_window_editor_clears(blank):
    c = _client()
    pid, a, b = _lose(c)
    t = _tasks(c, pid)
    _ok(c.post(f"/api/p/{pid}/nodes/{a}/window", json={
        "start": {"mode": "schedule", "task_id": t["Concrete pour"]["id"], "edge": "start"}, "stop": {"mode": "duration"}, "months": 4}))
    assert _flag(c, pid, a) is None


def test_f5_relink_by_programme_links_clears(blank):
    c = _client()
    pid, a, b = _lose(c)
    t = _tasks(c, pid)
    _ok(c.post(f"/api/p/{pid}/programme/links", json={"node_id": a, "task_id": t["Concrete pour"]["id"], "role": "start", "edge": "start"}))
    assert _flag(c, pid, a) is None


def test_f5_relink_by_accepted_suggestion_clears(blank):
    c = _client()
    pid, a, b = _lose(c)
    # a schedule that now has a task named like the line, still without Site start: the flag stays, one entry
    r = _upload(c, pid, CSV_GONE + "1.3,Earthworks,01/11/2026,31/01/2027\n")
    assert _flag(c, pid, a) == _expected_flag()
    sug = [s for s in r["suggestions"] if s["target_id"] == a]
    assert len(sug) == 1, r["suggestions"]
    s = sug[0]
    _ok(c.post(f"/api/p/{pid}/programme/suggestions/accept", json={"items": [{"task_id": s["task_id"], "kind": s["kind"], "target_id": a}]}))
    assert _flag(c, pid, a) is None


def test_f5_return_to_schedule_does_not_clear_known_limit(blank):
    """Known limit in the brief: "Return to schedule" does not clear the flag (by design). Recorded so a change is noticed."""
    c = _client()
    pid, a, b = _lose(c)
    c.post(f"/api/p/{pid}/nodes/{a}/window-reset", json={})
    assert _flag(c, pid, a) == _expected_flag()


# --- migration -------------------------------------------------------------
def test_f5_migration_on_older_db_and_twice(tmp_path):
    """An older database (simulated: the column removed from a current one, with a line already in it) gains the
    column on start-up, keeps its data, and a second start-up is harmless."""
    path = tmp_path / "old.db"
    saved = db.DB_PATH
    try:
        db.init_db(path)
        con = sqlite3.connect(path)
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'pmtlog_%'").fetchall():
            con.execute(f"DROP TRIGGER {name}")
        con.execute("ALTER TABLE cbs_node DROP COLUMN schedule_link_lost")
        con.execute("INSERT INTO project(name) VALUES ('Old synthetic')")
        pid = con.execute("SELECT max(id) FROM project").fetchone()[0]
        con.execute("INSERT INTO cbs_node(project_id, code, name, kind) VALUES (?, 'PS04.001', 'Earthworks', 'line')", (pid,))
        con.commit()
        assert "schedule_link_lost" not in {r[1] for r in con.execute("PRAGMA table_info(cbs_node)")}
        con.close()

        db.init_db(path)
        db.init_db(path)

        con = sqlite3.connect(path)
        cols = [r[1] for r in con.execute("PRAGMA table_info(cbs_node)")]
        assert cols.count("schedule_link_lost") == 1
        assert con.execute("SELECT code, name, schedule_link_lost FROM cbs_node WHERE project_id=?", (pid,)).fetchall() == [("PS04.001", "Earthworks", None)]
        trig = con.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='pmtlog_cbs_node_u'").fetchone()
        assert trig and "schedule_link_lost" in trig[0]      # the sync trigger covers the new column
        con.close()
    finally:
        db.DB_PATH = saved


# --- two synced copies -----------------------------------------------------
class _Copy:
    """One user's copy of PMT, sharing a synced folder with the other (same pattern as the builders' sync tests)."""

    def __init__(self, root, upn, name):
        self.upn, self.name, self.path = upn, name, Path(root) / f"{upn.split('@')[0]}.db"

    def use(self, monkeypatch):
        monkeypatch.setenv("PMT_USER_UPN", self.upn)
        monkeypatch.setenv("PMT_USER_NAME", self.name)
        identity.reset()
        db.DB_PATH = self.path
        if not self.path.exists():
            db.ID_SLOT = 0
            db.init_db()
            sync.start(background=False)
        else:
            con = db.connect()
            db.ID_SLOT = int(sync._state(con, "slot"))
            con.close()
        return self


@pytest.fixture()
def two_copies(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="argus-share-"))
    monkeypatch.setattr(db, "SHARED_DIR", root / "shared")
    monkeypatch.setattr(identity, "device", lambda: "PC1")
    a = _Copy(root, "argus.alpha@example.invalid", "Alpha Synthetic")
    b = _Copy(root, "argus.bravo@example.invalid", "Bravo Synthetic")
    yield a, b
    db.ID_SLOT = 0
    identity.reset()


def _db_flag(copy, nid):
    con = sqlite3.connect(copy.path)
    try:
        v = con.execute("SELECT schedule_link_lost FROM cbs_node WHERE id=?", (nid,)).fetchone()[0]
    finally:
        con.close()
    return json.loads(v) if v else None


def _shared_flow(two_copies, monkeypatch):
    """Copy A builds the project and syncs; copy B syncs and (as a user would) looks at Cost control; A re-uploads
    without Site start and syncs; B syncs. Leaves copy B in use."""
    ca, cb = two_copies
    c = _client()
    ca.use(monkeypatch)
    pid, a, b = _f5_setup(c, "F5 shared synthetic")
    sync.sync_now()
    cb.use(monkeypatch)
    sync.sync_now()
    assert _flag(c, pid, a) is None                 # B has the line, unflagged, and has viewed Cost control
    ca.use(monkeypatch)
    sync.sync_now()
    _upload(c, pid, CSV_GONE)
    assert _flag(c, pid, a) == _expected_flag()
    sync.sync_now()
    cb.use(monkeypatch)
    sync.sync_now()
    return c, pid, a, b, ca, cb


def test_f5_sync_stored_flag_and_dismissal_reach_the_other_copy(two_copies, monkeypatch):
    """The stored value on each copy (read straight from that copy's synthetic database file)."""
    c, pid, a, b, ca, cb = _shared_flow(two_copies, monkeypatch)
    assert _db_flag(cb, a) == _expected_flag()
    assert _db_flag(cb, b) is None
    assert _ok(c.delete(f"/api/p/{pid}/nodes/{a}/schedule-link-lost")) == {"cleared": 1}
    sync.sync_now()
    ca.use(monkeypatch)
    sync.sync_now()
    assert _db_flag(ca, a) is None


@pytest.mark.xfail(strict=True, reason="Argus defect 31/10/2026 (pre-existing, not F5's code): after a synced batch that "
                   "also changes the project row, the receiving copy's Cost control keeps serving its earlier cached result, "
                   "so the flag is stored but not shown. Remove this mark when fixed.")
def test_f5_sync_flag_shows_in_cost_control_on_the_other_copy(two_copies, monkeypatch):
    """What the other user sees: the Cost control row on copy B after the sync."""
    c, pid, a, b, ca, cb = _shared_flow(two_copies, monkeypatch)
    assert _flag(c, pid, a) == _expected_flag()


def test_f5_sync_dismissal_shows_in_cost_control_on_the_other_copy(two_copies, monkeypatch):
    """What the first user sees after copy B dismisses: copy A's Cost control row (A viewed it while flagged)."""
    c, pid, a, b, ca, cb = _shared_flow(two_copies, monkeypatch)
    assert _ok(c.delete(f"/api/p/{pid}/nodes/{a}/schedule-link-lost")) == {"cleared": 1}
    assert _flag(c, pid, a) is None
    sync.sync_now()
    ca.use(monkeypatch)
    assert _flag(c, pid, a) == _expected_flag()     # A, before it syncs
    sync.sync_now()
    assert _flag(c, pid, a) is None
    assert _ok(c.delete(f"/api/p/{pid}/nodes/{a}/schedule-link-lost")) == {"cleared": 0}
