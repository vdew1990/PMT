import io
import pytest

from app import accruals, db, engine, programme, pronto, reports, revenue, services, templates_io, variations


# ---- the engine ------------------------------------------------------------------------------
def test_eac_includes_accruals_and_cmt_style_excludes_them(demo):
    con, pid = demo
    t = engine.compute(con, pid)["total"]
    assert t["acc"] > 0
    assert t["eac"] == pytest.approx(t["ctd"] + t["acc"] + t["ctc"])
    assert t["eac_cmt_style"] == pytest.approx(t["ctd"] + t["ctc"])


def test_month_grid_ties_to_eac(demo):
    con, pid = demo
    t = engine.compute(con, pid)["total"]
    assert sum(t["a"]) + sum(t["x"]) + sum(t["f"]) == pytest.approx(t["eac"], abs=0.01)


def test_ctd_ties_to_pronto_ctd_overview(demo):
    con, pid = demo
    ids = {h["id"] for h in reports.health(con, pid) if h["level"] == "ok"}
    assert "ctd_tie_ok" in ids
    assert not [h for h in reports.health(con, pid) if h["id"] in ("unplaced", "ctd_tie", "grid_tie")]


def test_parent_totals_equal_sum_of_children(demo):
    con, pid = demo
    res = engine.compute(con, pid)
    rows = res["rows"]
    for g in [r for r in rows if r["kind"] == "group"]:
        kids = [r for r in rows if r["parent_id"] == g["node_id"]]
        assert g["eac"] == pytest.approx(sum(k["eac"] for k in kids), abs=0.01)
        assert g["allowance"] == pytest.approx(sum(k["allowance"] for k in kids), abs=0.01)


def test_unposted_timesheets_become_accruals(demo):
    con, pid = demo
    ts = db.scalar(con, "SELECT SUM(total_cost) FROM pronto_labour WHERE project_id=? AND posted=0", (pid,))
    assert ts > 0
    assert engine.compute(con, pid)["total"]["acc"] >= ts


def test_accrual_reverses_when_invoice_lands(demo):
    con, pid = demo
    a = db.one(con, "SELECT * FROM accrual WHERE project_id=? AND inv_ref='INV-7781'", (pid,))
    assert a["status"] == "matched"
    assert a["matched_amount"] == pytest.approx(118500.0)


def test_accrual_amount_mismatch_flags_investigate(demo):
    con, pid = demo
    a = db.one(con, "SELECT * FROM accrual WHERE project_id=? AND inv_ref='INV-7781'", (pid,))
    con.execute("UPDATE accrual SET amount=100000 WHERE id=?", (a["id"],))
    accruals.match(con, pid)
    assert db.one(con, "SELECT status FROM accrual WHERE id=?", (a["id"],))["status"] == "investigate"
    con.execute("UPDATE accrual SET amount=118500 WHERE id=?", (a["id"],))
    accruals.match(con, pid)


def test_unallocated_actuals_surface_as_suggestions(demo):
    con, pid = demo
    sug = pronto.suggestions(con, pid)
    codes = {s["resource_code"] for s in sug}
    assert "S30CARD01" in codes and "S30MSC01" in codes


def test_creating_a_line_moves_actuals_off_the_pot(demo):
    con, pid = demo
    parent = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND category='PM06'", (pid,))
    before = [r for r in engine.compute(con, pid)["rows"] if r["kind"] == "line" and r.get("origin") == "wip" and r["parent_id"] == parent["id"]][0]  # unmatched cost sits on WIP
    services.add_node(con, pid, parent["id"], "Site Supplies", resource_kind="supplier", resource_code="S30MSC01", resource_name="SITE SUPPLIES PTY LTD")
    pronto.resolve_all(con, pid)
    res = engine.compute(con, pid)
    pots = [r for r in res["rows"] if r["kind"] == "pot" and r["node_id"] == parent["id"]]  # an empty pot is not shown
    pot = pots[0] if pots else {"ctd": 0}
    line = [r for r in res["rows"] if r["kind"] == "line" and r["resource_code"] == "S30MSC01"][0]
    assert before["ctd"] > 1 and pot["ctd"] == pytest.approx(0) and line["ctd"] == pytest.approx(before["ctd"])


# ---- allowance ledger -------------------------------------------------------------------------
def test_estimate_locked_after_initialise(demo):
    con, pid = demo
    n = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND category='PL01'", (pid,))
    with pytest.raises(services.Problem):
        services.set_estimate(con, pid, n["id"], 1)


