"""Linked projects: a parent project is its children's CBS merged code by code, read-only, ties to the children."""
import pytest
from fastapi.testclient import TestClient

from app import db, engine, linking, portfolio, revenue


@pytest.fixture(scope="module")
def two(demo):
    """Two seeded demo projects (the second a fresh seed of the same data, so every CBS code exists in both)."""
    from demo import build_demo
    con, p1 = demo
    p2, _ = build_demo.seed(con)
    con.execute("UPDATE project SET name='Demo two', epec_pm='Pat PM', project_director=NULL WHERE id=?", (p2,))
    con.commit()
    return con, p1, p2


def test_parent_ties_to_children(two):
    con, p1, p2 = two
    parent = linking.link(con, "Program parent", [p1, p2], director="Dana Director")
    con.commit()
    res = engine.compute(con, parent)
    a, b = engine.compute(con, p1), engine.compute(con, p2)
    for k in ("allowance", "ctd", "acc", "ctc", "eac"):
        assert res["total"][k] == pytest.approx(a["total"][k] + b["total"][k], abs=0.01)
    # a line both children have is one row in the parent, with each child's share to drill into
    line = next(r for r in res["rows"] if r["kind"] == "line" and r["eac"])
    assert {x["project_id"] for x in line["by_project"]} == {p1, p2}
    assert line["eac"] == pytest.approx(sum(x["eac"] for x in line["by_project"]), abs=0.01)
    # groups add up to their merged children
    g = next(r for r in res["rows"] if r["kind"] == "group" and r["level"] == 1)
    kids = [r for r in res["rows"] if r["parent_id"] == g["node_id"]]
    assert g["eac"] == pytest.approx(sum(r["eac"] for r in kids), abs=0.01)
    assert len(res["grid"]) == len(res["total"]["f"])
    # revenue is the children's added
    assert revenue.summary(con, parent)["recognised"] == pytest.approx(
        revenue.summary(con, p1)["recognised"] + revenue.summary(con, p2)["recognised"], abs=0.01)


def test_parent_follows_child_changes(two):
    con, p1, p2 = two
    parent = db.scalar(con, "SELECT parent_project_id FROM project WHERE id=?", (p1,))
    before = engine.compute(con, parent)["total"]["eac"]
    nid = db.scalar(con, "SELECT id FROM cbs_node WHERE project_id=? AND kind='line' ORDER BY id LIMIT 1", (p2,))
    con.execute("UPDATE cbs_node SET method='TOP-DOWN', eac_override=COALESCE(eac_override,0)+123456 WHERE id=?", (nid,))
    db.bump(con, p2)
    con.commit()
    after = engine.compute(con, parent)["total"]["eac"]
    assert after != pytest.approx(before)
    assert after == pytest.approx(engine.compute(con, p1)["total"]["eac"] + engine.compute(con, p2)["total"]["eac"], abs=0.01)


def test_rules(two):
    con, p1, p2 = two
    parent = db.scalar(con, "SELECT parent_project_id FROM project WHERE id=?", (p1,))
    with pytest.raises(ValueError):          # already under a parent
        linking.link(con, "Another", [p1, p2])
    with pytest.raises(ValueError):          # a parent is not a child
        linking.link(con, "Nested", [parent, p1])
    with pytest.raises(ValueError):
        linking.link(con, "One", [p1])


def test_portfolio_and_rollup_count_once(two):
    con, p1, p2 = two
    parent = db.scalar(con, "SELECT parent_project_id FROM project WHERE id=?", (p1,))
    pf = portfolio.run(con)
    assert parent not in [r["id"] for r in pf["projects"]]
    assert parent in [r["id"] for r in pf["parents"]]
    child = next(r for r in pf["projects"] if r["id"] == p2)
    assert child["parent_id"] == parent and child["director"] == "Dana Director"   # inherits the parent's director
    # the parent in a rollup stands for its children: never counted twice
    r1 = portfolio.rollup(con, [parent, p1])
    r2 = portfolio.rollup(con, [p1, p2])
    assert r1["total"]["eac"] == pytest.approx(r2["total"]["eac"], abs=0.01)


