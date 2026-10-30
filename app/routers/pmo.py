"""PMO and Reporting routes: portfolio and linked projects, gates and phases, lifecycle log, project library, close-out, dashboard, margin bridge, PMR, EOM report, snapshots and audit."""
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from .. import (checklists, knowledge, gates, linking, library, portfolio, eom_report, db, identity, engine,
                exporters, reports, revenue, services)

from ._shared import J, _xlsx, get_con, need_project

router = APIRouter(default_response_class=J)


# ---- linked projects: child -> parent project (-> portfolio -> program) -------------------------------------------------
@router.post("/api/links")
def link_projects(body: dict, con=Depends(get_con)):
    """Link projects under a parent: a new parent ({name, ids, director}) or more children for one ({parent_id, ids})."""
    pid = linking.link(con, body.get("name"), body.get("ids") or [], body.get("director"), body.get("parent_id"))
    return {"id": pid}


@router.post("/api/projects/{pid}/unlink")
def unlink_project(pid: int, con=Depends(get_con)):
    need_project(con, pid)
    return {"parent_id": linking.unlink(con, pid)}


@router.get("/api/p/{pid}/linked")
def linked(pid: int, con=Depends(get_con)):
    """A parent: its children with their figures. A child: its parent and siblings. Otherwise: projects it could link with."""
    p = need_project(con, pid)
    pr = lambda x: dict(id=x["id"], name=x["name"], code=x.get("code"), client=x.get("client_name"), pm=x.get("epec_pm"),
                        director=x.get("project_director"), status_date=x.get("status_date"), parent_id=x.get("parent_project_id"))
    out = dict(project=pr(p), is_parent=bool(p.get("is_parent")), parent=None, children=[], candidates=[])
    if p.get("is_parent"):
        res = engine.compute(con, pid)
        figs = {c["id"]: c for c in res["children"]}
        out["children"] = [dict(pr(c), **{k: figs.get(c["id"], {}).get(k) for k in ("allowance", "ctd", "acc", "ctc", "eac", "contingency", "status_month", "error")},
                                revenue=revenue.summary(con, c["id"])["recognised"]) for c in linking.children(con, pid)]
        out["total"] = {k: res["total"][k] for k in ("allowance", "ctd", "acc", "ctc", "eac", "contingency")}
    elif p.get("parent_project_id"):
        par = db.one(con, "SELECT * FROM project WHERE id=?", (p["parent_project_id"],))
        out["parent"] = pr(par) if par else None
        out["children"] = [pr(c) for c in linking.children(con, p["parent_project_id"])]
    free = "archived_at IS NULL AND COALESCE(is_template,0)=0 AND COALESCE(is_parent,0)=0 AND parent_project_id IS NULL"
    out["candidates"] = [pr(c) for c in db.rows(con, f"SELECT * FROM project WHERE {free} AND id!=? ORDER BY name", (pid,))]
    out["parents"] = [pr(c) for c in db.rows(con, "SELECT * FROM project WHERE COALESCE(is_parent,0)=1 AND archived_at IS NULL ORDER BY name")]
    return out


@router.get("/api/rollup")
def rollup(ids: str = "", months: int = 0, con=Depends(get_con)):
    """The CBS of several projects lumped together (a PM's portfolio or a director's program), each row with its
    projects' shares (by_project) to drill into."""
    res = portfolio.rollup(con, [int(x) for x in ids.split(",") if x.strip().isdigit()])
    if not months:
        res = dict(res, rows=[{k: v for k, v in r.items() if k not in ("a", "x", "f")} for r in res["rows"]])
    return res


@router.get("/api/portfolio")
def project_portfolio(con=Depends(get_con)):
    """The running projects with their figures and monthly series: the Portfolio page filters them by person."""
    return portfolio.run(con)


@router.get("/api/gates")
def gates_catalogue():
    return {"gates": gates.catalogue(), "stages": list(gates.STAGES)}


