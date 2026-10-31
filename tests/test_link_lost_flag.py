"""Q13 / F5: a CBS line whose schedule item disappears on a re-upload stays flagged (cbs_node.schedule_link_lost), for every
user, until it is linked to the schedule again or the flag is dismissed."""
import json
from datetime import date

from app import db, engine, programme
from tests.test_schedule_reupload import _job
from tests.test_sync import _seed, shared  # noqa: F401  (the two-copy fixture)

GONE = "WBS,Name,Start,Finish\n1.2,Concrete pour,01/12/2026,31/03/2027\n"      # Site start is no longer in the schedule


def _row(con, pid, nid):
    engine._cache.clear()
    return next(r for r in engine.compute(con, pid)["rows"] if r["id"] == nid)


def test_the_column_is_added_to_an_existing_database(blank):
    con = blank
    assert "schedule_link_lost" in {r[1] for r in con.execute("PRAGMA table_info(cbs_node)")}
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='cbs_node'").fetchall():
        con.execute(f"DROP TRIGGER {t}")                                   # (the change-log triggers name every column)
    con.execute("ALTER TABLE cbs_node DROP COLUMN schedule_link_lost"); con.commit()
    db.init_db(); db.init_db()                                             # an older copy picks it up; running twice is harmless
    assert "schedule_link_lost" in {r[1] for r in con.execute("PRAGMA table_info(cbs_node)")}


def test_a_lost_link_flags_the_line_until_dismissed(blank):
    c, pid, a, b = _job(blank)
    assert _row(blank, pid, a)["schedule_link_lost"] is None
    c.post(f"/api/p/{pid}/programme/upload", files={"file": ("s.csv", GONE, "text/csv")})
    flag = _row(blank, pid, a)["schedule_link_lost"]
    assert flag == [dict(date=date.today().isoformat(), task="Site start", wbs="1.1", role="start")]
    assert _row(blank, pid, b)["schedule_link_lost"] is None                # its link (suspended) survived: not flagged
    api = next(r for r in c.get(f"/api/p/{pid}/cost-control").json()["rows"] if r["id"] == a)
    assert api["schedule_link_lost"] == flag                                # in the Cost control row data the page gets
    c.post(f"/api/p/{pid}/programme/upload", files={"file": ("s.csv", GONE, "text/csv")})
    assert _row(blank, pid, a)["schedule_link_lost"] == flag               # a second upload does not clear or repeat it
    # the change is in the change log, so it syncs
    assert db.scalar(blank, "SELECT COUNT(*) FROM change_log WHERE tbl='cbs_node' AND row_id=? AND data LIKE '%schedule_link_lost%'", (a,)) >= 1
    assert c.delete(f"/api/p/{pid}/nodes/{a}/schedule-link-lost").json() == {"cleared": 1}
    assert _row(blank, pid, a)["schedule_link_lost"] is None
    assert c.delete(f"/api/p/{pid}/nodes/{a}/schedule-link-lost").json() == {"cleared": 0}
    assert _window_kept(blank, a)


def _window_kept(con, nid):
    return tuple(con.execute("SELECT start_date, end_date FROM cbs_node WHERE id=?", (nid,)).fetchone()) == ("2026-11-10", "2027-02-28")


def test_linking_the_line_again_clears_the_flag(blank):
    c, pid, a, b = _job(blank)
    c.post(f"/api/p/{pid}/programme/upload", files={"file": ("s.csv", GONE, "text/csv")})
    assert _row(blank, pid, a)["schedule_link_lost"]
    tid = blank.execute("SELECT id FROM programme_task WHERE project_id=? AND name='Concrete pour'", (pid,)).fetchone()[0]
    c.post(f"/api/p/{pid}/programme/links", json=dict(node_id=a, task_id=tid, role="start", edge="start"))
    assert _row(blank, pid, a)["schedule_link_lost"] is None


def test_each_way_of_linking_clears_it(blank):
    c, pid, a, b = _job(blank)
    tid = lambda: blank.execute("SELECT id FROM programme_task WHERE project_id=? AND name='Concrete pour'", (pid,)).fetchone()[0]
    flagged = lambda: db.scalar(blank, "SELECT schedule_link_lost FROM cbs_node WHERE id=?", (a,), None)
    lose = lambda: c.post(f"/api/p/{pid}/programme/upload", files={"file": ("s.csv", GONE, "text/csv")})
    lose(); assert flagged()
    programme.set_window(blank, pid, a, {"mode": "schedule", "task_id": tid(), "edge": "start"}, {"mode": "typed", "date": "2027-02-28"})
    assert not flagged()                                                   # the window editor
    blank.execute("UPDATE cbs_node SET schedule_link_lost=? WHERE id=?", (json.dumps([dict(date="2026-10-31", task="x", wbs=None, role="start")]), a)); blank.commit()
    c.put(f"/api/p/{pid}/programme/tasks/{tid()}", json=dict(link_node_id=a))
    assert not flagged()                                                   # a span link from the schedule page


def test_the_flag_reaches_the_other_copy_and_so_does_the_dismissal(shared, monkeypatch):  # noqa: F811
    from app import sync
    pc, pm = shared
    pc.use(monkeypatch)
    con = pc.con()
    pid, nid = _seed(con)
    programme.flag_link_lost(con, pid, [dict(node_id=nid, task="Site start", wbs="1.1", role="start")])
    con.commit(); con.close()
    sync.sync_now()

    pm.use(monkeypatch)
    sync.sync_now()
    con = pm.con()
    got = programme.link_lost(db.scalar(con, "SELECT schedule_link_lost FROM cbs_node WHERE id=?", (nid,), None))
    assert got and got[0]["task"] == "Site start" and got[0]["role"] == "start"
    assert programme.clear_link_lost(con, pid, [nid], why="Schedule item gone: flag dismissed") == 1
    con.commit(); con.close()
    sync.sync_now()

    pc.use(monkeypatch)
    sync.sync_now()
    con = pc.con()
    assert db.scalar(con, "SELECT schedule_link_lost FROM cbs_node WHERE id=?", (nid,), None) is None
    con.close()
