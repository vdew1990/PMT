"""Variation engine: price items built from cost lines (the workbook's formulas), spreads, options, client detail and
funding an approved variation (top up the CBS, or track it on its own copy of the CBS)."""
import pytest

from app import db, pronto, variations

L = lambda **k: dict(dict(price_id=1, risk_pct=0.07, markup_pct=0.16, unit="hour"), **k)


def test_lines_and_items_follow_the_workbook():
    # EPC-VAR-002 Rev 2, "Labour / Design": Design Manager 32 h x 275, Drafter 64 h x 175, Designers 128 h x 175
    items = [dict(id=1, section="Labour", name="Design")]
    lines = [L(description="Design Manager", qty=32, rate=275), L(description="Drafter", qty=64, rate=175), L(description="Designers", qty=128, rate=175)]
    b = variations.build({}, items, lines)
    assert b["items"][0]["lines"][0]["price"] == pytest.approx(10824)
    assert b["items"][0]["price"] == pytest.approx(52152) and b["total"]["cost"] == pytest.approx(42400) and b["total"]["risk"] == pytest.approx(2968)
    # time build-up: count x (hrs x days x weeks + extra)
    assert variations.line_calc(dict(item_count=2, hrs_day=11, days_wk=4, wks=1, rate=1))["qty"] == 88
    assert variations.line_calc(dict(item_count=3, hrs_day=10, days_wk=5, wks=1, extra_qty=2, rate=1))["qty"] == 156
    # a contract (sell) rate overrides the price: EPC-VAR-007 accommodation
    c = variations.line_calc(dict(qty=1, rate=2500, contract_rate=1537.5, risk_pct=0.07, markup_pct=0.16))
    assert c["cost"] == 2500 and c["price"] == 1537.5


def _three():
    items = [dict(id=1, section="Labour", name="Design"), dict(id=2, section="Labour", name="Supervision"),
             dict(id=3, section="Materials", name="Cable"), dict(id=4, section="Overheads", name="Site overheads", spread="uniform")]
    lines = [dict(price_id=1, qty=1, rate=1000), dict(price_id=2, qty=1, rate=3000), dict(price_id=3, qty=1, rate=6000), dict(price_id=4, qty=1, rate=900, node_id=99)]
    return items, lines


def test_uniform_and_proportional_spread_keep_the_total():
    items, lines = _three()
    b = variations.build({}, items, lines)
    p = {i["name"]: i["price"] for i in b["items"]}
    assert p == {"Design": 1300, "Supervision": 3300, "Cable": 6300, "Site overheads": 0}  # 900 / 3 each, overheads hidden
    assert b["total"]["price"] == 10900 and b["total"]["base"] == 10900
    items[3]["spread"] = "proportional"
    p = {i["name"]: i["price"] for i in variations.build({}, items, lines)["items"]}
    assert p["Design"] == pytest.approx(1090) and p["Cable"] == pytest.approx(6540)
    # cost and risk of the spread item stay on its own CBS
    assert next(d for d in variations.build({}, items, lines)["by_node"] if d["node_id"] == 99)["cost"] == 900


def test_carriers_scope_and_options():
    items, lines = _three()
    items[2]["carries"] = 0                      # cable does not carry the spread
    p = {i["name"]: i["price"] for i in variations.build({}, items, lines)["items"]}
    assert p["Cable"] == 6000 and p["Design"] == 1450 and p["Supervision"] == 3450
    items[2]["carries"] = 1
    items[3].update(section="Labour", spread_scope="section")  # only over items in its own section
    p = {i["name"]: i["price"] for i in variations.build({}, items, lines)["items"]}
    assert p["Cable"] == 6000 and p["Design"] == 1450
    items[2].update(optional=1, selected="Pending")   # an option not (yet) selected is not in the value
    b = variations.build({}, items, lines)
    assert b["total"]["optional"] == 6000 and b["total"]["price"] == 4900
    items[2]["selected"] = "Yes"
    assert variations.build({}, items, lines)["total"]["price"] == 10900


@pytest.fixture()
def job(blank):
    con = blank
    pid = db.insert(con, "project", dict(name="Var job", status_date="2026-10-01", project_start="2025-01-01", project_end="2027-06-30"))
    top = db.insert(con, "cbs_node", dict(project_id=pid, code="PS", name="Project Subcontractors", kind="group", gp="PS"))
    g = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=top, code="PS04", name="Construction Subcontractors", kind="group", gp="PS", category="PS04"))
    rid = db.insert(con, "resource", dict(project_id=pid, kind="supplier", code="S30ELE01", name="SPARKY"))
    line = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=g, code="PS04.001", name="Sparky", kind="line", gp="PS", resource_id=rid))
    vid = db.insert(con, "variation", dict(project_id=pid, ref="EPC-VAR-003", title="Harmonic filters", client_status="Approved", epec_status="Agreed", pronto_ref="VAR3"))
    db.insert(con, "variation_rev", dict(variation_id=vid, rev=0, value=13000, is_current=1))
    it = db.insert(con, "variation_price", dict(variation_id=vid, seq=1, section="Subcontractors", name="Install filters"))
    db.insert(con, "variation_line", dict(variation_id=vid, price_id=it, node_id=line, description="Electricians", qty=1, rate=10000, risk_pct=0.1, markup_pct=0.2))
    con.commit()
    return con, pid, vid, g, line