@router.get("/api/gates/{gate}/form")
def gate_form(gate: int):
    """Download the gate's paper (EPEC's Word form)."""
    f = gates.form_file(gate)
    if not f:
        raise HTTPException(404, f"No paper has been loaded for Gate {gate} yet")
    return FileResponse(f, filename=f.name, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.get("/api/phases")
def phases_catalogue():
    return {"phases": gates.phase_catalogue()}


@router.get("/api/forms/{code}")
def review_form(code: str):
    """Download a readiness review checklist or the site start up agenda (EPEC's Word forms)."""
    f = gates.review_form(code)
    if not f:
        raise HTTPException(404, f"No paper has been loaded for {code}")
    return FileResponse(f, filename=f.name, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.get("/api/p/{pid}/phases")
def phases_list(pid: int, con=Depends(get_con)):
    need_project(con, pid)
    rows = gates.phase_log(con, pid)
    return {"rows": rows, "current": gates.phase_current(rows), "phases": gates.phase_catalogue()}


@router.post("/api/p/{pid}/phases")
def phases_add(pid: int, body: dict, con=Depends(get_con)):
    """The PM moves the project to a delivery phase (Design, Procure, Construct, Commission, Close Out)."""
    need_project(con, pid)
    try:
        gates.phase_add(con, pid, body.get("phase"), body.get("date"), body.get("note"), (identity.current() or {}).get("name"), body.get("end_date"))
    except (ValueError, TypeError) as e:
        raise services.Problem(str(e))
    return {"ok": True}


@router.put("/api/p/{pid}/phases/{rid}")
def phases_update(pid: int, rid: int, body: dict, con=Depends(get_con)):
    """Correct the start, end and note of a recorded delivery phase."""
    need_project(con, pid)
    try:
        gates.phase_update(con, pid, rid, body.get("date"), body.get("end_date"), body.get("note"))
    except (ValueError, TypeError) as e:
        raise services.Problem(str(e))
    return {"ok": True}


@router.get("/api/p/{pid}/lifecycle-log")
def stage_list(pid: int, con=Depends(get_con)):
    need_project(con, pid)
    rows = gates.stage_log(con, pid)
    return {"rows": rows, "current": gates.stage_current(rows)}


@router.post("/api/p/{pid}/lifecycle-log")
def stage_post(pid: int, body: dict, con=Depends(get_con)):
    """The PM records a lifecycle stage (Handover, Setup, Delivery, Close Out, Warranty) with its start, end and note."""
    need_project(con, pid)
    try:
        return {"id": gates.stage_add(con, pid, body.get("stage"), body.get("date"), body.get("note"), (identity.current() or {}).get("name"), body.get("end_date"))}
    except (ValueError, TypeError) as e:
        raise services.Problem(str(e))


@router.put("/api/p/{pid}/lifecycle-log/{rid}")
def stage_put(pid: int, rid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    try:
        gates.stage_update(con, pid, rid, body.get("date"), body.get("end_date"), body.get("note"))
    except (ValueError, TypeError) as e:
        raise services.Problem(str(e))
    return {"ok": True}


@router.delete("/api/p/{pid}/lifecycle-log/{rid}")
def stage_delete(pid: int, rid: int, con=Depends(get_con)):
    need_project(con, pid)
    con.execute("DELETE FROM lifecycle_log WHERE id=? AND project_id=?", (rid, pid))
    return {"ok": True}


@router.delete("/api/p/{pid}/phases/{rid}")
def phases_delete(pid: int, rid: int, con=Depends(get_con)):
    con.execute("DELETE FROM phase_log WHERE id=? AND project_id=?", (rid, pid))
    return {"ok": True}


@router.get("/api/p/{pid}/gates")
def gates_list(pid: int, con=Depends(get_con)):
    need_project(con, pid)
    rows = gates.log(con, pid)
    return {"rows": rows, "current": gates.current(rows), "gates": gates.catalogue(), "stages": list(gates.STAGES)}


@router.post("/api/p/{pid}/gates")
def gates_add(pid: int, body: dict, con=Depends(get_con)):
    """Record that the project is at a gate (any of 1 to 7, so it can move back as well as on)."""
    need_project(con, pid)
    try:
        gates.add(con, pid, body.get("gate"), body.get("date"), body.get("stage"), body.get("note"), (identity.current() or {}).get("name"))
    except (ValueError, TypeError) as e:
        raise services.Problem(str(e))
    return {"ok": True}


@router.delete("/api/p/{pid}/gates/{gid}")
def gates_delete(pid: int, gid: int, con=Depends(get_con)):
    con.execute("DELETE FROM gate_log WHERE id=? AND project_id=?", (gid, pid))
    return {"ok": True}


@router.get("/api/library")
def project_library(con=Depends(get_con)):
    """The project library: archived projects with their figures at archiving, for searching."""
    return library.listing(con)


@router.post("/api/projects/{pid}/template")
def mark_template(pid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    db.update(con, "project", pid, {"is_template": 1 if body.get("value") else 0})
    return {"ok": True}


@router.get("/api/p/{pid}/close-out")
def close_out(pid: int, con=Depends(get_con)):
    need_project(con, pid)
    return checklists.close_out(con, pid)


@router.post("/api/p/{pid}/close-out/tick")
def close_out_tick(pid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    try:
        checklists.tick(con, pid, body.get("key"), bool(body.get("done")), (identity.current() or {}).get("name"))
    except ValueError as e:
        raise services.Problem(str(e))
    return checklists.close_out(con, pid)


# ---------------------------------------------------------------------------
# Project library (PMO): knowledge documents
# ---------------------------------------------------------------------------
@router.get("/api/kb")
def kb_list(con=Depends(get_con)):
    return {"docs": knowledge.listing(con), "types": knowledge.TYPES, "phases": knowledge.PHASES, "project_types": knowledge.PROJECT_TYPES, "gates": gates.catalogue()}


@router.post("/api/kb")
async def kb_add(file: UploadFile = File(...), title: str = Form(""), doc_type: str = Form("Other"), phase: str = Form(""), gate: str = Form(""),
                 description: str = Form(""), project_type: str = Form(""), con=Depends(get_con)):
    try:
        return {"id": knowledge.add(con, await file.read(), file.filename or "document", title, doc_type, phase, gate, description, (identity.current() or {}).get("name"), project_type)}
    except ValueError as e:
        raise services.Problem(str(e))


@router.put("/api/kb/{did}")
def kb_update(did: int, body: dict, con=Depends(get_con)):
    try:
        knowledge.update(con, did, body)
    except ValueError as e:
        raise services.Problem(str(e))
    return {"ok": True}


@router.delete("/api/kb/{did}")
def kb_delete(did: int, con=Depends(get_con)):
    con.execute("DELETE FROM kb_doc WHERE id=?", (did,))
    return {"ok": True}


@router.get("/api/kb/download-all")
def kb_download_all(con=Depends(get_con)):
    """All library documents and the blank setup templates in one zip."""
    return Response(knowledge.bundle(con), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="EPEC-project-library.zip"'})


@router.get("/api/kb/{did}/file")
def kb_file(did: int, con=Depends(get_con)):
    f = knowledge.file_of(con, did)
    if not f:
        raise HTTPException(404, "Document not found")
    return Response(f["data"], media_type=f["mime"] or "application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{f["filename"]}"'})


@router.get("/api/p/{pid}/lifecycle/documents")
def lifecycle_documents(pid: int, con=Depends(get_con)):
    need_project(con, pid)
    return knowledge.relevant(con, pid)


@router.get("/api/p/{pid}/dashboard")
def dashboard(pid: int, node: str = None, frm: str = None, to: str = None, con=Depends(get_con)):
    need_project(con, pid)
    return reports.dashboard(con, pid, node, frm, to)


@router.get("/api/p/{pid}/margin-bridge")
def margin_bridge(pid: int, con=Depends(get_con)):
    """Why the forecast profit differs from the original: revenue, allowance and the overruns and underruns behind it."""
    need_project(con, pid)
    return reports.margin_bridge(con, pid)


@router.get("/api/p/{pid}/flows")
def flows(pid: int, node: str = None, con=Depends(get_con)):
    need_project(con, pid)
    return reports.flows(con, pid, node)


@router.get("/api/p/{pid}/health")
def health(pid: int, con=Depends(get_con)):
    return reports.health(con, pid)


@router.get("/api/p/{pid}/reconcile")
def reconcile(pid: int, con=Depends(get_con)):
    return reports.reconcile(con, pid)


@router.post("/api/p/{pid}/cmt")
def cmt_save(pid: int, body: dict, con=Depends(get_con)):
    return {"id": db.insert(con, "cmt_entry", dict(project_id=pid, as_of=db.iso(body.get("as_of")), revenue=float(body.get("revenue") or 0),
                                                   eac=float(body.get("eac") or 0), ctd=float(body.get("ctd") or 0), note=body.get("note")))}


@router.get("/api/p/{pid}/pmr")
def pmr(pid: int, con=Depends(get_con)):
    return reports.pmr(con, pid)


@router.get("/api/p/{pid}/pmr.xlsx")
def pmr_xlsx(pid: int, con=Depends(get_con)):
    return _xlsx(exporters.pmr_xlsx(con, pid), "pmr-output.xlsx")


@router.get("/api/p/{pid}/eom-report")
def eom_json(pid: int, hide_zero: int = 1, revision: str = None, con=Depends(get_con)):
    return eom_report.build(con, pid, revision or None, bool(hide_zero))


def _eom_name(d, ext):
    return f"EOM-report_{d['header']['number'] or 'project'}_{d['header']['status_month']}_rev{d['header']['revision']}.{ext}".replace(" ", "-")


@router.get("/api/p/{pid}/eom-report.xlsx")
def eom_xlsx(pid: int, hide_zero: int = 1, revision: str = None, con=Depends(get_con)):
    d = eom_report.build(con, pid, revision or None, bool(hide_zero))
    return _xlsx(eom_report.xlsx(d), _eom_name(d, "xlsx"))


@router.get("/api/p/{pid}/eom-report.pdf")
def eom_pdf(pid: int, hide_zero: int = 1, revision: str = None, con=Depends(get_con)):
    d = eom_report.build(con, pid, revision or None, bool(hide_zero))
    return Response(eom_report.pdf(d), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{_eom_name(d, "pdf")}"'})


@router.get("/api/p/{pid}/cost-control.xlsx")
def cc_xlsx(pid: int, con=Depends(get_con)):
    return _xlsx(exporters.cost_control_xlsx(con, pid), "cost-control.xlsx")


@router.get("/api/p/{pid}/snapshots")
def snaps(pid: int, con=Depends(get_con)):
    return db.rows(con, "SELECT id, period, label, kind, status_date, created_at, summary_json FROM snapshot WHERE project_id=? ORDER BY period DESC, id DESC", (pid,))


@router.post("/api/p/{pid}/snapshots")
def snap_create(pid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    return {"id": reports.create_snapshot(con, pid, body.get("label"), "eom")}


@router.delete("/api/p/{pid}/snapshots/{sid}")
def snap_delete(pid: int, sid: int, con=Depends(get_con)):
    con.execute("DELETE FROM snapshot WHERE id=? AND project_id=?", (sid, pid))
    return {"ok": True}


@router.get("/api/p/{pid}/snapshots/{sid}")
def snap_get(pid: int, sid: int, con=Depends(get_con)):
    s = db.one(con, "SELECT * FROM snapshot WHERE id=? AND project_id=?", (sid, pid))
    if not s:
        raise HTTPException(404)
    s["summary"] = json.loads(s.pop("summary_json") or "{}")
    s["curve"] = json.loads(s.pop("curve_json") or "{}")
    return s


@router.get("/api/p/{pid}/snapshots-compare")
def snap_compare(pid: int, a: str, b: str = "live", con=Depends(get_con)):
    return reports.snapshot_compare(con, pid, a, b)


@router.get("/api/p/{pid}/snapshots-series")
def snap_series(pid: int, a: str, b: str = "live", code: str = None, con=Depends(get_con)):
    return reports.snapshot_series(con, pid, a, b, code)


@router.get("/api/p/{pid}/snapshots-curves")
def snap_curves(pid: int, a: str, b: str = "live", con=Depends(get_con)):
    return reports.snapshot_curves(con, pid, a, b)


@router.get("/api/p/{pid}/audit")
def audit(pid: int, con=Depends(get_con)):
    return db.rows(con, "SELECT * FROM audit_log WHERE project_id=? ORDER BY id DESC LIMIT 200", (pid,))
