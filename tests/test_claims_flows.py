import pytest

from app import db, engine, reports, revenue, subcontracts
from tests.test_core import _mini, _row


def _sub(con, pid, n, value=100000, ret=0.05):
    sid = db.insert(con, "subcontract", dict(project_id=pid, name="Sub A", node_id=n, contract_value=value, retention_pct=ret))
    db.insert(con, "sub_milestone", dict(subcontract_id=sid, seq=1, name="Works", type="Progress", pct=1.0, value=0, start_month="2026-01", end_month="2026-08"))
    con.execute("UPDATE cbs_node SET method='CLAIM' WHERE id=?", (n,))
    return sid


def test_claim_defaults_to_schedule_and_flows_to_accrual(blank):
    pid, n = _mini(blank, allowance=200000)
    sid = _sub(blank, pid, n)
    cid = subcontracts.create_claim(blank, sid, "2026-05")
    d = subcontracts.claim_detail(blank, sid, cid)
    assert d["lines"][0]["suggested"] == pytest.approx(62500)          # 5 of 8 months of 100,000
    assert d["claimed"] == pytest.approx(62500) and d["basis"] == "claimed"
    db.bump(blank, pid)
    r = _row(blank, pid, n)
    assert r["acc_claim"] == pytest.approx(62500 * 0.95)                # net of 5% retention, in the claim month
    assert r["acc"] == pytest.approx(62500 * 0.95)


def test_approved_amount_replaces_claimed_in_the_accrual(blank):
    pid, n = _mini(blank, allowance=200000)
    sid = _sub(blank, pid, n)
    cid = subcontracts.create_claim(blank, sid, "2026-05")
    subcontracts.approve_total(blank, cid, 50000)
    subcontracts.refresh_cache(blank, cid)
    db.bump(blank, pid)
    d = subcontracts.claim_detail(blank, sid, cid)
    assert d["approved"] == pytest.approx(50000) and d["effective"] == pytest.approx(50000) and d["basis"] == "approved"
    assert _row(blank, pid, n)["acc_claim"] == pytest.approx(50000 * 0.95)


def test_line_by_line_approval_mixes_approved_and_claimed(blank):
    pid, n = _mini(blank, allowance=200000)
    sid = _sub(blank, pid, n)
    db.insert(blank, "sub_milestone", dict(subcontract_id=sid, seq=2, name="Extra", type="Milestone", value=10000, start_month="2026-05"))
    cid = subcontracts.create_claim(blank, sid, "2026-05")
    lines = db.rows(blank, "SELECT * FROM sub_claim_line WHERE claim_id=? ORDER BY id", (cid,))
    assert len(lines) == 2
    blank.execute("UPDATE sub_claim_line SET approved=40000 WHERE id=?", (lines[0]["id"],))  # one line reviewed, one still as claimed
    t = subcontracts.claim_totals(blank, db.one(blank, "SELECT * FROM sub_claim WHERE id=?", (cid,)), db.one(blank, "SELECT * FROM subcontract WHERE id=?", (sid,)))
    assert t["effective"] == pytest.approx(40000 + 10000) and t["basis"] == "part approved"


def test_invoice_landing_in_pronto_retires_the_claim_accrual(blank):
    pid, n = _mini(blank, allowance=200000)
    sid = _sub(blank, pid, n)
    cid = subcontracts.create_claim(blank, sid, "2026-05")
    blank.execute("UPDATE sub_claim SET inv_ref='INV-9' WHERE id=?", (cid,))
    db.bump(blank, pid)
    assert _row(blank, pid, n)["acc_claim"] > 0
    db.insert(blank, "pronto_tx", dict(project_id=pid, category="PS04", account_code="S30AAA01", doc_type="CV", doc_no="55", reference="INV-9", tx_date="2026-05-20",
                                       cost=59375, **{"class": "actual"}, resource_code="S30AAA01", month="2026-05", node_id=n))
    db.bump(blank, pid)
    r = _row(blank, pid, n)
    assert r["acc_claim"] == 0 and r["ctd"] == 40000 + 59375          # the invoice is cost to date now, not an accrual as well


def test_claim_forecast_is_what_is_left_after_claims(blank):
    pid, n = _mini(blank, allowance=200000)
    sid = _sub(blank, pid, n)
    db.bump(blank, pid)
    before = _row(blank, pid, n)["ctc"]
    assert before == pytest.approx(100000 * 0.95)                     # nothing claimed yet: the whole net schedule remains
    cid = subcontracts.create_claim(blank, sid, "2026-05")
    db.bump(blank, pid)
    after = _row(blank, pid, n)
    assert after["ctc"] == pytest.approx(100000 * 0.95 - 62500 * 0.95)
    assert after["eac"] == pytest.approx(after["ctd"] + after["acc"] + after["ctc"])


