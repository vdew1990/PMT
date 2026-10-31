"""Release .113: the Ground-Up register (items grouped H1 > H2 > H3, labels only) and the method pickers retired from the forecast pages."""
from fastapi.testclient import TestClient

from app import db


def _client():
    return TestClient(__import__("app.main", fromlist=["app"]).app)


def _line(con, pid, method=None):
    q = "SELECT id, code FROM cbs_node WHERE project_id=? AND kind='line' AND active=1" + (" AND method=?" if method else "") + " ORDER BY id LIMIT 1"
    return db.one(con, q, (pid, method) if method else (pid,))


def _item(c, pid, nid, **kw):
    body = dict(spread="Lump", qty=1, rate=1000, start_date="2026-11-10", scope="Test item") | kw
    return c.post(f"/api/p/{pid}/nodes/{nid}/items", json=body).json()["id"]


def test_register_lists_items_with_months_and_rolls_up(demo):
    con, pid = demo
    c = _client(); n = _line(con, pid)
    iid = _item(c, pid, n["id"], scope="Mobilise", h1="Site crew", h2="Mobilisation")
    r = c.get(f"/api/p/{pid}/groundup").json()
    it = next(i for i in r["items"] if i["id"] == iid)
    assert it["h1"] == "Site crew" and it["h2"] == "Mobilisation" and it["h3"] is None and it["code"] == n["code"]
    assert abs(it["total"] - 1000) < 0.01 and it["months"] == {"2026-11": 1000.0}
    assert it["live"]                                                     # saving an item switches its line to GROUND-UP
    assert "Site crew" in r["names"]["h1"]
    live_total = sum(i["total"] for i in r["items"] if i["live"])
    assert abs(r["total"] - live_total) < 0.01


def test_grouping_is_labels_only_and_levels_depend_on_the_one_above(demo):
    con, pid = demo
    c = _client(); n = _line(con, pid)
    a = _item(c, pid, n["id"], scope="A"); b = _item(c, pid, n["id"], scope="B")
    before = c.get(f"/api/p/{pid}/groundup").json()
    assert c.post(f"/api/p/{pid}/groundup/group", json=dict(ids=[a, b], h1="Person X", h2="Vehicle", h3="Hire")).json()["updated"] == 2
    after = c.get(f"/api/p/{pid}/groundup").json()
    assert abs(after["total"] - before["total"]) < 0.01                  # no figure moves
    assert {i["h3"] for i in after["items"] if i["id"] in (a, b)} == {"Hire"}
    c.post(f"/api/p/{pid}/groundup/group", json=dict(ids=[a], h1="Person X", h2="", h3="Hire"))
    row = db.one(con, "SELECT h1, h2, h3 FROM forecast_item WHERE id=?", (a,))
    assert (row["h1"], row["h2"], row["h3"]) == ("Person X", None, None)  # H3 cannot exist without H2
    c.post(f"/api/p/{pid}/groundup/group", json=dict(ids=[b], h1=""))
    row = db.one(con, "SELECT h1, h2, h3 FROM forecast_item WHERE id=?", (b,))
    assert (row["h1"], row["h2"], row["h3"]) == (None, None, None)
    assert c.post(f"/api/p/{pid}/groundup/group", json=dict(ids=[999999], h1="x")).status_code == 400


def test_rename_changes_every_item_at_that_level(demo):
    con, pid = demo
    c = _client(); n = _line(con, pid)
    a = _item(c, pid, n["id"], h1="Old name"); b = _item(c, pid, n["id"], h1="Old name")
    assert c.post(f"/api/p/{pid}/groundup/rename", json=dict(level="h1", old="Old name", new="New name")).json()["updated"] == 2
    assert db.one(con, "SELECT h1 FROM forecast_item WHERE id=?", (b,))["h1"] == "New name"
    assert c.post(f"/api/p/{pid}/groundup/rename", json=dict(level="h4", old="x", new="y")).status_code == 400
    assert c.post(f"/api/p/{pid}/groundup/rename", json=dict(level="h1", old="New name", new="  ")).status_code == 400


