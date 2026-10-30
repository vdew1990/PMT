import pytest

from app import db, services, subcontracts
from tests.conftest import *  # noqa: F401,F403


def _lines(con, pid):
    return [n for n in db.rows(con, "SELECT * FROM cbs_node WHERE project_id=? AND kind='line' ORDER BY id", (pid,))]


def test_claim_method_needs_a_subcontract_with_a_claim_schedule(demo):
    con, pid = demo
    a, b = _lines(con, pid)[:2]
    with pytest.raises(services.Problem):                     # no subcontract linked
        services.update_node(con, pid, a["id"], {"method": "CLAIM"})
    sid = db.insert(con, "subcontract", dict(project_id=pid, name="Civil", node_id=b["id"], contract_value=1000.0))
    with pytest.raises(services.Problem):                     # a subcontract but no schedule lines yet
        services.update_node(con, pid, b["id"], {"method": "CLAIM"})
    db.insert(con, "sub_milestone", dict(subcontract_id=sid, seq=1, name="Mobilise", type="Milestone", value=1000.0, start_month="2026-11"))
    assert b["id"] in subcontracts.claim_nodes(con, pid)
    services.update_node(con, pid, b["id"], {"method": "CLAIM"})
    assert db.one(con, "SELECT method FROM cbs_node WHERE id=?", (b["id"],))["method"] == "CLAIM"
    services.update_node(con, pid, a["id"], {"method": "MANUAL"})   # the other methods stay open to every line


def test_cost_control_lists_the_claim_lines_and_month_values(demo):
    from fastapi.testclient import TestClient
    from app.main import app
    con, pid = demo
    con.commit()
    with TestClient(app) as c:
        r = c.get(f"/api/p/{pid}/cost-control?months=1").json()
    assert "claim_nodes" in r and r["grid"]
    leaves = [x for x in r["rows"] if x["kind"] in ("line", "pot")]
    assert all(len(x["a"]) == len(r["grid"]) and len(x["f"]) == len(r["grid"]) for x in leaves)


def test_programme_mpp_is_read_through_mpxj(tmp_path):
    pytest.importorskip("jpype")
    import shutil
    from app import programme
    from tests.conftest import ROOT
    f = tmp_path / "prog.mpp"                       # MPXJ detects the format from the content, so MSPDI content stands in for a binary file
    shutil.copy(ROOT / "demo" / "demo_programme.xml", f)
    source, tasks = programme.parse(f, "prog.mpp")
    assert source == "mpp" and len(tasks) == len(programme.read_xml(ROOT / "demo" / "demo_programme.xml"))


def test_forecast_margin_carries_the_unspent_risk_bucket_like_the_original(demo):
    from app import engine, reports
    con, pid = demo
    t = engine.compute(con, pid)["total"]
    m = reports.project_margin(con, pid)
    assert m["cost_forecast"] == pytest.approx(t["eac"] + t["risk"])
    assert m["gp_forecast"] == pytest.approx(m["revenue_recognised"] - m["cost_forecast"])
    assert m["erosion"] == pytest.approx(m["gp_forecast"] - m["gp_original"])


def test_forecast_drag_moves_either_way_never_into_the_past(demo):
    from fastapi.testclient import TestClient
    from app.main import app
    con, pid = demo
    con.commit()
    with TestClient(app) as c:
        res = c.get(f"/api/p/{pid}/cost-control?months=1").json()
        M, grid = res["status_month"], res["grid"]
        line = next(r for r in res["rows"] if r["kind"] == "line" and (r["method"] or "AT-BUDGET") in ("BURN-RATE", "AT-BUDGET") and sum(r["f"]) > 100)
        fut = [m for m, v in zip(grid, line["f"]) if m >= M and v > 0.5]
        src, dst = fut[0], grid[grid.index(fut[0]) + 2]
        url = f"/api/p/{pid}/nodes/{line['node_id']}/forecast-move"
        assert c.post(url, json={"src": src, "dst": dst}).status_code >= 400          # needs convert=true
        r = c.post(url, json={"src": src, "dst": dst, "convert": True})
        assert r.status_code == 200 and r.json()["converted"]
        back = c.post(url, json={"src": dst, "dst": src})                              # and back to the left
        assert back.status_code == 200
        past = [m for m in grid if m < M]
        if past:
            assert c.post(url, json={"src": src, "dst": past[-1]}).status_code >= 400
        after = next(x for x in c.get(f"/api/p/{pid}/cost-control?months=1").json()["rows"] if x["id"] == line["id"])
        assert after["method"] == "MANUAL" and sum(after["f"]) == pytest.approx(sum(line["f"]), abs=1)
