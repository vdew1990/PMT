"""A claim schedule with past months, this month's claim and the forecast overwrites the claim schedule: months before the status
month become claims already made (numbered and dated from the sheet's register), the status month the draft claim, later months
the forecast. Undo puts the old schedule and claims back."""
import datetime as dt
import io

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app import db, revenue, schedule_import as si, templates_io
from app.main import app


def _book(path, register=True):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Claim"
    d = dt.datetime
    months = [d(2026, m, 28) for m in range(1, 13)]
    ws.append(["INDEX", "Fictional site", None, None, "Period", d(2026, 9, 30)])
    reg_head = [None, "Claim #", "Date Submitted", "Date Approved", "Invoice Ref", "Approved This Claim (ex GST)"] if register else []
    ws.append(["REF", "ITEM", "SCOPE DESCRIPTION", "START", "END", "MONTHS", "AUD (excl GST)", "CLAIM REQUIREMENT", "PHASE", "INVOICED", *months, *reg_head])
    a = {1: 100, 2: 100, 3: 300, 4: 200, 9: 100, 10: 200}           # line A, 1,000
    b = {3: 100, 4: 100, 9: 50, 11: 250}                             # line B, 500
    regrows = [[1, d(2026, 3, 5), d(2026, 3, 20), "INV1", 200], [2, d(2026, 4, 3), d(2026, 4, 15), "INV2", 400], [3, d(2026, 5, 2), d(2026, 5, 20), "INV3", 300]]
    rows = [
        [None, "1.01", "Preliminaries", None, None, None, 1500, None, None, None] + [None] * 12,
        ["EPC", "1.01.01", "Line A", d(2026, 1, 31), d(2026, 10, 31), 10, 1000, "Transmittal", "Design", 700] + [a.get(m) for m in range(1, 13)],
        ["EPC", "1.01.02", "Line B", d(2026, 3, 31), d(2026, 11, 30), 9, 500, "Docket", "Construction", 250] + [b.get(m) for m in range(1, 13)],
    ]
    for r, rg in zip(rows, regrows):                                  # the register sits to the right, one claim per row
        ws.append(r + ([None] + rg if register else []))
    wb.save(path)


def _project(con, status="2026-09-30"):
    return db.insert(con, "project", dict(name="Overwrite", status_date=status, client_name="C"))


def test_past_months_become_numbered_claims_the_status_month_a_draft_and_later_months_the_forecast(tmp_path, blank):
    con = blank
    pid = _project(con)
    p = tmp_path / "s.xlsx"
    _book(p)
    parsed = si.parse(p)
    assert parsed["period"] == "2026-09-30" and [r["no"] for r in parsed["register"]] == [1, 2, 3]
    h = si.history(parsed, "2026-09")
    assert h["n_claims"] == 3 and h["unmatched"] == [] and h["past_total"] == 900 and h["current_total"] == 150 and h["future_total"] == 450
    assert [c["months"] for c in h["claims"]] == [["2026-01", "2026-02"], ["2026-03"], ["2026-04"]]       # claim 1 is an opening balance over two months
    res = si.apply(con, pid, parsed, "overwrite", status_month="2026-09")
    assert res["claims_created"] == 4 and res["past_total"] == 900 and res["current_total"] == 150 and res["forecast_total"] == 450 and res["over_scheduled"] == 0
    claims = {c["period"]: c for c in db.rows(con, "SELECT * FROM claim WHERE project_id=? ORDER BY period", (pid,))}
    assert [c["status"] for c in claims.values()] == ["certified"] * 4 + ["draft"]
    assert claims["2026-03"]["claim_no"] == "CLAIM002" and claims["2026-03"]["certified_date"] == "2026-04-15" and "INV2" in claims["2026-03"]["note"]
    assert claims["2026-01"]["claim_no"] == "CLAIM001-2026-01" and claims["2026-02"]["claim_no"] == "CLAIM001-2026-02"
    assert claims["2026-09"]["claim_no"] == "CLAIM004"
    items = {i["ref"]: i for i in revenue.items_tree(con, pid)}
    a, b = items["1.01.01"], items["1.01.02"]
    assert a["claimed"] == 700 and a["claimed_m"] == {"2026-01": 100.0, "2026-02": 100.0, "2026-03": 300.0, "2026-04": 200.0}
    assert a["plan"] == {"2026-09": 100.0, "2026-10": 200.0} and b["plan"] == {"2026-09": 50.0, "2026-11": 250.0}   # no plan rows for the claimed months
    assert items["1.01"]["value_calc"] == 1500
    # the claimed months are locked, the status month and the forecast stay editable and the cap still holds
    with pytest.raises(ValueError):
        revenue.set_cell(con, pid, a["id"], "2026-03", amount=1)
    with pytest.raises(ValueError):
        revenue.set_cell(con, pid, a["id"], "2026-11", amount=1)                                          # 700 claimed + 300 scheduled = the price