def test_editing_the_schedule_keeps_claim_lines(demo):
    con, pid = demo
    sub = db.one(con, "SELECT * FROM subcontract WHERE project_id=?", (pid,))
    before = db.scalar(con, "SELECT COUNT(*) FROM sub_claim_line")
    import app.main as m  # the save endpoint upserts schedule lines by id
    items = subcontracts.items(con, sub["id"])
    m.sub_save(pid, dict(id=sub["id"], name=sub["name"], milestones=[dict(i) for i in items]), con)
    assert db.scalar(con, "SELECT COUNT(*) FROM sub_claim_line") == before


# ---- client claims: certified amounts -------------------------------------------------------------
def test_certified_amount_counts_instead_of_claimed(demo):
    con, pid = demo
    cid = db.insert(con, "claim", dict(project_id=pid, claim_no="CERT", period="2026-10", status="submitted"))
    it = [i for i in revenue.items_tree(con, pid) if i["is_leaf"] and i["kind"] == "base"][0]
    db.insert(con, "claim_line", dict(claim_id=cid, item_id=it["id"], amount=100000))
    claimed_before = [i for i in revenue.items_tree(con, pid) if i["id"] == it["id"]][0]["claimed"]
    revenue.certify_total(con, cid, 80000)
    after = [i for i in revenue.items_tree(con, pid) if i["id"] == it["id"]][0]["claimed"]
    assert after == pytest.approx(claimed_before - 20000)
    con.execute("DELETE FROM claim WHERE id=?", (cid,))


def test_certify_total_shares_across_lines_exactly(demo):
    con, pid = demo
    cid = db.insert(con, "claim", dict(project_id=pid, claim_no="SPLIT", period="2026-10", status="submitted"))
    for i in [x for x in revenue.items_tree(con, pid) if x["is_leaf"]][:3]:
        db.insert(con, "claim_line", dict(claim_id=cid, item_id=i["id"], amount=33333.33))
    revenue.certify_total(con, cid, 77777.77)
    assert db.scalar(con, "SELECT SUM(certified) FROM claim_line WHERE claim_id=?", (cid,)) == pytest.approx(77777.77)
    con.execute("DELETE FROM claim WHERE id=?", (cid,))


# ---- revenue against cost: the three views --------------------------------------------------------
def test_work_view_cost_ties_to_eac_and_revenue_to_recognised(demo):
    con, pid = demo
    f = reports.flows(con, pid)
    res = engine.compute(con, pid)
    assert sum(f["work"]["cost"]) == pytest.approx(res["total"]["eac"], abs=1)
    assert f["work"]["revenue"] is not None and sum(f["work"]["revenue"]) > 0
    assert f["months"][0] <= f["status_month"] <= f["months"][-1]


def test_status_month_revenue_uses_schedule_when_no_claim_issued(demo):
    con, pid = demo
    f = reports.flows(con, pid)
    i = f["months"].index(f["status_month"])
    assert f["work"]["revenue"][i] > 0                                 # September has a draft claim only; its schedule still shows


def test_cash_view_is_internally_consistent(demo):
    con, pid = demo
    c = reports.flows(con, pid)["cash"]
    assert c["cum_net"][-1] == pytest.approx(sum(c["received"]) - sum(c["paid"]), abs=1)
    assert c["client_terms_days"] > 0 and c["supplier_terms_days"] > 0
    assert c["lowest"]["value"] <= c["cum_net"][0]


def test_scoped_flows_have_cost_only(demo):
    con, pid = demo
    node = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND code='PS'", (pid,))["id"]
    f = reports.flows(con, pid, node=str(node))
    assert f["work"]["revenue"] is None and f["invoices"]["invoiced"] is None and sum(f["work"]["cost"]) > 0


# ---- snapshots ------------------------------------------------------------------------------------
def test_snapshot_compare_and_monthly_series(demo):
    con, pid = demo
    snaps = db.rows(con, "SELECT id, kind, period FROM snapshot WHERE project_id=? ORDER BY period", (pid,))
    assert len(snaps) >= 4                                              # day zero, July, August, September
    base = [s for s in snaps if s["kind"] == "baseline"][0]
    cmp = reports.snapshot_compare(con, pid, base["id"], "live")
    top = [r for r in cmp["rows"] if r["level"] == 1]
    assert sum(r["eac_d"] for r in top) == pytest.approx(engine.compute(con, pid)["total"]["eac"] - sum(r["eac_a"] for r in top))
    ser = reports.snapshot_series(con, pid, snaps[1]["id"], "live", code="PS04")
    assert len(ser["a"]) == len(ser["months"]) == len(ser["delta"])
    assert sum(ser["b"]) > 0
    assert any(abs(x) > 1 for x in ser["delta"])                        # forecast moved between the two versions
    cur = reports.snapshot_curves(con, pid, snaps[1]["id"], "live")
    assert cur["a"]["cost"][-1] > 0 and cur["b"]["revenue"][-1] > 0


