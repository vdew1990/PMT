"""Accruals as in the PMT workbook (Vincent 20/10): estimates, invoices awaiting approval matched by invoice / quote / PO
number, the work-month timing of matched invoices, finance's accruals in Pronto, unposted timesheets that do not belong
here, and the three timelines (work performed, billed, paid)."""
import pytest

from app import accruals, db, engine


def _line(con, pid):
    return db.one(con, "SELECT id, code FROM cbs_node WHERE project_id=? AND kind='line' AND code LIKE 'PE%' ORDER BY code LIMIT 1", (pid,))


def _x(con, pid, nid):
    res = engine.compute(con, pid)
    row = next(r for r in res["rows"] if r.get("node_id") == nid and r["kind"] == "line")
    return dict(zip(res["grid"], row["x"])), row


def _invoice(con, pid, nid, ref, amount, day, po=None, desc="", supplier="S30TST01"):
    db.insert(con, "pronto_tx", dict(project_id=pid, node_id=nid, category="PE01", reference=ref, doc_no=ref, doc_type="PO" if po else "CV", po_no=po,
                                     tx_date=day, month=day[:7], cost=amount, description=desc, resource_code=supplier, account_desc="TEST SUPPLIER", **{"class": "actual"}))


def test_matched_invoice_counts_in_the_work_month_and_reverses_where_it_lands(demo):
    con, pid = demo
    n = _line(con, pid)["id"]
    aid = db.insert(con, "accrual", dict(project_id=pid, node_id=n, month="2026-07", amount=10000, kind="invoice", inv_ref="INV-90001", source="PM"))
    accruals.match(con, pid)
    x, row = _x(con, pid, n)
    acc_before = row["acc"]
    assert x["2026-07"] == pytest.approx(10000, abs=0.01)
    # the invoice lands two months later for a little more: matched by number, "0090001" or "inv 90001" both match
    _invoice(con, pid, n, "0090001", 10500, "2026-09-12")
    accruals.match(con, pid)
    a = db.one(con, "SELECT * FROM accrual WHERE id=?", (aid,))
    assert (a["status"], a["matched_month"], a["matched_via"]) == ("investigate", "2026-09", "invoice number")
    x, row = _x(con, pid, n)
    assert x["2026-07"] == pytest.approx(10500, abs=0.01)            # trued up to the invoice in the month of the work
    assert x["2026-09"] <= -10500 + 0.01                               # reversed where it landed: Sep nets to zero with the invoice
    assert row["acc"] == pytest.approx(acc_before - 10000, abs=0.01)  # no longer an open accrual
    # the PM decides: part of the work is still to come -> the difference stays accrued; accept -> matched
    db.update(con, "accrual", aid, {"amount": 12000, "resolution": "rest_open"})
    accruals.match(con, pid)
    assert db.one(con, "SELECT status FROM accrual WHERE id=?", (aid,))["status"] == "partial"
    x, _ = _x(con, pid, n)
    assert x["2026-07"] == pytest.approx(12000, abs=0.01)             # 10,500 landed + 1,500 still accrued
    db.update(con, "accrual", aid, {"resolution": "accept"})
    accruals.match(con, pid)
    assert db.one(con, "SELECT status FROM accrual WHERE id=?", (aid,))["status"] == "matched"


def test_quote_and_po_matching_and_estimates_never_match(demo):
    con, pid = demo
    n = _line(con, pid)["id"]
    q = db.insert(con, "accrual", dict(project_id=pid, node_id=n, month="2026-08", amount=4000, kind="invoice", quote_ref="Q-55512", source="PM"))
    po = db.insert(con, "accrual", dict(project_id=pid, node_id=n, month="2026-08", amount=7000, kind="invoice", po_no="9901", supplier_code="S30TST01", source="PM"))
    est = db.insert(con, "accrual", dict(project_id=pid, node_id=n, month="2026-08", amount=7000, kind="work", po_no="9901", source="PM"))
    _invoice(con, pid, n, "INV-A1", 4000, "2026-09-03", desc="Supply as per quote Q-55512")
    _invoice(con, pid, n, "9901AA", 3000, "2026-07-20", po="9901")    # before the accrual month: not this one
    _invoice(con, pid, n, "9901AB", 7000, "2026-09-20", po="9901")
    accruals.match(con, pid)
    st = {r["id"]: r for r in db.rows(con, "SELECT * FROM accrual WHERE id IN (?,?,?)", (q, po, est))}
    assert (st[q]["status"], st[q]["matched_via"]) == ("matched", "quote number")
    assert (st[po]["status"], st[po]["matched_via"], st[po]["matched_refs"]) == ("matched", "PO number", '["9901AB"]')
    assert st[est]["status"] == "open"                                 # an estimate is not one invoice: the PM reverses it


