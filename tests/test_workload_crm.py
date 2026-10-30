"""PM workload (project and client complexity, phase, PM level, travel and spread), the client CRM and the people
register behind the Portfolio's Clients and Team workload views."""
from app import workload as w


def _p(**k):
    base = dict(id=1, name="P", contract_value=20e6, project_type="Solar farm", voltage="33/132", start="2026-01-01", end="2027-06-30",
                status_date="2026-09-30", lat=-26.1, lon=149.9, client="ACME")
    base.update(k)
    return base


def test_complexity_suggestion_and_phase():
    assert w.suggest_complexity(3e6) == 1 and w.suggest_complexity(20e6) == 3 and w.suggest_complexity(20e6, voltage="33/330") == 4
    assert w.suggest_complexity(20e6, "Hybrid (solar + BESS)", "275") == 5 and w.suggest_complexity(500e6, voltage="500") == 5
    assert w.phase("2026-11-15", "2027-12-31", "2026-09-30") == (0.35, "Mobilising")
    assert w.phase("2027-06-01", "2027-12-31", "2026-09-30")[0] == 0.15
    assert w.phase("2025-01-01", "2026-06-30", "2026-09-30")[1] == "Close-out and defects"
    assert w.phase("2026-01-01", "2026-10-15", "2026-09-30")[1] == "Commissioning and handover"
    assert w.max_kv("33/330 kV") == 330 and w.max_kv(None) is None


def test_workload_grows_with_complexity_client_travel_and_spread_and_falls_with_level():
    brisbane = dict(name="A", pm_level=2, fte=1, lat=-27.47, lon=153.03)
    one = w.pm_workload(brisbane, [_p(complexity=3)], {})
    assert one["projects"][0]["demand"] > 0.40          # 0.40 peak load, plus travel from Brisbane to Wandoan (~340 km)
    assert one["projects"][0]["km_from_base"] and 300 < one["projects"][0]["km_from_base"] < 400
    hard = w.pm_workload(brisbane, [_p(complexity=3)], {"acme": dict(complexity=5, risk="High")})
    assert hard["pct"] > one["pct"] * 1.3                # difficult, high-risk client
    near = w.pm_workload(brisbane, [_p(complexity=3, id=1, lat=-27.5, lon=153.0), _p(complexity=3, id=2, lat=-27.6, lon=152.9)], {})
    far = w.pm_workload(brisbane, [_p(complexity=3, id=1, lat=-27.5, lon=153.0), _p(complexity=3, id=2, lat=-12.4, lon=130.8)], {})
    assert far["spread_factor"] > near["spread_factor"] and far["pct"] > near["pct"]
    senior = w.pm_workload(dict(brisbane, pm_level=3), [_p(complexity=3)], {})
    half = w.pm_workload(dict(brisbane, fte=0.5), [_p(complexity=3)], {})
    assert senior["pct"] < one["pct"] < half["pct"] and abs(half["pct"] - 2 * one["pct"]) < 0.2
    stretch = w.pm_workload(dict(brisbane, pm_level=2), [_p(complexity=5)], {})
    assert stretch["stretch"] == ["P"] and w.band(120)[0] == "over" and w.band(50)[0] == "available"


def test_clients_people_and_team_endpoints(demo):
    from fastapi.testclient import TestClient
    from app.main import app
    con, pid = demo
    c = TestClient(app)
    c.put(f"/api/projects/{pid}", json={"epec_pm": "Alex Marsden", "project_director": "Jordan Pike", "project_type": "BESS", "capacity_mw": "200",
                                       "storage_mwh": "800", "voltage": "33/275", "lat": "-26.13", "lon": "149.96", "complexity": "4"})
    pf = c.get("/api/portfolio").json()
    p = next((x for x in pf["projects"] if x["id"] == pid), None)
    assert p, f"the project is not in the portfolio; errors: {pf.get('errors')}"
    assert (p["project_type"], p["mw"], p["mwh"], p["kv"], p["complexity"], p["complexity_set"]) == ("BESS", 200, 800, 275, 4, True)
    client = p["client"]
    cid = c.post("/api/clients", json={"name": client.upper(), "risk": "High", "complexity": "5", "contacts": "Pat · PD"}).json()["id"]
    assert c.post("/api/clients", json={"name": client}).json()["id"] == cid          # same client, matched by name
    row = next(x for x in c.get("/api/clients").json() if x["id"] == cid)
    assert row["risk"] == "High" and pid in [r["id"] for r in row["running"]] and "Alex Marsden" in row["pms"]
    people = c.get("/api/people").json()
    assert {x["name"].title() for x in people} >= {"Alex Marsden", "Jordan Pike"}
    before = next(r for r in c.get("/api/workload?director=Jordan Pike").json()["team"] if r["name"] == "Alex Marsden")
    c.post("/api/people", json={"name": "alex marsden", "pm_level": "3", "fte": "1", "lat": "-27.47", "lon": "153.03", "reports_to": "Jordan Pike"})
    after = next(r for r in c.get("/api/workload?director=Jordan Pike").json()["team"] if r["name"].lower() == "alex marsden")
    assert after["level"] == 3 and after["capacity"] > before["capacity"] and after["projects"][0]["km_from_base"] > 300
    assert after["projects"][0]["client_factor"] > 1.2                               # the difficult, high-risk client
    c.delete(f"/api/clients/{cid}")


def test_invoices_by_supplier(demo):
    """Actuals > Invoices by supplier: every PO receipt / direct invoice / supplier journal, grouped per supplier; the
    invoices add up to the suppliers' GL cost, labour timesheets are left out."""
    from app import db, invoices
    con, pid = demo
    d = invoices.listing(con, pid)
    assert d["suppliers"] and d["invoices"]
    gl = db.scalar(con, "SELECT SUM(cost) FROM pronto_tx WHERE project_id=? AND class IN ('actual','journal') AND doc_type IN ('PO','CV','GJ','GV') "
                        "AND COALESCE(resource_code,'')!=''", (pid,))
    assert abs(d["total"] - gl) < 1 and abs(sum(i["amount"] for i in d["invoices"]) - gl) < 1
    assert not any(i["doc_type"] == "TS" for i in d["invoices"])
    s = d["suppliers"][0]
    assert s["name"] and s["invoices"] == sum(1 for i in d["invoices"] if i["supplier"] == s["code"])
    assert invoices.xlsx(con, pid)[:2] == b"PK"
