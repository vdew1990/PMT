"""Platform routes: reference data, who is using the app, help, sync, activity and history, Pronto and CMT data load, diagnostics, menu and tile preferences, demonstration data."""
import json
import re
import secrets
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from .. import (complexity, cmt_import, build, pronto_raw, help as help_mod, diagnostics, accruals, activity, db,
                identity, sync, pronto, services)
from ..taxonomy import (ACCRUAL_REASONS, CLAIM_STATUS, CLIENT_STATUS, CONTRACT_STATUS, EPEC_STATUS, FREQUENCIES,
                        GP_GROUP, GRANDPARENTS, METHODS, PARENTS, PRICING_MODELS, SPREAD_MODES, SPREAD_NOTES,
                        FORECAST_BASIS, ROSTER_PATTERNS, MILESTONE_PRESETS)

from ._shared import J, UPLOADS, _rm, get_con, need_project

router = APIRouter(default_response_class=J)


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
@router.get("/api/taxonomy")
def taxonomy():
    return dict(grandparents=GRANDPARENTS, parents=PARENTS, gp_group=GP_GROUP, methods=METHODS, spreads=SPREAD_MODES, spread_notes=SPREAD_NOTES,
                basis=FORECAST_BASIS, patterns=ROSTER_PATTERNS, milestone_presets=MILESTONE_PRESETS,
                frequencies=FREQUENCIES, client_status=CLIENT_STATUS, epec_status=EPEC_STATUS, contract_status=CONTRACT_STATUS,
                pricing_models=PRICING_MODELS, claim_status=CLAIM_STATUS, accrual_reasons=ACCRUAL_REASONS)


# ---------------------------------------------------------------------------
# Who is using the app, sharing status, history
# ---------------------------------------------------------------------------
@router.get("/api/me")
def whoami(con=Depends(get_con)):
    return dict(**sync.me(con), sync=_sync_status(), build=build.STARTED, build_now=build.on_disk(max_age=20), release=build.RELEASE)


@router.post("/api/shutdown")
def shutdown(request: Request):
    """Stop this server cleanly. Used by the launcher to replace a server started before the files were updated.
    Only from this PC, and only with the X-PMT header (a web page elsewhere cannot send it without permission)."""
    if (request.client.host if request.client else "") not in ("127.0.0.1", "::1") or request.headers.get("x-pmt") != "1":
        raise HTTPException(403)
    if build.SERVER is None:
        raise HTTPException(409, "This server was not started by PMT's launcher")
    build.SERVER.should_exit = True
    return {"ok": True}


@router.get("/api/help/ask")
def help_ask(q: str = "", page: str = ""):
    """The chat panel's built-in guide: the best answer for a question, related topics, and the page's own topic."""
    r = help_mod.answer(q, page or None) if q.strip() else dict(answer=None, related=[])
    return dict(**r, page=page, page_name=help_mod.PAGES.get(page), page_topic=help_mod.page_topic(page), suggestions=help_mod.suggestions(page))


@router.get("/api/help/topic/{tid}")
def help_topic(tid: str):
    t = next((t for t in help_mod.topics() if t["id"] == tid), None)
    if not t:
        raise HTTPException(404, "No such topic")
    return t


