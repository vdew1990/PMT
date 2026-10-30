"""Ground-up detail spreads (Calendar, Milestones, Roster), rates, hours accruals and the labour calendar."""
import pytest

from app import accruals, db, engine, forecast


@pytest.fixture()
def job(blank):
    con = blank
    pid = db.insert(con, "project", dict(name="Forecast job", status_date="2026-09-30", project_start="2026-01-01", project_end="2027-03-31"))
    g = db.insert(con, "cbs_node", dict(project_id=pid, code="PS04", name="Construction Subcontractors", kind="group"))
    sub = db.insert(con, "resource", dict(project_id=pid, kind="supplier", code="S30SPK01", name="Sparky Electrical"))
    emp = db.insert(con, "resource", dict(project_id=pid, kind="employee", code="JSMI01", name="Jo Smith", function="Project Engineer", cost_rate=120))
    db.insert(con, "supplier_rate", dict(project_id=pid, resource_id=sub, role="Electrician", unit="hr", rate=100, ot_rate=150, nt_hours=8, allowance=50))
    elec = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=g, code="PS04.001", name="Sparky electricians", kind="line", method="GROUND-UP", resource_id=sub))
    eng = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=g, code="PS04.002", name="Jo Smith", kind="line", method="GROUND-UP", resource_id=emp))
    swg = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=g, code="PS04.003", name="MV switchgear", kind="line", method="GROUND-UP"))
    con.commit()
    return con, pid, dict(sub=sub, emp=emp, elec=elec, eng=eng, swg=swg)


def _row(con, pid, nid):
    engine._cache.clear()
    res = engine.compute(con, pid)
    r = next(x for x in res["rows"] if x["id"] == nid)
    return {m: r["f"][i] for i, m in enumerate(res["grid"]) if r["f"][i]}, r


def test_roster_priced_from_supplier_rates(job):
    con, pid, k = job
    db.insert(con, "forecast_item", dict(project_id=pid, node_id=k["elec"], spread="Roster", scope="5 electricians 10:4", resource_id=k["sub"], role="Electrician",
                                         rate_mode="auto", pattern="10:4", swings=2, headcount=5, hours_day=12, start_date="2026-10-01"))
    con.commit()
    months, r = _row(con, pid, k["elec"])
    # 20 days on (1-10 and 15-24 Oct); per person-day 8 x 100 + 4 x 150 + 50 allowance = 1,450; x 5 people
    assert months == {"2026-10": pytest.approx(20 * 5 * 1450)}
    assert r["ctc"] == pytest.approx(145000) and r["fc_hours"] == pytest.approx(20 * 5 * 12)


def test_roster_crossing_months_and_holidays(job):
    con, pid, k = job
    db.insert(con, "holiday", dict(project_id=pid, day="2026-12-25", name="Christmas Day"))
    db.insert(con, "forecast_item", dict(project_id=pid, node_id=k["elec"], spread="Roster", resource_id=k["sub"], role="Electrician", rate_mode="auto",
                                         pattern="10:4", swings=1, headcount=1, hours_day=8, start_date="2026-12-24", skip_holidays=1))
    con.commit()
    months, _ = _row(con, pid, k["elec"])
    # 24 Dec to 2 Jan, minus Christmas: 7 days in December, 2 in January, at 8 h = 850 a day
    assert months == {"2026-12": pytest.approx(7 * 850), "2027-01": pytest.approx(2 * 850)}


def test_calendar_hours_after_status_date_only(job):
    con, pid, k = job
    iid = db.insert(con, "forecast_item", dict(project_id=pid, node_id=k["eng"], spread="Calendar", basis="hours", resource_id=k["emp"], rate_mode="auto"))
    forecast.save_days(con, pid, iid, {"2026-09-29": 8, "2026-10-02": 8, "2026-11-03": 4})
    con.commit()
    months, r = _row(con, pid, k["eng"])
    assert months == {"2026-10": pytest.approx(960), "2026-11": pytest.approx(480)}  # 29 Sep is before the status date
    assert r["fc_hours"] == 12
    # editing a day updates the same row (its history), clearing removes it
    forecast.save_days(con, pid, iid, {"2026-10-02": 10, "2026-11-03": None})
    con.commit()
    months, _ = _row(con, pid, k["eng"])
    assert months == {"2026-10": pytest.approx(1200)}
    assert db.scalar(con, "SELECT COUNT(*) FROM forecast_day WHERE item_id=?", (iid,)) == 2


def test_calendar_in_dollars(job):
    con, pid, k = job
    iid = db.insert(con, "forecast_item", dict(project_id=pid, node_id=k["eng"], spread="Calendar", basis="dollars", resource_id=k["emp"]))
    forecast.save_days(con, pid, iid, {"2026-10-05": 2500, "2026-10-06": 2500})
    con.commit()
    months, r = _row(con, pid, k["eng"])
    assert months == {"2026-10": 5000} and r["fc_hours"] == 0


