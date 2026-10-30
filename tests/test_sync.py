"""Two users sharing a project through a synced folder: attribution, merge, deletes, out-of-order arrival."""
import json
import tempfile
from pathlib import Path

import pytest

from app import activity, db, identity, sync


class Replica:
    """One user's copy of PMT on their own PC."""

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

    def con(self):
        return db.connect()


@pytest.fixture()
def shared(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="pmt-share-"))
    monkeypatch.setattr(db, "SHARED_DIR", root / "shared")
    monkeypatch.setattr(identity, "device", lambda: "PC1")
    pc = Replica(root, "pat.coord@epec.com.au", "Pat Coord")
    pm = Replica(root, "max.manager@epec.com.au", "Max Manager")
    yield pc, pm
    db.ID_SLOT = 0
    identity.reset()


def _seed(con):
    pid = db.insert(con, "project", dict(name="Shared job", status_date="2026-10-31"))
    nid = db.insert(con, "cbs_node", dict(project_id=pid, code="PS04.01", name="Electrical contractor", kind="line"))
    con.commit()
    return pid, nid


def test_two_users_merge_and_attribution(shared, monkeypatch):
    pc, pm = shared
    pc.use(monkeypatch)
    con = pc.con()
    pid, nid = _seed(con)
    assert pid >= db.ID_SPAN  # ids come from the writer's own block
    aid = db.insert(con, "accrual", dict(project_id=pid, node_id=nid, month="2026-10", amount=5000.0, inv_ref="INV-1", reason="Work done, invoice not yet received"))
    con.commit(); con.close()
    sync.sync_now()

    pm.use(monkeypatch)
    sync.sync_now()
    con = pm.con()
    a = db.one(con, "SELECT * FROM accrual WHERE id=?", (aid,))
    assert a["amount"] == 5000 and a["inv_ref"] == "INV-1"
    st = activity.stamps(con, "accrual", [aid])[aid]
    assert st["created_by"] == "Pat Coord"
    # PM reverses the accrual because the invoice landed
    db.update(con, "accrual", aid, {"status": "cancelled", "note": "Invoice INV-1 landed, reversed"})
    con.commit(); con.close()
    sync.sync_now()

    # meanwhile the PC (not yet synced) corrects the amount on their copy
    pc.use(monkeypatch)
    con = pc.con()
    db.update(con, "accrual", aid, {"amount": 5200.0})
    con.commit(); con.close()
    sync.sync_now()
    con = pc.con()
    a = db.one(con, "SELECT * FROM accrual WHERE id=?", (aid,))
    assert (a["status"], a["amount"], a["note"]) == ("cancelled", 5200.0, "Invoice INV-1 landed, reversed")  # both edits kept
    hist = activity.row_history(con, pid, "accrual", aid)
    who = [(h["user"], h["action"]) for h in hist]
    assert who[0] == ("Pat Coord", "added") and ("Max Manager", "changed") in who
    ch = [c for h in hist if h["user"] == "Max Manager" for c in h["changes"]]
    assert {"field": "status", "old": "open", "new": "cancelled"} in ch
    con.close()

    pm.use(monkeypatch)
    sync.sync_now()
    con = pm.con()
    assert db.one(con, "SELECT amount FROM accrual WHERE id=?", (aid,))["amount"] == 5200.0
    con.close()


def test_later_edit_wins_and_delete_is_final(shared, monkeypatch):
    pc, pm = shared
    pc.use(monkeypatch)
    con = pc.con()
    pid, nid = _seed(con)
    con.close()
    sync.sync_now()
    pm.use(monkeypatch)
    sync.sync_now()
    con = pm.con()
    db.update(con, "cbs_node", nid, {"name": "Electrical contractor (PM)"})
    con.commit(); con.close()
    pc.use(monkeypatch)
    con = pc.con()
    db.update(con, "cbs_node", nid, {"name": "Electrical contractor (PC, later)"})
    con.commit(); con.close()
    for r in (pm, pc, pm):
        r.use(monkeypatch)
        sync.sync_now()
    for r in (pm, pc):
        r.use(monkeypatch)
        con = r.con()
        assert db.one(con, "SELECT name FROM cbs_node WHERE id=?", (nid,))["name"] == "Electrical contractor (PC, later)"
        con.close()
    # delete on one side, an edit on the other: the delete stands
    con = pc.con()
    con.execute("DELETE FROM cbs_node WHERE id=?", (nid,))
    con.commit(); con.close()
    pm.use(monkeypatch)
    con = pm.con()
    db.update(con, "cbs_node", nid, {"notes": "edited after the delete elsewhere"})
    con.commit(); con.close()
    for r in (pc, pm, pc):
        r.use(monkeypatch)
        sync.sync_now()
    for r in (pm, pc):
        r.use(monkeypatch)
        con = r.con()
        assert db.one(con, "SELECT id FROM cbs_node WHERE id=?", (nid,)) is None
        con.close()


