"""The chat panel's built-in guide, and each person's view defaults (Settings > Your defaults)."""
from app import help as hm, sync


def test_guide_answers_the_common_questions():
    cases = {
        "what does 11 P 11 mean on the labour calendar": "What do the numbers in a labour calendar cell mean?",
        "how is EAC calculated": "What is EAC and how is it calculated?",
        "revise my accrual NT OT": "How do I change an accrual on the labour calendar?",
        "how do I update PMT without losing data": "How do I update PMT without losing my data?",
        "open a table on my second screen": "How do I open a page or table in another window?",
    }
    for q, title in cases.items():
        r = hm.answer(q, "calendar")
        assert r["answer"] and r["answer"]["title"] == title, (q, r["answer"] and r["answer"]["title"])
    assert hm.answer("qwerty zzz")["answer"] is None


def test_every_page_has_a_topic_and_the_guide_downloads():
    assert hm.page_topic("calendar")["title"] == "Labour calendar"
    assert hm.suggestions("calendar")[0].startswith("What do the numbers")
    md = hm.guide_md()
    assert md.startswith("# PMT") and "## Questions and answers" in md and "Labour calendar" in md and "EAC: estimate at completion" in md


def test_prefs_are_kept_per_person(blank):
    con = blank
    assert sync.get_prefs(con) == {}
    saved = sync.set_prefs(con, {"cc_months": True, "cal_weeks": 9, "copilot_embed": "https://x", "bad": {"nested": 1}})
    assert saved == {"cc_months": True, "cal_weeks": 9, "copilot_embed": "https://x"}
    assert sync.me(con)["prefs"]["cc_months"] is True
    sync.set_prefs(con, {})
    assert sync.get_prefs(con) == {}


def test_help_and_prefs_endpoints(demo):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/api/help/ask", params={"q": "what is contingency", "page": "costcontrol"}).json()
    assert r["answer"]["title"] == "What is contingency?" and r["page_name"] == "Cost control" and r["suggestions"]
    assert c.get("/api/help/guide.md").headers["content-disposition"].endswith('PMT_user_guide.md"')
    assert c.get("/api/help/topic/faq0").json()["page"] == "calendar"
    assert c.put("/api/me/prefs", json={"prefs": {"cc_level": 3}}).json() == {"cc_level": 3}
    assert c.get("/api/me").json()["prefs"] == {"cc_level": 3}
    c.put("/api/me/prefs", json={"prefs": {}})


def test_archive_takes_a_project_off_the_list_and_restores_it(demo):
    from fastapi.testclient import TestClient
    from app.main import app
    from app import help as hm
    con, pid = demo
    c = TestClient(app)
    r = c.post(f"/api/projects/{pid}/archive", json={"value": True}).json()
    assert r["archived_at"]
    p = next(x for x in c.get("/api/projects").json() if x["id"] == pid)
    assert p["archived_at"] and c.get(f"/api/projects/{pid}").status_code == 200   # still there, data kept
    assert c.post(f"/api/projects/{pid}/archive", json={"value": False}).json()["archived_at"] is None
    assert hm.answer("how do I archive an old project")["answer"]["title"] == "How do I archive or delete a project?"


def test_library_keeps_figures_and_portfolio_lists_running_projects(demo):
    from fastapi.testclient import TestClient
    from app.main import app
    con, pid = demo
    c = TestClient(app)
    c.put(f"/api/projects/{pid}", json={"epec_pm": "Alex Marsden", "project_director": "Jordan Pike", "location": "Wandoan QLD"})
    pf = c.get("/api/portfolio").json()
    p = next(x for x in pf["projects"] if x["id"] == pid)
    assert p["pm"] == "Alex Marsden" and p["director"] == "Jordan Pike" and "Jordan Pike" in pf["directors"]
    assert p["contract_value"] > 0 and abs(p["contract_value"] - p["eac"] - p["risk_provision"] - p["margin"]) < 1 and p["months"]
    c.post(f"/api/projects/{pid}/archive", json={"value": True})
    assert pid not in [x["id"] for x in c.get("/api/portfolio").json()["projects"]]
    lib = c.get("/api/library").json()
    row = next(x for x in lib if x["id"] == pid)
    assert row["location"] == "Wandoan QLD" and row["contract_value"] == round(p["contract_value"], 2) and row["final_cost"] == round(p["eac"], 2)
    c.post(f"/api/projects/{pid}/archive", json={"value": False})
    assert pid in [x["id"] for x in c.get("/api/portfolio").json()["projects"]]