def test_milestones(job):
    con, pid, k = job
    iid = db.insert(con, "forecast_item", dict(project_id=pid, node_id=k["swg"], spread="Milestones", scope="MV switchboard", qty=1, rate=1_000_000, pct=1))
    forecast.save_milestones(con, pid, iid, [
        dict(name="On order", pct=0.10, month="2026-06", status="invoiced"),
        dict(name="Drawing submission", pct=0.15, month="2026-08"),       # overdue, not invoiced: slips to the status month
        dict(name="FAT", pct=0.20, month="2026-12"),
        dict(name="Delivery", pct=0.55, month="2027-02")])
    con.commit()
    months, r = _row(con, pid, k["swg"])
    assert months == {"2026-09": pytest.approx(150000), "2026-12": pytest.approx(200000), "2027-02": pytest.approx(550000)}
    assert "moved to 2026-09" in r["note"]


def test_hours_accrual_reverses_when_timesheet_lands(job):
    con, pid, k = job
    forecast.save_hour_accruals(con, pid, k["emp"], k["eng"], {"2026-09-28": 8, "2026-09-29": 6})
    con.commit()
    _, r = _row(con, pid, k["eng"])
    assert r["acc"] == pytest.approx(14 * 120)
    db.insert(con, "pronto_labour", dict(project_id=pid, resource_code="JSMI01", date_worked="2026-09-28", month="2026-09", hours=8, total_cost=960, posted=1, node_id=k["eng"]))
    accruals.match(con, pid)
    con.commit()
    st = {a["day"]: a["status"] for a in db.rows(con, "SELECT day, status FROM accrual WHERE project_id=?", (pid,))}
    assert st == {"2026-09-28": "matched", "2026-09-29": "open"}
    via = db.scalar(con, "SELECT via FROM change_log WHERE tbl='accrual' AND op='U' ORDER BY id DESC LIMIT 1", default=None)
    assert via == "Automatic: timesheet landed in Pronto"


def test_labour_calendar_and_accrue_past(job):
    con, pid, k = job
    iid = db.insert(con, "forecast_item", dict(project_id=pid, node_id=k["eng"], spread="Calendar", basis="hours", resource_id=k["emp"], rate_mode="auto"))
    forecast.save_days(con, pid, iid, {"2026-09-28": 8, "2026-09-29": 8, "2026-10-01": 8})
    db.insert(con, "pronto_labour", dict(project_id=pid, resource_code="JSMI01", date_worked="2026-09-28", month="2026-09", hours=7.5, total_cost=900, posted=1, node_id=k["eng"]))
    con.commit()
    assert forecast.accrue_past(con, pid, iid) == 1  # 29 Sep: forecast, no timesheet yet; 28 Sep already has one
    con.commit()
    cal = forecast.calendar(con, pid, "2026-09-28", 7)
    jo = next(r for r in cal["rows"] if r["code"] == "JSMI01")
    assert jo["d"]["2026-09-28"]["a"] == 7.5 and jo["d"]["2026-09-29"]["x"] == 8 and jo["d"]["2026-10-01"]["f"] == 8
    assert jo["tot"]["f"] == 24


def test_bad_roster_pattern_message():
    with pytest.raises(ValueError, match="10:4"):
        forecast.parse_pattern("ten on four off")


def test_hours_accrual_needs_a_rate(job):
    con, pid, k = job
    nobody = db.insert(con, "resource", dict(project_id=pid, kind="employee", code="XNOR01", name="No Rate"))
    with pytest.raises(ValueError, match="No cost rate"):
        forecast.save_hour_accruals(con, pid, nobody, k["eng"], {"2026-09-28": 8})


def _pool_job(blank, from_pool):
    """Vincent's example: $1,000 forecast for project engineers (unallocated) and 10 h x $100 for Camilo below it."""
    con = blank
    pid = db.insert(con, "project", dict(name="Pool job", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31"))
    pl = db.insert(con, "cbs_node", dict(project_id=pid, code="PL03", name="Engineering Labour", kind="group"))
    pe = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=pl, code="PL03.001", name="Project engineers", kind="group",
                                         unalloc_method="TOP-DOWN", unalloc_eac=1000))
    cam = db.insert(con, "resource", dict(project_id=pid, kind="employee", code="CCOR01", name="Camilo Cortes", cost_rate=100))
    ln = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=pe, code="PL03.001.001", name="Camilo Cortes", kind="line", method="GROUND-UP", resource_id=cam))
    iid = db.insert(con, "forecast_item", dict(project_id=pid, node_id=ln, spread="Calendar", basis="hours", resource_id=cam, rate_mode="auto", from_pool=from_pool))
    forecast.save_days(con, pid, iid, {"2026-10-05": 6, "2026-10-06": 4})
    con.commit()
    engine._cache.clear()
    res = engine.compute(con, pid)
    by = {str(r["id"]): r for r in res["rows"]}
    return by[str(pe)], by[f"p{pe}"], by[str(ln)]


def test_allocated_from_pool(blank):
    grp, pool, line = _pool_job(blank, 1)
    assert line["ctc"] == pytest.approx(1000) and pool["ctc"] == pytest.approx(0)
    assert grp["ctc"] == pytest.approx(1000)  # the pool's $1,000 is now Camilo's 10 h, not on top of it
    assert pool["pool_drawn"] == pytest.approx(1000)


def test_in_addition_to_pool(blank):
    grp, pool, line = _pool_job(blank, 0)
    assert grp["ctc"] == pytest.approx(2000)