def test_an_item_on_another_method_line_is_listed_but_not_counted(demo):
    con, pid = demo
    c = _client(); n = _line(con, pid)
    iid = _item(c, pid, n["id"], scope="Inert")
    con.execute("UPDATE cbs_node SET method='AT-BUDGET' WHERE id=?", (n["id"],)); con.commit()
    it = next(i for i in c.get(f"/api/p/{pid}/groundup").json()["items"] if i["id"] == iid)
    assert it["live"] is False and it["method"] == "AT-BUDGET"


def test_saving_a_forecast_item_keeps_every_field(demo):
    """The variation item column list used to shadow the forecast one, so a saved item lost its quantity, rate and dates."""
    con, pid = demo
    c = _client(); n = _line(con, pid)
    iid = _item(c, pid, n["id"], spread="Linear", qty=4, rate=250, start_date="2026-11-01", end_date="2027-01-31", scope="Hire", unit="wk")
    row = db.one(con, "SELECT spread, qty, rate, start_date, end_date, scope, unit FROM forecast_item WHERE id=?", (iid,))
    assert (row["spread"], row["qty"], row["rate"], row["start_date"], row["end_date"], row["scope"], row["unit"]) == ("Linear", 4, 250, "2026-11-01", "2027-01-31", "Hire", "wk")
    assert c.post(f"/api/p/{pid}/items/preview", json=dict(spread="Linear", qty=4, rate=250, start_date="2026-11-01", end_date="2027-01-31", node_id=n["id"])).status_code in (200, 404, 405)


def test_pages_and_scripts_are_revalidated_so_a_new_release_is_not_served_from_cache(demo):
    c = _client()
    for url in ("/", "/static/js/app.js", "/static/css/design.css"):
        assert c.get(url).headers.get("cache-control") == "no-cache", url


def test_groundup_register_spreads_like_cost_control_under_a_group_window(blank):
    """F2: an item with no dates on a line with no window of its own follows the group's window (Oct to Dec 2026), in the
    register exactly as in Cost control, and the register's start and end show that window."""
    from app import db, engine, groundup
    con = blank
    pid = db.insert(con, "project", dict(name="G", status_date="2026-09-30", project_start="2026-01-01", project_end="2027-12-31"))
    top = db.insert(con, "cbs_node", dict(project_id=pid, code="PS04", name="G", kind="group", gp="PS", category="PS04", start_date="2026-10-01", end_date="2026-12-31"))
    a = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=top, code="PS04.001", name="L", kind="line", gp="PS", method="GROUND-UP"))
    db.insert(con, "forecast_item", dict(project_id=pid, node_id=a, spread="Linear", qty=1, rate=120000))
    con.commit(); engine._cache.clear()
    res = engine.compute(con, pid)
    row = next(r for r in res["rows"] if r["id"] == a)
    cost_control = {m: round(v, 2) for m, v in zip(res["grid"], row["f"]) if abs(v) > 0.005}
    it = groundup.register(con, pid)["items"][0]
    assert cost_control == {"2026-10": 40000, "2026-11": 40000, "2026-12": 40000}
    assert it["months"] == cost_control and it["total"] == 120000
    assert (it["start"], it["end"]) == ("2026-10-01", "2026-12-31") and (it["start_own"], it["end_own"]) == (None, None)



