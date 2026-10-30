import pytest

from app import challenge, crm, db, portfolio
from tests.conftest import *  # noqa: F401,F403


def test_position_orders_the_corners_as_described():
    best = challenge.position_score(5, 1)        # expert and easy
    clue_hard = challenge.position_score(1, 5)
    exp_hard = challenge.position_score(5, 5)
    clue_easy = challenge.position_score(1, 1)
    assert best == 0 and clue_hard == 100
    assert best < clue_easy < exp_hard < clue_hard   # both difficult corners are challenging, in different ways
    assert challenge.quadrant(5, 1)[0] == "Ideal client"
    assert challenge.quadrant(5, 5)[0] == "Demanding expert" and challenge.quadrant(1, 5)[0] == "Hands-on and hard"
    assert challenge.band(24) == "Easy" and challenge.band(44) == "Manageable" and challenge.band(64) == "Challenging" and challenge.band(65) == "Very challenging"


def test_difficult_pm_on_a_simple_project_and_the_reverse_both_count():
    a = challenge.project_summary([dict(month="2026-01", pm_difficulty=5, complexity=1)])
    b = challenge.project_summary([dict(month="2026-01", pm_difficulty=1, complexity=5)])
    assert a["score"] == b["score"] == 50
    rising = challenge.project_summary([dict(month="2026-01", pm_difficulty=2, complexity=2), dict(month="2026-03", pm_difficulty=4, complexity=4)])
    assert rising["trend"] > 0 and rising["latest_month"] == "2026-03"


def test_client_card_position_and_assessments_set_the_challenge(demo):
    con, pid = demo
    name = db.one(con, "SELECT client_name FROM project WHERE id=?", (pid,))["client_name"]
    crm.save_client(con, dict(name=name, knowledge=1, complexity=5))          # clueless and difficult
    con.commit()
    c = next(x for x in crm.clients(con) if x["name"] == name)
    assert c["knowledge"] == 1 and c["challenge"]["position"] == 100 and c["challenge"]["evidence"] is None and c["challenge"]["score"] == 100
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as t:
        r = t.put(f"/api/p/{pid}/assessments", json=dict(month="2026-08", client_pm="Sam Client", pm_difficulty=1, complexity=1))
        assert r.status_code == 200
        assert t.put(f"/api/p/{pid}/assessments", json=dict(month="2026-09", client_pm="Sam Client", pm_difficulty=3)).status_code == 200
        assert t.put(f"/api/p/{pid}/assessments", json=dict(month="2026-09")).status_code >= 400          # needs a rating
        got = t.get(f"/api/p/{pid}/assessments").json()
        assert len(got["rows"]) == 2 and got["summary"]["client_pm"] == "Sam Client"
        row = next(x for x in t.get("/api/portfolio").json()["projects"] if x["id"] == pid)
        assert row["client_challenge"] is not None and row["client_pm_name"] == "Sam Client" and row["assessed_complexity"] == 1
    c = next(x for x in crm.clients(con) if x["name"] == name)
    assert c["challenge"]["evidence"] is not None and c["challenge"]["score"] < 100          # easy PM, simple project pulls it down
    assert c["challenge"]["client_pms"][0]["name"] == "Sam Client"
    assert db.one(con, "SELECT complexity FROM project WHERE id=?", (pid,))["complexity"] == 1   # the project follows its latest assessment


def test_gates_log_moves_back_and_forth_and_feeds_the_portfolio(demo):
    from fastapi.testclient import TestClient
    from app import gates
    from app.main import app
    con, pid = demo
    con.commit()
    assert gates.GATES[5]["name"] == "Handover to Delivery" and gates.GATES[3]["name"] == "Approval to submit proposal" and gates.GATES[4]["form"] == "EPEC-OP-FR-0004"     # Gates 3 and 4 forms not supplied
    with TestClient(app) as t:
        assert t.post(f"/api/p/{pid}/gates", json=dict(gate=8, date="2026-01-05")).status_code >= 400
        assert t.post(f"/api/p/{pid}/gates", json=dict(gate=3, date="2026-01-05", stage="Early Works")).status_code == 200
        assert t.post(f"/api/p/{pid}/gates", json=dict(gate=5, date="2026-03-01", stage="Early Works")).status_code == 200
        assert t.post(f"/api/p/{pid}/gates", json=dict(gate=3, date="2026-06-01", stage="EPC", note="EPC proposal")).status_code == 200   # back to Gate 3 for the EPC award
        got = t.get(f"/api/p/{pid}/gates").json()
        assert [r["gate"] for r in got["rows"]] == [3, 5, 3] and got["current"]["gate"] == 3 and got["current"]["stage"] == "EPC"
        assert t.post(f"/api/p/{pid}/gates", json=dict(gate=5, date="2026-09-01", stage="EPC")).status_code == 200
        row = next(x for x in t.get("/api/portfolio").json()["projects"] if x["id"] == pid)
        assert row["gate"] == 5 and row["gate_phase"] == "Setup" and row["gate_stage"] == "EPC"


