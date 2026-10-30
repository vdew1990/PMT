"""Release .115: role levels for people, the project team against the complexity band, fit and the first risk rule."""
from fastapi.testclient import TestClient

from app import complexity, db, team


def _client():
    return TestClient(__import__("app.main", fromlist=["app"]).app)


def _role(con, role):
    from app import identity
    upn = identity.current()["upn"]
    con.execute("INSERT INTO sync_state(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("role:" + upn, role))
    con.commit()


def _baseline(c, con, pid, total_each):
    _role(con, "Project Director")
    c.put(f"/api/p/{pid}/complexity/baseline", json=dict(scores={k: dict(score=total_each) for k in complexity.KEYS}))


def _clear(con, pid):
    con.execute("DELETE FROM team_slot WHERE project_id=?", (pid,)); con.commit()


def test_requirement_table_matches_the_workbook():
    assert team.REQ["pm"]["C3"]["level"] == 4 and team.REQ["pm"]["C4"]["level"] == 5
    assert team.REQ["pe"]["C3"]["mandatory"] and not team.REQ["pe"]["C2"]["mandatory"]
    assert team.REQ["tc"]["C1"]["mode"] == "none" and team.REQ["tc"]["C2"]["mode"] == "if_applicable"
    assert team.level_labels("pe")[3] == "Senior / Lead PE (Mandatory)" and team.level_labels("pm")[5].startswith("PM Level 5")
    assert len(team.ROLES) == 7


def test_no_baseline_means_no_requirement_and_an_unknown_rating(demo):
    con, pid = demo
    c = _client(); _clear(con, pid)
    con.execute("DELETE FROM cx_baseline WHERE project_id=?", (pid,)); con.commit()
    t = c.get(f"/api/p/{pid}/project-team").json()
    assert t["band"] is None and t["risk"]["rating"] == "unknown" and all(r["fit"] == "no_band" for r in t["rows"])


def test_fit_follows_the_band_and_the_levels(demo):
    con, pid = demo
    c = _client(); _clear(con, pid)
    _baseline(c, con, pid, 3)                                              # 30 points: C3 High
    con.execute("UPDATE project SET epec_pm='Pat Senior' WHERE id=?", (pid,)); con.commit()
    pat = c.post("/api/directory/add", json=dict(kind="pm", name="Pat Senior")).json()
    db.update(con, "person", pat["id"], {"pm_level": 3}); con.commit()
    t = c.get(f"/api/p/{pid}/project-team").json()
    assert t["band"]["code"] == "C3"
    rows = {r["role_key"]: r for r in t["rows"]}
    assert rows["pm"]["fit"] == "below" and rows["pm"]["required"]["level"] == 4          # a Level 3 PM on a C3 project
    assert rows["pe"]["fit"] == "vacant" and rows["pe"]["required"]["mandatory"]
    assert t["risk"]["rating"] == "red"
    db.update(con, "person", pat["id"], {"pm_level": 4}); con.commit()
    c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="pe", person_name="Lee Lead", level=3, status="selected"))
    t = c.get(f"/api/p/{pid}/project-team").json()
    rows = {r["role_key"]: r for r in t["rows"]}
    assert rows["pm"]["fit"] == "meets" and rows["pe"]["fit"] == "meets" and rows["pe"]["best_level"] == 3
    assert rows["dm"]["fit"] == "vacant"
    assert t["risk"]["rating"] == "amber" and any("Design Manager" in x for x in t["risk"]["reasons"])


def test_a_shared_or_conditional_role_is_not_a_gap_and_a_leaver_stops_counting(demo):
    con, pid = demo
    c = _client(); _clear(con, pid)
    _baseline(c, con, pid, 1)                                              # 10 points: C1 Low
    con.execute("UPDATE project SET epec_pm='Jo Junior' WHERE id=?", (pid,)); con.commit()
    jo = c.post("/api/directory/add", json=dict(kind="pm", name="Jo Junior")).json()
    db.update(con, "person", jo["id"], {"pm_level": 1}); con.commit()
    t = c.get(f"/api/p/{pid}/project-team").json()
    assert {r["role_key"]: r["fit"] for r in t["rows"]}["tc"] == "not_required"
    assert t["risk"]["rating"] == "green"                                  # every other role is shared at C1
    _baseline(c, con, pid, 2)                                              # C2
    c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="ct", person_name="Cy Controls", level=2, end_date="2026-01-31"))
    t = c.get(f"/api/p/{pid}/project-team").json()
    assert {r["role_key"]: r["fit"] for r in t["rows"]}["ct"] == "vacant"   # left before the status date


def test_slots_need_a_name_unless_recruiting_and_levels_stay_on_the_person(demo):
    con, pid = demo
    c = _client(); _clear(con, pid)
    assert c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="dm", status="selected")).status_code == 400
    assert c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="dm", status="recruitment")).status_code == 200
    assert c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="pm", person_name="X")).status_code == 400        # the PM is set on Project setup
    assert c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="co", person_name="Casey Coord", level=5)).status_code == 400
    r = c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="co", person_name="Casey Coord", level=2)).json()
    pid_ = next(m["person_id"] for m in r["extra"] if m["person"] == "Casey Coord")
    assert team.levels_of(con, pid_)["co"] == 2
    ppl = {p["name"]: p for p in c.get("/api/people").json()}
    assert ppl["Casey Coord"]["role_levels"]["co"] == 2


def test_the_pms_assessment_above_the_baseline_turns_the_rating_red(demo):
    con, pid = demo
    c = _client(); _clear(con, pid)
    con.execute("DELETE FROM assessment WHERE project_id=?", (pid,)); con.commit()
    _baseline(c, con, pid, 2)
    _role(con, "Project Manager")
    c.put(f"/api/p/{pid}/complexity/assessment", json=dict(month="2026-09", scores={k: dict(score=4) for k in complexity.KEYS}))
    t = c.get(f"/api/p/{pid}/project-team").json()
    assert t["risk"]["rating"] == "red" and any("above the baseline" in x for x in t["risk"]["reasons"])


def test_people_template_downloads():
    r = _client().get("/api/people/template.xlsx")
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_the_same_person_cannot_be_added_twice_in_one_role(demo):
    con, pid = demo
    c = _client(); _clear(con, pid)
    assert c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="dm", person_name="Dee Em", level=2)).status_code == 200
    assert c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="dm", person_name="dee em")).status_code == 400
    assert c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="pe", person_name="Dee Em")).status_code == 200      # a person can hold two roles