def test_top_up_or_track_the_variation_on_its_own_cbs(job):
    con, pid, vid, g, line = job
    variations.sync(con, pid, vid)
    led = lambda n: db.one(con, "SELECT COALESCE(SUM(budget),0) b, COALESCE(SUM(risk),0) r FROM allowance_ledger WHERE node_id=? AND kind='variation'", (n,))
    assert led(line)["b"] == 10000 and led(line)["r"] == 1000            # top up the original line
    made = variations.duplicate_cbs(con, pid, vid, [g])                  # track it separately: copy PS04 and below
    copy_line = made[line]
    assert db.one(con, "SELECT variation_id, copied_from, name FROM cbs_node WHERE id=?", (copy_line,))["copied_from"] == line
    codes = {r["code"] for r in db.rows(con, "SELECT code FROM cbs_node WHERE variation_id=?", (vid,))}
    assert codes == {"PS04-V003", "PS04-V003.001"}  # the copy's codes mirror the originals
    assert led(line)["b"] == 0 and led(copy_line)["b"] == 10000          # the new funds sit on the copy
    # Pronto: cost coded to the variation lands on the copy; other cost stays on the original
    for vno, cost in (("VAR3", 4000), (None, 2500)):
        db.insert(con, "pronto_tx", dict(project_id=pid, category="PS04", resource_code="S30ELE01", cost=cost, variation_no=vno, month="2026-09", tx_date="2026-09-15"))
    con.execute("UPDATE pronto_tx SET class='actual'")
    pronto.resolve_all(con, pid)
    on = lambda n: db.scalar(con, "SELECT COALESCE(SUM(cost),0) FROM pronto_tx WHERE node_id=?", (n,))
    assert on(copy_line) == 4000 and on(line) == 2500
    plan = variations.funding_plan(con, pid, vid)
    assert plan["funding"] == "separate" and plan["rows"][0]["copied"]


def test_cost_control_shows_base_and_variation_scope_together(job):
    from app import engine
    con, pid, vid, g, line = job
    made = variations.duplicate_cbs(con, pid, vid, [g])
    con.commit()
    rows = engine.compute(con, pid)["rows"]
    tot = next(r for r in rows if r["code"] == "PS")["eac"]
    merged = engine.merge_variation_copies(con, pid, [dict(r) for r in rows])
    codes = {r["code"] for r in merged}
    assert "PS04-V003" not in codes and "PS04-V003.001" not in codes          # the copies are folded into their originals
    m = next(r for r in merged if r["id"] == line)
    assert [x["part"] for x in m["parts"]] == ["base", "variation"]
    assert m["parts"][1]["variation_ref"] == "EPC-VAR-003" and m["parts"][1]["allowance"] == pytest.approx(10000)  # current allowance: the cost (its risk is in the company bucket)
    assert m["allowance"] == pytest.approx(m["parts"][0]["allowance"] + 10000)
    assert next(r for r in merged if r["code"] == "PS")["eac"] == pytest.approx(tot)  # parents unchanged


def test_budget_build_up_original_plus_each_variation(job):
    from app import engine, services
    con, pid, vid, g, line = job
    services.set_estimate(con, pid, line, 50000, 0)
    variations.sync(con, pid, vid)                                   # EPC-VAR-003 tops the line up: +10,000 (+1,000 risk)
    v2 = db.insert(con, "variation", dict(project_id=pid, ref="EPC-VAR-004", title="Extra cabling", client_status="Approved", epec_status="Agreed"))
    db.insert(con, "variation_rev", dict(variation_id=v2, rev=0, value=3000, is_current=1))
    it = db.insert(con, "variation_price", dict(variation_id=v2, seq=1, name="Cabling"))
    db.insert(con, "variation_line", dict(variation_id=v2, price_id=it, node_id=line, qty=1, rate=2500))
    variations.duplicate_cbs(con, pid, v2, [line])                    # EPC-VAR-004 tracked on its own copy of the line
    con.commit()
    b = engine.budget_buildup(con, pid, line)
    got = [(r["label"], r["budget"], r.get("tracked")) for r in b["rows"]]
    assert got == [("Original budget", 50000, None), ("EPC-VAR-003 Harmonic filters", 10000, "topped up this line"),
                   ("EPC-VAR-004 Extra cabling", 2500, "tracked on its own CBS copy")]
    assert b["total"]["budget"] == 62500 and b["total"]["risk"] == pytest.approx(1000)


def test_copy_only_the_cbs_lines_the_variation_uses(job):
    con, pid, vid, g, line = job
    other = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=g, code="PS04.002", name="Civils (not used)", kind="line", gp="PS"))
    con.commit()
    made = variations.duplicate_cbs(con, pid, vid, only_used=True)
    assert set(made) == {line} and other not in made                   # no copy of the group or of the unused line
    c = db.one(con, "SELECT code, parent_id FROM cbs_node WHERE id=?", (made[line],))
    assert c["code"] == "PS04.001-V003" and c["parent_id"] == g          # next to the original line
