import pytest

from app import allowance, db, engine
from app.services import Problem


def _job(con, bucket=100000, cost=0, code="ACME"):
    pid = db.insert(con, "project", dict(name="Allowance", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31"))
    top = db.insert(con, "cbs_node", dict(project_id=pid, code="PS04", name="Construction Subcontractors", kind="group", category="PS04", gp="PS"))
    grp = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=top, code="PS04.001", name="Civil", kind="group", gp="PS"))
    db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=grp, kind="estimate", budget=bucket, date="2026-01-01"))
    if cost:
        db.insert(con, "pronto_tx", {"project_id": pid, "cost": cost, "tx_date": "2026-08-15", "month": "2026-08", "class": "actual", "node_id": grp,
                                     "category": "PS04", "resource_code": code})
    con.commit(); engine._cache.clear()
    return pid, grp


def _alw(con, pid, nid):
    engine._cache.clear()
    return {r["node_id"]: r for r in engine.compute(con, pid)["rows"] if r["kind"] in ("line", "pot")}


def test_option1_sets_the_initial_budget_and_cannot_overdraw(blank):
    pid, grp = _job(blank)
    with pytest.raises(Problem):
        allowance.link(blank, pid, grp, "supplier", "NEW", 1, 150000)
    out = allowance.link(blank, pid, grp, "supplier", "NEW", 1, 30000, name="New Co")
    assert out["draw"] == 30000 and out["bucket_after"] == pytest.approx(70000)
    assert blank.execute("SELECT COUNT(*) FROM allowance_ledger WHERE ref='LINK'").fetchone()[0] == 2
    assert _alw(blank, pid, grp)[out["line_id"]]["budget"] == pytest.approx(30000)


def test_option2_covers_the_cost_and_is_capped_by_the_bucket(blank):
    pid, grp = _job(blank, bucket=100000, cost=60000)
    out = allowance.link(blank, pid, grp, "supplier", "ACME", 2)
    assert out["cost"] == pytest.approx(60000) and out["draw"] == pytest.approx(60000) and out["uncovered"] == 0
    pid2, grp2 = _job(blank, bucket=40000, cost=60000)
    out = allowance.link(blank, pid2, grp2, "supplier", "ACME", 2)
    assert out["draw"] == pytest.approx(40000) and out["uncovered"] == pytest.approx(20000)


def test_option3_is_a_floor_plus_an_extra_amount(blank):
    pid, grp = _job(blank, bucket=100000, cost=60000)
    out = allowance.link(blank, pid, grp, "supplier", "ACME", 3, 25000)
    assert out["draw"] == pytest.approx(85000) and out["line_allowance_after"] == pytest.approx(85000)
    pid2, grp2 = _job(blank, bucket=100000, cost=60000)
    with pytest.raises(Problem):
        allowance.link(blank, pid2, grp2, "supplier", "ACME", 3, 50000)


def test_preview_changes_nothing_and_options_check_the_cost(blank):
    pid, grp = _job(blank, cost=60000)
    n = blank.execute("SELECT COUNT(*) FROM cbs_node").fetchone()[0]
    out = allowance.link(blank, pid, grp, "supplier", "ACME", 2, dry=True)
    assert out["draw"] == pytest.approx(60000) and blank.execute("SELECT COUNT(*) FROM cbs_node").fetchone()[0] == n
    assert blank.execute("SELECT COUNT(*) FROM allowance_ledger WHERE ref='LINK'").fetchone()[0] == 0
    with pytest.raises(Problem):
        allowance.link(blank, pid, grp, "supplier", "ACME", 1, 5000)
    ov = allowance.overview(blank, pid)
    assert ov["buckets"] and ov["resources"][0]["state"] == "cost_no_line" and ov["resources"][0]["code"] == "ACME"


def test_spread_moves_the_pool_to_its_lines_and_cannot_overdraw_or_leave_the_group(blank):
    pid, grp = _job(blank, bucket=100000)
    a = allowance.link(blank, pid, grp, "supplier", "A1", 1, 0, name="A")["line_id"]
    b = allowance.link(blank, pid, grp, "supplier", "B1", 1, 0, name="B")["line_id"]
    out = allowance.spread(blank, pid, grp, [{"to_id": a, "budget": 30000}, {"to_id": b, "budget": 20000}])
    assert out["total"] == 50000 and out["left_after"] == pytest.approx(50000) and len(out["pairs"]) == 2
    with pytest.raises(Problem):
        allowance.spread(blank, pid, grp, [{"to_id": a, "budget": 60000}])               # more than the pool has left
    other = db.insert(blank, "cbs_node", dict(project_id=pid, code="PS09", name="Elsewhere", kind="line", gp="PS"))
    with pytest.raises(Problem):
        allowance.spread(blank, pid, grp, [{"to_id": other, "budget": 10}])              # not beneath this group
    allowance.undo_spread(blank, pid, out["pairs"])
    assert blank.execute("SELECT COUNT(*) FROM allowance_ledger WHERE ref='SPREAD'").fetchone()[0] == 0
