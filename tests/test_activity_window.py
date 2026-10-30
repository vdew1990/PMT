import pytest
from fastapi.testclient import TestClient

from app import db, engine, programme


def _job(con):
    pid = db.insert(con, "project", dict(name="Window", status_date="2026-09-30", project_start="2026-01-01", project_end="2027-06-30"))
    top = db.insert(con, "cbs_node", dict(project_id=pid, code="PS04", name="Construction Subcontractors", kind="group", gp="PS", category="PS04"))
    a = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=top, code="PS04.001", name="Civil", kind="line", gp="PS", method="AT-BUDGET", start_date="2026-01-01", end_date="2027-06-30"))
    b = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=top, code="PS04.002", name="Fencing", kind="line", gp="PS", method="AT-BUDGET"))
    for n in (a, b):
        db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=n, kind="estimate", budget=120000, date="2026-01-01"))
    ta = db.insert(con, "programme_task", dict(project_id=pid, seq=0, name="Civil works", start_date="2026-10-01", finish_date="2027-03-31", link_node_id=a))
    tb = db.insert(con, "programme_task", dict(project_id=pid, seq=1, name="Fencing", start_date="2026-10-01", finish_date="2027-03-31", link_node_id=b))
    con.commit(); engine._cache.clear()
    return pid, a, b, ta, tb


def _manual(con, nid):
    return {r["month"]: r["amount"] for r in con.execute("SELECT month, amount FROM forecast_manual WHERE node_id=? AND item_id IS NULL", (nid,))}


def test_typing_a_future_month_copies_the_old_method_then_overwrites_the_cell(blank):
    pid, a, b, *_ = _job(blank)
    c = TestClient(__import__("app.main", fromlist=["app"]).app)
    r = c.post(f"/api/p/{pid}/nodes/{a}/forecast-set", json=dict(month="2026-11", unit="$", value=5000, convert=True)).json()
    assert r["converted"] and r["amount"] == 5000
    engine._cache.clear()
    row = next(x for x in engine.compute(blank, pid)["rows"] if x["id"] == a)
    assert row["method"] == "MANUAL"
    m = _manual(blank, a)
    assert m["2026-11"] == 5000 and len(m) > 2             # the other months kept what AT-BUDGET gave


def test_window_set_by_hand_survives_a_schedule_update_and_can_return_to_it(blank):
    from app import services
    pid, a, b, ta, tb = _job(blank)
    services.update_node(blank, pid, a, {"start_date": "2026-11-01", "end_date": "2027-01-31"})        # override on line a
    assert db.one(blank, "SELECT window_manual w FROM cbs_node WHERE id=?", (a,))["w"] == 1
    services.update_node(blank, pid, b, {"start_date": None, "end_date": None})
    assert db.one(blank, "SELECT window_manual w FROM cbs_node WHERE id=?", (b,))["w"] == 0
    db.update(blank, "programme_task", ta, {"finish_date": "2027-04-30"})
    db.update(blank, "programme_task", tb, {"finish_date": "2027-04-30"})
    r = programme.apply(blank, pid, targets=("costs",))
    assert r["kept"] == 1 and r["nodes"] == 1
    assert db.one(blank, "SELECT end_date e FROM cbs_node WHERE id=?", (a,))["e"] == "2027-01-31"      # kept
    assert db.one(blank, "SELECT end_date e FROM cbs_node WHERE id=?", (b,))["e"] == "2027-04-30"      # followed the schedule
    c = TestClient(__import__("app.main", fromlist=["app"]).app)
    blank.commit()
    c.post(f"/api/p/{pid}/nodes/{a}/window-reset")
    assert db.one(blank, "SELECT end_date e, window_manual w FROM cbs_node WHERE id=?", (a,)) == {"e": "2027-04-30", "w": 0}


def test_typed_months_outside_a_moved_window_are_reported(blank):
    pid, a, b, ta, tb = _job(blank)
    db.update(blank, "cbs_node", b, {"method": "MANUAL", "start_date": "2026-10-01", "end_date": "2027-03-31"})
    for m in ("2026-12", "2027-03"):
        db.insert(blank, "forecast_manual", dict(project_id=pid, node_id=b, item_id=None, month=m, amount=1000))
    db.update(blank, "programme_task", tb, {"finish_date": "2027-01-31"})
    r = programme.apply(blank, pid, targets=("costs",))
    w = r["warnings"]
    assert len(w) == 1 and w[0]["node_id"] == b and w[0]["months"] == ["2027-03"]
    assert _manual(blank, b)["2027-03"] == 1000            # nothing is cleared silently


