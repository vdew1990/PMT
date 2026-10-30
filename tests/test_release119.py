"""Release .119: baseline visibility (Project Director and above), the PM level kept apart from the ECF level, leavers across projects."""
from fastapi.testclient import TestClient

from app import complexity, db, team


def _client():
    return TestClient(__import__("app.main", fromlist=["app"]).app)


def _role(con, role):
    from app import identity
    upn = identity.current()["upn"]
    con.execute("INSERT INTO sync_state(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("role:" + upn, role))
    con.commit()


def test_project_director_and_above_see_the_baseline_others_do_not():
    yes = ["Project Director", "Head of Delivery", "Head of Project Management", "Head of Project Engineering", "General Manager Projects", "Operations Manager - Projects", "Chief Operating Officer", "Executive Director", "Technical Director"]
    no = ["Project Manager", "Senior Project Manager", "Project Coordinator", "Project Engineer", "Construction Manager", "Cost Controller", "PMO", "Other", "", None]
    assert all(complexity.DIRECTOR.search(r) for r in yes)
    assert not any(complexity.DIRECTOR.search(r or "") for r in no)


def test_a_head_of_delivery_can_set_the_baseline(demo):
    con, pid = demo
    c = _client(); _role(con, "Head of Delivery")
    assert c.put(f"/api/p/{pid}/complexity/baseline", json=dict(scores={k: dict(score=2) for k in complexity.KEYS})).status_code == 200
    _role(con, "Senior Project Manager")
    v = c.get(f"/api/p/{pid}/complexity").json()
    assert v["director"] is False and "baseline" not in v


def _pe_team(c, con, pid):
    _role(con, "Project Director")
    c.put(f"/api/p/{pid}/complexity/baseline", json=dict(scores={k: dict(score=3) for k in complexity.KEYS}))
    con.execute("DELETE FROM team_slot WHERE project_id=?", (pid,)); con.commit()


def test_a_leaving_date_on_the_person_ends_every_role_they_hold(demo):
    con, pid = demo
    c = _client(); _pe_team(c, con, pid)
    sd = db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,))["status_date"]
    c.post("/api/people", json=dict(name="Lee Leaver", ecf_role="sr_eng"))
    c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="pe", person_name="Lee Leaver"))
    t = c.get(f"/api/p/{pid}/project-team").json()
    assert next(r for r in t["rows"] if r["role_key"] == "pe")["fit"] == "meets"
    lid = db.one(con, "SELECT id FROM person WHERE name='Lee Leaver'")["id"]
    leave = team._add_months(sd[:7], 2) + "-10"
    assert c.put(f"/api/people/{lid}", json=dict(name="Lee Leaver", leaving_date=leave, employment_status="serving notice")).status_code == 200
    t = c.get(f"/api/p/{pid}/project-team").json()
    assert next(r for r in t["rows"] if r["role_key"] == "pe")["fit"] == "meets"          # still here today
    gap = t["ahead"]["first_gap"]
    assert gap["month"] == team._add_months(sd[:7], 2) and any("Project Engineer" in x for x in gap["reasons"])
    imp = c.get(f"/api/people/{lid}/impact").json()
    assert imp["leaving_date"] == leave and [p["project_id"] for p in imp["projects"]] == [pid] and imp["projects"][0]["roles"] == ["Project Engineer"]
    assert pid in [p["project_id"] for l in c.get("/api/team/leavers").json()["leavers"] for p in l["projects"]]