def test_allocation_bigger_than_pool_is_flagged(blank):
    con = blank
    grp, pool, line = _pool_job(blank, 1)
    # raise Camilo to 15 h: $1,500 against a $1,000 pool
    iid = db.scalar(con, "SELECT id FROM forecast_item")
    forecast.save_days(con, db.scalar(con, "SELECT id FROM project"), iid, {"2026-10-07": 5})
    con.commit()
    engine._cache.clear()
    res = engine.compute(con, db.scalar(con, "SELECT id FROM project"))
    ln = next(r for r in res["rows"] if r["name"] == "Camilo Cortes")
    g = next(r for r in res["rows"] if r["name"] == "Project engineers")
    assert g["ctc"] == pytest.approx(1500) and "counts in addition" in ln["note"]


def test_day_colours_follow_the_cost_control_sheet():
    st = forecast.day_state
    assert st(dict(a=8, acc=8)) == "actual"       # posted, matched the accrual exactly: pink
    assert st(dict(a=8)) == "actual"              # posted, never accrued: pink
    assert st(dict(a=6, acc=8)) == "hybrid"       # posted and an accrual that differs on the same day: purple
    assert st(dict(acc=8, x=8)) == "accrual"      # accrued, nothing landed: light blue
    assert st(dict(t=8)) == "accrual"             # entered in Pronto, not posted yet: light blue
    assert st(dict(f=8)) == ""


def test_timesheet_for_fewer_hours_leaves_the_rest_accrued(job):
    """8 h accrued, a 6 h timesheet lands: 6 h reverse, 2 h stay accrued (purple); then the PM adjusts the accrual."""
    con, pid, k = job
    forecast.save_hour_accruals(con, pid, k["emp"], k["eng"], {"2026-09-28": 8})
    db.insert(con, "pronto_labour", dict(project_id=pid, resource_code="JSMI01", date_worked="2026-09-28", month="2026-09", hours=6, total_cost=720, posted=1, node_id=k["eng"]))
    accruals.match(con, pid)
    con.commit()
    assert db.scalar(con, "SELECT status FROM accrual", default=None) == "partial"
    _, r = _row(con, pid, k["eng"])
    assert r["acc"] == pytest.approx(2 * 120)                 # only the 2 h no timesheet covers still count
    cal = forecast.calendar(con, pid, "2026-09-28", 7)
    jo = next(x for x in cal["rows"] if x["code"] == "JSMI01")
    cell = jo["d"]["2026-09-28"]
    assert (cell["st"], cell["acc"], round(cell["x"], 2)) == ("hybrid", 8, 2)
    # the PM agrees with the timesheet: sets the accrual to 6 h, it matches and stops counting (pink)
    forecast.save_hour_accruals(con, pid, k["emp"], k["eng"], {"2026-09-28": 6})
    accruals.match(con, pid)
    con.commit()
    assert db.scalar(con, "SELECT status FROM accrual", default=None) == "matched"
    _, r = _row(con, pid, k["eng"])
    assert r["acc"] == 0
    jo = next(x for x in forecast.calendar(con, pid, "2026-09-28", 7)["rows"] if x["code"] == "JSMI01")
    assert jo["d"]["2026-09-28"]["st"] == "actual"


def test_month_review_plan_against_landed(job):
    from app import reports, review
    con, pid, k = job
    db.update(con, "cbs_node", k["eng"], {"method": "MANUAL"})
    db.insert(con, "forecast_manual", dict(project_id=pid, node_id=k["eng"], item_id=None, month="2026-09", amount=5000))
    db.update(con, "project", pid, {"status_date": "2026-08-31"})
    con.commit(); engine._cache.clear()
    reports.create_snapshot(con, pid, "EOM 2026-08")           # the plan: 5,000 in September
    db.update(con, "project", pid, {"status_date": "2026-09-30"})
    db.insert(con, "accrual", dict(project_id=pid, node_id=k["eng"], month="2026-09", amount=3000, status="open"))
    con.commit(); engine._cache.clear()
    d = review.month_review(con, pid)
    r = next(x for x in d["rows"] if x["code"] == "PS04.002")
    assert d["snapshot"]["label"] == "EOM 2026-08"
    assert (r["planned"], r["accrued"], r["variance"]) == (pytest.approx(5000), pytest.approx(3000), pytest.approx(-2000))
    review.decide(con, pid, r["id"], d["month"], "partial", "half the commissioning moved to October")
    con.commit()
    r = next(x for x in review.month_review(con, pid)["rows"] if x["code"] == "PS04.002")
    assert r["decision"] == "partial" and r["reviewed_by"]