def test_change_before_row_arrives(shared, monkeypatch):
    """An update that reaches a third copy before the insert it depends on is kept and applied when the insert lands."""
    pc, pm = shared
    pc.use(monkeypatch)
    con = pc.con()
    pid, nid = _seed(con)
    con.close()
    sync.sync_now()
    journal = db.SHARED_DIR / "journal"
    entries = [json.loads(line) for f in sorted(journal.glob("*/*.jsonl")) for line in f.read_text().splitlines()]
    upd = dict(entries[-1], uid="zz@PC9:1", ts=entries[-1]["ts"] + 10, op="U", tbl="cbs_node", row_id=nid, data={"name": ["x", "Renamed"]})
    db.DB_PATH = Path(tempfile.mkdtemp()) / "third.db"  # a third user's copy that has not synced yet
    monkeypatch.setenv("PMT_USER_UPN", "third@epec.com.au")
    identity.reset()
    db.init_db()
    con = db.connect(logging=False)
    con.execute("PRAGMA foreign_keys = OFF")
    sync.apply_entries(con, [upd])  # the update first
    assert db.one(con, "SELECT id FROM cbs_node WHERE id=?", (nid,)) is None
    sync.apply_entries(con, entries)  # then the inserts
    assert db.one(con, "SELECT name FROM cbs_node WHERE id=?", (nid,))["name"] == "Renamed"
    con.close()


def test_slots_differ_and_profiles_published(shared, monkeypatch):
    pc, pm = shared
    pc.use(monkeypatch)
    con = pc.con(); sync.set_role(con, "Project Coordinator"); con.commit(); con.close()
    s1 = db.ID_SLOT
    pm.use(monkeypatch)
    s2 = db.ID_SLOT
    assert s1 and s2 and s1 != s2
    ppl = sync.people(pm.con())
    assert ppl["pat.coord@epec.com.au"]["role"] == "Project Coordinator"


def test_publish_existing_database(shared, monkeypatch, tmp_path):
    old = tmp_path / "old.db"
    save = db.DB_PATH
    db.DB_PATH = old
    db.ID_SLOT = 0
    db.init_db()
    con = db.connect()
    pid, nid = _seed(con)
    con.close()
    pc, pm = shared
    pc.use(monkeypatch)
    assert sync.publish_existing(old) >= 2
    sync.sync_now()
    pm.use(monkeypatch)
    sync.sync_now()
    con = pm.con()
    assert db.one(con, "SELECT name FROM project WHERE id=?", (pid,))["name"] == "Shared job"
    con.close()
    db.DB_PATH = save


def test_same_code_created_by_two_people(shared, monkeypatch):
    pc, pm = shared
    pc.use(monkeypatch)
    con = pc.con()
    pid, nid = _seed(con)
    con.close()
    sync.sync_now()
    pm.use(monkeypatch)
    sync.sync_now()
    con = pm.con()
    db.insert(con, "resource", dict(project_id=pid, kind="supplier", code="S30ABC01", name="ABC (by PM)"))
    con.commit(); con.close()
    pc.use(monkeypatch)
    con = pc.con()
    db.insert(con, "resource", dict(project_id=pid, kind="supplier", code="S30ABC01", name="ABC (by PC)"))
    con.commit(); con.close()
    for r in (pc, pm, pc):
        r.use(monkeypatch)
        sync.sync_now()
    seen = []
    for r in (pc, pm):
        r.use(monkeypatch)
        con = r.con()
        seen.append(sorted((x["code"], x["name"]) for x in db.rows(con, "SELECT code, name FROM resource WHERE project_id=?", (pid,))))
        con.close()
    assert seen[0] == seen[1] and len(seen[0]) == 2  # both kept, identical everywhere
    assert sum(1 for c, _ in seen[0] if c == "S30ABC01") == 1


def test_bulk_load_does_not_push_the_clock_ahead():
    import time
    from app import changelog
    for _ in range(20000):  # a Pronto import writes thousands of rows in a second
        changelog.now_ts()
    assert changelog.now_ts() - time.time() * 1_000_000 < 100_000  # less than 0.1 s ahead of real time


def test_role_belongs_to_the_person(blank, monkeypatch):
    con = blank
    for upn, role in (("pat.coord@epec.com.au", "Project Coordinator"), ("max.manager@epec.com.au", "Project Manager")):
        monkeypatch.setenv("PMT_USER_UPN", upn)
        identity.reset()
        sync.set_role(con, role)
    assert sync.me(con)["role"] == "Project Manager"
    identity.reset()