def test_serving_notice_without_a_last_day_is_flagged_not_ended(demo):
    con, pid = demo
    c = _client(); _pe_team(c, con, pid)
    c.post("/api/people", json=dict(name="Sam Notice", ecf_role="sr_eng"))
    c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="pe", person_name="Sam Notice"))
    sid = db.one(con, "SELECT id FROM person WHERE name='Sam Notice'")["id"]
    c.put(f"/api/people/{sid}", json=dict(name="Sam Notice", employment_status="serving notice"))
    t = c.get(f"/api/p/{pid}/project-team").json()
    assert next(r for r in t["rows"] if r["role_key"] == "pe")["fit"] == "meets"
    assert any("Sam Notice" in x and "last day is not recorded" in x for x in t["risk"]["reasons"])
    assert c.put(f"/api/people/{sid}", json=dict(name="Sam Notice", employment_status="gone")).status_code == 400
    assert c.put(f"/api/people/{sid}", json=dict(name="Sam Notice", engagement="volunteer")).status_code == 400
    assert c.put(f"/api/people/{sid}", json=dict(name="Sam Notice", engagement="contractor")).status_code == 200


def test_the_pm_leaving_ends_the_pm_role_too(demo):
    con, pid = demo
    c = _client(); _pe_team(c, con, pid)
    sd = db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,))["status_date"]
    pm = c.post("/api/people", json=dict(name="Pat Leaving", pm_level=4)).json()["id"]
    con.execute("UPDATE project SET epec_pm='Pat Leaving' WHERE id=?", (pid,)); con.commit()
    assert next(r for r in c.get(f"/api/p/{pid}/project-team").json()["rows"] if r["role_key"] == "pm")["fit"] == "meets"
    c.put(f"/api/people/{pm}", json=dict(name="Pat Leaving", leaving_date=team._add_months(sd[:7], 1) + "-05"))
    t = c.get(f"/api/p/{pid}/project-team").json()
    assert t["ahead"]["first_gap"]["month"] == team._add_months(sd[:7], 1) and any("Project Manager" in x for x in t["ahead"]["first_gap"]["reasons"])


def test_the_paper_signoff_is_filled_from_titles_and_the_approver_is_the_users_choice(demo):
    import io
    import zipfile
    con, pid = demo
    c = _client(); _pe_team(c, con, pid)
    con.execute("UPDATE project SET project_director='Dana Director' WHERE id=?", (pid,)); con.execute("UPDATE project SET settings_json=json_remove(COALESCE(settings_json,'{}'), '$.paper') WHERE id=?", (pid,)); con.commit()
    c.post("/api/people", json=dict(name="Matt Ops", business_title="Operations Manager \u2013 Projects"))
    c.post("/api/people", json=dict(name="Tim Comm", business_title="Substation Commissioning Manager"))
    so = c.get(f"/api/p/{pid}/project-team/signoff").json()
    names = {a["role"]: a["name"] for a in so["authorisers"]}
    assert names["Project Director"] == "Dana Director" and names["Operations Manager"] == "Matt Ops" and names["Test and Commissioning Manager"] == "Tim Comm"
    assert so["approver"] == dict(role="General Manager Project", name=None) and so["saved"] is False       # not assumed: GM Projects is vacant
    so = c.put(f"/api/p/{pid}/project-team/signoff", json=dict(authorisers=[dict(role="Project Director", name="Dana Director"), dict(role="", name="x")], approver=dict(role="Head of Delivery", name="Jason Maloney"))).json()
    assert [a["role"] for a in so["authorisers"]] == ["Project Director"] and so["approver"] == dict(role="Head of Delivery", name="Jason Maloney") and so["saved"]
    xml = zipfile.ZipFile(io.BytesIO(c.get(f"/api/p/{pid}/project-team/paper.docx").content)).read("word/document.xml").decode()
    assert "Head of Delivery" in xml and "Jason Maloney" in xml and "General Manager Project" not in xml