def _ms(con, pid, name, d):
    return db.insert(con, "programme_task", dict(project_id=pid, seq=9, name=name, start_date=d, finish_date=d, milestone=1))


def _dates(con, nid):
    r = db.one(con, "SELECT start_date s, end_date e FROM cbs_node WHERE id=?", (nid,))
    return r["s"], r["e"]


def test_same_milestone_on_both_ends_lands_the_forecast_in_that_month(blank):
    pid, a, b, ta, tb = _job(blank)
    ms = _ms(blank, pid, "Energisation", "2026-12-15")
    programme.set_window(blank, pid, a, {"mode": "schedule", "task_id": ms, "edge": "start"}, {"mode": "schedule", "task_id": ms, "edge": "start"})
    assert _dates(blank, a) == ("2026-12-15", "2026-12-15")
    db.update(blank, "programme_task", ms, {"start_date": "2027-01-20", "finish_date": "2027-01-20"})
    programme.apply(blank, pid, targets=("costs",))
    assert _dates(blank, a) == ("2027-01-20", "2027-01-20")                 # the milestone moves, the window moves with it


def test_milestone_start_plus_duration_drives_the_end(blank):
    pid, a, b, ta, tb = _job(blank)
    ms = _ms(blank, pid, "Site start", "2026-11-10")
    programme.set_window(blank, pid, a, {"mode": "schedule", "task_id": ms, "edge": "start"}, {"mode": "duration"}, 4)
    assert _dates(blank, a) == ("2026-11-10", "2027-02-28")
    db.update(blank, "programme_task", ms, {"start_date": "2026-12-05", "finish_date": "2026-12-05"})
    programme.apply(blank, pid, targets=("costs",))
    assert _dates(blank, a) == ("2026-12-05", "2027-03-31")


def test_typing_over_one_end_detaches_only_that_end_and_it_can_return(blank):
    pid, a, b, ta, tb = _job(blank)                                          # a is linked the old way: start and stop follow task ta
    programme.apply(blank, pid, targets=("costs",))
    assert _dates(blank, a) == ("2026-10-01", "2027-03-31")
    programme.set_window(blank, pid, a, {"mode": "typed", "date": "2026-11-15"}, {"mode": "schedule", "task_id": ta, "edge": "finish"})
    db.update(blank, "programme_task", ta, {"start_date": "2026-09-01", "finish_date": "2027-05-31"})
    programme.apply(blank, pid, targets=("costs",))
    assert _dates(blank, a) == ("2026-11-15", "2027-05-31")                   # start kept (typed), stop followed the schedule
    w = programme.window_state(blank, pid, a)[1]
    assert w["start"]["suspended"] and not w["stop"]["suspended"]
    programme.reset_window(blank, pid, a, "start")
    assert _dates(blank, a) == ("2026-09-01", "2027-05-31")


def test_links_listing_both_directions(blank):
    from fastapi.testclient import TestClient
    pid, a, b, ta, tb = _job(blank)
    ms = _ms(blank, pid, "Handover", "2027-02-01")
    blank.commit()
    c = TestClient(__import__("app.main", fromlist=["app"]).app)
    c.post(f"/api/p/{pid}/programme/links", json=dict(task_id=ms, node_id=b, role="stop", edge="start"))
    r = c.get(f"/api/p/{pid}/programme/links").json()
    assert any(x["task_id"] == ta and x["node_id"] == a for x in r["span"])
    assert any(x["task_id"] == ms and x["node_id"] == b and x["role"] == "stop" for x in r["anchors"])
    c.delete(f"/api/p/{pid}/programme/links", params=dict(task_id=ms, node_id=b, role="stop"))
    assert c.get(f"/api/p/{pid}/programme/links").json()["anchors"] == []