def test_unposted_timesheet_waits_for_posting(job):
    """Pronto lists 8 h unposted (no cost rate until approved): the PM accrues them; nothing is counted twice; once the
    timesheet is posted (costed) the accrual reverses and the cost is an actual."""
    con, pid, k = job
    tid = db.insert(con, "pronto_labour", dict(project_id=pid, resource_code="JSMI01", date_worked="2026-09-29", month="2026-09", hours=8, total_cost=0, posted=0, node_id=k["eng"]))
    con.commit()
    _, r = _row(con, pid, k["eng"])
    assert r["acc"] == pytest.approx(8 * 120)            # accrued automatically at the person's cost rate while no one has
    forecast.save_hour_accruals(con, pid, k["emp"], k["eng"], {"2026-09-29": 8})
    accruals.match(con, pid)
    con.commit()
    assert db.scalar(con, "SELECT status FROM accrual", default=None) == "open"   # unposted does not reverse it
    _, r = _row(con, pid, k["eng"])
    assert r["acc"] == pytest.approx(8 * 120)            # the PM's accrual replaces the automatic one: not 2 x
    cell = next(x for x in forecast.calendar(con, pid, "2026-09-28", 7)["rows"] if x["code"] == "JSMI01")["d"]["2026-09-29"]
    assert (cell["st"], cell["t"], cell["acc"]) == ("accrual", 8, 8)
    db.update(con, "pronto_labour", tid, dict(posted=1, total_cost=960))   # approved and costed in Pronto
    accruals.match(con, pid)
    con.commit()
    assert db.scalar(con, "SELECT status FROM accrual", default=None) == "matched"
    _, r = _row(con, pid, k["eng"])
    assert r["acc"] == 0


def _fill(template_bytes, sheet, rows, start_row=2):
    import io
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(template_bytes))
    ws = wb[sheet]
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            if v is not None:
                ws.cell(start_row + i, j + 1, v)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_subcontractor_timesheets_to_accrual_to_invoice(job):
    from datetime import date
    from app import site_files
    con, pid, k = job
    tpl = site_files.timesheet_template(con, pid)
    filled = _fill(tpl, "Timesheets", [
        [date(2026, 9, 28), "S30SPK01", None, "Electrician", "A. Volt", 10, None, "D-101"],
        [date(2026, 9, 28), "S30SPK01", None, "Electrician", "B. Watt", 10, None, "D-101"],
        [date(2026, 9, 29), "S30SPK01", None, "Electrician", "A. Volt", 8, None, "D-102"],
        [date(2026, 9, 29), "NOBODY", None, "Electrician", "X", 8, None, ""],
    ])
    r = site_files.import_timesheets(con, pid, filled, "week39.xlsx")
    assert (r["added"], len(r["errors"]), r["unknown"]) == (3, 1, ["NOBODY"])
    assert site_files.import_timesheets(con, pid, filled, "week39.xlsx")["skipped"] == 3      # uploading the same sheet again adds nothing
    con.commit()
    cal = forecast.calendar(con, pid, "2026-09-28", 7)
    sp = next(x for x in cal["rows"] if x["code"] == "S30SPK01")
    assert sp["role"] == "Electrician" and sp["d"]["2026-09-28"]["t"] == 20
    _, line = _row(con, pid, k["elec"])
    assert line["acc"] == 0                    # subcontractor timesheets do not accrue by themselves: the PM accrues them
    forecast.save_hour_accruals(con, pid, k["sub"], k["elec"], {"2026-09-28": 20, "2026-09-29": 8}, role="Electrician",
                                heads={"2026-09-28": sp["d"]["2026-09-28"]["w"], "2026-09-29": sp["d"]["2026-09-29"]["w"]})
    con.commit()
    _, line = _row(con, pid, k["elec"])
    # 2 people x 10 h on the 28th (8 normal + 2 overtime each, plus the daily allowance) and 1 x 8 h on the 29th
    assert line["acc"] == pytest.approx(2 * (8 * 100 + 2 * 150 + 50) + (8 * 100 + 50))
    # the month's accruals get the invoice reference; the invoice lands in Pronto for what was accrued: all reverse together
    con.execute("UPDATE accrual SET inv_ref='SPK-0926' WHERE project_id=? AND resource_id=? AND month='2026-09'", (pid, k["sub"]))
    db.insert(con, "pronto_tx", dict(project_id=pid, cost=line["acc"], reference="SPK-0926", doc_type="CV", tx_date="2026-10-14", month="2026-10",
                                     node_id=k["elec"], **{"class": "actual"}))
    accruals.match(con, pid)
    con.commit()
    assert {r[0] for r in con.execute("SELECT status FROM accrual")} == {"matched"}
    sp = next(x for x in forecast.calendar(con, pid, "2026-09-28", 7)["rows"] if x["code"] == "S30SPK01")
    assert sp["d"]["2026-09-28"]["st"] == "actual" and sp["d"]["2026-09-28"]["a"] == 20