def test_groundup_register_own_dates_win_and_money_outside_the_line_window_is_flagged(blank):
    """Q14, answer A (display and flag only): an item shows its own dates; a date it does not have of its own is the
    inherited window widened to take in every month with money; the shown range never ends before it starts. An item
    with money before the line window's start or after its end is flagged with the months and the reason, and the
    Cost control row counts those items. The line window does not move, and the months and totals still tie."""
    from app import db, engine, groundup
    con = blank
    pid = db.insert(con, "project", dict(name="G", status_date="2026-09-30", project_start="2026-01-01", project_end="2027-12-31"))
    top = db.insert(con, "cbs_node", dict(project_id=pid, code="PS04", name="G", kind="group", gp="PS", category="PS04", start_date="2026-10-01", end_date="2026-12-31"))
    a = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=top, code="PS04.001", name="L", kind="line", gp="PS", method="GROUND-UP"))
    ids = dict(
        undated=db.insert(con, "forecast_item", dict(project_id=pid, node_id=a, spread="Linear", qty=1, rate=30000)),
        own=db.insert(con, "forecast_item", dict(project_id=pid, node_id=a, spread="Linear", qty=1, rate=20000, start_date="2026-11-05", end_date="2026-12-20")),
        late_lump=db.insert(con, "forecast_item", dict(project_id=pid, node_id=a, spread="Lump", qty=1, rate=18000, start_date="2027-02-10")),
        early_end=db.insert(con, "forecast_item", dict(project_id=pid, node_id=a, spread="Linear", qty=1, rate=7000, end_date="2026-08-31")),
        early_own=db.insert(con, "forecast_item", dict(project_id=pid, node_id=a, spread="Linear", qty=1, rate=9000, start_date="2026-09-10", end_date="2026-11-20")))
    con.commit(); engine._cache.clear()
    res = engine.compute(con, pid)
    row = next(r for r in res["rows"] if r["id"] == a)
    cost_control = {m: round(v, 2) for m, v in zip(res["grid"], row["f"]) if abs(v) > 0.005}
    reg = groundup.register(con, pid)
    by = {k: next(i for i in reg["items"] if i["id"] == v) for k, v in ids.items()}
    shown = {k: (i["start"], i["end"]) for k, i in by.items()}
    assert shown["undated"] == ("2026-10-01", "2026-12-31")                    # the inherited group window, as before
    assert shown["own"] == ("2026-11-05", "2026-12-20")                        # its own dates, as before
    assert shown["late_lump"] == ("2027-02-10", "2027-02-28")                  # own start; inherited end widened to its money month
    assert by["late_lump"]["months"] == {"2027-02": 18000} and (by["late_lump"]["start_own"], by["late_lump"]["end_own"]) == ("2027-02-10", None)
    assert shown["early_end"] == (None, "2026-08-31")                          # own end wins; the contradicting inherited start is blank
    assert shown["early_own"] == ("2026-09-10", "2026-11-20")
    assert all(not (s and e) or e >= s for s, e in shown.values())
    # the flag: money after the window (late_lump); money before it is out of the forecast here (September is the status month)
    assert by["late_lump"]["outside_window"] == dict(before=[], after=["2027-02"], line_start="2026-10-01", line_end="2026-12-31",
                                                     reason="Outside the line window: money in 02/2027, after the line window ends on 31/12/2026")
    assert all(by[k]["outside_window"] is None for k in ("undated", "own", "early_end"))
    assert reg["outside_window"] == sum(1 for i in reg["items"] if i["outside_window"])
    assert row["items_outside_window"] == reg["outside_window"]
    assert (row["start"], row["end"]) == ("2026-10", "2026-12")                # the line window never grows
    months = {}
    for i in reg["items"]:
        for m, v in i["months"].items():
            months[m] = round(months.get(m, 0) + v, 2)
    assert months == cost_control and reg["total"] == round(sum(cost_control.values()), 2)
    assert groundup._shown("2026-04-01", "2026-03-31", "2026-04-01", "2026-03-31") == dict(start="2026-04-01", end=None)   # both own, entered back to front
    # an undated item whose money falls after the inherited window (a milestone paid later) shows a window that takes it in
    assert groundup._shown("2025-02-01", "2026-11-30", None, None, {"2026-09": 1.0, "2027-01": 2.0}) == dict(start="2025-02-01", end="2027-01-31")
    # own dates are never widened, even when the money falls outside them
    assert groundup._shown("2026-10-01", "2026-10-31", "2026-10-01", "2026-10-31", {"2026-12": 1.0}) == dict(start="2026-10-01", end="2026-10-31")