def test_transfer_keeps_total_allowance(demo):
    con, pid = demo
    a, b = [r["id"] for r in db.rows(con, "SELECT id FROM cbs_node WHERE project_id=? AND kind='line' LIMIT 2", (pid,))]
    t0 = engine.compute(con, pid)["total"]["allowance"]
    services.transfer(con, pid, a, b, 1000, 70)
    assert engine.compute(con, pid)["total"]["allowance"] == pytest.approx(t0)
    pair = db.one(con, "SELECT pair_id FROM allowance_ledger WHERE kind='transfer' ORDER BY id DESC")["pair_id"]
    con.execute("DELETE FROM allowance_ledger WHERE pair_id=?", (pair,))


def test_line_cannot_have_children(demo):
    con, pid = demo
    line = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND kind='line' LIMIT 1", (pid,))
    with pytest.raises(services.Problem):
        services.add_node(con, pid, line["id"], "child")


def test_standard_cbs_cannot_be_deleted(demo):
    con, pid = demo
    n = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND code='PL01'", (pid,))
    with pytest.raises(services.Problem):
        services.delete_node(con, pid, n["id"])


def test_node_with_actuals_cannot_be_deleted(demo):
    con, pid = demo
    n = db.one(con, "SELECT node_id id FROM pronto_tx WHERE project_id=? AND node_id IN (SELECT id FROM cbs_node WHERE kind='line') LIMIT 1", (pid,))
    with pytest.raises(services.Problem):
        services.delete_node(con, pid, n["id"])


# ---- forecast methods on a hand-built project -----------------------------------------------
def _mini(con, allowance=120000, spend_months=4):
    pid = services.create_project(con, dict(name="Mini", status_date="2026-05-31", project_start="2026-01-01", project_end="2026-08-31",
                                            grid_start="2026-01-01", grid_end="2026-09-30", default_risk_pct=0))
    parent = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND category='PS04'", (pid,))["id"]
    n = services.add_node(con, pid, parent, "Sub A", resource_kind="supplier", resource_code="S30AAA01", resource_name="Sub A", budget=allowance, risk=0,
                          start_date="2026-01-01", end_date="2026-08-31")
    services.initialise(con, pid, force=True)
    for i in range(spend_months):
        m = f"2026-0{i + 1}"
        db.insert(con, "pronto_tx", dict(project_id=pid, category="PS04", account_code="S30AAA01", doc_type="PO", doc_no="1", tx_date=m + "-15", cost=10000,
                                         **{"class": "actual"}, resource_code="S30AAA01", month=m, node_id=n))
    db.bump(con, pid)
    return pid, n


def _row(con, pid, n):
    return [r for r in engine.compute(con, pid)["rows"] if r["id"] == n][0]


@pytest.mark.parametrize("method,expect", [("AT-BUDGET", 80000), ("BURN-RATE", 10000 * 4)])
def test_methods(blank, method, expect):
    pid, n = _mini(blank)
    blank.execute("UPDATE cbs_node SET method=? WHERE id=?", (method, n))
    db.bump(blank, pid)
    r = _row(blank, pid, n)
    assert r["ctd"] == 40000
    # status month May: 4 months remaining including May? remaining = May..Aug = 4
    assert r["ctc"] == pytest.approx(expect)
    assert r["eac"] == pytest.approx(r["ctd"] + r["acc"] + r["ctc"])


def test_top_down_and_manual(blank):
    pid, n = _mini(blank)
    blank.execute("UPDATE cbs_node SET method='TOP-DOWN', eac_override=150000 WHERE id=?", (n,))
    db.bump(blank, pid)
    assert _row(blank, pid, n)["eac"] == pytest.approx(150000)
    blank.execute("UPDATE cbs_node SET method='MANUAL' WHERE id=?", (n,))
    for m, a in (("2026-06", 5000), ("2026-07", 7000), ("2026-03", 99999)):  # March is past, ignored
        db.insert(blank, "forecast_manual", dict(project_id=pid, node_id=n, item_id=None, month=m, amount=a))
    db.bump(blank, pid)
    assert _row(blank, pid, n)["ctc"] == pytest.approx(12000)


