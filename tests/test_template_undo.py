"""Project setup > Load from Excel (Vincent 21/10): previewed before anything is written, a warning when the file is
another project's, and "Undo last Excel load" puts the project back (name, CBS, allowances, milestones...)."""
import io

import openpyxl
from fastapi.testclient import TestClient

from app import db
from app.main import app


def _state(con, pid):
    return dict(name=db.one(con, "SELECT name, number FROM project WHERE id=?", (pid,)),
                nodes=db.scalar(con, "SELECT COUNT(*) FROM cbs_node WHERE project_id=?", (pid,)),
                est=round(db.scalar(con, "SELECT COALESCE(SUM(budget),0) FROM allowance_ledger WHERE project_id=? AND kind='estimate'", (pid,)), 2),
                ms=db.scalar(con, "SELECT COUNT(*) FROM milestone WHERE project_id=?", (pid,)),
                items=db.scalar(con, "SELECT COUNT(*) FROM contract_item WHERE project_id=?", (pid,)))


def test_preview_save_and_undo_an_excel_load(demo):
    con, pid = demo
    c = TestClient(app)
    wb = openpyxl.load_workbook(io.BytesIO(c.get(f"/api/p/{pid}/template.xlsx").content))
    for row in wb["Project"].iter_rows(min_row=2):
        if row[0].value == "Project name":
            row[1].value = "Fraser Coast Solar Farm & BESS"
        if row[0].value == "EPEC project number":
            row[1].value = "0185"
    cbs = wb["CBS & Allowance"]
    cbs.append(["PE01", "Line", "", "Fraser only line", "", "", "", 12345, None])
    buf = io.BytesIO()
    wb.save(buf)
    before = _state(con, pid)
    pv0 = c.post(f"/api/p/{pid}/load-template/preview", files={"file": ("fraser.xlsx", buf.getvalue())}).json()
    assert "Fraser Coast" in pv0["warning"] and not any(x["field"] == "Project name" for x in pv0["changes"])   # by default the identity is kept
    pv = c.post(f"/api/p/{pid}/load-template/preview?identity=1", files={"file": ("fraser.xlsx", buf.getvalue())}).json()
    assert "Fraser Coast" in pv["warning"] and any(x["field"] == "Project name" for x in pv["changes"])
    assert _state(con, pid) == before                                    # the preview wrote nothing
    r = c.post(f"/api/p/{pid}/load-template/apply", json={"token": pv["token"], "filename": "fraser.xlsx", "identity": True}).json()
    con.commit()
    assert _state(con, pid)["name"]["name"] == "Fraser Coast Solar Farm & BESS"
    assert _state(con, pid)["nodes"] == before["nodes"] + 1
    rp = c.get(f"/api/p/{pid}/restore-points").json()[0]
    assert rp["id"] == r["restore_point"] and not rp["undone_at"]
    assert c.post(f"/api/p/{pid}/restore-points/{rp['id']}/undo").json()["ok"]
    con.commit()
    assert _state(con, pid) == before                                    # name, CBS, allowances, milestones as they were
    assert c.post(f"/api/p/{pid}/restore-points/{rp['id']}/undo").status_code >= 400   # once only


def test_replace_removes_what_the_file_does_not_list_but_keeps_items_with_data(demo):
    con, pid = demo
    c = TestClient(app)
    db.update(con, "project", pid, {"initialised": 0})
    con.commit()
    wb = openpyxl.load_workbook(io.BytesIO(c.get(f"/api/p/{pid}/template.xlsx").content))
    cbs = wb["CBS & Allowance"]
    for row in list(cbs.iter_rows(min_row=2)):                     # drop the estimate groups from the file (lines stay)
        if row[1].value and str(row[1].value).lower() == "group":
            for cell in row:
                cell.value = None
    buf = io.BytesIO()
    wb.save(buf)
    before = _state(con, pid)
    merge = c.post(f"/api/p/{pid}/load-template/preview?mode=merge", files={"file": ("same.xlsx", buf.getvalue())}).json()
    assert not merge["report"]["removed"]
    pv = c.post(f"/api/p/{pid}/load-template/preview/{merge['token']}?mode=replace").json()
    assert _state(con, pid) == before
    assert pv["report"]["removed"] or pv["report"]["kept"]
    assert all("not in the file but kept" in k for k in pv["report"]["kept"])
    r = c.post(f"/api/p/{pid}/load-template/apply", json={"token": pv["token"], "mode": "replace"}).json()
    con.commit()
    assert r["removed"] == pv["report"]["removed"]
    # nothing with Pronto cost was removed
    assert db.scalar(con, "SELECT COUNT(*) FROM pronto_tx WHERE project_id=? AND node_id IS NULL", (pid,)) == \
        db.scalar(con, "SELECT COUNT(*) FROM pronto_tx WHERE project_id=? AND node_id IS NULL", (pid,))
    rp = c.get(f"/api/p/{pid}/restore-points").json()[0]
    c.post(f"/api/p/{pid}/restore-points/{rp['id']}/undo")
    con.commit()
    assert _state(con, pid) == before