def test_api_guard_unlink_delete(two):
    con, p1, p2 = two
    parent = db.scalar(con, "SELECT parent_project_id FROM project WHERE id=?", (p1,))
    from app.main import app
    c = TestClient(app)
    r = c.post(f"/api/p/{parent}/contract/items", json={"description": "x"})
    assert r.status_code == 400 and "parent project" in r.json()["detail"]
    d = c.get(f"/api/p/{parent}/linked").json()
    assert d["is_parent"] and {x["id"] for x in d["children"]} == {p1, p2}
    assert c.get(f"/api/p/{parent}/dashboard").status_code == 200
    assert c.get(f"/api/p/{parent}/cost-control?months=1&merge=1").json()["is_parent"]
    assert c.post(f"/api/projects/{p2}/unlink").json()["parent_id"] == parent
    assert [x["id"] for x in c.get(f"/api/p/{parent}/linked").json()["children"]] == [p1]
    assert c.post("/api/links", json={"parent_id": parent, "ids": [p2]}).status_code == 200
    assert c.delete(f"/api/projects/{parent}?confirm=Program parent").status_code == 200
    assert db.scalar(con, "SELECT COUNT(*) FROM project WHERE parent_project_id=?", (parent,)) == 0
    assert db.one(con, "SELECT id FROM project WHERE id=?", (p1,))


def test_junior_pm_runs_one_project():
    from app import workload
    proj = [dict(id=i, name=f"P{i}", complexity=2, client=None, project_type=None, voltage=None, start=None, end=None, status_date=None,
                 lat=None, lon=None, contract_value=1e6) for i in range(2)]
    junior = workload.pm_workload(dict(name="J", pm_level=1), proj, {})
    assert junior["span"] == "project" and "one project" in junior["too_many"]
    assert workload.pm_workload(dict(name="J", pm_level=1), proj[:1], {})["too_many"] is None
    assert workload.pm_workload(dict(name="S", pm_level=3), proj, {})["span"] == "portfolio"
    assert workload.pm_workload(dict(name="D", pm_level=4), proj, {})["span"] == "program"


def test_demo_team(blank):
    """The demo team: a director over a junior PM (1 project), two PMs (2 each) and a senior PM (3), one parent shared."""
    from demo import build_demo
    from app import crm, portfolio
    con = blank
    build_demo.write_template_file(build_demo.DEMO / "demo_project_template.xlsx")
    build_demo.build_pronto_file(build_demo.DEMO / "demo_pronto_export.xlsx")
    r = build_demo.seed_team(con)
    con.commit()
    pf = portfolio.run(con)
    by_pm = {}
    for p in pf["projects"]:
        by_pm[p["pm"]] = by_pm.get(p["pm"], 0) + 1
        assert p["director"] == "Taylor Brooks" and p["name"].startswith("Demo team: ")
    assert by_pm == {"Riley Chen": 1, "Jordan Reyes": 2, "Priya Nair": 2, "Sam Whitlock": 3}
    kids = {p["pm"] for p in pf["projects"] if p["parent_id"] == r["parent"]}
    assert kids == {"Priya Nair", "Sam Whitlock"}
    team = {t["name"]: t for t in crm.team(con, "Taylor Brooks")["team"]}
    assert set(team) == {"Riley Chen", "Jordan Reyes", "Priya Nair", "Sam Whitlock"}
    assert team["Riley Chen"]["span"] == "project" and team["Riley Chen"]["too_many"] is None
    assert team["Sam Whitlock"]["span"] == "portfolio"
    assert len({round(p["contingency"]) for p in pf["projects"]}) == 8      # each project has its own figures
    with pytest.raises(ValueError):
        build_demo.seed_team(con)