def test_ground_up_items(blank):
    pid, n = _mini(blank)
    blank.execute("UPDATE cbs_node SET method='GROUND-UP' WHERE id=?", (n,))
    db.insert(blank, "forecast_item", dict(project_id=pid, node_id=n, spread="Lump", qty=1, rate=9000, start_date="2026-07-10"))
    db.insert(blank, "forecast_item", dict(project_id=pid, node_id=n, spread="Linear", qty=1, rate=6000, start_date="2026-06-01", end_date="2026-07-31"))
    db.insert(blank, "forecast_item", dict(project_id=pid, node_id=n, spread="Recurring", qty=2, rate=100, freq="Monthly", start_date="2026-06-05", occurrences=3))
    db.bump(blank, pid)
    assert _row(blank, pid, n)["ctc"] == pytest.approx(9000 + 6000 + 600)


def test_at_commit_uses_open_po_and_flags_short_ctc(blank):
    pid, n = _mini(blank)
    db.insert(blank, "pronto_po", dict(project_id=pid, order_no="1", status="On Order", committed=50000, received=10000, is_open=1, node_id=n, category="PS04"))
    blank.execute("UPDATE cbs_node SET method='TOP-DOWN', eac_override=45000 WHERE id=?", (n,))
    db.bump(blank, pid)
    r = _row(blank, pid, n)
    assert r["outstanding"] == 40000 and r["po_status"] == "SHORT"
    blank.execute("UPDATE cbs_node SET method='AT-COMMIT' WHERE id=?", (n,))
    db.bump(blank, pid)
    assert _row(blank, pid, n)["ctc"] == pytest.approx(40000)


def test_closed_po_commits_only_what_was_received(blank):
    pid, n = _mini(blank)
    db.insert(blank, "pronto_po", dict(project_id=pid, order_no="9", status="Completed", committed=90000, received=30000, is_open=0, node_id=n, category="PS04"))
    db.bump(blank, pid)
    r = _row(blank, pid, n)
    assert r["po_committed"] == 30000 and r["outstanding"] == 0


def test_group_dates_are_inherited_by_lines(blank):
    pid, n = _mini(blank)
    parent = db.one(blank, "SELECT parent_id p FROM cbs_node WHERE id=?", (n,))["p"]
    blank.execute("UPDATE cbs_node SET method='AT-BUDGET', start_date=NULL, end_date=NULL WHERE id=?", (n,))
    blank.execute("UPDATE cbs_node SET start_date='2026-05-01', end_date='2026-06-30' WHERE id=?", (parent,))
    db.bump(blank, pid)
    r = _row(blank, pid, n)
    assert [round(v) for v in r["f"] if v] == [40000, 40000]  # 80k left over May and June only
    blank.execute("UPDATE cbs_node SET end_date='2026-07-31' WHERE id=?", (n,))  # own date wins
    db.bump(blank, pid)
    assert len([v for v in _row(blank, pid, n)["f"] if v]) == 3


# ---- Pronto import ----------------------------------------------------------------------------
def test_reimport_replace_does_not_double_count(demo):
    con, pid = demo
    from demo import build_demo
    exp = build_demo.DEMO / "demo_pronto_export.xlsx"
    before = engine.compute(con, pid)["total"]["ctd"]
    it = [s for s in pronto.analyse(exp) if s["kind"] == "transactions"][0]
    pronto.import_sheet(con, pid, exp, exp.name, it["sheet"], it["kind"], it["header_row"], "replace", build_demo.PRONTO_PROJECT)
    pronto.import_sheet(con, pid, exp, exp.name, it["sheet"], it["kind"], it["header_row"], "merge", build_demo.PRONTO_PROJECT)
    assert engine.compute(con, pid)["total"]["ctd"] == pytest.approx(before)


def test_analyse_recognises_every_demo_report(demo):
    from demo import build_demo
    kinds = {s["kind"] for s in pronto.analyse(build_demo.DEMO / "demo_pronto_export.xlsx")}
    assert kinds == {"transactions", "labour", "po", "claims", "variations", "ctd"}


def test_missing_categories_are_offered_and_added(blank):
    pid = services.create_project(blank, dict(name="C"))
    db.insert(blank, "pronto_tx", dict(project_id=pid, category="PL10", cat_desc="Harmonic Filter", doc_type="TS", tx_date="2026-01-05", cost=100,
                                       **{"class": "actual"}, month="2026-01"))
    miss = pronto.missing_categories(blank, pid)
    assert miss and miss[0]["code"] == "PL10" and miss[0]["name"] == "Harmonic Filter"
    services.add_category(blank, pid, "PL10", "Harmonic Filter")
    pronto.resolve_all(blank, pid)
    assert not pronto.missing_categories(blank, pid)
    assert db.scalar(blank, "SELECT COUNT(*) FROM pronto_tx WHERE project_id=? AND node_id IS NOT NULL", (pid,)) == 1


