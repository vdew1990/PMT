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



def test_groundup_register_never_shows_an_end_before_the_start(blank):
    """F2 follow-up (display only): an own date that falls outside the inherited line window no longer shows an end
    before the start; the contradicting inherited date is left blank. Items inside the window are unchanged, and the
    months and totals still tie to Cost control. (Which window wins is open question Q14; this test does not pick.)"""
    from app import db, engine, groundup
    con = blank
    pid = db.insert(con, "project", dict(name="G", status_date="2026-09-30", project_start="2026-01-01", project_end="2027-12-31"))
    top = db.insert(con, "cbs_node", dict(project_id=pid, code="PS04", name="G", kind="group", gp="PS", category="PS04", start_date="2026-10-01", end_date="2026-12-31"))
    a = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=top, code="PS04.001", name="L", kind="line", gp="PS", method="GROUND-UP"))
    ids = dict(
        undated=db.insert(con, "forecast_item", dict(project_id=pid, node_id=a, spread="Linear", qty=1, rate=30000)),
        own=db.insert(con, "forecast_item", dict(project_id=pid, node_id=a, spread="Linear", qty=1, rate=20000, start_date="2026-11-05", end_date="2026-12-20")),
        late_lump=db.insert(con, "forecast_item", dict(project_id=pid, node_id=a, spread="Lump", qty=1, rate=18000, start_date="2027-02-10")),
        early_end=db.insert(con, "forecast_item", dict(project_id=pid, node_id=a, spread="Linear", qty=1, rate=7000, end_date="2026-08-31")))
    con.commit(); engine._cache.clear()
    res = engine.compute(con, pid)
    row = next(r for r in res["rows"] if r["id"] == a)
    cost_control = {m: round(v, 2) for m, v in zip(res["grid"], row["f"]) if abs(v) > 0.005}
    reg = groundup.register(con, pid)
    by = {k: next(i for i in reg["items"] if i["id"] == v) for k, v in ids.items()}
    shown = {k: (i["start"], i["end"]) for k, i in by.items()}
    assert shown["undated"] == ("2026-10-01", "2026-12-31")                    # the inherited group window, as before
    assert shown["own"] == ("2026-11-05", "2026-12-20")                        # its own dates, as before
    assert shown["late_lump"] == ("2027-02-10", None)                          # was 10/02/2027 to 31/12/2026
    assert by["late_lump"]["months"] == {"2027-02": 18000} and (by["late_lump"]["start_own"], by["late_lump"]["end_own"]) == ("2027-02-10", None)
    assert shown["early_end"] == (None, "2026-08-31")                          # was 01/10/2026 to 31/08/2026
    assert all(not (s and e) or e >= s for s, e in shown.values())
    months = {}
    for i in reg["items"]:
        for m, v in i["months"].items():
            months[m] = round(months.get(m, 0) + v, 2)
    assert months == cost_control and reg["total"] == round(sum(cost_control.values()), 2)
    assert groundup._shown("2026-04-01", "2026-03-31", "2026-04-01", "2026-03-31") == dict(start="2026-04-01", end=None)   # both own, entered back to front
