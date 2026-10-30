"""Release .118: the PM's competency by dimension against what the project's dimension scores ask (Complexity Matrix levels)."""
from fastapi.testclient import TestClient

from app import complexity, db, team


def _client():
    return TestClient(__import__("app.main", fromlist=["app"]).app)


def _role(con, role):
    from app import identity
    upn = identity.current()["upn"]
    con.execute("INSERT INTO sync_state(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("role:" + upn, role))
    con.commit()


def test_matrix_levels_follow_the_workbook_and_dimension_bands_follow_the_total_limits():
    m = complexity.MATRIX_LEVELS
    assert set(m) == set(complexity.KEYS) and all(set(v) == {"C1", "C2", "C3", "C4"} for v in m.values())
    assert m["cost"]["C3"] == (4, 4) and m["contracting"]["C3"] == (3, 4) and m["stakeholders"]["C2"] == (2, 3) and m["scope"]["C1"] is None
    assert [complexity.dimension_band(s) for s in range(6)] == ["C1", "C1", "C2", "C3", "C4", "C4"]
    for s, code in ((1.5, "C1"), (2.5, "C2"), (3.5, "C3")):                       # the average a dimension needs for the total to reach each band limit
        assert complexity.band_of(round(s * 10))["code"] == code


def _setup(c, con, pid, scores):
    _role(con, "Project Director")
    c.put(f"/api/p/{pid}/complexity/baseline", json=dict(scores={k: dict(score=scores.get(k, 2)) for k in complexity.KEYS}))
    con.execute("UPDATE project SET epec_pm='Cam Contracts' WHERE id=?", (pid,)); con.commit()


def test_pm_level_in_a_dimension_is_set_or_falls_back_to_the_overall_level(demo):
    con, pid = demo
    c = _client(); _setup(c, con, pid, dict(cost=4, contracting=3, scope=1))
    p = c.post("/api/people", json=dict(name="Cam Contracts", pm_level=3)).json()["id"]
    r = c.get(f"/api/p/{pid}/pm-competency").json()
    rows = {x["key"]: x for x in r["rows"]}
    assert r["ready"] and r["overall"] == 3
    assert rows["cost"]["band"] == "C4" and rows["cost"]["asked"] == [4, 5] and rows["cost"]["fit"] == "below" and rows["cost"]["source"] == "overall PM level"
    assert rows["contracting"]["band"] == "C3" and rows["contracting"]["asked"] == [3, 4] and rows["contracting"]["fit"] == "meets"
    assert rows["scope"]["fit"] == "no_level"                                      # the matrix names no level for scope at C1
    c.put(f"/api/people/{p}", json=dict(name="Cam Contracts", pm_level=3, dimension_levels=dict(cost=5, contracting=2)))
    rows = {x["key"]: x for x in c.get(f"/api/p/{pid}/pm-competency").json()["rows"]}
    assert rows["cost"]["fit"] == "meets" and rows["cost"]["source"] == "set" and rows["contracting"]["fit"] == "below"
    assert c.get(f"/api/p/{pid}/pm-competency").json()["gaps"] == 1
    c.put(f"/api/people/{p}", json=dict(name="Cam Contracts", dimension_levels=dict(contracting="")))                  # cleared: back to the overall level
    assert {x["key"]: x for x in c.get(f"/api/p/{pid}/pm-competency").json()["rows"]}["contracting"]["source"] == "overall PM level"
    assert c.put(f"/api/people/{p}", json=dict(name="Cam Contracts", dimension_levels=dict(cost=6))).status_code == 400
    assert c.put(f"/api/people/{p}", json=dict(name="Cam Contracts", dimension_levels=dict(nope=2))).status_code == 400


def test_only_a_director_role_gets_the_competency_view(demo):
    con, pid = demo
    c = _client(); _setup(c, con, pid, dict(cost=4))
    _role(con, "Project Manager")
    assert c.get(f"/api/p/{pid}/pm-competency").json() == {"director": False}


def test_nothing_to_compare_without_a_baseline_or_a_pm(demo):
    con, pid = demo
    c = _client(); _role(con, "Project Director")
    con.execute("DELETE FROM cx_baseline WHERE project_id=?", (pid,)); con.commit()
    assert c.get(f"/api/p/{pid}/pm-competency").json()["ready"] is False


def test_team_fit_counts_the_dimensions_where_the_pm_is_below(demo):
    con, pid = demo
    c = _client(); _setup(c, con, pid, dict(cost=4, risk=4))
    con.execute("DELETE FROM person_dimension"); con.commit()                       # the earlier tests set levels on the same person
    c.post("/api/people", json=dict(name="Cam Contracts", pm_level=3))
    mine = next(p for p in c.get("/api/team/fit").json()["projects"] if p["id"] == pid)
    assert mine["pm_dimension_gaps"] == 2