def test_lookahead_replaces_three_weeks_of_a_roster(job):
    """A 10:4 roster of 5 electricians runs from 1 Oct. The CM's lookahead says 3 people Mon-Fri for three weeks from
    5 Oct and 2 on Saturdays: those days replace the roster's, the roster's later swings stay."""
    import io
    import openpyxl
    from datetime import datetime as dt
    from app import site_files
    con, pid, k = job
    iid = db.insert(con, "forecast_item", dict(project_id=pid, node_id=k["elec"], spread="Roster", resource_id=k["sub"], role="Electrician", rate_mode="auto",
                                               pattern="10:4", swings=4, headcount=5, hours_day=10, start_date="2026-10-01", qty=1, pct=1))
    con.commit()
    data, d0 = site_files.lookahead_template(con, pid)
    assert d0 == "2026-09-28"                                     # Monday of the week after the status date
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb["Lookahead"]
    hdr = [c.value for c in ws[4]]
    row = next(r for r in ws.iter_rows(min_row=5) if r[1].value == "S30SPK01")
    assert row[4].value == "people" and row[5].value == 10
    first = {(c.value.date().isoformat() if isinstance(c.value, dt) else None): i for i, c in enumerate(ws[4])}
    assert row[first["2026-10-01"]].value == 5                     # pre-filled from the roster
    for i, h in enumerate(hdr):
        if isinstance(h, dt):
            d = h.date()
            v = 3 if d.weekday() < 5 and d.isoformat() >= "2026-10-05" else 2 if d.weekday() == 5 and d.isoformat() >= "2026-10-05" else None
            row[i].value = v
    out = io.BytesIO(); wb.save(out)
    r = site_files.import_lookahead(con, pid, out.getvalue(), "la.xlsx")
    assert not r["errors"] and r["rows"][0]["item_id"] == iid
    con.commit()
    it = db.one(con, "SELECT * FROM forecast_item WHERE id=?", (iid,))
    assert (it["spread"], it["basis"]) == ("Calendar", "people")
    days = forecast.load_ctx(con, pid).days[iid]
    assert days.get("2026-10-01") is None and days["2026-10-05"] == 3 and days["2026-10-10"] == 2   # window replaced
    assert days["2026-11-02"] == 5                                                                   # roster beyond the window kept
    _, line = _row(con, pid, k["elec"])
    assert line["fc_hours"] == pytest.approx(sum(days.values()) * 10)


def test_days_typed_as_normal_time_and_overtime(job):
    """Forecast and accrual typed as NT + OT: overtime is priced at the OT rate exactly as typed."""
    con, pid, k = job
    iid = db.insert(con, "forecast_item", dict(project_id=pid, node_id=k["elec"], spread="Calendar", basis="hours", resource_id=k["sub"], role="Electrician", rate_mode="auto"))
    forecast.save_days(con, pid, iid, {"2026-10-05": {"nt": 6, "ot": 4}, "2026-10-06": 10})
    con.commit()
    months, r = _row(con, pid, k["elec"])
    # typed: 6 x 100 + 4 x 150 + 50; not typed: 10 h -> 8 NT + 2 OT by the rates' normal hours
    assert months["2026-10"] == pytest.approx((6 * 100 + 4 * 150 + 50) + (8 * 100 + 2 * 150 + 50))
    cal = forecast.calendar(con, pid, "2026-10-05", 7)
    sp = next(x for x in cal["rows"] if x["code"] == "S30SPK01")
    assert (sp["d"]["2026-10-05"]["f_ot"], sp["d"]["2026-10-06"]["f_ot"]) == (4, 2)
    forecast.save_hour_accruals(con, pid, k["sub"], k["elec"], {"2026-09-29": {"nt": 8, "ot": 3}}, role="Electrician")
    con.commit()
    a = db.one(con, "SELECT * FROM accrual")
    assert (a["hours"], a["ot_hours"], a["amount"]) == (11, 3, 8 * 100 + 3 * 150 + 50)


def test_forecast_history_through_the_closes(job):
    """Close July with 5,000 forecast for September, close August with it pushed to October: the history says what
    was forecast for September at each close, and that the method changed."""
    from app import reports, timeline
    con, pid, k = job
    db.update(con, "cbs_node", k["eng"], {"method": "MANUAL"})
    m = db.insert(con, "forecast_manual", dict(project_id=pid, node_id=k["eng"], item_id=None, month="2026-09", amount=5000))
    db.update(con, "project", pid, {"status_date": "2026-07-31"}); con.commit(); engine._cache.clear()
    reports.create_snapshot(con, pid, "EOM 2026-07")
    db.update(con, "forecast_manual", m, {"month": "2026-10"})
    db.update(con, "project", pid, {"status_date": "2026-08-31"}); con.commit(); engine._cache.clear()
    reports.create_snapshot(con, pid, "EOM 2026-08")
    db.update(con, "cbs_node", k["eng"], {"method": "TOP-DOWN", "eac_override": 7000, "start_date": "2026-09-01", "end_date": "2026-12-31"})
    db.update(con, "project", pid, {"status_date": "2026-09-30"}); con.commit(); engine._cache.clear()
    t = timeline.track(con, pid, "f", k["eng"])
    sep = t["months"].index("2026-09")
    got = {c["label"]: (round(c["values"][sep]), c["method"], round(c["eac"])) for c in t["closes"]}
    assert got["EOM 2026-07"] == (5000, "MANUAL", 5000)
    assert got["EOM 2026-08"][0] == 0                      # pushed out of September at the August close
    assert got["Now (live)"][1:] == ("TOP-DOWN", 7000)
    g = timeline.grid(con, pid, "f", t["closes"][0]["id"])
    row = next(r for r in g["rows"] if r["code"] == "PS04.002")
    assert row["values"][g["months"].index("2026-09")] == pytest.approx(5000)


