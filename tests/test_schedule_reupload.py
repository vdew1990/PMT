"""A schedule re-upload keeps the activity-window links (window_link) of the CBS lines: anchored and suspended alike."""
from fastapi.testclient import TestClient

from app import db, programme

CSV1 = "WBS,Name,Start,Finish\n1.1,Site start,10/11/2026,10/11/2026\n1.2,Concrete pour,01/12/2026,31/03/2027\n"


def _job(con):
    from app.routers import _shared
    _shared.UPLOADS.mkdir(parents=True, exist_ok=True)
    pid = db.insert(con, "project", dict(name="Reupload", status_date="2026-09-30", project_start="2026-01-01", project_end="2027-06-30"))
    top = db.insert(con, "cbs_node", dict(project_id=pid, code="PS04", name="Group", kind="group", gp="PS", category="PS04"))
    a = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=top, code="PS04.001", name="Earthworks", kind="line", gp="PS", method="AT-BUDGET"))
    b = db.insert(con, "cbs_node", dict(project_id=pid, parent_id=top, code="PS04.002", name="Fencing", kind="line", gp="PS", method="AT-BUDGET"))
    con.commit()
    c = TestClient(__import__("app.main", fromlist=["app"]).app)
    assert c.post(f"/api/p/{pid}/programme/upload", files={"file": ("s.csv", CSV1, "text/csv")}).status_code == 200
    task = lambda name: con.execute("SELECT id FROM programme_task WHERE project_id=? AND name=?", (pid, name)).fetchone()[0]
    # line a: Start follows the Site start milestone, Stop is four months on
    programme.set_window(con, pid, a, {"mode": "schedule", "task_id": task("Site start"), "edge": "start"}, {"mode": "duration"}, 4)
    # line b: Stop followed the Concrete pour finish, then the user typed over it (a suspended link)
    programme.set_window(con, pid, b, {"mode": "typed", "date": "2026-10-01"}, {"mode": "schedule", "task_id": task("Concrete pour"), "edge": "finish"})
    programme.set_window(con, pid, b, {"mode": "typed", "date": "2026-10-01"}, {"mode": "typed", "date": "2027-02-28"})
    con.commit()
    return c, pid, a, b


def _links(con, nid):
    return {r["role"]: (r["task"], r["edge"], r["suspended"]) for r in db.rows(
        con, "SELECT w.role, t.name AS task, w.edge, w.suspended FROM window_link w JOIN programme_task t ON t.id=w.task_id WHERE w.node_id=?", (nid,))}


def _window(con, nid):
    return tuple(con.execute("SELECT start_date, end_date FROM cbs_node WHERE id=?", (nid,)).fetchone())


def test_anchored_and_suspended_links_survive_a_reupload_that_moves_the_milestone(blank):
    c, pid, a, b = _job(blank)
    assert _window(blank, a) == ("2026-11-10", "2027-02-28")
    assert _links(blank, b)["stop"] == ("Concrete pour", "finish", 1)
    r = c.post(f"/api/p/{pid}/programme/upload", files={"file": ("s.csv", CSV1.replace("10/11/2026,10/11/2026", "05/01/2027,05/01/2027"), "text/csv")}).json()
    assert r["links_lost"] == []
    assert _links(blank, a)["start"] == ("Site start", "start", 0)
    assert _window(blank, a) == ("2027-01-05", "2027-04-30")              # the anchor moved the line, the duration followed
    assert _links(blank, b)["stop"] == ("Concrete pour", "finish", 1)     # the typed override is still suspending its link
    assert _window(blank, b) == ("2026-10-01", "2027-02-28")
    c.post(f"/api/p/{pid}/nodes/{b}/window-reset")                         # and "Return to schedule" still works
    assert _window(blank, b)[1] == "2027-03-31"


def test_a_link_whose_task_is_gone_is_dropped_and_the_line_keeps_its_dates(blank):
    c, pid, a, b = _job(blank)
    csv2 = "WBS,Name,Start,Finish\n1.2,Concrete pour,01/12/2026,31/03/2027\n"          # Site start is no longer in the schedule
    r = c.post(f"/api/p/{pid}/programme/upload", files={"file": ("s.csv", csv2, "text/csv")}).json()
    assert [(x["node_id"], x["role"], x["task"], x["start"], x["end"]) for x in r["links_lost"]] == [(a, "start", "Site start", "2026-11-10", "2027-02-28")]
    assert _links(blank, a) == {}                                          # not re-pointed to another task
    assert _window(blank, a) == ("2026-11-10", "2027-02-28")              # the dates stay, now as typed values
    assert blank.execute("SELECT window_months FROM cbs_node WHERE id=?", (a,)).fetchone()[0] is None
    assert _links(blank, b)["stop"] == ("Concrete pour", "finish", 1)
    assert db.scalar(blank, "SELECT COUNT(*) FROM audit_log WHERE project_id=? AND action='Schedule item gone' AND detail LIKE 'PS04.001%'", (pid,)) == 1