@router.get("/api/help/guide.md")
def help_guide():
    return Response(help_mod.guide_md(), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="PMT_user_guide.md"'})


@router.put("/api/me/prefs")
def set_my_prefs(body: dict, con=Depends(get_con)):
    return sync.set_prefs(con, body.get("prefs") or {})


@router.put("/api/me")
def set_me(body: dict, con=Depends(get_con)):
    sync.set_role(con, body.get("role"), body.get("name"), body.get("entity"))
    return sync.me(con)


def _sync_status():
    s = {k: v for k, v in sync.status.items()}
    if sync.enabled():
        s["writers"] = sorted(sync.writers().values(), key=lambda w: w.get("last_seen") or "", reverse=True)
    return s


@router.get("/api/sync")
def sync_status():
    return _sync_status()


@router.post("/api/sync/now")
def sync_run():
    if not sync.enabled():
        raise services.Problem("This copy is not sharing. Put the program in a synced SharePoint folder that contains a 'shared' folder.")
    sync.sync_now()
    return _sync_status()


@router.post("/api/sync/publish")
async def sync_publish(file: UploadFile = File(...)):
    if not sync.enabled():
        raise services.Problem("Publishing is only for a shared folder.")
    tmp = UPLOADS / f"publish-{secrets.token_hex(6)}.db"
    tmp.write_bytes(await file.read())
    try:
        n = sync.publish_existing(tmp)
    finally:
        _rm(tmp)
    sync.sync_now()
    return {"rows": n}


@router.get("/api/p/{pid}/activity")
def project_activity(pid: int, user: str = None, tbl: str = None, q: str = None, limit: int = 300, before: int = None, con=Depends(get_con)):
    need_project(con, pid)
    return dict(rows=[r for r in activity.activity(con, pid, user, tbl, q, limit, before) if r.get("tbl") != "cx_baseline" or complexity.DIRECTOR.search(sync.me(con).get("role") or "")], people=list(sync.people(con).values()),
                tables=activity.LABEL)


@router.get("/api/p/{pid}/history")
def record_history(pid: int, tbl: str, id: int, con=Depends(get_con)):
    if tbl not in activity.LABEL:
        raise services.Problem("Unknown record type")
    return activity.row_history(con, pid, tbl, id)


# ---------------------------------------------------------------------------
# Pronto
# ---------------------------------------------------------------------------
@router.put("/api/p/{pid}/pronto/project")
def pronto_set_project(pid: int, body: dict, con=Depends(get_con)):
    """The project's code in Pronto: uploads for any other project code are flagged before they are loaded."""
    need_project(con, pid)
    s = db.project_settings(con, pid)
    code = str(body.get("code") or "").strip()[:40]
    if code:
        s["pronto_project"] = code
    else:
        s.pop("pronto_project", None)
    db.update(con, "project", pid, {"settings_json": json.dumps(s)})
    return {"code": code}


@router.post("/api/p/{pid}/pronto/analyse")
async def pronto_analyse(pid: int, file: UploadFile = File(...), con=Depends(get_con)):
    need_project(con, pid)
    token = secrets.token_hex(8)
    suffix = Path(file.filename or "").suffix.lower() or ".xlsx"
    if suffix not in (".xlsx", ".xlsm", ".ods", ".csv"):
        raise services.Problem("Upload an .xlsx, .xlsm, .ods or .csv file exported from Pronto")
    path = UPLOADS / f"{token}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    found = pronto.analyse(path)
    if not found:
        _rm(path)
        raise services.Problem("No Pronto export recognised in that file. Expected GL transactions, labour timesheets, purchase orders, claims, variations or CTD overview.")
    s = db.project_settings(con, pid)
    for item in found:
        item["projects"] = pronto.project_codes(path, item["sheet"], item["kind"], item["header_row"])
        item["default_project"] = s.get("pronto_project") or (max(item["projects"], key=item["projects"].get) if item["projects"] else None)
    codes = {c for item in found for c in (item.get("projects") or {})}
    return dict(token=token, filename=file.filename, sheets=found, warning=pronto.wrong_project_warning(con, pid, codes))


@router.post("/api/p/{pid}/pronto/commit")
def pronto_commit(pid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    token = re.sub(r"[^a-f0-9]", "", body.get("token", ""))
    matches = list(UPLOADS.glob(f"{token}.*"))
    if not matches:
        raise services.Problem("Upload expired. Please upload the file again.")
    path = matches[0]
    results = []
    for it in body.get("items", []):
        results.append(pronto.import_sheet(con, pid, path, body.get("filename") or path.name, it["sheet"], it["kind"], it["header_row"],
                                           it.get("mode", "replace"), it.get("pronto_project") or None))
    if body.get("pronto_project"):
        s = db.project_settings(con, pid)
        s["pronto_project"] = body["pronto_project"]
        db.update(con, "project", pid, {"settings_json": json.dumps(s)})
    accruals.match(con, pid)
    created = 0
    if body.get("create_categories") or body.get("create_lines"):
        for c in pronto.missing_categories(con, pid):
            services.add_category(con, pid, c["code"], c["name"])
        pronto.resolve_all(con, pid)
    if body.get("create_lines"):
        created = _apply_suggestions(con, pid, pronto.suggestions(con, pid))
    _rm(path)
    return dict(results=results, lines_created=created, suggestions=len(pronto.suggestions(con, pid)))


def _apply_suggestions(con, pid, items):
    n = 0
    s = db.project_settings(con, pid)
    methods = {**{"PL": "BURN-RATE", "PS": "AT-BUDGET", "PM": "AT-COMMIT", "PE": "BURN-RATE"}, **(s.get("default_methods") or {})}
    p = db.one(con, "SELECT initialised FROM project WHERE id=?", (pid,))
    for it in items:
        parent = db.one(con, "SELECT * FROM cbs_node WHERE project_id=? AND category=? AND kind='group'", (pid, it["category"]))
        if it.get("parent_id"):
            parent = services.get_node(con, pid, int(it["parent_id"]))
        if not parent:
            continue
        services.add_node(con, pid, parent["id"], it.get("name") or it["resource_code"], kind="line", resource_kind=it["kind"],
                          resource_code=it["resource_code"], resource_name=it.get("name"), function=it.get("function"),
                          method=methods.get(parent["gp"]) if p["initialised"] else None, origin="pronto",
                          start_date=it.get("first"))
        n += 1
    pronto.resolve_all(con, pid)
    return n


@router.get("/api/p/{pid}/pronto/batches")
def batches(pid: int, con=Depends(get_con)):
    return db.rows(con, "SELECT * FROM import_batch WHERE project_id=? ORDER BY id DESC", (pid,))


@router.delete("/api/p/{pid}/pronto/batches/{bid}")
def batch_delete(pid: int, bid: int, con=Depends(get_con)):
    b = db.one(con, "SELECT * FROM import_batch WHERE id=? AND project_id=?", (bid, pid))
    if not b:
        raise HTTPException(404)
    con.execute(f"DELETE FROM {pronto.TABLE_OF[b['kind']]} WHERE batch_id=?", (bid,))
    con.execute("DELETE FROM import_batch WHERE id=?", (bid,))
    return {"ok": True}


@router.get("/api/p/{pid}/pronto/status")
def pronto_status(pid: int, con=Depends(get_con)):
    out = {}
    for kind, tbl in pronto.TABLE_OF.items():
        out[kind] = dict(rows=db.scalar(con, f"SELECT COUNT(*) FROM {tbl} WHERE project_id=?", (pid,)),
                         batch=db.one(con, "SELECT filename, uploaded_at, as_of FROM import_batch WHERE project_id=? AND kind=? AND active=1 ORDER BY id DESC LIMIT 1", (pid, kind)))
        if out[kind]["rows"] and kind in pronto_raw.RAW:
            # the card's "to ...": the latest date that is not in the future; rows dated later are counted apart
            last, later = pronto_raw.as_of(con, pid, kind)
            out[kind]["last"], out[kind]["future"] = last, later
    return out


@router.get("/api/p/{pid}/pronto/checks")
def pronto_checks(pid: int, con=Depends(get_con)):
    """Rows worth a look before trusting the numbers: future-dated, totals-like, large reversed pairs, duplicates."""
    need_project(con, pid)
    return [{k: v for k, v in c.items() if k != "ids"} for c in pronto_raw.checks(con, pid)]


@router.get("/api/p/{pid}/pronto/raw/{kind}")
def pronto_raw_rows(pid: int, kind: str, q: str = "", check: str = "", offset: int = 0, limit: int = 500, sort: str = "", desc: int = 1, con=Depends(get_con)):
    """The rows of one Pronto report exactly as loaded (searchable, sortable, filtered to a check's rows)."""
    need_project(con, pid)
    if kind not in pronto_raw.RAW:
        raise HTTPException(404)
    return pronto_raw.rows(con, pid, kind, q or None, check or None, offset, min(limit, 5000), sort or None, bool(desc))


@router.get("/api/p/{pid}/pronto/raw-xlsx/{kind}")
def pronto_raw_xlsx(pid: int, kind: str, q: str = "", check: str = "", con=Depends(get_con)):
    need_project(con, pid)
    if kind not in pronto_raw.RAW:
        raise HTTPException(404)
    return Response(pronto_raw.xlsx(con, pid, kind, q or None, check or None), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="Pronto_{kind}_as_loaded.xlsx"'})


@router.get("/api/p/{pid}/pronto/suggestions")
def pronto_suggestions(pid: int, con=Depends(get_con)):
    return dict(items=pronto.suggestions(con, pid), unresolved=pronto.unresolved_summary(con, pid))


@router.post("/api/p/{pid}/pronto/suggestions/apply")
def pronto_apply(pid: int, body: dict, con=Depends(get_con)):
    return {"created": _apply_suggestions(con, pid, body.get("items", []))}


@router.get("/api/p/{pid}/pronto/missing-categories")
def missing_categories(pid: int, con=Depends(get_con)):
    return pronto.missing_categories(con, pid)


@router.post("/api/p/{pid}/categories")
def add_category(pid: int, body: dict, con=Depends(get_con)):
    nid = services.add_category(con, pid, body.get("code"), body.get("name"))
    pronto.resolve_all(con, pid)
    return {"id": nid}


@router.post("/api/p/{pid}/pronto/resolve")
def pronto_resolve(pid: int, con=Depends(get_con)):
    pronto.resolve_all(con, pid)
    return {"ok": True}


@router.get("/api/p/{pid}/pronto/tx")
def pronto_tx(pid: int, node: str = None, month: str = None, q: str = None, limit: int = 400, con=Depends(get_con)):
    where, args = ["t.project_id=?", "t.class IN ('actual','journal')"], [pid]
    if node:
        if node.startswith("p"):
            where.append("t.node_id=?")
            args.append(int(node[1:]))
        else:
            ids = services.subtree_ids(con, pid, int(node))
            where.append(f"t.node_id IN ({','.join('?' * len(ids))})")
            args += ids
    if month:
        where.append("t.month=?")
        args.append(month)
    if q:
        where.append("(t.description LIKE ? OR t.reference LIKE ? OR t.account_desc LIKE ? OR t.account_code LIKE ? OR t.doc_no LIKE ?)")
        args += [f"%{q}%"] * 5
    w = " AND ".join(where)
    total = db.one(con, f"SELECT COUNT(*) n, COALESCE(SUM(t.cost),0) cost FROM pronto_tx t WHERE {w}", args)
    rows = db.rows(con, f"SELECT t.*, n.code AS node_code FROM pronto_tx t LEFT JOIN cbs_node n ON n.id=t.node_id WHERE {w} "
                        f"ORDER BY t.tx_date DESC, t.id DESC LIMIT ?", args + [limit])
    return dict(total=total, rows=rows)


@router.get("/api/p/{pid}/diagnostics")
def diagnostics_page(pid: int, con=Depends(get_con)):
    """Every divergence between PMT and Pronto, for the Diagnostics page."""
    need_project(con, pid)
    return diagnostics.run(con, pid)


# ---------------------------------------------------------------------------
# Menu layout in the person's profile (follows them between PCs through the shared database)
# ---------------------------------------------------------------------------
MENU_KEYS = ("menu_order", "menu_open")


@router.get("/api/me/menu")
def my_menu(con=Depends(get_con)):
    upn = identity.current()["upn"]
    got = {r["key"]: r["value"] for r in db.rows(con, "SELECT key, value FROM user_setting WHERE upn=?", (upn,))}
    split = lambda v: [x for x in (v or "").split("|") if x] if v is not None else None
    return {"order": split(got.get("menu_order")) or [], "open": split(got.get("menu_open"))}


@router.put("/api/me/menu")
def set_my_menu(body: dict, con=Depends(get_con)):
    upn = identity.current()["upn"]
    for key, field_ in (("menu_order", "order"), ("menu_open", "open")):
        if field_ not in body:
            continue
        val = None if body[field_] is None else "|".join(str(x)[:30] for x in (body[field_] or [])[:30])
        row = db.one(con, "SELECT id FROM user_setting WHERE upn=? AND key=?", (upn, key))
        if row:
            db.update(con, "user_setting", row["id"], {"value": val})
        else:
            db.insert(con, "user_setting", dict(upn=upn, key=key, value=val))
    return my_menu(con)


@router.get("/api/me/shortcuts")
def my_shortcuts(con=Depends(get_con)):
    r = db.one(con, "SELECT value FROM user_setting WHERE upn=? AND key='shortcuts'", (identity.current()["upn"],))
    try:
        return {"shortcuts": json.loads(r["value"]) if r and r["value"] else None}
    except ValueError:
        return {"shortcuts": None}


@router.put("/api/me/shortcuts")
def set_my_shortcuts(body: dict, con=Depends(get_con)):
    """The person's own keyboard shortcuts [{combo, action}]; null puts the defaults back."""
    upn = identity.current()["upn"]
    items = body.get("shortcuts")
    if items is not None:
        clean, seen = [], set()
        for it in (items or [])[:40]:
            combo, action = str(it.get("combo") or "").strip()[:30], str(it.get("action") or "").strip()[:60]
            if combo and action and combo not in seen and (action in ("search", "back", "forward") or action.startswith("page:")):
                seen.add(combo); clean.append(dict(combo=combo, action=action))
        items = clean
    val = None if items is None else json.dumps(items)
    row = db.one(con, "SELECT id FROM user_setting WHERE upn=? AND key='shortcuts'", (upn,))
    if row:
        db.update(con, "user_setting", row["id"], {"value": val})
    else:
        db.insert(con, "user_setting", dict(upn=upn, key="shortcuts", value=val))
    return my_shortcuts(con)


@router.get("/api/me/tiles")
def my_tiles(con=Depends(get_con)):
    r = db.one(con, "SELECT value FROM user_setting WHERE upn=? AND key='tiles'", (identity.current()["upn"],))
    try:
        return {"tiles": json.loads(r["value"]) if r and r["value"] else {}}
    except ValueError:
        return {"tiles": {}}


@router.put("/api/me/tiles")
def set_my_tiles(body: dict, con=Depends(get_con)):
    """The order of the tiles on one page's grid (key -> list of tile labels); order null puts that grid back, reset=true all of them."""
    upn = identity.current()["upn"]
    cur = my_tiles(con)["tiles"]
    if body.get("reset"):
        cur = {}
    else:
        key = str(body.get("key") or "")[:300]
        order = body.get("order")
        if key and isinstance(order, list):
            cur[key] = [str(x)[:80] for x in order[:40]]
        elif key:
            cur.pop(key, None)
    val = json.dumps(dict(list(cur.items())[-200:]))
    row = db.one(con, "SELECT id FROM user_setting WHERE upn=? AND key='tiles'", (upn,))
    if row:
        db.update(con, "user_setting", row["id"], {"value": val})
    else:
        db.insert(con, "user_setting", dict(upn=upn, key="tiles", value=val))
    return my_tiles(con)


# ---------------------------------------------------------------------------
# CMT upload: gap analysis against cost control, then align item by item
# ---------------------------------------------------------------------------
@router.post("/api/p/{pid}/cmt/analyse")
async def cmt_analyse(pid: int, file: UploadFile = File(...), con=Depends(get_con)):
    """Read a CMT workbook and compare it with the app. Nothing is changed; the analysis is kept under a token for /cmt/apply."""
    need_project(con, pid)
    token = secrets.token_hex(8)
    src = UPLOADS / f"cmt-{token}.xlsx"
    src.parent.mkdir(parents=True, exist_ok=True)
    for old_f in UPLOADS.glob("cmt-*"):          # comparisons older than a day are forgotten
        if time.time() - old_f.stat().st_mtime > 86400:
            _rm(old_f)
    src.write_bytes(await file.read())          # kept, so the CMT can be handed back with the app's figures in it
    try:
        out = cmt_import.compare(con, pid, cmt_import.parse(src))
    except ValueError as e:
        _rm(src)
        raise HTTPException(400, str(e))
    out["filename"] = file.filename
    (UPLOADS / f"cmt-{token}.json").write_text(json.dumps(out))
    return {**out, "token": token}


@router.get("/api/p/{pid}/cmt/report")
def cmt_report(pid: int, token: str):
    f = UPLOADS / f"cmt-{re.sub(r'[^0-9a-f]', '', token)}.json"
    if not f.exists():
        raise HTTPException(404, "The comparison has expired: choose the CMT again")
    return Response(cmt_import.report_xlsx(json.loads(f.read_text())), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="cmt-gap-report.xlsx"'})


@router.post("/api/p/{pid}/cmt/apply")
def cmt_apply(pid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    token = re.sub(r"[^0-9a-f]", "", str(body.get("token") or ""))
    f = UPLOADS / f"cmt-{token}.json"
    if not token or not f.exists():
        raise HTTPException(400, "The comparison has expired: choose the CMT again")
    analysis = json.loads(f.read_text())
    decisions = body.get("decisions") or {}
    res = cmt_import.apply(con, pid, analysis, decisions, body.get("targets") or {})
    edits = cmt_import.cmt_edits(analysis, decisions)
    res["cmt_edits"] = len(edits)
    if edits:                                    # the updated CMT is built on download; keep what it needs
        analysis["edits"] = [[r, c, v] for (r, c), v in edits.items()]
        f.write_text(json.dumps(analysis))
    else:
        _rm(f); _rm(UPLOADS / f"cmt-{token}.xlsx")
    return res


@router.get("/api/p/{pid}/cmt/updated")
def cmt_updated(pid: int, token: str):
    """The CMT as uploaded, with the app's forecast figures written into the lines the user chose to align the CMT to the app."""
    t = re.sub(r"[^0-9a-f]", "", token)
    f, src = UPLOADS / f"cmt-{t}.json", UPLOADS / f"cmt-{t}.xlsx"
    if not f.exists() or not src.exists():
        raise HTTPException(404, "The comparison has expired: load the CMT again")
    a = json.loads(f.read_text())
    edits = {(int(r), int(c)): v for r, c, v in a.get("edits") or []}
    if not edits:
        raise HTTPException(400, "No line was set to update the CMT")
    try:
        data = cmt_import.updated_workbook(src, (a.get("meta") or {}).get("sheet"), edits)
    except ValueError as e:
        raise HTTPException(400, str(e))
    name = re.sub(r"\.xlsx?$", "", a.get("filename") or "CMT", flags=re.I) + " (aligned with the app).xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/api/p/{pid}/cmt/undo")
def cmt_undo(pid: int, con=Depends(get_con)):
    return {"restored": cmt_import.undo(con, pid)}


# ---------------------------------------------------------------------------
# Demonstration project
# ---------------------------------------------------------------------------
@router.post("/api/demo/team")
def load_demo_team(con=Depends(get_con)):
    """A demo team (demo/build_demo.seed_team): project director Taylor Brooks over a junior PM (1 project), two PMs (2 each)
    and a senior PM (3), with one parent project shared by a PM and the senior PM. Fictional; about half a minute."""
    from demo import build_demo
    build_demo.write_template_file(build_demo.DEMO / "demo_project_template.xlsx")
    build_demo.build_pronto_file(build_demo.DEMO / "demo_pronto_export.xlsx")
    try:
        return build_demo.seed_team(con)
    except ValueError as e:
        raise services.Problem(str(e))


@router.post("/api/demo")
def load_demo(con=Depends(get_con)):
    """Builds the fictional demo project (see demo/build_demo.py) so every screen can be explored."""
    from demo import build_demo
    build_demo.write_template_file(build_demo.DEMO / "demo_project_template.xlsx")
    build_demo.build_pronto_file(build_demo.DEMO / "demo_pronto_export.xlsx")
    name = "Demo: Greenfield Substation"
    n = db.scalar(con, "SELECT COUNT(*) FROM project WHERE name LIKE ?", (name + "%",))
    pid, _ = build_demo.seed(con, name if not n else f"{name} ({n + 1})")
    build_demo.seed_extras(con, pid)
    return {"id": pid}
