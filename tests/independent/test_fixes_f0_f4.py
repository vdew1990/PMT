"""Argus: independent checks for Neo's fixes F1 to F4 (31/10/2026), driven over HTTP only.

Expected results come from Neo's test briefs as relayed by Atlas, not from the code. Synthetic data only;
each test starts from the `blank` fixture (a fresh database) in tests/conftest.py.
"""
from fastapi.testclient import TestClient

from app import main


def _client():
    from app.routers import _shared
    _shared.UPLOADS.mkdir(parents=True, exist_ok=True)
    return TestClient(main.app)


def _ok(r):
    assert r.status_code == 200, (r.status_code, r.text)
    return r.json()


def _project(c, name, **extra):
    body = dict(name=name, status_date="30/09/2026", **extra)
    return _ok(c.post("/api/projects", json=body))["id"]


def _node(c, pid, **body):
    return _ok(c.post(f"/api/p/{pid}/nodes", json=body))["id"]


def _group(c, pid, code):
    """The standard CBS group a new project starts with (PS04 Construction Subcontractors)."""
    rows = _ok(c.get(f"/api/p/{pid}/cost-control"))["rows"]
    return next(r["id"] for r in rows if r.get("code") == code and r.get("kind") == "group")


def _upload(c, pid, csv):
    return _ok(c.post(f"/api/p/{pid}/programme/upload", files={"file": ("schedule.csv", csv, "text/csv")}))


def _tasks(c, pid):
    return {t["name"]: t for t in _ok(c.get(f"/api/p/{pid}/programme/tasks"))}


def _row(c, pid, nid):
    cc = _ok(c.get(f"/api/p/{pid}/cost-control"))
    return next(r for r in cc["rows"] if str(r["id"]) == str(nid)), cc


def _window(c, pid, nid):
    r, _ = _row(c, pid, nid)
    return r["start"], r["end"]


def _anchors(c, pid, nid):
    return {a["role"]: a for a in _ok(c.get(f"/api/p/{pid}/programme/links"))["anchors"] if a["node_id"] == nid}


# ---------------------------------------------------------------------------
# F1: activity-window links survive a schedule re-upload
# ---------------------------------------------------------------------------
CSV_F1 = "WBS,Name,Start,Finish\n1.1,Site start,10/11/2026,10/11/2026\n1.2,Concrete pour,01/12/2026,31/03/2027\n"


def _f1_setup(c):
    pid = _project(c, "F1 synthetic", project_start="01/01/2026", project_end="30/06/2027")
    grp = _group(c, pid, "PS04")
    ew = _node(c, pid, parent_id=grp, code="PS04.001", name="Earthworks", kind="line")
    fe = _node(c, pid, parent_id=grp, code="PS04.002", name="Fencing", kind="line")
    _upload(c, pid, CSV_F1)
    t = _tasks(c, pid)
    _ok(c.post(f"/api/p/{pid}/nodes/{ew}/window", json={
        "start": {"mode": "schedule", "task_id": t["Site start"]["id"], "edge": "start"}, "stop": {"mode": "duration"}, "months": 4}))
    _ok(c.post(f"/api/p/{pid}/nodes/{fe}/window", json={
        "start": {"mode": "typed", "date": "01/10/2026"}, "stop": {"mode": "schedule", "task_id": t["Concrete pour"]["id"], "edge": "finish"}}))
    _ok(c.post(f"/api/p/{pid}/nodes/{fe}/window", json={
        "start": {"mode": "typed", "date": "01/10/2026"}, "stop": {"mode": "typed", "date": "28/02/2027"}}))
    return pid, ew, fe


def _node_dates(blank, nid):
    """The line's stored Start and Stop (ISO). Read-only look at the fresh test database; no single-node GET route is relied on."""
    return tuple(blank.execute("SELECT start_date, end_date FROM cbs_node WHERE id=?", (nid,)).fetchone())


def test_f1_outcome_a_milestone_moves(blank):
    c = _client()
    pid, ew, fe = _f1_setup(c)
    # starting state as the brief implies it: Earthworks 10/11/2026 + 4 months, Fencing typed over
    assert _node_dates(blank, ew) == ("2026-11-10", "2027-02-28")
    assert _anchors(c, pid, fe)["stop"]["suspended"] in (1, True)
    r = _upload(c, pid, CSV_F1.replace("10/11/2026,10/11/2026", "05/01/2027,05/01/2027"))
    assert r["links_lost"] == []
    assert _node_dates(blank, ew) == ("2027-01-05", "2027-04-30")
    a = _anchors(c, pid, ew)
    assert "start" in a and a["start"]["suspended"] in (0, False, None)
    t = _tasks(c, pid)
    assert a["start"]["task_id"] == t["Site start"]["id"]
    assert _node_dates(blank, fe) == ("2026-10-01", "2027-02-28")
    f = _anchors(c, pid, fe)
    assert f["stop"]["suspended"] in (1, True) and f["stop"]["task_id"] == t["Concrete pour"]["id"]
    _ok(c.post(f"/api/p/{pid}/nodes/{fe}/window-reset", json={}))
    assert _node_dates(blank, fe)[1] == "2027-03-31"
    # the Cost control windows block reports the same state
    _, cc = _row(c, pid, ew)
    assert cc["windows"][str(ew)]["start"]["task"] == "Site start"