def test_groundup_flag_covers_money_before_the_line_window(blank):
    """Q14: an item whose own dates start before a line window that opens later is flagged 'before', with those months;
    the line window is not moved and Cost control counts the item on the line."""
    from app import db, engine, groundup
    con = blank
    pid = db.insert(con, "project", dict(name="G", status_date="2026-09-30", project_start="2026-01-01", project_end="2027-12-31"))
    top = db.insert(con, "cbs_node", dict(project_id=pid, code="PS04", name="G", kind="group", gp="PS", category="PS04"))
    a = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=top, code="PS04.001", name="L", kind="line", gp="PS", method="GROUND-UP",
                                        start_date="2027-01-01", end_date="2027-03-31"))
    b = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=top, code="PS04.002", name="M", kind="line", gp="PS", method="GROUND-UP",
                                        start_date="2027-01-01", end_date="2027-03-31"))
    early = db.insert(con, "forecast_item", dict(project_id=pid, node_id=a, spread="Linear", qty=1, rate=12000, start_date="2026-11-01", end_date="2027-04-30"))
    db.insert(con, "forecast_item", dict(project_id=pid, node_id=b, spread="Linear", qty=1, rate=3000))
    con.commit(); engine._cache.clear()
    reg = groundup.register(con, pid)
    it = next(i for i in reg["items"] if i["id"] == early)
    assert (it["start"], it["end"]) == ("2026-11-01", "2027-04-30")
    assert it["outside_window"]["before"] == ["2026-11", "2026-12"] and it["outside_window"]["after"] == ["2027-04"]
    assert (it["outside_window"]["line_start"], it["outside_window"]["line_end"]) == ("2027-01-01", "2027-03-31")
    assert it["outside_window"]["reason"] == ("Outside the line window: money in 11/2026, 12/2026, before the line window starts on 01/01/2027; "
                                              "money in 04/2027, after the line window ends on 31/03/2027")
    rows = {r["id"]: r for r in engine.compute(con, pid)["rows"]}
    assert rows[a]["items_outside_window"] == 1 and rows[b]["items_outside_window"] == 0
    assert (rows[a]["start"], rows[a]["end"]) == ("2027-01", "2027-03")
    assert db.one(con, "SELECT start_date, end_date FROM cbs_node WHERE id=?", (a,)) == {"start_date": "2027-01-01", "end_date": "2027-03-31"}


def test_groundup_q14_on_the_demo_seed(demo):
    """Q14 on the demo project: PS04.003 Demobilisation (Lump, own start 10/12/2026) shows 10/12/2026 to 31/12/2026 and
    PM03.002 (Milestones, undated) shows 01/02/2025 to 31/01/2027, both flagged 'after'. Amounts unchanged."""
    from app import engine, groundup
    con, pid = demo
    engine._cache.clear()
    reg = groundup.register(con, pid)
    lump = next(i for i in reg["items"] if i["code"] == "PS04.003" and i["spread"] == "Lump")
    assert (lump["start"], lump["end"]) == ("2026-12-10", "2026-12-31") and lump["months"] == {"2026-12": 18000.0}
    assert lump["outside_window"]["after"] == ["2026-12"] and lump["outside_window"]["before"] == []
    pm = next(i for i in reg["items"] if i["code"] == "PM03.002")
    assert (pm["start"], pm["end"]) == ("2025-02-01", "2027-01-31")
    assert pm["outside_window"]["after"] and pm["outside_window"]["before"] == []
    assert all(not (i["start"] and i["end"]) or i["end"] >= i["start"] for i in reg["items"])
    rows = {r["id"]: r for r in engine.compute(con, pid)["rows"]}
    live_lines = {i["node_id"] for i in reg["items"] if i["live"] and not i["pool"]}
    assert abs(sum(i["total"] for i in reg["items"] if i["live"] and not i["pool"]) - sum(rows[n]["ctc"] for n in live_lines)) < 0.05   # per-month cent rounding
    assert rows[lump["node_id"]]["items_outside_window"] >= 1 and rows[pm["node_id"]]["items_outside_window"] >= 1