def test_finance_accruals_in_pronto_are_shown_and_not_counted_twice(demo):
    con, pid = demo
    n = _line(con, pid)
    wip = dict(project_id=pid, node_id=n["id"], category="PE01", account_code="3000B1125", account_desc="Work in Progress", reference="7777", **{"class": "journal"})
    db.insert(con, "pronto_tx", dict(wip, doc_type="GJ", tx_date="2026-08-31", month="2026-08", cost=5000, description="Aug 26 Acc Acme Hire"))
    db.insert(con, "pronto_tx", dict(wip, doc_type="GV", tx_date="2026-09-01", month="2026-09", cost=-5000, description="Aug 26 Acc Acme Hire"))
    db.insert(con, "pronto_tx", dict(wip, doc_type="GJ", tx_date="2026-09-30", month="2026-09", cost=6000, description="Sep 26 Acc Acme Hire"))
    pr = [p for p in accruals.pronto_accruals(con, pid) if p["reference"] == "7777"]
    assert {(p["month"], p["open"]) for p in pr} == {("2026-08", 0.0), ("2026-09", 6000.0)}
    assert pr[0]["supplier"] == "Acme Hire"
    aid = db.insert(con, "accrual", dict(project_id=pid, node_id=n["id"], month="2026-09", amount=8000, kind="work", po_no="7777", source="PM"))
    assert accruals.pronto_cover(con, pid)[aid] == 6000
    assert sum(amt for nid, m, amt, src in accruals.counted(con, pid) if nid == n["id"] and src == "PM" and m == "2026-09") == pytest.approx(2000 + sum(
        a["amount"] for a in db.rows(con, "SELECT amount FROM accrual WHERE project_id=? AND node_id=? AND month='2026-09' AND status='open' AND id!=?", (pid, n["id"], aid))))
    assert accruals.overlaps(con, pid, n["id"], po_no="7777")
    db.update(con, "accrual", aid, {"status": "cancelled"})


def test_unposted_hours_that_do_not_belong_here_stop_accruing(demo):
    con, pid = demo
    rows, _ = accruals.unposted(con, pid)
    r = next(x for x in rows if x["auto"] > 0)
    before = sum(amt for _, m, amt, src in accruals.counted(con, pid) if src == "Timesheet")
    qid = db.insert(con, "timesheet_request", dict(project_id=pid, resource_code=r["resource_code"], person=r["person"], date_from=r["d0"], date_to=r["d1"], hours=r["hours"], target="NES2"))
    after = sum(amt for _, m, amt, src in accruals.counted(con, pid) if src == "Timesheet")
    assert after == pytest.approx(before - r["auto"], abs=0.01)
    assert next(x for x in accruals.unposted(con, pid)[0] if x["resource_code"] == r["resource_code"] and x["month"] == r["month"])["state"] == "journal requested"
    # payroll moves the hours: the request closes by itself
    con.execute("DELETE FROM pronto_labour WHERE project_id=? AND resource_code=? AND date_worked BETWEEN ? AND ?", (pid, r["resource_code"], r["d0"], r["d1"]))
    accruals.match(con, pid)
    assert db.one(con, "SELECT status FROM timesheet_request WHERE id=?", (qid,))["status"] == "done"


def test_api_refuses_an_invoice_already_in_pronto_and_timelines_tie(demo):
    from fastapi.testclient import TestClient
    from app.main import app
    con, pid = demo
    c = TestClient(app)
    n = _line(con, pid)["id"]
    _invoice(con, pid, n, "INV-55001", 900, "2026-09-10")
    con.commit()
    r = c.post(f"/api/p/{pid}/accruals", json={"node_id": n, "month": "2026-09", "amount": 900, "kind": "invoice", "inv_ref": "INV-55001"})
    assert r.status_code >= 400 and "already in Pronto" in r.text
    r = c.post(f"/api/p/{pid}/accruals", json={"node_id": n, "month": "2026-09", "amount": 900, "kind": "invoice"})
    assert r.status_code >= 400 and "needs its invoice, PO or quote" in r.text
    t = c.get(f"/api/p/{pid}/accruals/timelines").json()
    res = engine.compute(con, pid)
    # work performed in total = cost to date + open accruals; billed = cost to date less finance's accrual journals
    assert sum(t["work"]) == pytest.approx(res["total"]["ctd"] + res["total"]["acc"], abs=1)
    assert sum(t["billed"]) <= sum(t["work"]) + 1 and t["months"] == sorted(t["months"])


def test_negative_row_reversing_finance_accrual_is_never_matched_to_an_invoice(demo):
    """Vincent 20/10 (LMATS, PO 3174): the PM's -4,080 taking back finance's stale accrual stays counted."""
    con, pid = demo
    n = _line(con, pid)["id"]
    aid = db.insert(con, "accrual", dict(project_id=pid, node_id=n, month="2026-09", amount=-4080, kind="invoice", po_no="3174", source="PM"))
    _invoice(con, pid, n, "3174AA", 4080, "2026-09-11", po="3174")
    accruals.match(con, pid)
    assert db.one(con, "SELECT status FROM accrual WHERE id=?", (aid,))["status"] == "open"
    assert any(a == aid for a in [r["id"] for r in db.rows(con, "SELECT id FROM accrual WHERE project_id=? AND status='open'", (pid,))])