# ---- the org chart load, duplicates and merging ---------------------------------------------------------------------------------------
def test_the_org_chart_preview_writes_nothing_and_reports_what_needs_review(demo):
    con, pid = demo
    c = _client()
    n = db.scalar(con, "SELECT COUNT(*) FROM person")
    p = c.get("/api/people/org-chart").json()
    assert db.scalar(con, "SELECT COUNT(*) FROM person") == n
    assert p["people"] >= 180 and p["to_create"] + p["already_there"] == p["people"]
    titles = {x["name"]: x["why"] for x in p["titles_to_review"]}
    assert "Praveen Atmuri" in titles and "Pariya Mousavi" in titles                          # "SCADA & Controls Manager", "Scheduler": not on the allowed list
    assert "Peter Little" not in titles and "Vincent Dewulf" not in titles
    assert "Phil Gold" in [x["name"] for x in p["level_to_confirm"]]                           # Design Manager spans levels 6 to 7: the chart does not say which
    assert set(p["serving_notice"]) == {"Phil Gold", "Ian Jordaan"} and {x["name"] for x in p["engagement"]} == {"George Aspros", "Elliott Parker"}
    assert "Keven Tie" in p["no_title"] and "Nick Linwood" in p["from_grade_word"]


def test_the_org_chart_load_classifies_by_title_and_never_overwrites(demo):
    con, pid = demo
    c = _client()
    c.post("/api/people", json=dict(name="Peter Little", role="Project Director", email="keep@example.com", business_title="Chosen Title"))
    r = c.post("/api/people/org-chart").json()
    assert r["created"] > 150
    P = {x["name"]: x for x in c.get("/api/people").json()}
    pl, bf, sk = P["Peter Little"], P["Brad Fallis"], P["Sertac Kamil"]
    assert pl["business_title"] == "Chosen Title" and pl["email"] == "keep@example.com"       # an existing person keeps what is there
    assert pl["ecf_role"] == "pd" and pl["reports_to"] == "Jason Maloney"                      # and only blanks are filled
    assert bf["ecf_role"] == "spm" and bf["role"] == "Project Manager" and bf["reports_to"] == "Ben Thomson" and bf["pm_level"] is None      # no PM level from the chart
    assert sk["ecf_role"] == "spm" and sk["ecf_level"] is None
    assert P["Nick Linwood"]["ecf_role"] == "principal" and P["Nick Linwood"]["business_title"] is None
    assert P["Phil Gold"]["employment_status"] == "serving notice" and P["George Aspros"]["engagement"] == "contractor"
    assert P["Matt O'Connor"]["ecf_role"] == "bum" and P["Jamie Alonso"]["ecf_role"] == "coo"
    assert "Dirk van Rensburg" not in P and "David Diaz" not in P                               # people who have left are not loaded
    again = c.post("/api/people/org-chart").json()
    assert again["created"] == 0


def test_similar_names_are_found_and_merging_moves_everything(demo):
    from app import org_load
    con, pid = demo
    c = _client()
    assert org_load.similar("Brad Fallis", "Bradley Fallis") and org_load.similar("Ben Thomson", "Ben Thompson") and org_load.similar("Larissa Oliveira", "Larrissa Cordeiro de Oliveira")
    assert not org_load.similar("Pat Smith", "Paul Smith") and not org_load.similar("Ian Jordaan", "Ian Grayson") and not org_load.similar("Ann Lee", "Ann Lee")
    a = c.post("/api/people", json=dict(name="Bradley Fallis", pm_level=4, email="b@example.com")).json()["id"]
    b = c.post("/api/people", json=dict(name="Brad Fallis", ecf_role="spm", business_title="Senior Project Manager")).json()["id"]
    assert any({x["a"]["id"], x["b"]["id"]} == {a, b} for x in c.get("/api/people/duplicates").json()["pairs"])
    con.execute("UPDATE project SET epec_pm='Brad Fallis' WHERE id=?", (pid,)); con.commit()
    c.put(f"/api/p/{pid}/project-team/slots", json=dict(role_key="co", person_name="Brad Fallis", status="selected"))
    r = c.post("/api/people/merge", json=dict(keep=a, drop=b)).json()
    assert r["kept"] == "Bradley Fallis" and r["projects_updated"] == 1
    P = {x["name"]: x for x in c.get("/api/people").json()}
    assert "Brad Fallis" not in P and P["Bradley Fallis"]["ecf_role"] == "spm" and P["Bradley Fallis"]["pm_level"] == 4 and P["Bradley Fallis"]["email"] == "b@example.com"
    assert db.one(con, "SELECT epec_pm FROM project WHERE id=?", (pid,))["epec_pm"] == "Bradley Fallis"
    assert db.scalar(con, "SELECT COUNT(*) FROM team_slot WHERE person_id=?", (a,)) >= 1
    assert not any({x["a"]["id"], x["b"]["id"]} == {a, b} for x in c.get("/api/people/duplicates").json()["pairs"])
    again = c.post("/api/directory/add", json=dict(kind="employee", name="Brad Fallis")).json()          # the old spelling finds the same person
    assert again["id"] == a
    assert c.post("/api/people/merge", json=dict(keep=a, drop=a)).status_code == 400


