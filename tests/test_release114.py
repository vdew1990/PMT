"""Release .114: the project complexity score (ten dimensions, bands), the director's baseline, the PM's monthly assessment and who sees what."""
import json

from fastapi.testclient import TestClient

from app import complexity, db, sync


def _client():
    return TestClient(__import__("app.main", fromlist=["app"]).app)


def _role(con, role):
    from app import identity
    upn = identity.current()["upn"]
    con.execute("INSERT INTO sync_state(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("role:" + upn, role))
    con.commit()


def _scores(n):
    return {k: dict(score=n, note=None) for k in complexity.KEYS}


def test_band_thresholds_follow_the_workbook():
    assert [complexity.band_of(t)["code"] for t in (0, 15, 16, 25, 26, 35, 36, 50)] == ["C1", "C1", "C2", "C2", "C3", "C3", "C4", "C4"]
    assert [complexity.equivalent(t) for t in (0, 10, 11, 20, 27, 50)] == [1, 1, 2, 2, 3, 5]
    assert complexity.band_of(27)["name"] == "C3 – High"          # Smokey Creek in the example paper: 2+2+3+3+3+3+2+3+3+3 = 27
    smokey = dict(zip(complexity.KEYS, [2, 2, 3, 3, 3, 3, 2, 3, 3, 3]))
    assert complexity.total_of(complexity.clean_scores(smokey)) == 27


def test_every_dimension_must_be_scored_from_0_to_5(demo):
    con, pid = demo
    c = _client(); _role(con, "Project Director")
    part = _scores(2); part.pop("hse")
    assert c.put(f"/api/p/{pid}/complexity/baseline", json=dict(scores=part)).status_code == 400
    bad = _scores(2); bad["risk"] = 6
    assert c.put(f"/api/p/{pid}/complexity/baseline", json=dict(scores=bad)).status_code == 400


def test_director_sets_the_baseline_and_it_sets_the_project_complexity(demo):
    con, pid = demo
    c = _client(); _role(con, "Project Director")
    sc = dict(zip(complexity.KEYS, [2, 2, 3, 3, 3, 3, 2, 3, 3, 3]))
    r = c.put(f"/api/p/{pid}/complexity/baseline", json=dict(scores=sc, summary="First read")).json()
    assert r["baseline"]["total"] == 27 and r["baseline"]["band"].startswith("C3")
    assert db.one(con, "SELECT complexity FROM project WHERE id=?", (pid,))["complexity"] == 3
    c.put(f"/api/p/{pid}/complexity/baseline", json=dict(scores=_scores(4), summary="Harder"))
    v = c.get(f"/api/p/{pid}/complexity").json()
    assert v["baseline"]["total"] == 40 and len(v["revisions"]) >= 2        # a revision, the earlier one kept
    assert db.one(con, "SELECT complexity FROM project WHERE id=?", (pid,))["complexity"] == 4


def test_the_pm_never_sees_the_baseline_and_cannot_set_it(demo):
    con, pid = demo
    c = _client(); _role(con, "Project Director")
    c.put(f"/api/p/{pid}/complexity/baseline", json=dict(scores=_scores(3)))
    _role(con, "Project Manager")
    v = c.get(f"/api/p/{pid}/complexity").json()
    assert v["director"] is False and "baseline" not in v and "revisions" not in v and "compare" not in v
    assert c.put(f"/api/p/{pid}/complexity/baseline", json=dict(scores=_scores(1))).status_code == 400
    assert c.put(f"/api/p/{pid}/complexity/assessment", json=dict(month="2026-09", scores=_scores(2), pm_difficulty=4, note="Client changed PM")).status_code == 200
    v = c.get(f"/api/p/{pid}/complexity").json()
    assert v["assessments"][-1]["total"] == 20 and v["assessments"][-1]["pm_difficulty"] == 4 and "baseline" not in v


def test_director_sees_the_pm_against_the_baseline(demo):
    con, pid = demo
    c = _client(); _role(con, "Project Director")
    c.put(f"/api/p/{pid}/complexity/baseline", json=dict(scores=_scores(2)))             # 20
    sc = _scores(2); sc["risk"] = dict(score=5, note="HV cable option changed")
    _role(con, "Project Manager"); c.put(f"/api/p/{pid}/complexity/assessment", json=dict(month="2026-10", scores=sc))   # 23
    _role(con, "Project Director")
    v = c.get(f"/api/p/{pid}/complexity").json()
    assert v["compare"]["delta"] == 3 and v["compare"]["by_dimension"]["risk"] == 3 and v["compare"]["by_dimension"]["scope"] == 0
    assert c.get(f"/api/p/{pid}/month-end").json()["items"]


def test_saving_a_month_again_replaces_it_and_the_checklist_notices(demo):
    con, pid = demo
    c = _client(); _role(con, "Project Manager")
    m = c.get(f"/api/p/{pid}/month-end").json()["month"]
    item = lambda: next(i for i in c.get(f"/api/p/{pid}/month-end").json()["items"] if i["key"] == "assessment")
    con.execute("DELETE FROM assessment WHERE project_id=? AND month=?", (pid, m)); con.commit()
    assert item()["state"] == "todo"
    c.put(f"/api/p/{pid}/complexity/assessment", json=dict(month=m, scores=_scores(1)))
    c.put(f"/api/p/{pid}/complexity/assessment", json=dict(month=m, scores=_scores(3), pm_difficulty=2))
    assert item()["state"] == "done"
    assert db.scalar(con, "SELECT COUNT(*) FROM assessment WHERE project_id=? AND month=?", (pid, m)) == 1


def test_band_decides_the_pm_level_a_project_needs(demo):
    from app import workload
    assert workload.BAND_LEVEL == {"C1": 1, "C2": 2, "C3": 4, "C4": 5}
    p = dict(id=1, name="X", complexity=2, cx_band="C3")
    assert workload.project_demand(p)["required_level"] == 4
    assert workload.project_demand(dict(p, cx_band=None))["required_level"] == workload.REQUIRED_LEVEL[2]
    assert workload.LEVEL_CAPACITY[5] and "director" in workload.LEVEL_NAME[5]


def test_the_activity_list_hides_baseline_changes_from_a_pm(demo):
    con, pid = demo
    c = _client(); _role(con, "Project Director")
    c.put(f"/api/p/{pid}/complexity/baseline", json=dict(scores=_scores(3)))
    seen = lambda: [r for r in c.get(f"/api/p/{pid}/activity?limit=300").json()["rows"] if r.get("tbl") == "cx_baseline"]
    assert seen()
    _role(con, "Project Manager")
    assert not seen()
