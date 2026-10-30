"""Release .112: pre-flight before Initialise, the Month-end checklist, bulk allowance linking and the close-out checklist."""
from fastapi.testclient import TestClient

from app import allowance, db


def _client():
    return TestClient(__import__("app.main", fromlist=["app"]).app)


def test_preflight_lists_the_four_things_to_read(demo):
    con, pid = demo
    items = _client().get(f"/api/p/{pid}/preflight").json()["items"]
    assert [i["key"] for i in items] == ["resources", "parked", "schedule", "methods"]
    assert all(i["state"] in ("done", "todo", "warn", "info") and i["detail"] for i in items)
    ov = allowance.overview(con, pid)
    res = next(i for i in items if i["key"] == "resources")
    assert res["count"] == len(ov["resources"]) and (res["state"] == "done") == (not ov["resources"])


def test_month_end_checklist_follows_the_close(demo):
    con, pid = demo
    c = _client()
    d = c.get(f"/api/p/{pid}/month-end").json()
    assert [i["key"] for i in d["items"]] == ["pronto", "accruals", "review", "assessment", "team", "close", "reports"]
    assert all(i["page"] for i in d["items"])
    close_state = lambda: next(i for i in c.get(f"/api/p/{pid}/month-end").json()["items"] if i["key"] == "close")["state"]
    con.execute("DELETE FROM snapshot WHERE project_id=? AND kind='eom' AND period=?", (pid, d["month"]))
    con.commit()                                                   # the module's connection must not keep the database locked
    assert close_state() == "todo"
    assert c.post(f"/api/p/{pid}/snapshots", json={}).status_code == 200
    assert close_state() == "done"


def test_bulk_link_covers_cost_and_reports_what_it_skipped(demo):
    con, pid = demo
    ov = allowance.overview(con, pid)
    todo = [r for r in ov["resources"] if r["state"] == "cost_no_line" and r["bucket_id"]]
    if not todo:
        return                                                     # the demo has nothing left to link: nothing to prove here
    rows = [dict(kind=r["kind"], code=r["code"], name=r["name"], function=r["function"], bucket_id=r["bucket_id"]) for r in todo[:2]]
    rows.append(dict(kind="supplier", code="NOBUCKET", name="No bucket"))
    o = _client().post(f"/api/p/{pid}/allowance/link-many", json=dict(rows=rows, option=2)).json()
    assert o["linked"] + len(o["skipped"]) == len(rows) and any(s["code"] == "NOBUCKET" for s in o["skipped"])
    assert _client().post(f"/api/p/{pid}/allowance/link-many", json=dict(rows=rows, option=3)).status_code == 400   # only 1 and 2 in bulk


def test_close_out_checklist_ticks_are_kept_and_checked(demo):
    con, pid = demo
    c = _client()
    d = c.get(f"/api/p/{pid}/close-out").json()
    keys = [i["key"] for i in d["items"]]
    assert {"claims", "retention", "subs", "variations", "accruals", "gate", "dlp", "gate7_paper", "handover", "lessons", "archive"} <= set(keys)
    assert not any("gate8" in k for k in keys)                     # EPEC's gates stop at 7
    d = c.post(f"/api/p/{pid}/close-out/tick", json=dict(key="dlp", done=True)).json()
    assert next(i for i in d["items"] if i["key"] == "dlp")["state"] == "done"
    assert next(i for i in c.get(f"/api/p/{pid}/close-out").json()["items"] if i["key"] == "dlp")["state"] == "done"      # kept
    d = c.post(f"/api/p/{pid}/close-out/tick", json=dict(key="dlp", done=False)).json()
    assert next(i for i in d["items"] if i["key"] == "dlp")["state"] == "todo"
    assert c.post(f"/api/p/{pid}/close-out/tick", json=dict(key="claims", done=True)).status_code == 400    # only the manual items can be ticked
