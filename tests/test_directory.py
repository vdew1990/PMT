"""Company database: clients, employees and companies kept apart; lookups filter and add; backfill from the projects."""
from fastapi.testclient import TestClient

from app import db, directory


def test_backfill_and_lookups(demo):
    con, pid = demo
    directory.backfill(con)
    con.commit()
    comp = directory.companies(con)
    assert comp and all(c["kind"] in directory.ORG_KINDS for c in comp)
    sup = {c["name"] for c in directory.companies(con, "supplier")}
    assert sup and not any(":" in n for n in sup)          # names, never a subcontract's title
    assert directory.names(con, "employee")
    client = db.scalar(con, "SELECT client_name FROM project WHERE id=?", (pid,), None)
    if client:
        assert client in [x["name"] for x in directory.names(con, "client")]
        assert directory.names(con, "client", client[:3].lower())
    # clients, people and companies stay in their own tables
    a = directory.add(con, "client", "Separate Test Client")
    b = directory.add(con, "director", "Separate Test Director")
    c = directory.add(con, "consultant", "Separate Test Consulting")
    assert (a["table"], b["table"], c["table"]) == ("client", "person", "company")
    assert "Separate Test Client" not in [x["name"] for x in directory.names(con, "resource")]
    assert "Separate Test Consulting" not in [x["name"] for x in directory.names(con, "client")]
    # adding again (case and spaces ignored) returns the same record
    assert directory.add(con, "client", "  separate test CLIENT ")["id"] == a["id"]
    assert db.scalar(con, "SELECT role FROM person WHERE id=?", (b["id"],)) == "Project Director"
    con.commit()


def test_api_and_project_save_fills_the_database(demo):
    con, pid = demo
    from app.main import app
    c = TestClient(app)
    assert c.get("/api/directory/names?kind=pm").status_code == 200
    r = c.post("/api/directory/companies", json={"name": "Api Sub Pty", "kind": "subcontractor", "trade": "Civil"}).json()
    assert c.put(f"/api/directory/companies/{r['id']}", json={"kind": "consultant"}).status_code == 200
    assert [x["name"] for x in c.get("/api/directory/companies?kind=consultant").json()].count("Api Sub Pty") == 1
    assert c.post("/api/directory/companies", json={"name": "Bad", "kind": "client"}).status_code == 400
    c.put(f"/api/projects/{pid}", json={"client_name": "Typed Client Ltd", "epec_pm": "Typed Pm", "project_director": "Typed Director"})
    assert "Typed Client Ltd" in [x["name"] for x in c.get("/api/directory/names?kind=client").json()]
    assert db.scalar(con, "SELECT role FROM person WHERE name='Typed Director'") == "Project Director"