def test_f1_outcome_a_reupload_twice_is_stable(blank):
    """Exploratory: a second identical re-upload must not duplicate or drop links."""
    c = _client()
    pid, ew, fe = _f1_setup(c)
    csv2 = CSV_F1.replace("10/11/2026,10/11/2026", "05/01/2027,05/01/2027")
    _upload(c, pid, csv2)
    r = _upload(c, pid, csv2)
    assert r["links_lost"] == []
    links = _ok(c.get(f"/api/p/{pid}/programme/links"))["anchors"]
    assert sorted((a["node_id"], a["role"]) for a in links) == sorted([(ew, "start"), (fe, "stop")])
    assert _node_dates(blank, ew) == ("2027-01-05", "2027-04-30")
    assert _node_dates(blank, fe) == ("2026-10-01", "2027-02-28")


def test_f1_outcome_b_milestone_removed(blank):
    c = _client()
    pid, ew, fe = _f1_setup(c)
    r = _upload(c, pid, "WBS,Name,Start,Finish\n1.2,Concrete pour,01/12/2026,31/03/2027\n")
    assert _node_dates(blank, ew) == ("2026-11-10", "2027-02-28")
    assert _anchors(c, pid, ew) == {}
    assert blank.execute("SELECT window_months FROM cbs_node WHERE id=?", (ew,)).fetchone()[0] in (None, 0)
    lost = [(x["node_id"], x.get("name"), x["role"], x["task"]) for x in r["links_lost"]]
    assert lost == [(ew, "Earthworks", "start", "Site start")]
    gone = [a for a in _ok(c.get(f"/api/p/{pid}/audit")) if a["action"] == "Schedule item gone"]
    assert len(gone) == 1, gone
    # Fencing's suspended stop link to Concrete pour is untouched
    assert _anchors(c, pid, fe)["stop"]["suspended"] in (1, True)


# ---------------------------------------------------------------------------
# F2: Ground-Up register matches Cost control
# ---------------------------------------------------------------------------
def test_f2_groundup_register_matches_cost_control(blank):
    c = _client()
    pid = _project(c, "F2 synthetic", project_start="01/01/2026", project_end="31/12/2027")
    grp = _group(c, pid, "PS04")
    _ok(c.put(f"/api/p/{pid}/nodes/{grp}", json={"start_date": "01/10/2026", "end_date": "31/12/2026"}))
    ln = _node(c, pid, parent_id=grp, code="PS04.001", name="Earthworks", kind="line")
    _ok(c.post(f"/api/p/{pid}/nodes/{ln}/items", json={"spread": "Linear", "qty": 1, "rate": 120000}))
    expect = {"2026-10": 40000.00, "2026-11": 40000.00, "2026-12": 40000.00}

    row, cc = _row(c, pid, ln)
    assert row["method"] == "GROUND-UP"
    assert len(cc["grid"]) == len(row["f"])
    f = {m: round(v or 0, 2) for m, v in zip(cc["grid"], row["f"]) if abs(v or 0) > 0.005}
    assert f == expect, f

    reg = _ok(c.get(f"/api/p/{pid}/groundup"))
    assert len(reg["items"]) == 1
    it = reg["items"][0]
    assert it["months"] == expect
    assert it["total"] == 120000.00 and reg["total"] == 120000.00
    assert (it["start"], it["end"]) == ("2026-10-01", "2026-12-31")


# ---------------------------------------------------------------------------
# F3: clone copies supplier rates and holidays with the rate card
# ---------------------------------------------------------------------------
def _f3_source(c):
    src = _project(c, "F3 source synthetic")
    sup = _ok(c.post(f"/api/p/{src}/resources", json={"kind": "supplier", "code": "S30X", "name": "Synthetic Sparks"}))["id"]
    _ok(c.post(f"/api/p/{src}/supplier-rates", json={"resource_id": sup, "role": "Electrician", "unit": "hour", "rate": 95,
                                                      "ot_rate": 140, "nt_hours": 8, "allowance": 60}))
    for d in ("25/12/2026", "26/01/2027"):
        _ok(c.post(f"/api/p/{src}/holidays", json={"day": d, "name": "Synthetic"}))
    return src, sup