def test_the_object_catalogue_lists_what_is_held_and_what_is_not(demo):
    c = _client()
    d = c.get("/api/objects").json()
    types = {t["key"]: {p["key"]: p for p in t["properties"]} for t in d["types"]}
    assert set(types) == {"employee", "external_person", "client", "company", "project"}
    emp = types["employee"]
    assert "age" not in emp and all(p["status"] != "missing" for t in d["types"] for p in t["properties"])        # age removed; every live property has its column
    assert emp["pay_band"]["status"] == "deferred" and emp["pay_band"]["sensitivity"] == "restricted" and emp["home_address"]["status"] == "deferred"
    assert emp["ecf_level"]["status"] == "live" and emp["job_family"]["status"] == "derived" and emp["pronto_code"]["where"] == "person.employee_code"
    assert emp["pm_level"]["note"].startswith("EPEC-PM-FW-0002") and "different level" in emp["pm_level"]["note"]


def test_my_profile_shows_my_own_record_without_hr_only_fields_and_lets_me_change_only_what_i_may(demo):
    con, pid = demo
    c = _client()
    me = c.get("/api/me").json()["name"]
    c.post("/api/people", json=dict(name=me, email="me@epecgroup.com.au", phone="0400 000 000", base="Brisbane QLD", ecf_role="engineer", pm_level=2, employee_code="E123"))
    r = c.get("/api/me/record").json()
    f = {x["key"]: x for x in r["fields"]}
    assert r["found"] and r["hidden"] >= 3 and "pay_band" not in f and "work_rate" not in f and "dimension_levels" not in f and "aliases" not in f
    assert f["email"]["value"] == "me@epecgroup.com.au" and f["email"]["access"] == "view" and f["ecf_role"]["value"] == "Engineer" and f["job_family"]["value"] == "Engineering"
    assert f["phone"]["access"] == "edit" and f["home_base"]["access"] == "edit" and f["pronto_code"]["value"] == "E123"
    assert f["home_address"]["access"] == "unavailable"                                    # editable by the person, but not held until the access design exists
    r = c.put("/api/me/record", json=dict(phone="0411 111 111", home_base="Gold Coast QLD")).json()
    assert {x["key"]: x["value"] for x in r["fields"]}["phone"] == "0411 111 111"
    assert db.one(con, "SELECT base FROM person WHERE name=?", (me,))["base"] == "Gold Coast QLD"
    assert c.put("/api/me/record", json=dict(email="x@example.com")).status_code == 400          # visible, not editable
    assert c.put("/api/me/record", json=dict(pay_band="L5")).status_code == 400                  # not theirs to see or change
    assert c.put("/api/me/record", json=dict(home_address="1 Street")).status_code == 400        # the field is not held yet
    emp = {p["key"]: p for t in c.get("/api/objects").json()["types"] if t["key"] == "employee" for p in t["properties"]}
    assert emp["pay_band"]["self"] == "hidden" and emp["phone"]["self"] == "edit" and emp["email"]["self"] == "view"


def test_my_profile_when_there_is_no_matching_record(demo):
    con, pid = demo
    c = _client()
    con.execute("DELETE FROM person WHERE name=?", (c.get("/api/me").json()["name"],)); con.commit()
    r = c.get("/api/me/record").json()
    assert r["found"] is False and "No employee record" in r["message"]