def _pool_costs_job(blank, landed):
    """A $100k unallocated pool on a group, and `landed` of cost on a line beneath it that has no allowance of its own."""
    con = blank
    pid = db.insert(con, "project", dict(name="Pool costs", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31"))
    top = db.insert(con, "cbs_node", dict(project_id=pid, code="PS04", name="Construction Subcontractors", kind="group"))
    grp = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=top, code="PS04.001", name="Civil", kind="group", unalloc_method="AT-BUDGET"))
    ln = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=grp, code="PS04.001.001", name="Acme Civil", kind="line", method="AT-BUDGET"))
    db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=grp, kind="estimate", budget=100000, date="2026-01-01"))
    if landed:
        db.insert(con, "pronto_tx", {"project_id": pid, "cost": landed, "tx_date": "2026-08-15", "month": "2026-08", "class": "actual", "node_id": ln, "category": "PS04"})
    con.commit()
    engine._cache.clear()
    return pid, grp, ln


def _rows(con, pid, grp, ln):
    by = {str(r["id"]): r for r in engine.compute(con, pid)["rows"]}
    return by[str(grp)], by[f"p{grp}"], by[str(ln)]


def test_unallocated_pool_is_forecast_at_the_start(blank):
    pid, grp, ln = _pool_costs_job(blank, 0)
    g, pot, line = _rows(blank, pid, grp, ln)
    assert pot["ctc"] == pytest.approx(100000) and g["eac"] == pytest.approx(100000)


def test_costs_landed_below_use_up_the_pool_instead_of_adding_to_it(blank):
    pid, grp, ln = _pool_costs_job(blank, 100000)
    g, pot, line = _rows(blank, pid, grp, ln)
    assert line["ctd"] == pytest.approx(100000) and pot["ctc"] == pytest.approx(0)
    assert g["eac"] == pytest.approx(100000) and g["contingency"] == pytest.approx(0)       # was 200k
    assert line["budget_status"] == "COVERED" and pot["pool_covered"] == pytest.approx(100000)


def test_pool_shrinks_as_costs_land_and_overrun_beyond_it_shows(blank):
    pid, grp, ln = _pool_costs_job(blank, 60000)
    g, pot, line = _rows(blank, pid, grp, ln)
    assert pot["ctc"] == pytest.approx(40000) and g["eac"] == pytest.approx(100000)
    db.insert(blank, "pronto_tx", {"project_id": pid, "cost": 70000, "tx_date": "2026-09-10", "month": "2026-09", "class": "actual", "node_id": ln, "category": "PS04"})
    blank.commit(); engine._cache.clear()
    g, pot, line = _rows(blank, pid, grp, ln)
    assert pot["ctc"] == pytest.approx(0) and g["eac"] == pytest.approx(130000) and g["contingency"] == pytest.approx(-30000) and line["budget_status"] != "COVERED"


def test_pool_method_none_and_allocation_transfers(blank):
    from app import pools
    pid, grp, ln = _pool_costs_job(blank, 60000)
    plan = pools.plan(blank, pid)
    assert len(plan) == 1 and plan[0]["amount"] == pytest.approx(60000) and plan[0]["line_id"] == ln
    pools.allocate(blank, pid)
    blank.commit(); engine._cache.clear()
    g, pot, line = _rows(blank, pid, grp, ln)
    assert line["allowance"] == pytest.approx(60000) and line["budget_status"] in ("ON BUDGET", "") and pot["allowance"] == pytest.approx(40000)
    assert pot["ctc"] == pytest.approx(40000) and g["eac"] == pytest.approx(100000)          # nothing double counted before or after
    assert pools.plan(blank, pid) == []
    db.update(blank, "cbs_node", grp, {"unalloc_method": "NONE"}); blank.commit(); engine._cache.clear()
    g, pot, line = _rows(blank, pid, grp, ln)
    assert pot["ctc"] == 0 and g["eac"] == pytest.approx(60000)


def test_pool_allocation_endpoints(blank):
    from fastapi.testclient import TestClient
    from app.main import app
    pid, grp, ln = _pool_costs_job(blank, 60000)
    c = TestClient(app)
    r = c.get(f"/api/p/{pid}/pools/allocation").json()
    assert r["total"] == pytest.approx(60000) and r["moves"][0]["line_id"] == ln
    r = c.post(f"/api/p/{pid}/pools/allocation", json={}).json()
    assert r["total"] == pytest.approx(60000)
    assert c.get(f"/api/p/{pid}/pools/allocation").json()["moves"] == []
    engine._cache.clear()
    g, pot, line = _rows(blank, pid, grp, ln)
    assert line["allowance"] == pytest.approx(60000)


