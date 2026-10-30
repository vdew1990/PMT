"""Release .116: the team looking ahead, the monthly team confirmation, the director's team fit view and the Word resourcing paper."""
import io
import zipfile

from fastapi.testclient import TestClient

from app import complexity, db, team


def _client():
    return TestClient(__import__("app.main", fromlist=["app"]).app)


def _role(con, role):
    from app import identity
    upn = identity.current()["upn"]
    con.execute("INSERT INTO sync_state(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("role:" + upn, role))
    con.commit()


def _setup(c, con, pid, each=3):
    _role(con, "Project Director")
    c.put(f"/api/p/{pid}/complexity/baseline", json=dict(scores={k: dict(score=each, note="note " + k) for k in complexity.KEYS}, summary="Summary text"))
    con.execute("DELETE FROM team_slot WHERE project_id=?", (pid,)); con.execute("DELETE FROM team_review WHERE project_id=?", (pid,)); con.commit()
    con.execute("UPDATE project SET epec_pm='Pat Senior', project_director='Dana Director' WHERE id=?", (pid,)); con.commit()
    pat = c.post("/api/directory/add", json=dict(kind="pm", name="Pat Senior")).json()
    db.update(con, "person", pat["id"], {"pm_level": 4}); con.commit()


def test_a_leaver_turns_a_future_month_amber_and_is_reported_as_the_first_gap(demo):
    con, pid = demo
    c = _client(); _setup(c, con, pid)
    sd = db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,))["status_date"]       # 2026-09-30 in the demo
    end = team._add_months(sd[:7], 2) + "-10"
    for role, lv in (("pe", 3), ("dm", 3), ("cm", 3), ("tc", 3), ("ct", 3), ("co", 3)):
        c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key=role, person_name="Person " + role, level=lv, **(dict(end_date=end) if role == "dm" else {})))
    t = c.get(f"/api/p/{pid}/project-team").json()
    assert t["risk"]["rating"] == "green"
    months = {m["month"]: m for m in t["ahead"]["months"]}
    assert months[sd[:7]]["rating"] == "green" and months[team._add_months(sd[:7], 1)]["rating"] == "green"
    assert months[team._add_months(sd[:7], 2)]["rating"] == "amber"                    # he leaves on the 10th: gone by the 15th of that month
    gap = t["ahead"]["first_gap"]
    assert gap["month"] == team._add_months(sd[:7], 2) and "Design Manager" in gap["reasons"][0]


def test_a_joiner_with_a_start_date_fills_the_role_only_from_then(demo):
    con, pid = demo
    c = _client(); _setup(c, con, pid, each=2)                                           # 20 points: C2
    sd = db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,))["status_date"]
    start = team._add_months(sd[:7], 2) + "-01"
    c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="dm", person_name="New Dm", level=2, start_date=start))
    t = c.get(f"/api/p/{pid}/project-team").json()
    assert {r["role_key"]: r["fit"] for r in t["rows"]}["dm"] == "vacant"
    months = {m["month"]: m for m in t["ahead"]["months"]}
    assert not any("Design Manager" in x for x in months[team._add_months(sd[:7], 2)]["reasons"])


def test_the_pm_confirms_the_team_for_a_month_and_the_checklist_notices(demo):
    con, pid = demo
    c = _client(); _setup(c, con, pid)
    m = c.get(f"/api/p/{pid}/month-end").json()["month"]
    item = lambda: next(i for i in c.get(f"/api/p/{pid}/month-end").json()["items"] if i["key"] == "team")
    assert item()["state"] in ("todo", "warn")
    t = c.put(f"/api/p/{pid}/project-team/review", json=dict(month=m, note="No movements")).json()
    assert t["reviews"][0]["month"] == m and t["reviews"][0]["rating"] == t["risk"]["rating"] and t["reviews"][0]["note"] == "No movements"
    assert item()["state"] == "done"
    c.put(f"/api/p/{pid}/project-team/review", json=dict(month=m, note="Changed"))
    assert db.scalar(con, "SELECT COUNT(*) FROM team_review WHERE project_id=? AND month=?", (pid, m)) == 1
    assert c.put(f"/api/p/{pid}/project-team/review", json=dict(month="x")).status_code == 400


def test_the_director_sees_every_project_team_against_its_band(demo):
    con, pid = demo
    c = _client(); _setup(c, con, pid)
    o = c.get("/api/team/fit").json()
    mine = next(p for p in o["projects"] if p["id"] == pid)
    assert mine["band_code"] == "C2" or mine["band_code"] == "C3"
    assert set(mine["roles"]) == set(team.ROLE_KEYS) and mine["roles"]["pm"]["who"] == "Pat Senior"
    assert [r["key"] for r in o["roles"]] == team.ROLE_KEYS
    assert c.get("/api/team/fit?director=Nobody%20Here").json()["projects"] == []
    assert any(p["id"] == pid for p in c.get("/api/team/fit?director=Dana%20Director").json()["projects"])


def test_the_word_paper_has_the_framework_sections_and_only_the_director_gets_it(demo):
    con, pid = demo
    c = _client(); _setup(c, con, pid)
    r = c.get(f"/api/p/{pid}/project-team/paper.docx")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    z = zipfile.ZipFile(io.BytesIO(r.content)); xml = z.read("word/document.xml").decode()
    for text in ("Project Complexity Score", "Complexity Profile", "Project Resourcing Basis", "Project Resourcing Requirements", "Summary", "Authorisation", "Approval", "Dana Director", "General Manager Project"):
        assert text in xml, text
    assert any(n.startswith("word/media/") for n in z.namelist())                         # the radar picture
    _role(con, "Project Manager")
    assert c.get(f"/api/p/{pid}/project-team/paper.docx").status_code == 400