def test_history_snapshots_show_growing_cost_to_date(demo):
    con, pid = demo
    eom = db.rows(con, "SELECT id, summary_json FROM snapshot WHERE project_id=? AND kind='eom' ORDER BY period", (pid,))
    import json
    ctd = [json.loads(s["summary_json"])["totals"]["ctd"] for s in eom]
    assert ctd == sorted(ctd) and ctd[0] < ctd[-1]


def test_pm_forecast_on_the_claim_sheet_drives_cost_control(blank):
    """Lump sum $100k, two schedule lines, 10% retention released in Dec. A claim in September, then the PM forecasts
    the rest by month on the claim sheet: cost control follows the PM's months, not the schedule."""
    from app import engine, subcontracts as sc
    con = blank
    pid = db.insert(con, "project", dict(name="Subby job", status_date="2026-09-30", project_start="2026-01-01", project_end="2027-03-31"))
    nid = db.insert(con, "cbs_node", dict(project_id=pid, code="PS04.001", name="Sparky", kind="line", method="CLAIM"))
    sid = db.insert(con, "subcontract", dict(project_id=pid, name="Sparky LS", node_id=nid, contract_value=100000, retention_pct=0.1, retention_release_month="2026-12"))
    a = db.insert(con, "sub_milestone", dict(subcontract_id=sid, seq=1, name="Install", type="Progress", value=80000, start_month="2026-09", end_month="2026-12"))
    b = db.insert(con, "sub_milestone", dict(subcontract_id=sid, seq=2, name="Test", type="Milestone", value=20000, start_month="2026-12"))
    cid = sc.create_claim(con, sid, "2026-09", "C1")      # claims the September schedule: 20,000 of Install
    sc.approve_all(con, cid)
    con.commit()
    s = db.one(con, "SELECT * FROM subcontract WHERE id=?", (sid,))
    assert sc.seed_forecast(con, s, "2026-09") > 0
    # the PM expects Install to finish in Oct and Nov only, and testing in January
    con.execute("DELETE FROM sub_forecast WHERE subcontract_id=?", (sid,))
    sc.save_forecast(con, s, {a: {"2026-10": 30000, "2026-11": 30000}, b: {"2027-01": 20000}})
    con.commit()
    engine._cache.clear()
    res = engine.compute(con, pid)
    r = next(x for x in res["rows"] if x["id"] == nid)
    f = {m: round(v) for m, v in zip(res["grid"], r["f"]) if v}
    assert f == {"2026-10": 27000, "2026-11": 27000, "2026-12": 10000, "2027-01": 18000}   # net 90%, retention 10% x 100k back in Dec
    sh = sc.sheet(con, sid, "2026-09")
    inst = next(x for x in sh["rows"] if x["name"] == "Install")
    assert (inst["claimed"], inst["forecast_total"], inst["unforecast"]) == (20000, 60000, 0)
    sc.shift_forecast(con, s, "2026-09", 1)   # the subcontractor runs a month late
    con.commit()
    assert sc.forecasts(con, sid)[a] == {"2026-11": 30000, "2026-12": 30000}


def test_unclaimed_remainder_is_never_lost(blank):
    """The schedule has 10k in Sep and 10k in Oct; September is claimed for 6k. The 14k left must all be forecast,
    in October (not split into a September that already has its claim)."""
    from app import subcontracts as sc
    con = blank
    pid = db.insert(con, "project", dict(name="J", status_date="2026-09-30"))
    sid = db.insert(con, "subcontract", dict(project_id=pid, name="S", contract_value=20000, retention_pct=0))
    a = db.insert(con, "sub_milestone", dict(subcontract_id=sid, seq=1, name="Work", type="Progress", value=20000, start_month="2026-09", end_month="2026-10"))
    cid = db.insert(con, "sub_claim", dict(subcontract_id=sid, claim_no="C1", month="2026-09", status="received"))
    db.insert(con, "sub_claim_line", dict(claim_id=cid, item_id=a, claimed=6000, approved=6000))
    s = db.one(con, "SELECT * FROM subcontract WHERE id=?", (sid,))
    assert sc.gross_forecast(con, s, "2026-09")[a] == {"2026-10": pytest.approx(14000)}
    assert sc.sheet(con, sid, "2026-09")["rows"][0]["unforecast"] == pytest.approx(0)


def test_cost_to_date_never_includes_forecast(demo):
    """Vincent 20/10: "Cost incurred to date" counted the status month's forecast; incurred and forecast are now apart."""
    from app import engine, reports
    con, pid = demo
    res = engine.compute(con, pid)
    w = reports.flows(con, pid, res=res)["work"]
    assert w["cost_to_date"] == pytest.approx(res["total"]["ctd"] + res["total"]["acc"], abs=1)
    assert [round(a + b, 2) for a, b in zip(w["cost_incurred"], w["cost_forecast"])] == pytest.approx(w["cost"], abs=0.02)
    assert w["revenue_to_date"] == pytest.approx(sum(w["revenue_actual"]), abs=0.01)