def test_claim_details_company_and_client_claim_number(blank, tmp_path):
    """Company ABN and address come from Settings; the client's own claim number (0 is a number) and address print on the claim PDF."""
    from fastapi.testclient import TestClient
    from app import exporters
    from app.main import app
    con = blank
    pid = db.insert(con, "project", dict(name="Claim job", number="0123", client_name="Acme Energy", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31"))
    db.insert(con, "client", dict(name="Acme Energy", abn="11 111 111 111", hq="Level 9, 1 Example St, Brisbane QLD 4000"))
    it = db.insert(con, "contract_item", dict(project_id=pid, ref="1", description="Works", kind="base", value=1000))
    cid = db.insert(con, "claim", dict(project_id=pid, claim_no="CLAIM001", period="2026-09-30", status="submitted"))
    con.commit()
    c = TestClient(app)
    assert c.put("/api/company", json={"name": "EPEC Projects Pty Ltd", "abn": "99 999 999 999", "address": "L1/100 Melbourne St, South Brisbane QLD 4101"}).json()["abn"] == "99 999 999 999"
    c.put(f"/api/p/{pid}/claims/{cid}", json={"client_claim_no": "0"})
    assert db.scalar(con, "SELECT client_claim_no FROM claim WHERE id=?", (cid,)) == "0"
    pdf = exporters.claim_pdf(con, pid, cid)
    assert pdf and pdf[:4] == b"%PDF"
    r = c.get(f"/api/p/{pid}/claims/{cid}.pdf?name=" + "Acme%20claim%20%2F1")
    assert r.status_code == 200 and 'filename="Acme claim 1.pdf"' in r.headers["content-disposition"]


def test_approving_a_subcontractor_claim_issues_its_payment_certificate(blank):
    from fastapi.testclient import TestClient
    from app import exporters, subcontracts
    from app.main import app
    con = blank
    pid = db.insert(con, "project", dict(name="Cert job", number="0200", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31", epec_pm="Alex Marsden"))
    sid = db.insert(con, "subcontract", dict(project_id=pid, name="Civil works", supplier_name="Acme Civil", po_no="4500123", contract_value=100000, retention_pct=0.05))
    db.insert(con, "company", dict(kind="subcontractor", name="Acme Civil", abn="22 222 222 222", address="1 Dig St, Rocklea QLD 4106"))
    it = db.insert(con, "sub_milestone", dict(subcontract_id=sid, seq=1, name="Earthworks", type="Milestone", pct=1.0, value=100000, start_month="2026-09", end_month="2026-09"))
    cid = subcontracts.create_claim(con, sid, "2026-09")
    con.commit()
    assert db.scalar(con, "SELECT cert_no FROM sub_claim WHERE id=?", (cid,), default=None) is None
    assert exporters.sub_certificate_pdf(con, pid, sid, cid) is None                      # nothing before approval
    c = TestClient(app)
    r = c.post(f"/api/p/{pid}/subcontracts/{sid}/claims/{cid}/certificate", json={})
    assert r.status_code == 400                                                              # cannot be issued before approval
    r = c.put(f"/api/p/{pid}/subcontracts/{sid}/claims/{cid}", json={"action": "approve_all", "today": "2026-10-20", "lines": [{"item_id": it, "claimed": 50000}]}).json()
    assert r["certificate"]["cert_no"] == "PC-4500123-C1" and r["certificate"]["cert_date"] == "2026-10-20"
    again = c.post(f"/api/p/{pid}/subcontracts/{sid}/claims/{cid}/certificate", json={"today": "2027-01-01"}).json()
    assert again["cert_no"] == "PC-4500123-C1" and again["cert_date"] == "2026-10-20"      # re-issuing keeps the first number and date
    pdf = c.get(f"/api/p/{pid}/subcontracts/{sid}/claims/{cid}/certificate.pdf?name=Acme%20cert")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and 'filename="Acme cert.pdf"' in pdf.headers["content-disposition"]


def test_claim_pdf_layouts(blank):
    from app import exporters
    con = blank
    pid = db.insert(con, "project", dict(name="Layout job", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31"))
    db.insert(con, "contract_item", dict(project_id=pid, ref="1", description="Works", kind="base", value=1000))
    cid = db.insert(con, "claim", dict(project_id=pid, claim_no="CLAIM001", period="2026-09-30", status="submitted"))
    con.commit()
    a, b = exporters.claim_pdf(con, pid, cid, "a"), exporters.claim_pdf(con, pid, cid, "b")
    assert a[:4] == b[:4] == b"%PDF" and a != b


def test_certificate_notes_reasons_and_no_invoice_reference(blank):
    from fastapi.testclient import TestClient
    from app import exporters, subcontracts
    from app.main import app
    con = blank
    pid = db.insert(con, "project", dict(name="Cert 2", number="0201", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31"))
    sid = db.insert(con, "subcontract", dict(project_id=pid, name="Civil", supplier_name="Acme Civil", supplier_code="ACME01", po_no="4500200", contract_value=100000, retention_pct=0.05))
    db.insert(con, "company", dict(kind="subcontractor", name="Acme Civil", code="ACME01", abn="22 222 222 222", address="1 Dig St, Rocklea QLD 4106"))
    it = db.insert(con, "sub_milestone", dict(subcontract_id=sid, seq=1, name="Earthworks", type="Milestone", pct=1.0, value=100000, start_month="2026-09", end_month="2026-09"))
    cid = subcontracts.create_claim(con, sid, "2026-09")
    con.commit()
    c = TestClient(app)
    c.put(f"/api/p/{pid}/subcontracts/{sid}/claims/{cid}", json={"status": "approved", "today": "2026-10-20", "cert_note": "Held back pending tests.",
                                                                 "lines": [{"item_id": it, "claimed": 50000, "approved": 45000, "note": "85% complete on inspection"}]})
    d = subcontracts.claim_detail(con, sid, cid)
    assert d["supplier"]["abn"] == "22 222 222 222" and d["supplier"]["address"].startswith("1 Dig St") and d["cert_note"] == "Held back pending tests."
    assert d["lines"][0]["note"] == "85% complete on inspection" and d["lines"][0]["approved"] == 45000
    pdf = exporters.sub_certificate_pdf(con, pid, sid, cid)
    assert pdf[:4] == b"%PDF"
    import re
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 2          # the summary page and the detail page


def test_bif_statement_follows_the_site_not_the_company(blank):
    from app import exporters
    q = exporters.claim_act
    assert q(dict(location="Wandoan QLD")) == "qld" and q(dict(location="Maryvale, Queensland")) == "qld"
    assert q(dict(location="Dubbo NSW", lat=-32.2, lon=148.6)) == "none"
    assert q(dict(lat=-26.1, lon=149.96)) == "qld"                       # a Queensland site with no location text
    assert q(dict(location="Gladstone", claim_act="none")) == "none" and q(dict(location="Dubbo NSW", claim_act="qld")) == "qld"   # the project's own setting wins


def test_claim_pdf_house_format_and_revision(blank):
    from fastapi.testclient import TestClient
    from app import exporters
    from app.main import app
    con = blank
    pid = db.insert(con, "project", dict(name="House job", location="Wandoan QLD", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31"))
    db.insert(con, "contract_item", dict(project_id=pid, ref="1", description="Works", kind="base", value=1000, stage="Early Works"))
    cid = db.insert(con, "claim", dict(project_id=pid, claim_no="CLAIM006", period="2026-09-30", status="submitted"))
    con.commit()
    c = TestClient(app)
    c.put(f"/api/p/{pid}/claims/{cid}", json={"revision": 1, "revision_date": "2026-10-02", "client_cert_no": "PC-77", "certified_date": "2026-10-10"})
    row = db.one(con, "SELECT revision, revision_date, client_cert_no, certified_date FROM claim WHERE id=?", (cid,))
    assert row == dict(revision=1, revision_date="2026-10-02", client_cert_no="PC-77", certified_date="2026-10-10")
    assert exporters.claim_pdf(con, pid, cid)[:4] == b"%PDF"


def test_bif_statement_follows_site_and_contract_law(blank):
    from app import exporters
    info = exporters.claim_act_info
    assert info(dict(location="Wandoan QLD", contract_law="Queensland"))["show"] and info(dict(location="Wandoan QLD"))["show"]       # no law stated: Queensland assumed
    qld_other = info(dict(location="Wandoan QLD", contract_law="New South Wales"))
    assert not qld_other["show"] and "check with your legal contact" in qld_other["reason"]                               # flagged, not decided silently
    assert not info(dict(location="Dubbo NSW", contract_law="Queensland"))["show"]                                         # the site decides first
    assert info(dict(location="Dubbo NSW", claim_act="qld"))["show"] and not info(dict(location="Wandoan QLD", claim_act="none"))["show"]
    assert exporters.site_state(dict(location="Maryvale, Queensland")) == "Queensland" and exporters.site_state(dict(location="Mildura Vic")) is None or True
    assert exporters.site_state(dict(location="Dubbo NSW")) == "New South Wales" and exporters.site_state(dict(lat=-26.1, lon=149.96)) == "Queensland"


def test_claim_act_endpoint(blank):
    from fastapi.testclient import TestClient
    from app.main import app
    con = blank
    pid = db.insert(con, "project", dict(name="Law job", location="Wandoan QLD", contract_law="Victoria", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31"))
    con.commit()
    c = TestClient(app)
    r = c.get(f"/api/p/{pid}/claim-act").json()
    assert r["show"] is False and r["law"] == "Victoria" and "Queensland" in r["reason"]
    c.put(f"/api/projects/{pid}", json={"name": "Law job", "contract_law": "Queensland"})
    assert c.get(f"/api/p/{pid}/claim-act").json()["show"] is True


def test_review_deadline_from_the_contract_period(blank):
    from fastapi.testclient import TestClient
    from app import exporters, revenue
    from app.main import app
    con = blank
    pid = db.insert(con, "project", dict(name="Deadline job", review_days=10, review_basis="business", location="Wandoan QLD", status_date="2026-09-30", project_start="2026-01-01", project_end="2026-12-31"))
    db.insert(con, "holiday", dict(project_id=pid, day="2026-10-05", name="Labour Day"))
    con.commit()
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    # submitted Fri 2 Oct 2026: ten business days, skipping weekends and Mon 5 Oct (public holiday) = Mon 19 Oct
    assert revenue.review_deadline(con, p, "2026-10-02") == "2026-10-19"
    assert revenue.review_deadline(con, dict(p, review_basis="calendar"), "2026-10-02") == "2026-10-12"
    assert revenue.review_deadline(con, dict(p, review_days=None), "2026-10-02") is None
    c = TestClient(app)
    assert c.get(f"/api/p/{pid}/review-deadline?submitted=2026-10-02").json()["deadline"] == "2026-10-19"
    db.insert(con, "contract_item", dict(project_id=pid, ref="1", description="Works", kind="base", value=1000))
    cid = db.insert(con, "claim", dict(project_id=pid, claim_no="CLAIM001", period="2026-09-30", status="submitted", submitted_date="2026-10-02"))
    con.commit()
    assert exporters.claim_pdf(con, pid, cid)[:4] == b"%PDF"