def test_initialise_leaves_pools_unforecast_and_adds_ctc_lines_that_the_pool_never_covers(blank):
    from app import pools, services
    pid, a, b, ta, tb = _job(blank)
    top = db.one(blank, "SELECT id FROM cbs_node WHERE code='PS04'")["id"]
    grp = db.insert(blank, "cbs_node", dict(project_id=pid, parent_id=top, code="PS04.050", name="Civil works", kind="group", gp="PS"))
    db.insert(blank, "allowance_ledger", dict(project_id=pid, node_id=grp, kind="estimate", budget=50000, date="2026-01-01"))
    db.update(blank, "project", pid, {"project_start": "2026-01-01", "project_end": "2027-06-30"})
    blank.commit()
    services.initialise(blank, pid, force=True)
    blank.commit(); engine._cache.clear()
    assert db.one(blank, "SELECT unalloc_method m FROM cbs_node WHERE id=?", (grp,))["m"] == "NONE"        # the pool is not forecast by default
    ctc = db.rows(blank, "SELECT * FROM cbs_node WHERE origin='ctc'")
    assert any(c["parent_id"] == grp and c["code"] == "PS04.050.999" and c["name"] == "CTC (Unallocated)" and c["method"] == "NONE" for c in ctc)
    assert services.ensure_ctc_lines(blank, pid) == 0                                                      # idempotent
    # forecasting a cost on the CTC line is not covered by the pool above and is never allocated from it
    c = next(x for x in ctc if x["parent_id"] == grp)
    db.update(blank, "cbs_node", c["id"], {"method": "MANUAL"})
    db.insert(blank, "forecast_manual", dict(project_id=pid, node_id=c["id"], item_id=None, month="2026-11", amount=1000))
    blank.commit(); engine._cache.clear()
    row = next(r for r in engine.compute(blank, pid)["rows"] if r["id"] == c["id"])
    assert row["ctc"] == pytest.approx(1000) and row.get("budget_status") != "COVERED"
    assert not [m for m in pools.plan(blank, pid) if m["line_id"] == c["id"]]


def test_three_placeholders_and_no_ctc_until_a_window_is_set(blank):
    from app import services
    pid, a, b, *_ = _job(blank)
    root = db.insert(blank, "cbs_node", dict(project_id=pid, code="PS", name="Subcontractors", kind="group", gp="PS"))
    blank.execute("UPDATE cbs_node SET parent_id=? WHERE project_id=? AND code='PS04'", (root, pid))
    services.ensure_ctc_lines(blank, pid)
    codes = {r["code"]: r["origin"] for r in db.rows(blank, "SELECT code, origin FROM cbs_node WHERE project_id=? AND code LIKE 'PS04.99%'", (pid,))}
    assert codes == {"PS04.998": "wip", "PS04.999": "ctc"}              # the third placeholder is the group's own allowance pot
    db.update(blank, "cbs_node", b, {"method": "AT-BUDGET"})           # line b has no window of its own or from its group
    engine._cache.clear()
    rows = {x["id"]: x for x in engine.compute(blank, pid)["rows"]}
    assert rows[b]["ctc"] == 0 and rows[a]["ctc"] > 0                  # a has a window, b stays at zero CTC
    services.update_node(blank, pid, b, {"start_date": "2026-11-01", "end_date": "2027-01-31"})
    engine._cache.clear()
    assert next(x for x in engine.compute(blank, pid)["rows"] if x["id"] == b)["ctc"] > 0


def test_unmatched_cost_lands_on_wip_not_the_pot(blank):
    from app import pronto, services
    pid, a, b, *_ = _job(blank)
    root = db.insert(blank, "cbs_node", dict(project_id=pid, code="PS", name="Subcontractors", kind="group", gp="PS"))
    blank.execute("UPDATE cbs_node SET parent_id=? WHERE project_id=? AND code='PS04'", (root, pid))
    services.ensure_ctc_lines(blank, pid)
    db.insert(blank, "pronto_tx", dict(project_id=pid, category="PS04", account_code="WIP", doc_type="GL", tx_date="2026-05-10", cost=1234,
                                       **{"class": "actual"}, month="2026-05"))
    pronto.resolve_all(blank, pid)
    wip = db.one(blank, "SELECT id FROM cbs_node WHERE project_id=? AND origin='wip'", (pid,))["id"]
    assert db.one(blank, "SELECT node_id n FROM pronto_tx WHERE project_id=?", (pid,))["n"] == wip