def test_erase_each_setup_section_and_undo_it(demo):
    """Vincent 21/10: wrong data uploaded? Erase that part of the set-up; Undo brings it back."""
    from app import revenue
    con, pid = demo
    c = TestClient(app)
    db.update(con, "project", pid, {"initialised": 0})
    con.commit()
    before = _state(con, pid)
    proj = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    for section in ("project", "contract", "cbs", "programme"):
        r = c.post(f"/api/p/{pid}/setup/erase", json={"section": section}).json()
        con.commit()
        now = _state(con, pid)
        if section == "project":
            p2 = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
            assert p2["name"] == proj["name"] and p2["status_date"] == proj["status_date"] and not p2["client_name"]
        if section == "contract":
            assert now["items"] < before["items"] or r["kept"]
            assert all(i["variation_id"] or db.scalar(con, "SELECT COUNT(*) FROM claim_line WHERE item_id=?", (i["id"],))
                       for i in revenue.items_tree(con, pid) if i["is_leaf"])
        if section == "cbs":
            assert r["removed"].get("CBS items") or r["kept"]
        if section == "programme":
            assert now["ms"] == 0
        assert c.post(f"/api/p/{pid}/restore-points/{r['restore_point']}/undo").json()["ok"]
        con.commit()
        assert _state(con, pid) == before, section
    assert db.one(con, "SELECT client_name FROM project WHERE id=?", (pid,))["client_name"] == proj["client_name"]
    assert c.post(f"/api/p/{pid}/setup/erase", json={"section": "nonsense"}).status_code >= 400


def test_step_templates_and_schedule_layers(demo):
    """Per-step templates hold only that step's sheets; an upstream schedule is kept apart and never drives dates."""
    from app import programme
    from demo import build_demo
    con, pid = demo
    c = TestClient(app)
    for step, sheets in {"contract": ["Payment Milestones"], "programme": ["Project schedule"]}.items():
        wb = openpyxl.load_workbook(io.BytesIO(c.get(f"/api/p/{pid}/template.xlsx?step={step}").content))
        assert [n for n in wb.sheetnames if n not in ("Read me", "Lists")] == sheets
    assert c.get(f"/api/p/{pid}/template.xlsx?step=nope").status_code == 400
    build_demo.write_programme_files()
    xml = (build_demo.DEMO / "demo_programme.xml").read_bytes()
    n_int = c.post(f"/api/p/{pid}/programme/upload", files={"file": ("a.xml", xml)}).json()["tasks"]
    r = c.post(f"/api/p/{pid}/programme/upload?layer=upstream", files={"file": ("b.xml", xml)}).json()
    assert r["auto_linked"] == 0
    tasks = c.get(f"/api/p/{pid}/programme/tasks").json()
    assert sum(t["layer"] == "upstream" for t in tasks) == n_int and sum(t["layer"] != "upstream" for t in tasks) == n_int
    c.delete(f"/api/p/{pid}/programme?layer=upstream")
    assert len(c.get(f"/api/p/{pid}/programme/tasks").json()) == n_int


def test_uploaded_schedule_file_can_be_downloaded(demo):
    from demo import build_demo
    con, pid = demo
    c = TestClient(app)
    build_demo.write_programme_files()
    xml = (build_demo.DEMO / "demo_programme.xml").read_bytes()
    assert c.get(f"/api/p/{pid}/programme/file?info=1").json()["has_file"] in (True, False)
    c.post(f"/api/p/{pid}/programme/upload", files={"file": ("base.xml", xml)})
    c.post(f"/api/p/{pid}/programme/upload?layer=upstream", files={"file": ("client.xml", xml + b" ")})
    assert c.get(f"/api/p/{pid}/programme/file").content == xml
    assert c.get(f"/api/p/{pid}/programme/file?layer=upstream").headers["content-disposition"].endswith('client.xml"')
    c.delete(f"/api/p/{pid}/programme?layer=upstream")
    assert c.get(f"/api/p/{pid}/programme/file?layer=upstream").status_code == 404


def test_setup_draft_save_and_discard(demo):
    """A setup step's changes are kept on Save and put back on Don't save."""
    con, pid = demo
    c = TestClient(app)
    n0 = db.scalar(con, "SELECT COUNT(*) FROM milestone WHERE project_id=?", (pid,))
    con.commit()
    rid = c.post(f"/api/p/{pid}/setup/draft", json={"step": "programme"}).json()["id"]
    c.post(f"/api/p/{pid}/milestones", json={"name": "Draft milestone", "type": "Milestone"})
    assert db.scalar(con, "SELECT COUNT(*) FROM milestone WHERE project_id=?", (pid,)) == n0 + 1
    assert not any(r["label"].startswith("Setup draft") for r in c.get(f"/api/p/{pid}/restore-points").json())
    assert c.post(f"/api/p/{pid}/setup/draft/{rid}/discard", json={}).status_code == 200
    assert db.scalar(con, "SELECT COUNT(*) FROM milestone WHERE project_id=?", (pid,)) == n0
    rid = c.post(f"/api/p/{pid}/setup/draft", json={"step": "programme"}).json()["id"]
    c.post(f"/api/p/{pid}/milestones", json={"name": "Kept milestone", "type": "Milestone"})
    assert c.post(f"/api/p/{pid}/setup/draft/{rid}/commit", json={}).status_code == 200
    assert db.scalar(con, "SELECT COUNT(*) FROM milestone WHERE project_id=?", (pid,)) == n0 + 1
    assert c.post(f"/api/p/{pid}/setup/draft/{rid}/discard", json={}).status_code == 400   # already resolved