# ---- variations and revenue -------------------------------------------------------------------
def test_variation_recognition_flows_to_revenue_and_allowance(demo):
    con, pid = demo
    v = db.one(con, "SELECT id FROM variation WHERE project_id=? AND ref='EPC-VAR-002'", (pid,))["id"]
    rev0, alw0 = revenue.summary(con, pid)["recognised"], engine.compute(con, pid)["total"]["allowance"]
    node = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND category='PL03'", (pid,))["id"]
    db.insert(con, "variation_line", dict(variation_id=v, node_id=node, description="Eng", qty=100, rate=100, risk_pct=0.1, markup_pct=0.2))
    con.execute("UPDATE variation SET client_status='Approved', epec_status='Agreed' WHERE id=?", (v,))
    variations.sync(con, pid, v)
    assert revenue.summary(con, pid)["recognised"] == pytest.approx(rev0 + 62000)
    t = engine.compute(con, pid)["total"]
    assert t["allowance"] == pytest.approx(alw0 + 10000)       # the PM sees the 10,000 cost; the 1,000 risk is held by the company
    assert t["risk"] > 0
    con.execute("UPDATE variation SET client_status='Denied' WHERE id=?", (v,))
    variations.sync(con, pid, v)
    assert revenue.summary(con, pid)["recognised"] == pytest.approx(rev0)
    assert engine.compute(con, pid)["total"]["allowance"] == pytest.approx(alw0)


def test_variation_line_calculation():
    c = variations.line_calc(dict(item_count=2, hrs_day=8, days_wk=5, wks=2, rate=100, risk_pct=0.1, markup_pct=0.2))
    # as the workbook's Variation Engine: risk and markup are both a % of cost
    assert c["qty"] == 160 and c["cost"] == 16000 and c["risk"] == 1600 and c["profit"] == pytest.approx(3200) and c["price"] == pytest.approx(20800)


def test_official_requires_executed_deed_when_contract_change_needed(demo):
    con, pid = demo
    v = variations.get(con, pid, db.one(con, "SELECT id FROM variation WHERE project_id=? AND ref='EPC-VAR-001'", (pid,))["id"])
    assert v["recognised"] and v["official"]
    con.execute("UPDATE variation SET contract_change='Yes', contract_status='In progress' WHERE id=?", (v["id"],))
    v2 = variations.get(con, pid, v["id"])
    assert v2["recognised"] and not v2["official"]
    con.execute("UPDATE variation SET contract_change='No', contract_status='n/a' WHERE id=?", (v["id"],))


def test_claim_suggestions_never_exceed_contract(demo):
    con, pid = demo
    cid = db.insert(con, "claim", dict(project_id=pid, claim_no="TEST", period="2026-11", status="draft"))
    for l in revenue.claim_detail(con, pid, cid)["lines"]:
        assert l["prior"] + l["suggested"] <= l["value"] + 0.05


# ---- templates, clone, wipe -------------------------------------------------------------------
def test_template_roundtrip_reproduces_allowances(demo, blank):
    con, pid = demo
    data = templates_io.build_template(con, pid)
    new = services.create_project(blank, dict(name="Copy"))
    rep = templates_io.import_template(blank, new, io.BytesIO(data))
    assert not rep["errors"]
    a = engine.compute(con, pid)["total"]
    b = engine.compute(blank, new)["total"]
    assert b["orig_budget"] == pytest.approx(a["orig_budget"])
    assert db.scalar(blank, "SELECT COUNT(*) FROM contract_item WHERE project_id=?", (new,)) >= 9


def test_clone_structure_copies_no_data(demo, blank):
    con, pid = demo
    # copy by exporting then cloning within one database: use blank db with the template instead
    data = templates_io.build_template(con, pid)
    src = services.create_project(blank, dict(name="Src"))
    templates_io.import_template(blank, src, io.BytesIO(data))
    db.insert(blank, "pronto_tx", dict(project_id=src, category="PL01", doc_type="TS", tx_date="2026-01-01", cost=5, **{"class": "actual"}, month="2026-01"))
    dst = services.create_project(blank, dict(name="Dst"), from_template=src, include=dict(lines=True, allowances=True, rate_card=True))
    assert db.scalar(blank, "SELECT COUNT(*) FROM pronto_tx WHERE project_id=?", (dst,)) == 0
    assert db.scalar(blank, "SELECT COUNT(*) FROM cbs_node WHERE project_id=? AND kind='line'", (dst,)) == db.scalar(blank, "SELECT COUNT(*) FROM cbs_node WHERE project_id=? AND kind='line'", (src,))
    assert engine.compute(blank, dst)["total"]["orig_budget"] == pytest.approx(engine.compute(blank, src)["total"]["orig_budget"])
    assert db.scalar(blank, "SELECT initialised FROM project WHERE id=?", (dst,)) == 0


