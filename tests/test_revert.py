import pytest
from fastapi.testclient import TestClient

from app import db, engine


def _client():
    return TestClient(__import__("app.main", fromlist=["app"]).app)


def test_revert_puts_back_the_last_action_then_the_one_before(blank):
    c = _client()
    pid = db.insert(blank, "project", dict(name="Rev", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31"))
    top = db.insert(blank, "cbs_node", dict(project_id=pid, code="PS04", name="Construction", kind="group", gp="PS", category="PS04"))
    blank.commit()
    assert c.get(f"/api/p/{pid}/revert").json()["txn"] is None
    n = c.post(f"/api/p/{pid}/nodes", json=dict(parent_id=top, name="Civil", kind="line")).json()
    nid = n.get("id") or n.get("node_id")
    assert nid, n
    c.put(f"/api/p/{pid}/nodes/{nid}", json=dict(name="Civil works"))
    assert db.one(blank, "SELECT name FROM cbs_node WHERE id=?", (nid,))["name"] == "Civil works"
    assert c.post(f"/api/p/{pid}/revert").status_code == 200
    assert db.one(blank, "SELECT name FROM cbs_node WHERE id=?", (nid,))["name"] == "Civil"      # the rename is undone
    assert c.post(f"/api/p/{pid}/revert").status_code == 200
    assert db.one(blank, "SELECT 1 x FROM cbs_node WHERE id=?", (nid,)) is None                  # then the creation
    assert c.get(f"/api/p/{pid}/revert").json()["txn"] is None


def test_ledger_entry_edit_keeps_a_move_balanced(blank):
    c = _client()
    pid = db.insert(blank, "project", dict(name="Led", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31"))
    a = db.insert(blank, "cbs_node", dict(project_id=pid, code="PS04", name="A", kind="group", gp="PS"))
    b = db.insert(blank, "cbs_node", dict(project_id=pid, code="PS04.001", parent_id=a, name="B", kind="line", gp="PS"))
    db.insert(blank, "allowance_ledger", dict(project_id=pid, node_id=a, kind="estimate", budget=1000))
    blank.commit()
    assert c.post(f"/api/p/{pid}/ledger/transfer", json=dict(from_id=a, to_id=b, budget=300, risk=0, ref="T1")).status_code == 200
    legs = db.rows(blank, "SELECT * FROM allowance_ledger WHERE project_id=? AND kind='transfer' ORDER BY id", (pid,))
    to_leg = next(x for x in legs if x["budget"] > 0)
    assert c.put(f"/api/p/{pid}/ledger/{to_leg['id']}", json=dict(budget=250, note="fixed", reason="keying error")).status_code == 200
    legs = db.rows(blank, "SELECT * FROM allowance_ledger WHERE project_id=? AND kind='transfer'", (pid,))
    assert sorted(x["budget"] for x in legs) == [-250, 250] and all(x["note"] == "fixed" for x in legs)
    assert c.delete(f"/api/p/{pid}/ledger/{to_leg['id']}?reason=entered%20twice").status_code == 200
    assert not db.rows(blank, "SELECT 1 FROM allowance_ledger WHERE project_id=? AND kind='transfer'", (pid,))
    assert c.post(f"/api/p/{pid}/revert").status_code == 200                                       # revert brings the move back
    assert len(db.rows(blank, "SELECT 1 FROM allowance_ledger WHERE project_id=? AND kind='transfer'", (pid,))) == 2


def test_redo_applies_the_reverted_action_again_until_a_new_change(blank):
    c = _client()
    pid = db.insert(blank, "project", dict(name="Redo", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31"))
    top = db.insert(blank, "cbs_node", dict(project_id=pid, code="PS04", name="Construction", kind="group", gp="PS", category="PS04"))
    blank.commit()
    n = c.post(f"/api/p/{pid}/nodes", json=dict(parent_id=top, name="Civil", kind="line")).json()
    nid = n.get("id") or n.get("node_id")
    c.put(f"/api/p/{pid}/nodes/{nid}", json=dict(name="Civil works"))
    assert c.get(f"/api/p/{pid}/revert").json()["redo"] is None
    c.post(f"/api/p/{pid}/revert"); c.post(f"/api/p/{pid}/revert")
    assert db.one(blank, "SELECT 1 x FROM cbs_node WHERE id=?", (nid,)) is None
    assert c.get(f"/api/p/{pid}/revert").json()["redo"]
    assert c.post(f"/api/p/{pid}/redo").status_code == 200                                            # the creation comes back
    assert db.one(blank, "SELECT name FROM cbs_node WHERE id=?", (nid,))["name"] == "Civil"
    assert c.post(f"/api/p/{pid}/redo").status_code == 200                                            # then the rename
    assert db.one(blank, "SELECT name FROM cbs_node WHERE id=?", (nid,))["name"] == "Civil works"
    assert c.get(f"/api/p/{pid}/revert").json()["redo"] is None
    c.post(f"/api/p/{pid}/revert")                                                                     # undo the rename, then make a new change
    c.put(f"/api/p/{pid}/nodes/{nid}", json=dict(name="Different"))
    assert c.get(f"/api/p/{pid}/revert").json()["redo"] is None                                       # a new change ends the redo trail


def test_stage_and_phase_records_keep_start_and_end_and_close_the_previous_one(blank):
    from app import gates
    pid = db.insert(blank, "project", dict(name="Stages", status_date="2026-09-30"))
    gates.stage_add(blank, pid, "Handover", "2026-01-05", "kick-off")
    gates.stage_add(blank, pid, "Setup", "2026-03-01")
    rows = {r["stage"]: r for r in gates.stage_log(blank, pid)}
    assert rows["Handover"]["end_date"] == "2026-03-01" and rows["Setup"]["end_date"] is None
    assert gates.stage_current(gates.stage_log(blank, pid))["stage"] == "Setup"
    gates.stage_update(blank, pid, rows["Setup"]["id"], "2026-03-01", "2026-06-30", "set up done")
    assert gates.stage_log(blank, pid)[-1]["end_date"] == "2026-06-30"
    with pytest.raises(ValueError):
        gates.stage_update(blank, pid, rows["Setup"]["id"], "2026-03-01", "2026-02-01")
    gates.phase_add(blank, pid, "Design", "2026-04-01")
    gates.phase_add(blank, pid, "Procure", "2026-05-15", end_date="2026-08-01")
    ph = {r["phase"]: r for r in gates.phase_log(blank, pid)}
    assert ph["Design"]["end_date"] == "2026-05-15" and ph["Procure"]["end_date"] == "2026-08-01"


def test_delivery_sub_phases_only_exist_inside_the_delivery_stage(blank):
    from app import gates
    pid = db.insert(blank, "project", dict(name="Sub", status_date="2026-09-30"))
    gates.stage_add(blank, pid, "Setup", "2026-02-01")
    gates.phase_add(blank, pid, "Commission", "2026-08-01")                         # cannot be in Setup and Commissioning
    assert gates.stage_current(gates.stage_log(blank, pid))["stage"] == "Delivery"
    assert {r["stage"]: r["end_date"] for r in gates.stage_log(blank, pid)}["Setup"] == "2026-08-01"
    gates.stage_add(blank, pid, "Close Out", "2026-11-01")                          # leaving Delivery ends the open sub-phase
    assert gates.phase_log(blank, pid)[-1]["end_date"] == "2026-11-01"