def test_gate_papers_download_where_a_form_exists(demo):
    from fastapi.testclient import TestClient
    from app.main import app
    con, pid = demo
    with TestClient(app) as t:
        for g in (1, 2, 3, 4, 5, 6, 7):
            r = t.get(f"/api/gates/{g}/form")
            assert r.status_code == 200 and r.content[:2] == b"PK" and "wordprocessingml" in r.headers["content-type"]
        assert t.get("/api/gates/8/form").status_code == 404
        cat = t.get("/api/gates").json()["gates"]
        assert [g["has_form"] for g in cat] == [True] * 7


def test_phase_moves_are_logged_and_checklists_come_from_the_forms(demo):
    from fastapi.testclient import TestClient
    from app import gates
    from app.main import app
    con, pid = demo
    con.commit()
    cat = {p["phase"]: p for p in gates.phase_catalogue()}
    assert list(cat) == ["Design", "Procure", "Construct", "Commission", "Close Out"]
    construct = {r["code"]: r for r in cat["Construct"]["reviews"]}
    assert construct["EPEC-PD-FR-0009"]["has_form"] and sum(len(s["items"]) for s in construct["EPEC-PD-FR-0009"]["sections"]) > 60
    assert any(s["title"] == "Approvals" for s in cat["Commission"]["reviews"][0]["sections"])
    assert not cat["Close Out"]["reviews"][0]["has_form"] and cat["Close Out"]["reviews"][0]["status"] == "Mandatory"
    with TestClient(app) as t:
        assert t.post(f"/api/p/{pid}/phases", json=dict(phase="Nonsense", date="2026-10-01")).status_code >= 400
        assert t.post(f"/api/p/{pid}/phases", json=dict(phase="Construct", date="2026-08-01")).status_code == 200
        assert t.post(f"/api/p/{pid}/phases", json=dict(phase="Commission", date="2026-10-01")).status_code == 200
        got = t.get(f"/api/p/{pid}/phases").json()
        assert got["current"]["phase"] == "Commission" and len(got["rows"]) == 2
        assert t.get("/api/forms/EPEC-PD-FR-0012").content[:2] == b"PK" and t.get("/api/forms/EPEC-PD-FR-0014").status_code == 404
        row = next(x for x in t.get("/api/portfolio").json()["projects"] if x["id"] == pid)
        assert row["delivery_phase"] == "Commission"


def test_org_chart_keeps_one_epec_and_only_valid_links(demo):
    from fastapi.testclient import TestClient
    from app.main import app
    con, pid = demo
    with TestClient(app) as t:
        got = t.get(f"/api/p/{pid}/orgchart").json()
        assert got["saved"] is False and got["parties"][0]["epec"] and got["epec_role"] == "Principal Contractor" and "Transgrid" in got["nsps"]
        body = dict(epec_role="Contractor", parties=[
            dict(id="epec", role="Owner", name="x", epec=True, x=400, y=250), dict(id="o", role="Owner", name="GridCo", x=10, y=10), dict(id="n", role="NSP", name="Powerlink", x=300, y=10),
            dict(id="z", role="Spaceship", name="Odd", x=1, y=1), dict(id="e2", role="Developer", name="Second EPEC", epec=True, x=5, y=5)],
            links=[dict(id="l1", **{"from": "o"}, to="epec", kind="contract", label="EPC"), dict(id="l2", **{"from": "n"}, to="n", kind="contract"),
                   dict(id="l3", **{"from": "n"}, to="ghost", kind="reporting"), dict(id="l4", **{"from": "n"}, to="epec", kind="telepathy")])
        r = t.put(f"/api/p/{pid}/orgchart", json=body).json()
        by = {x["id"]: x for x in r["parties"]}
        assert by["epec"]["role"] == "Contractor" and sum(1 for x in r["parties"] if x["epec"]) == 1       # EPEC takes the chosen role, only one EPEC
        assert by["z"]["role"] == "Other" and by["e2"]["epec"] is False
        assert [(l["from"], l["to"], l["kind"]) for l in r["links"]] == [("o", "epec", "contract"), ("n", "epec", "communication")]   # self and dangling links dropped, bad kind becomes communication
        assert t.get(f"/api/p/{pid}/orgchart").json()["saved"] is True