def test_clone_copies_supplier_rates_and_holidays_with_the_rate_card(blank):
    """F3: cloning with the rate card also copies the supplier rates (on the copied supplier) and the public holidays."""
    src = services.create_project(blank, dict(name="Src"))
    sup = db.insert(blank, "resource", dict(project_id=src, kind="supplier", code="S30X", name="Sparkies Pty Ltd"))
    db.insert(blank, "supplier_rate", dict(project_id=src, resource_id=sup, role="Electrician", unit="hr", rate=95, ot_rate=140, nt_hours=8, allowance=60))
    db.insert(blank, "holiday", dict(project_id=src, day="2026-12-25", name="Christmas Day"))
    db.insert(blank, "holiday", dict(project_id=src, day="2027-01-26", name="Australia Day"))
    dst = services.create_project(blank, dict(name="Dst"), from_template=src, include=dict(resources=True, rate_card=True))
    rate = db.one(blank, "SELECT r.role, r.unit, r.rate, r.ot_rate, r.nt_hours, r.allowance, s.code, s.project_id FROM supplier_rate r "
                         "JOIN resource s ON s.id=r.resource_id WHERE r.project_id=?", (dst,))
    assert rate == dict(role="Electrician", unit="hr", rate=95, ot_rate=140, nt_hours=8, allowance=60, code="S30X", project_id=dst)
    assert [(h["day"], h["name"]) for h in db.rows(blank, "SELECT day, name FROM holiday WHERE project_id=? ORDER BY day", (dst,))] == \
        [("2026-12-25", "Christmas Day"), ("2027-01-26", "Australia Day")]
    bare = services.create_project(blank, dict(name="Bare"), from_template=src, include=dict(resources=True))
    assert db.scalar(blank, "SELECT COUNT(*) FROM supplier_rate WHERE project_id=?", (bare,)) == 0
    assert db.scalar(blank, "SELECT COUNT(*) FROM holiday WHERE project_id=?", (bare,)) == 0


def test_wipe_keeps_identity_and_standard_cbs(blank):
    pid = services.create_project(blank, dict(name="W", code="W1"))
    parent = db.one(blank, "SELECT id FROM cbs_node WHERE project_id=? AND category='PS04'", (pid,))["id"]
    services.add_node(blank, pid, parent, "X", resource_kind="supplier", resource_code="S30X", budget=100)
    db.insert(blank, "pronto_tx", dict(project_id=pid, category="PS04", doc_type="PO", tx_date="2026-01-01", cost=5, **{"class": "actual"}, month="2026-01"))
    services.wipe_project(blank, pid, ["pronto", "allowances", "structure"])
    assert db.scalar(blank, "SELECT COUNT(*) FROM pronto_tx WHERE project_id=?", (pid,)) == 0
    assert db.scalar(blank, "SELECT COUNT(*) FROM cbs_node WHERE project_id=? AND origin!='standard'", (pid,)) == 0
    assert db.scalar(blank, "SELECT COUNT(*) FROM cbs_node WHERE project_id=?", (pid,)) == 4 + 32
    assert db.one(blank, "SELECT code FROM project WHERE id=?", (pid,))["code"] == "W1"


def test_initialise_needs_allowances_and_dates(blank):
    pid = services.create_project(blank, dict(name="I"))
    with pytest.raises(services.Problem):
        services.initialise(blank, pid)


# ---- programme ---------------------------------------------------------------------------------
def test_programme_parsers_read_xml_and_pdf(tmp_path):
    from demo import build_demo
    import subprocess, sys
    build_demo.write_programme_files()
    src, tasks = programme.parse(build_demo.DEMO / "demo_programme.xml", "p.xml")
    assert src == "xml" and len(tasks) == 13 and tasks[3]["name"] == "IFC design"
    if (build_demo.DEMO / "demo_programme.pdf").exists():
        src, t2 = programme.parse(build_demo.DEMO / "demo_programme.pdf", "p.pdf")
        assert src == "pdf" and {t["name"] for t in t2} >= {"IFC design", "Energisation"}
        assert [t for t in t2 if t["name"] == "Energisation"][0]["milestone"] == 1