def test_f3_clone_with_rate_card_copies_rates_and_holidays(blank):
    c = _client()
    src, sup = _f3_source(c)
    dst = _ok(c.post("/api/projects", json={"name": "F3 clone", "from_template_id": src, "include": {"resources": True, "rate_card": True}}))["id"]
    rates = _ok(c.get(f"/api/p/{dst}/supplier-rates"))
    assert len(rates) == 1
    r = rates[0]
    assert (r["role"], r["unit"], r["rate"], r["ot_rate"], r["nt_hours"], r["allowance"], r["code"]) == ("Electrician", "hour", 95, 140, 8, 60, "S30X")
    dst_sup = [x for x in _ok(c.get(f"/api/p/{dst}/resources")) if x["code"] == "S30X"]
    assert len(dst_sup) == 1 and r["resource_id"] == dst_sup[0]["id"] and r["resource_id"] != sup
    assert sorted(h["day"] for h in _ok(c.get(f"/api/p/{dst}/holidays"))) == ["2026-12-25", "2027-01-26"]
    # the source is untouched
    assert len(_ok(c.get(f"/api/p/{src}/supplier-rates"))) == 1
    assert len(_ok(c.get(f"/api/p/{src}/holidays"))) == 2


def test_f3_clone_resources_only_copies_neither(blank):
    c = _client()
    src, _ = _f3_source(c)
    dst = _ok(c.post("/api/projects", json={"name": "F3 clone res", "from_template_id": src, "include": {"resources": True}}))["id"]
    assert _ok(c.get(f"/api/p/{dst}/supplier-rates")) == []
    assert _ok(c.get(f"/api/p/{dst}/holidays")) == []
    assert [x["code"] for x in _ok(c.get(f"/api/p/{dst}/resources")) if x["code"] == "S30X"] == ["S30X"]


# ---------------------------------------------------------------------------
# F4: upload suggests links instead of creating them
# ---------------------------------------------------------------------------
CSV_F4 = "WBS,Name,Start,Finish\n1.1,Earthworks,01/11/2026,31/01/2027\n1.2,Fencing,01/12/2026,28/02/2027\n1.3,Site start,10/11/2026,10/11/2026\n"


def _f4_setup(c):
    pid = _project(c, "F4 synthetic", project_start="01/01/2026", project_end="30/06/2027")
    grp = _group(c, pid, "PS04")
    ew = _node(c, pid, parent_id=grp, code="PS04.001", name="Earthworks", kind="line")
    fe = _node(c, pid, parent_id=grp, code="PS04.002", name="Fencing", kind="line")
    return pid, ew, fe


def _linked(c, pid):
    l = _ok(c.get(f"/api/p/{pid}/programme/links"))
    return {s["node_id"] for s in l["span"]} | {a["node_id"] for a in l["anchors"]}


def test_f4_upload_suggests_and_links_nothing(blank):
    c = _client()
    pid, ew, fe = _f4_setup(c)
    before = (_node_dates(blank, ew), _node_dates(blank, fe))
    r = _upload(c, pid, CSV_F4)
    assert r["auto_linked"] == 0
    sug = r["suggestions"]
    assert len(sug) == 2 and all(s["kind"] == "node" for s in sug)
    assert sorted(s["target_id"] for s in sug) == sorted([ew, fe])
    assert _linked(c, pid) == set()
    assert (_node_dates(blank, ew), _node_dates(blank, fe)) == before
    assert len(_ok(c.get(f"/api/p/{pid}/programme/suggestions"))) == 2


def test_f4_accept_one_reject_other_and_not_offered_again(blank):
    c = _client()
    pid, ew, fe = _f4_setup(c)
    sug = {s["target_id"]: s for s in _upload(c, pid, CSV_F4)["suggestions"]}
    item = lambda s: {"task_id": s["task_id"], "kind": s["kind"], "target_id": s["target_id"]}
    _ok(c.post(f"/api/p/{pid}/programme/suggestions/accept", json={"items": [item(sug[ew])]}))
    assert _linked(c, pid) == {ew}
    assert _node_dates(blank, ew) == ("2026-11-01", "2027-01-31")
    fe_before = _node_dates(blank, fe)
    _ok(c.post(f"/api/p/{pid}/programme/suggestions/reject", json={"items": [item(sug[fe])]}))
    assert _linked(c, pid) == {ew}
    assert _node_dates(blank, fe) == fe_before
    assert _ok(c.get(f"/api/p/{pid}/programme/suggestions")) == []
    r = _upload(c, pid, CSV_F4)                          # same file again
    assert r["auto_linked"] == 0
    assert [s for s in r["suggestions"] if s["target_id"] == fe] == []
    assert _linked(c, pid) == {ew}                      # the accepted link survived the re-upload
    assert _node_dates(blank, fe) == fe_before


def test_f4_accept_all_on_fresh_upload(blank):
    c = _client()
    pid, ew, fe = _f4_setup(c)
    _upload(c, pid, CSV_F4)
    _ok(c.post(f"/api/p/{pid}/programme/suggestions/accept", json={"all": True}))
    assert _linked(c, pid) == {ew, fe}
    assert _node_dates(blank, ew) == ("2026-11-01", "2027-01-31")
    assert _node_dates(blank, fe) == ("2026-12-01", "2027-02-28")
    assert _ok(c.get(f"/api/p/{pid}/programme/suggestions")) == []
