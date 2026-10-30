"""Pronto data > Inspect (Vincent 20/10): the rows as loaded, and checks for totals rows, future dates, large reversed
keying errors and identical rows, without flagging timesheet notes that merely mention a total."""
import pytest
from fastapi.testclient import TestClient

from app import db, pronto_raw
from app.main import app


def _tx(con, pid, **k):
    base = dict(project_id=pid, category="PE01", tx_date="2026-08-10", month="2026-08", cost=100, doc_type="CV", doc_no="1", reference="R", description="x", **{"class": "actual"})
    base.update(k)
    return db.insert(con, "pronto_tx", base)


def test_checks_find_future_reversed_and_totals(demo):
    con, pid = demo
    cut = db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,))["status_date"]
    f = _tx(con, pid, tx_date="2030-12-01", month="2030-12", cost=-12.5, doc_no="F1")
    a = _tx(con, pid, tx_date="2026-05-05", month="2026-05", cost=15_734_436, doc_no="2614", reference="2614AA")
    b = _tx(con, pid, tx_date="2026-05-06", month="2026-05", cost=-15_734_436, doc_no="4008", doc_type="GJ", reference="2614", **{"class": "journal"})
    t = _tx(con, pid, category="", tx_date=None, month=None, cost=999, doc_no="", description="TOTAL")
    # month-end revenue accrual and its reversal: routine, not a keying error
    _tx(con, pid, tx_date="2026-06-30", month="2026-06", cost=-2_000_000, doc_type="GJ", **{"class": "revenue"})
    _tx(con, pid, tx_date="2026-07-01", month="2026-07", cost=2_000_000, doc_type="GV", **{"class": "revenue"})
    c = {x["id"]: x for x in pronto_raw.checks(con, pid)}
    assert f in c["transactions:future"]["ids"] and cut < "2030-12-01"
    assert set(c["transactions:reversed"]["ids"]) == {a, b}
    assert t in c["transactions:totals"]["ids"] and c["transactions:totals"]["level"] == "bad"
    last, later = pronto_raw.as_of(con, pid, "transactions")
    assert last < "2030-12-01" and later >= 1


def test_labour_notes_mentioning_a_total_are_not_totals(demo):
    con, pid = demo
    db.insert(con, "pronto_labour", dict(project_id=pid, resource_code="JB01", name="J B", category="PL01", date_worked="2026-02-17", month="2026-02", hours=11,
                                        total_cost=1665, notes="Site Uplift LAFHA Qty 1 Rate $24.50 Total $24.50"))
    c = {x["id"]: x for x in pronto_raw.checks(con, pid)}
    assert c["labour:totals"]["level"] == "ok"


def test_raw_rows_api_search_check_and_excel(demo):
    con, pid = demo
    _tx(con, pid, tx_date="2030-12-01", month="2030-12", cost=-7, description="SITE BBQ AFTER CONCRETE POUR")
    con.commit()
    cl = TestClient(app)
    d = cl.get(f"/api/p/{pid}/pronto/raw/transactions", params={"check": "transactions:future"}).json()
    assert d["count"] >= 1 and all(r["tx_date"] > "2027" for r in d["rows"])
    d = cl.get(f"/api/p/{pid}/pronto/raw/transactions", params={"q": "bbq concrete"}).json()
    assert d["count"] == 1 and d["amount"] == -7
    assert "ids" not in cl.get(f"/api/p/{pid}/pronto/checks").json()[0]
    st = cl.get(f"/api/p/{pid}/pronto/status").json()["transactions"]
    assert st["future"] >= 1 and st["last"] < "2030"
    r = cl.get(f"/api/p/{pid}/pronto/raw-xlsx/transactions", params={"check": "transactions:future"})
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert cl.get(f"/api/p/{pid}/pronto/raw/nonsense").status_code == 404


def test_future_dated_actuals_stay_in_ctd_and_raise_an_error(demo):
    """Vincent 20/10: an actual in Pronto is part of CTD wherever it is dated, but a date in the future is an error to flag."""
    from app import diagnostics, engine, reports
    con, pid = demo
    before = engine.compute(con, pid)["total"]["ctd"]
    n = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND kind='line' ORDER BY code LIMIT 1", (pid,))["id"]
    _tx(con, pid, node_id=n, tx_date="2030-12-01", month="2030-12", cost=-102.51, doc_no="10910", account_desc="EXPENSE CLAIM")
    con.execute("UPDATE project SET version=version+1 WHERE id=?", (pid,))   # as a Pronto import does (the engine caches per version)
    assert engine.compute(con, pid)["total"]["ctd"] == pytest.approx(before - 102.51, abs=0.01)
    h = {c["id"]: c for c in reports.health(con, pid)}
    assert h["pronto_future"]["level"] == "error" and "CV 10910" in h["pronto_future"]["detail"]
    assert "2030" not in (h.get("pronto_ok") or h.get("pronto_stale"))["detail"]       # the latest date shown is a real one
    d = next(c for c in diagnostics.run(con, pid)["checks"] if c["id"] == "pronto_future")
    assert any(r["pronto"] == "-102.51" for r in d["rows"])