def test_without_a_register_each_past_month_is_a_submitted_claim(tmp_path, blank):
    con = blank
    pid = _project(con)
    p = tmp_path / "s.xlsx"
    _book(p, register=False)
    parsed = si.parse(p)
    assert parsed["register"] == []
    res = si.apply(con, pid, parsed, "overwrite", status_month="2026-09")
    assert res["claims_created"] == 4                                        # Jan, Feb, Mar, Apr: no opening balance to group them
    cl = db.rows(con, "SELECT claim_no, period, status FROM claim WHERE project_id=? ORDER BY period", (pid,))
    assert [(c["claim_no"], c["status"]) for c in cl] == [("CLAIM001", "submitted"), ("CLAIM002", "submitted"), ("CLAIM003", "submitted"), ("CLAIM004", "submitted"), ("CLAIM005", "draft")]


def test_overwrite_replaces_the_old_schedule_and_claims_and_undo_brings_them_back(tmp_path, blank):
    con = blank
    pid = _project(con)
    old = db.insert(con, "contract_item", dict(project_id=pid, ref="9.9", description="Old item", kind="base", value=777, start_date="2026-01-01", end_date="2026-02-28", method="even"))
    oc = db.insert(con, "claim", dict(project_id=pid, claim_no="OLD1", period="2026-01", status="paid"))
    db.insert(con, "claim_line", dict(claim_id=oc, item_id=old, amount=777))
    p = tmp_path / "s.xlsx"
    _book(p)
    # a plain Replace refuses while claims refer to the schedule; Overwrite is the explicit way
    with pytest.raises(ValueError):
        si.apply(con, pid, si.parse(p), "replace", status_month="2026-09")
    rid = templates_io.make_restore_point(con, pid, "Claim schedule overwrite", "T", with_claims=True)
    si.apply(con, pid, si.parse(p), "overwrite", status_month="2026-09")
    assert db.scalar(con, "SELECT COUNT(*) FROM claim WHERE project_id=? AND claim_no='OLD1'", (pid,)) == 0
    assert db.scalar(con, "SELECT COUNT(*) FROM contract_item WHERE project_id=? AND ref='9.9'", (pid,)) == 0
    assert db.scalar(con, "SELECT COUNT(*) FROM claim WHERE project_id=?", (pid,)) == 5
    templates_io.undo(con, pid, rid)
    assert [c["claim_no"] for c in db.rows(con, "SELECT claim_no FROM claim WHERE project_id=?", (pid,))] == ["OLD1"]
    assert db.scalar(con, "SELECT COUNT(*) FROM contract_item WHERE project_id=? AND ref='9.9'", (pid,)) == 1
    assert db.scalar(con, "SELECT amount FROM claim_line cl JOIN claim c ON c.id=cl.claim_id WHERE c.id=?", (oc,)) == 777
    assert db.scalar(con, "SELECT COUNT(*) FROM contract_item WHERE project_id=? AND ref LIKE '1.01%'", (pid,)) == 0   # the file's items are gone again


def test_overwrite_over_http_with_a_preview_first(tmp_path, blank):
    con = blank
    pid = _project(con)
    con.commit()
    p = tmp_path / "s.xlsx"
    _book(p)
    with TestClient(app) as c:
        _http_flow(c, p, pid)


def _http_flow(c, p, pid):
    con = db.connect()
    base = f"/api/p/{pid}"
    with open(p, "rb") as f:
        r = c.post(f"{base}/schedule/analyse", files={"file": ("s.xlsx", f)}).json()
    h = r["history"]
    assert r["status_month"] == "2026-09" and h["n_claims"] == 3 and h["past_total"] == 900 and r["existing_claims"] == 0 and r["sheet_period"] == "2026-09-30"
    out = c.post(f"{base}/schedule/commit", json={"token": r["token"], "filename": "s.xlsx", "mode": "overwrite"}).json()
    assert out["claims_created"] == 4 and out["draft_claim"] and out["restore_point"]
    cm = c.get(f"{base}/contract").json()["claim_months"]
    assert cm["2026-03"]["issued"] and cm["2026-09"]["status"] == "draft" and not cm["2026-09"]["issued"]
    # a second upload over the top asks for the existing claims to be counted
    with open(p, "rb") as f:
        r2 = c.post(f"{base}/schedule/analyse", files={"file": ("s.xlsx", f)}).json()
    assert r2["existing_claims"] == 5
    bad = c.post(f"{base}/schedule/commit", json={"token": r2["token"], "mode": "replace"})
    assert bad.status_code == 400                                            # replace still refuses; overwrite is the explicit choice


def test_overwrite_needs_a_status_date(tmp_path, blank):
    con = blank
    pid = db.insert(con, "project", dict(name="No date"))
    con.commit()
    p = tmp_path / "s.xlsx"
    _book(p)
    with TestClient(app) as c:
        with open(p, "rb") as f:
            r = c.post(f"/api/p/{pid}/schedule/analyse", files={"file": ("s.xlsx", f)}).json()
        bad = c.post(f"/api/p/{pid}/schedule/commit", json={"token": r["token"], "mode": "overwrite"})
        assert bad.status_code == 400 and "status date" in bad.json()["detail"]