def test_mpp_is_refused_with_instructions():
    with pytest.raises(ValueError, match="XML"):
        programme.parse("x.mpp", "x.mpp")


def test_programme_dates_drive_claims_and_costs(blank):
    pid, n = _mini(blank)
    sov = db.insert(blank, "contract_item", dict(project_id=pid, ref="1", description="Subcontractor works", value=120000, stage="EPC"))
    db.insert(blank, "programme_task", dict(project_id=pid, seq=0, name="Subcontractor works", start_date="2026-06-01", finish_date="2026-07-31"))
    assert programme.suggest(blank, pid) >= 1
    programme.apply(blank, pid)
    it = db.one(blank, "SELECT * FROM contract_item WHERE id=?", (sov,))
    assert it["start_date"] == "2026-06-01" and it["method"] == "even"
    plan = [i for i in revenue.items_tree(blank, pid) if i["id"] == sov][0]["plan"]
    assert plan == {"2026-06": 60000.0, "2026-07": 60000.0}
    # a task linked to the line sets its window; only_empty leaves it alone afterwards
    t = db.one(blank, "SELECT id FROM programme_task WHERE project_id=?", (pid,))["id"]
    db.update(blank, "programme_task", t, dict(link_node_id=n))
    programme.apply(blank, pid, ("costs",))
    assert db.one(blank, "SELECT start_date s FROM cbs_node WHERE id=?", (n,))["s"] == "2026-06-01"
    db.update(blank, "programme_task", t, dict(start_date="2026-02-01"))
    programme.apply(blank, pid, ("costs",), only_empty=True)
    assert db.one(blank, "SELECT start_date s FROM cbs_node WHERE id=?", (n,))["s"] == "2026-06-01"


def test_uploaded_excel_is_released_after_reading(tmp_path):
    """Windows cannot delete a workbook that is still open, so every reader must close it."""
    import openpyxl
    from app import pronto
    p = tmp_path / "t.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Resource Code", "Description", "Work Rate Code", "Date Worked", "Hours Worked", "Total Cost", "Cost Category"])
    ws.append(["AAA01", "A Person", "PJ01", "2026-01-05", 7.6, 456, "PL02"])
    wb.save(p)
    closed = []
    orig = openpyxl.workbook.workbook.Workbook.close
    openpyxl.workbook.workbook.Workbook.close = lambda self: (closed.append(1), orig(self))[1]
    try:
        pronto.analyse(p)
        n = len(closed)
        assert n >= 1
        pronto.read_rows(p, "Sheet", "labour", 0)
        assert len(closed) > n
    finally:
        openpyxl.workbook.workbook.Workbook.close = orig


def test_programme_sheet_carries_actual_dates_through_the_template(tmp_path, blank):
    import io
    import openpyxl
    from app import templates_io
    con = blank
    pid = db.insert(con, "project", dict(name="P", status_date="2026-03-31"))
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Programme"
    ws.append(["Phase", "Milestone / activity", "Type", "Baseline start", "Baseline end", "Forecast start", "Forecast end", "PMR row", "Actual date"])
    ws.append(["Key dates", "Civil completed", "Milestone", None, None, "2026-02-01", "2026-02-01", None, "2026-02-03"])
    ws.append(["Design", "Design", "Phase", None, None, "2025-01-01", "2025-12-31", None, None])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    rep = templates_io.import_template(con, pid, buf)
    assert rep["created"]["milestones"] == 2
    m = db.rows(con, "SELECT name, type, forecast_end, actual_date FROM milestone WHERE project_id=? ORDER BY sort_order", (pid,))
    assert (m[0]["actual_date"], m[0]["type"]) == ("2026-02-03", "Milestone") and m[1]["actual_date"] is None


def test_delete_project_needs_its_name_and_removes_it(demo):
    """Vincent 21/10: pick the project from a list, then OK; the API still refuses without the project's name."""
    from fastapi.testclient import TestClient
    from app.main import app
    con, pid = demo
    c = TestClient(app)
    other = c.post("/api/projects", json={"name": "Throwaway project"}).json()
    oid = other.get("id") or other.get("project", {}).get("id")
    before = {p["id"] for p in c.get("/api/projects").json()}
    assert c.delete(f"/api/projects/{oid}?confirm=wrong").status_code >= 400
    assert c.delete(f"/api/projects/{oid}?confirm=Throwaway%20project").json()["ok"]
    assert {p["id"] for p in c.get("/api/projects").json()} == before - {oid}
