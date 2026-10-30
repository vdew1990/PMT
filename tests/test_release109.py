"""Release .109: the margin bridge, the accruals master list, the people behind a payroll accrual, estimate hints,
and a reason on every accrual edit or delete."""
from fastapi.testclient import TestClient

from app import accruals, db


def _client():
    return TestClient(__import__("app.main", fromlist=["app"]).app)


def test_margin_bridge_adds_up_to_the_forecast_profit(demo):
    con, pid = demo
    b = _client().get(f"/api/p/{pid}/margin-bridge").json()
    assert abs(b["check"]) < 0.01                                          # the steps reconcile
    steps = {s["key"]: s["value"] for s in b["steps"]}
    assert abs(steps["original"] + steps["revenue"] + steps["allowance"] + steps["overruns"] + steps["underruns"] + steps["other"] - steps["forecast"]) < 0.05
    assert b["direction"] == ("uplift" if b["erosion"] >= 0 else "erosion")
    assert all(r["effect"] < 0 for r in b["over"]) and all(r["effect"] > 0 for r in b["under"])


def _line(con, pid):
    return db.one(con, "SELECT id, code FROM cbs_node WHERE project_id=? AND kind='line' ORDER BY id LIMIT 1", (pid,))


def test_accrual_edit_and_delete_need_a_reason_which_is_logged(demo):
    con, pid = demo
    c = _client(); n = _line(con, pid)
    made = c.post(f"/api/p/{pid}/accruals", json=dict(node_id=n["id"], month="2026-09", amount=1000, kind="work", note="estimate")).json()
    aid = made["id"]
    assert c.post(f"/api/p/{pid}/accruals", json=dict(id=aid, node_id=n["id"], month="2026-09", amount=1200, kind="work")).status_code == 400   # no reason
    ok = c.post(f"/api/p/{pid}/accruals", json=dict(id=aid, node_id=n["id"], month="2026-09", amount=1200, kind="work", change_reason="PM revalued the work"))
    assert ok.status_code == 200
    via = [r["via"] for r in con.execute("SELECT via FROM change_log WHERE tbl='accrual' AND row_id=? AND op='U' ORDER BY id", (aid,))]
    assert any("PM revalued the work" in (v or "") for v in via)           # the reason is in the history
    assert c.delete(f"/api/p/{pid}/accruals/{aid}").status_code == 400
    assert c.delete(f"/api/p/{pid}/accruals/{aid}?reason=entered%20twice").status_code == 200
    assert db.one(con, "SELECT 1 x FROM accrual WHERE id=?", (aid,)) is None


def test_master_list_has_every_source_and_the_parties(demo):
    con, pid = demo
    c = _client(); n = _line(con, pid)
    c.post(f"/api/p/{pid}/accruals", json=dict(node_id=n["id"], month="2026-09", amount=500, kind="work", supplier_name="Acme Hire"))
    c.post(f"/api/p/{pid}/accruals", json=dict(node_id=n["id"], month="2026-09", amount=700, kind="invoice", inv_ref="ACME-1", supplier_name="ACME HIRE"))
    m = c.get(f"/api/p/{pid}/accruals/master").json()
    srcs = {r["source"] for r in m["rows"]}
    assert {"estimate", "approval"} <= srcs and srcs <= set(accruals.SOURCES)
    acme = [p for p in m["parties"] if p["name"].upper() == "ACME HIRE"]
    assert len(acme) == 1 and acme[0]["n"] == 2 and acme[0]["type"] == "company"    # one party whatever the case
    est = next(r for r in m["rows"] if r["source"] == "estimate" and r["amount"] == 500)
    assert est["editable"] and est["invoice"] == "" and est["party_type"] == "company"
    ap = next(r for r in m["rows"] if r["source"] == "approval" and r["amount"] == 700)
    assert ap["invoice"] == "ACME-1"


def test_people_behind_a_payroll_accrual_and_the_estimate_hint(blank):
    con = blank
    pid = db.insert(con, "project", dict(name="P109", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31"))
    g = db.insert(con, "cbs_node", dict(project_id=pid, code="PL04", name="Construction Labour", kind="group", gp="PL", category="PL04"))
    ln = db.insert(con, "cbs_node", dict(project_id=pid, code="PL04.001", parent_id=g, name="Foreman", kind="line", gp="PL"))
    for who, h_, posted in (("Ana Cole", 40, 0), ("Ben Ode", 30, 1)):
        db.insert(con, "pronto_labour", dict(project_id=pid, resource_code=who[:3].upper(), name=who, date_worked="2026-03-10", month="2026-03", category="PL04",
                                             hours=h_, total_cost=h_ * 50 if posted else 0, posted=posted, node_id=ln))
    con.commit()
    people = accruals.timesheet_people(con, pid, "PL04", "2026-03")
    assert [p["person"] for p in people] == ["Ana Cole", "Ben Ode"]
    assert people[0]["unposted_hours"] == 40 and people[1]["posted_cost"] == 1500
    assert accruals.timesheet_people(con, pid, "PL05", "2026-03") == []
    # an estimate on a PO, and an invoice for that PO lands later on the same line: the estimate is flagged
    est = db.insert(con, "accrual", dict(project_id=pid, node_id=ln, month="2026-08", amount=900, kind="work", po_no="PO77", status="open"))
    db.insert(con, "pronto_tx", {"project_id": pid, "class": "actual", "doc_type": "PO", "doc_no": "1", "reference": "INV-9", "tx_date": "2026-09-05", "month": "2026-09",
                                 "po_no": "PO77", "node_id": ln, "resource_code": "S1", "account_desc": "Acme", "cost": 880})
    con.commit()
    hints = accruals.estimate_hints(con, pid, db.rows(con, "SELECT * FROM accrual WHERE project_id=?", (pid,)))
    assert est in hints and "INV-9" in hints[est]
