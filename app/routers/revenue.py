"""Revenue and Subcontracts routes: contract and claim schedule, claims, variations, subcontracts and milestones."""
import json
import re
import secrets
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response

from .. import (claim_template, diagnostics, variation_io, subcontract_io, suppliers, schedule_import, review, db,
                identity, engine, exporters, revenue, services, subcontracts, templates_io, variations)
from ..taxonomy import CLAIM_STATUS

from ._shared import J, UPLOADS, _rm, _xlsx, get_con, need_project

router = APIRouter(default_response_class=J)


# ---------------------------------------------------------------------------
# Revenue
# ---------------------------------------------------------------------------
@router.get("/api/p/{pid}/contract")
def contract(pid: int, con=Depends(get_con)):
    need_project(con, pid)
    return dict(items=revenue.items_tree(con, pid), summary=revenue.summary(con, pid), claim_months=revenue.claim_months(con, pid))


CI_COLS = ("ref", "description", "stage", "kind", "optional_status", "value", "phase", "claim_requirement", "start_date", "end_date",
           "method", "sort_order", "in_original")


@router.post("/api/p/{pid}/contract/items/bulk")
def contract_items_bulk(pid: int, body: dict, con=Depends(get_con)):
    """Fill handle: give several payment milestones the same value of one field (not the item number)."""
    need_project(con, pid)
    field = body.get("field")
    if field not in CI_COLS or field in ("ref", "sort_order"):
        raise services.Problem("That column cannot be filled")
    ids = [int(i) for i in body.get("ids") or []]
    n = 0
    for i in ids:
        if not db.one(con, "SELECT 1 x FROM contract_item WHERE id=? AND project_id=? AND variation_id IS NULL", (i, pid)):
            continue
        contract_item_save(pid, {"id": i, field: body.get("value"), **(body.get("extra") or {})}, con)
        n += 1
    return {"updated": n}


@router.post("/api/p/{pid}/contract/items")
def contract_item_save(pid: int, body: dict, con=Depends(get_con)):
    d = {k: body.get(k) for k in CI_COLS if k in body}
    if "optional_status" in d:
        kind = d.get("kind") or (db.one(con, "SELECT kind FROM contract_item WHERE id=?", (body.get("id"),)) or {}).get("kind")
        d["optional_status"] = (revenue.var_status if kind == "variation" else revenue.opt_status)(d["optional_status"]) if kind in ("optional", "variation") else None
    for k in ("start_date", "end_date"):
        if d.get(k):
            d[k] = db.iso(d[k])
    if "parent_ref" in body:
        pr = db.one(con, "SELECT id FROM contract_item WHERE project_id=? AND ref=?", (pid, body["parent_ref"]))
        d["parent_id"] = pr["id"] if pr else None
    if "parent_id" in body:
        d["parent_id"] = body["parent_id"]
    if body.get("id"):
        db.update(con, "contract_item", body["id"], d)
        return {"id": body["id"]}
    if not d.get("description"):
        raise services.Problem("Description is required")
    d.setdefault("sort_order", db.scalar(con, "SELECT COALESCE(MAX(sort_order),0)+1 FROM contract_item WHERE project_id=?", (pid,)))
    return {"id": db.insert(con, "contract_item", dict(project_id=pid, **d))}


@router.post("/api/p/{pid}/schedule/analyse")
async def schedule_analyse(pid: int, file: UploadFile = File(...), con=Depends(get_con)):
    need_project(con, pid)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".xlsx", ".xlsm"):
        raise services.Problem("Upload the claim schedule as an .xlsx or .xlsm file")
    token = secrets.token_hex(8)
    path = UPLOADS / f"{token}{suffix}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        parsed = schedule_import.parse(path)
    except schedule_import.NotRecognised as e:
        _rm(path)
        raise services.Problem(str(e))
    existing = db.scalar(con, "SELECT COUNT(*) FROM contract_item WHERE project_id=? AND variation_id IS NULL", (pid,)) or 0
    claimed = db.scalar(con, "SELECT COUNT(*) FROM claim_line cl JOIN contract_item ci ON ci.id=cl.item_id WHERE ci.project_id=? AND ci.variation_id IS NULL", (pid,)) or 0
    proj = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    grid = claim_template.read_grid(path)                       # the claim schedule template carries a Claimed | Approved month grid
    M = claim_template.read_status_month(path) or engine.project_status_month(proj)
    n_claims = db.scalar(con, "SELECT COUNT(*) FROM claim WHERE project_id=?", (pid,)) or 0
    # a plain file with month columns can overwrite the schedule and claims (past months = claims, status month = draft claim, later = forecast);
    # a template with the Claimed | Approved grid loads its own claims instead
    return dict(token=token, filename=file.filename, existing_items=existing, claim_lines=claimed, existing_claims=n_claims, status_month=M,
                project_status_date=proj.get("status_date"), grid=claim_template.grid_summary(grid, M) if grid else None,
                **schedule_import.preview(parsed, None if grid else M))


@router.get("/api/p/{pid}/schedule/template.xlsx")
def schedule_template(pid: int, blank: int = 0, grid: int = 0, con=Depends(get_con)):
    """Payment Milestones (grid=0) or the claim schedule with its Claimed | Approved month grid (grid=1), as an Excel
    template: this project's items, claims and plan, or blank."""
    need_project(con, pid)
    name = ("claim-schedule" if grid else "payment-milestones") + ("-blank" if blank else "")
    return Response(claim_template.template(con, pid, blank=bool(blank), grid=bool(grid)), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.post("/api/p/{pid}/schedule/commit")
def schedule_commit(pid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    token = re.sub(r"[^a-f0-9]", "", body.get("token", ""))
    matches = list(UPLOADS.glob(f"{token}.*"))
    if not token or not matches:
        raise services.Problem("Upload expired. Please upload the file again.")
    path = matches[0]
    try:
        parsed = schedule_import.parse(path)
        mode = body.get("mode") or "merge"
        proj = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
        if mode == "overwrite" and not proj.get("status_date"):
            raise services.Problem("Set the project's status date first (Project setup, Project): months before it are loaded as claims already made.")
        grid = claim_template.read_grid(path) if body.get("grid", True) else None
        sm = claim_template.read_status_month(path) or engine.project_status_month(proj)
        rid = None
        if mode == "overwrite":                  # the claims go too, so keep them to put back (Project setup > Undo)
            rid = templates_io.make_restore_point(con, pid, f"Claim schedule overwrite: {body.get('filename') or 'file'}", (identity.current() or {}).get("name"), with_claims=True)
        res = schedule_import.apply(con, pid, parsed, mode, variations_in_original=bool(body.get("variations_in_original")),
                                    optionals_in_original=body.get("optionals_in_original", True) is not False, status_month=sm,
                                    claims_from_months=not grid)            # a template's own Claimed | Approved grid makes the claims below
        res["restore_point"] = rid
        if grid:                                   # the claim schedule template: claims to the status month and the plan
            res["grid"] = claim_template.apply_grid(con, pid, grid, sm)
    except (schedule_import.NotRecognised, ValueError) as e:
        raise services.Problem(str(e))
    finally:
        _rm(path)
    return res


@router.delete("/api/p/{pid}/contract/items/{iid}")
def contract_item_delete(pid: int, iid: int, con=Depends(get_con)):
    it = db.one(con, "SELECT * FROM contract_item WHERE id=? AND project_id=?", (iid, pid))
    if it and it["variation_id"]:
        raise services.Problem("This item comes from a variation. Change the variation instead.")
    con.execute("DELETE FROM contract_item WHERE id=? AND project_id=?", (iid, pid))
    return {"ok": True}


@router.post("/api/p/{pid}/contract/items/{iid}/window")
def contract_item_window(pid: int, iid: int, body: dict, con=Depends(get_con)):
    """A claim line's window: start and end (YYYY-MM) and/or months. The price not yet claimed is spread over it."""
    need_project(con, pid)
    try:
        return revenue.set_item_window(con, pid, iid, body.get("start"), body.get("stop"), body.get("months"))
    except ValueError as e:
        raise services.Problem(str(e))


@router.put("/api/p/{pid}/contract/items/{iid}/plan")
def contract_plan(pid: int, iid: int, body: dict, con=Depends(get_con)):
    con.execute("DELETE FROM revenue_plan WHERE item_id=?", (iid,))
    for m, a in (body.get("months") or {}).items():
        if a not in (None, "", 0):
            db.insert(con, "revenue_plan", dict(item_id=iid, month=m[:7], amount=float(a)))
    db.update(con, "contract_item", iid, {"method": "manual"})
    return {"ok": True}


@router.put("/api/p/{pid}/contract/items/{iid}/cell")
def contract_cell(pid: int, iid: int, body: dict, con=Depends(get_con)):
    """One month of the claim schedule: amount ($), pct (% of the item's price) or rest (whatever is left)."""
    need_project(con, pid)
    try:
        return revenue.set_cell(con, pid, iid, body.get("month"), amount=body.get("amount"), pct=body.get("pct"), rest=bool(body.get("rest")))
    except ValueError as e:
        raise services.Problem(str(e))


@router.post("/api/p/{pid}/contract/items/{iid}/move")
def contract_move(pid: int, iid: int, body: dict, con=Depends(get_con)):
    need_project(con, pid)
    try:
        return revenue.move_cell(con, pid, iid, body.get("from"), body.get("to"))
    except ValueError as e:
        raise services.Problem(str(e))


@router.post("/api/p/{pid}/contract/trim-excess")
def contract_trim(pid: int, con=Depends(get_con)):
    need_project(con, pid)
    return revenue.trim_excess(con, pid)


@router.get("/api/p/{pid}/claims")
def claims(pid: int, con=Depends(get_con)):
    return revenue.claim_list(con, pid)


@router.post("/api/p/{pid}/claims")
def claim_create(pid: int, body: dict, con=Depends(get_con)):
    per = (body.get("period") or "")[:7]
    if not per:
        raise services.Problem("Claim period is required")
    n = db.scalar(con, "SELECT COUNT(*) FROM claim WHERE project_id=?", (pid,)) + 1
    cid = db.insert(con, "claim", dict(project_id=pid, claim_no=body.get("claim_no") or f"CLAIM{n:03d}", period=per))
    if body.get("prefill", True):
        d = revenue.claim_detail(con, pid, cid)
        for l in d["lines"]:
            if l["planned_this"] > 0:           # the claim starts as the month's column of the claim schedule; "suggested" still shows any catch-up
                db.insert(con, "claim_line", dict(claim_id=cid, item_id=l["item_id"], amount=l["planned_this"]))
    return {"id": cid}


@router.get("/api/p/{pid}/claims/{cid:int}")
def claim_get(pid: int, cid: int, con=Depends(get_con)):
    d = revenue.claim_detail(con, pid, cid)
    if not d:
        raise HTTPException(404)
    return d


@router.put("/api/p/{pid}/claims/{cid:int}")
def claim_save(pid: int, cid: int, body: dict, con=Depends(get_con)):
    d = {k: body.get(k) for k in ("claim_no", "status", "submitted_date", "certified_date", "paid_date", "certified_amount",
                                  "paid_amount", "retention", "pronto_claim_no", "client_claim_no", "revision", "revision_date", "client_cert_no", "note") if k in body}
    for k in ("submitted_date", "certified_date", "paid_date", "revision_date"):
        if d.get(k):
            d[k] = db.iso(d[k])
    if d.get("status") and d["status"] not in CLAIM_STATUS:
        raise services.Problem("Unknown claim status")
    db.update(con, "claim", cid, d)
    if "lines" in body:
        con.execute("DELETE FROM claim_line WHERE claim_id=?", (cid,))
        for l in body["lines"]:
            if l.get("amount") or l.get("certified") not in (None, ""):
                db.insert(con, "claim_line", dict(claim_id=cid, item_id=int(l["item_id"]), amount=float(l.get("amount") or 0), note=l.get("note"),
                                                  certified=None if l.get("certified") in (None, "") else float(l["certified"])))
    act = body.get("action")
    if act == "certify_all":
        revenue.certify_all(con, cid)
    elif act == "certify_total":
        revenue.certify_total(con, cid, body.get("amount"))
    if act in ("certify_all", "certify_total"):
        db.update(con, "claim", cid, dict(status="certified", certified_date=db.iso(body.get("today"))))
    return {"ok": True}


@router.delete("/api/p/{pid}/claims/{cid:int}")
def claim_delete(pid: int, cid: int, con=Depends(get_con)):
    con.execute("DELETE FROM claim WHERE id=? AND project_id=?", (cid, pid))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Variations
# ---------------------------------------------------------------------------
VAR_COLS = ("ref", "stage", "title", "description", "client_status", "client_status_date", "epec_status", "epec_status_date",
            "contract_change", "contract_status", "closed", "close_date", "prepared_by", "validity", "pricing_model",
            "pronto_ref", "submission_date", "outcome", "detail_level", "funding", "exclusions")


ITEM_COLS = ("section", "name", "pricing_type", "optional", "selected", "detail", "spread", "spread_scope", "carries", "note")


LINE_COLS = ("section", "node_id", "category", "description", "role", "unit", "qty", "rate", "item_count", "hrs_day", "days_wk", "wks",
             "extra_qty", "risk_pct", "markup_pct", "price_override", "contract_rate", "optional", "note")


@router.get("/api/p/{pid}/variations")
def var_list(pid: int, con=Depends(get_con)):
    return variations.listing(con, pid)


@router.post("/api/p/{pid}/variations")
def var_create(pid: int, body: dict, con=Depends(get_con)):
    d = {k: body.get(k) for k in VAR_COLS if k in body}
    d["ref"] = d.get("ref") or variations.next_ref(con, pid, "EPC-VAR" if (d.get("stage") or "").upper() == "EPC" else "VAR")
    for k in ("client_status_date", "epec_status_date", "close_date", "submission_date"):
        if d.get(k):
            d[k] = db.iso(d[k])
    if db.one(con, "SELECT 1 x FROM variation WHERE project_id=? AND ref=?", (pid, d["ref"])):
        raise services.Problem(f"Variation {d['ref']} already exists")
    vid = db.insert(con, "variation", dict(project_id=pid, **d))
    db.insert(con, "variation_rev", dict(variation_id=vid, rev=0, date=d.get("submission_date"), value=float(body.get("value") or 0), is_current=1))
    db.insert(con, "variation_event", dict(variation_id=vid, date=db.iso(body.get("submission_date")), kind="note", text="Variation raised", who=body.get("prepared_by")))
    return {"id": vid, "ref": d["ref"]}


@router.get("/api/p/{pid}/variations/from-schedule")
def var_from_schedule_count(pid: int, con=Depends(get_con)):
    """How many variations in the uploaded contract have no register entry yet."""
    return {"missing": len(variations.schedule_variations(con, pid))}


@router.post("/api/p/{pid}/variations/from-schedule")
def var_from_schedule(pid: int, con=Depends(get_con)):
    """Create the register entries (with an empty cost build-up) for the variations in the uploaded contract."""
    made = variations.placeholders_from_schedule(con, pid)
    db.bump(con, pid)
    return {"created": len(made)}


@router.get("/api/p/{pid}/variations/template.xlsx")
def var_template(pid: int, blank: int = 0, con=Depends(get_con)):
    """The variation register in Excel: blank, or the current register to update and upload again."""
    need_project(con, pid)
    return _xlsx(variation_io.template(con, pid, bool(blank)), "variation-register.xlsx")


@router.post("/api/p/{pid}/variations/upload")
async def var_upload(pid: int, file: UploadFile = File(...), apply: str = Form("0"), today: str = Form(""), con=Depends(get_con)):
    need_project(con, pid)
    try:
        return variation_io.import_workbook(con, pid, await file.read(), apply == "1", today or None)
    except ValueError as e:
        raise services.Problem(str(e))


@router.post("/api/p/{pid}/variations/{vid}/preview")
def var_preview(pid: int, vid: int, body: dict, con=Depends(get_con)):
    """Live totals while editing: the build of the price items and lines sent (nothing is saved)."""
    items = [dict(it, id=it.get("id") if isinstance(it.get("id"), int) else str(it.get("key"))) for it in body.get("items") or []]
    lines = [dict(l, price_id=(l.get("price_id") if l.get("price_id") is not None else str(l.get("price_key")))) for l in body.get("lines") or []]
    return variations.build({}, items, lines)


@router.get("/api/p/{pid}/variations/{vid}/funding")
def var_funding(pid: int, vid: int, con=Depends(get_con)):
    return variations.funding_plan(con, pid, vid)


@router.put("/api/p/{pid}/variations/{vid}/funding")
def var_funding_set(pid: int, vid: int, body: dict, con=Depends(get_con)):
    if body.get("funding") not in ("topup", "separate"):
        raise services.Problem("Funding is topup or separate")
    db.update(con, "variation", vid, {"funding": body["funding"]})
    variations.sync(con, pid, vid)
    return variations.funding_plan(con, pid, vid)


@router.post("/api/p/{pid}/variations/{vid}/duplicate-cbs")
def var_duplicate(pid: int, vid: int, body: dict, con=Depends(get_con)):
    """Copy CBS groups or lines for this variation, so it is tracked on its own lines."""
    try:
        made = variations.duplicate_cbs(con, pid, vid, body.get("node_ids") or [], only_used=body.get("mode") == "used")
    except ValueError as e:
        raise services.Problem(str(e))
    from .. import pronto as pronto_mod
    pronto_mod.resolve_all(con, pid)  # Pronto cost already coded to this variation moves onto the copies
    return dict(variations.funding_plan(con, pid, vid), created=len(made))


@router.get("/api/p/{pid}/variations/{vid}")
def var_get(pid: int, vid: int, con=Depends(get_con)):
    v = variations.get(con, pid, vid)
    if not v:
        raise HTTPException(404)
    return v


@router.put("/api/p/{pid}/variations/{vid}")
def var_update(pid: int, vid: int, body: dict, con=Depends(get_con)):
    before = db.one(con, "SELECT client_status, epec_status FROM variation WHERE id=?", (vid,))
    d = {k: body.get(k) for k in VAR_COLS if k in body}
    for k in ("client_status_date", "epec_status_date", "close_date", "submission_date"):
        if d.get(k):
            d[k] = db.iso(d[k])
    if "client_status" in d and d["client_status"] != before["client_status"] and not d.get("client_status_date"):
        d["client_status_date"] = db.iso(body.get("today"))
    db.update(con, "variation", vid, d)
    for k, lab in (("client_status", "Client status"), ("epec_status", "EPEC status")):
        if k in d and d[k] != before[k]:
            db.insert(con, "variation_event", dict(variation_id=vid, date=db.iso(body.get("today")), kind="status",
                                                   text=f"{lab}: {before[k]} to {d[k]}", who=body.get("who")))
    if "revs" in body:
        con.execute("DELETE FROM variation_rev WHERE variation_id=?", (vid,))
        for i, r in enumerate(body["revs"]):
            db.insert(con, "variation_rev", dict(variation_id=vid, rev=r.get("rev", i), date=db.iso(r.get("date")), value=float(r.get("value") or 0),
                                                 note=r.get("note"), is_current=1 if r.get("is_current") else 0))
    keymap = {}
    if "items" in body:  # price items: kept by id (so their history reads well); new ones carry a temporary key
        keep = []
        for i, it in enumerate(body["items"]):
            d2 = {k: it.get(k) for k in ITEM_COLS if k in it}
            d2["seq"] = i + 1
            if isinstance(it.get("id"), int) and db.one(con, "SELECT 1 x FROM variation_price WHERE id=? AND variation_id=?", (it["id"], vid)):
                db.update(con, "variation_price", it["id"], d2)
                keymap[str(it["id"])] = it["id"]
                keep.append(it["id"])
            else:
                nid = db.insert(con, "variation_price", dict(variation_id=vid, **d2))
                keymap[str(it.get("key") or it.get("id"))] = nid
                keep.append(nid)
        q = ",".join("?" * len(keep)) or "NULL"
        con.execute(f"DELETE FROM variation_price WHERE variation_id=? AND id NOT IN ({q})", [vid, *keep])
    if "lines" in body:
        con.execute("DELETE FROM variation_line WHERE variation_id=?", (vid,))
        for i, l in enumerate(body["lines"]):
            d2 = {k: l.get(k) for k in LINE_COLS}
            pk = l.get("price_id") if l.get("price_id") is not None else l.get("price_key")
            d2["price_id"] = keymap.get(str(pk), pk if isinstance(pk, int) else None)
            db.insert(con, "variation_line", dict(variation_id=vid, sort_order=i, **d2))
    variations.sync(con, pid, vid)
    return {"ok": True}


@router.post("/api/p/{pid}/variations/{vid}/events")
def var_event(pid: int, vid: int, body: dict, con=Depends(get_con)):
    return {"id": db.insert(con, "variation_event", dict(variation_id=vid, date=db.iso(body.get("date")), kind=body.get("kind") or "note",
                                                         text=body.get("text"), who=body.get("who")))}


@router.delete("/api/p/{pid}/variations/{vid}")
def var_delete(pid: int, vid: int, con=Depends(get_con)):
    con.execute("DELETE FROM allowance_ledger WHERE project_id=? AND variation_id=?", (pid, vid))
    con.execute("DELETE FROM contract_item WHERE project_id=? AND variation_id=?", (pid, vid))
    con.execute("DELETE FROM variation WHERE id=? AND project_id=?", (vid, pid))
    return {"ok": True}


@router.get("/api/p/{pid}/variations/{vid}/proposal", response_class=HTMLResponse)
def var_proposal(pid: int, vid: int, breakdown: int = 1, level: str = None, con=Depends(get_con)):
    """level (items | scope | contributions | full) overrides the variation's and the price items' own detail levels."""
    return exporters.variation_proposal_html(con, pid, vid, bool(breakdown), level or None)


# ---------------------------------------------------------------------------
# Subcontracts and schedule
# ---------------------------------------------------------------------------
@router.get("/api/p/{pid}/subcontracts")
def sub_list(pid: int, con=Depends(get_con)):
    out = subcontracts.summary(con, pid)
    kn, pos = suppliers.known(con, pid), suppliers.all_pos(con, pid)
    for s in out:
        s["milestones"] = db.rows(con, "SELECT * FROM sub_milestone WHERE subcontract_id=? ORDER BY seq, id", (s["id"],))
        s["terms"] = subcontracts.terms(con, s)
        s["link"] = suppliers.link_state(con, pid, s, kn, pos)
        s["claims"] = []
        for c in subcontracts.claims_of(con, s["id"]):
            c.update({k: v for k, v in subcontracts.claim_totals(con, c, s).items() if k != "lines"})
            s["claims"].append(c)
    return out


@router.post("/api/p/{pid}/subcontracts/{sid}/match")
def sub_match(pid: int, sid: int, body: dict, con=Depends(get_con)):
    try:
        return diagnostics.match_subcontract(con, pid, sid, body.get("supplier_code"), body.get("po_no"))
    except ValueError as e:
        raise services.Problem(str(e))


@router.get("/api/p/{pid}/suppliers")
def supplier_list(pid: int, con=Depends(get_con)):
    """Suppliers and their purchase orders as known from Pronto, for the supplier / PO pickers."""
    need_project(con, pid)
    return suppliers.listing(con, pid)


@router.get("/api/p/{pid}/subcontracts/template.xlsx")
def sub_template(pid: int, sid: str = None, con=Depends(get_con)):
    """Payment schedule template: blank, one subcontract (sid) or every subcontract (sid=all)."""
    need_project(con, pid)
    name = "subcontract-payment-schedule.xlsx" if not sid else ("subcontracts-payment-schedules.xlsx" if sid == "all" else f"subcontract-{sid}-payment-schedule.xlsx")
    return _xlsx(subcontract_io.template(con, pid, sid), name)


@router.post("/api/p/{pid}/subcontracts/upload")
async def sub_upload(pid: int, file: UploadFile = File(...), apply: str = Form("0"), links: str = Form(""), con=Depends(get_con)):
    need_project(con, pid)
    try:
        return subcontract_io.import_workbook(con, pid, await file.read(), apply == "1", json.loads(links) if links else None)
    except ValueError as e:
        raise services.Problem(str(e))


@router.post("/api/p/{pid}/subcontracts")
def sub_save(pid: int, body: dict, con=Depends(get_con)):
    d = {k: body.get(k) for k in ("name", "supplier_code", "supplier_name", "po_no", "node_id", "contract_value", "retention_pct",
                                  "retention_release_month", "status", "notes") if k in body}
    if body.get("id"):
        sid = body["id"]
        db.update(con, "subcontract", sid, d)
    else:
        if not d.get("name"):
            raise services.Problem("Name is required")
        sid = db.insert(con, "subcontract", dict(project_id=pid, **d))
    if "milestones" in body:
        # upsert by id so claim lines that point at a schedule line survive an edit of the schedule
        keep = []
        for i, m in enumerate(body["milestones"]):
            d = dict(seq=i + 1, name=m.get("name"), type=m.get("type") or "Milestone", pct=float(m.get("pct") or 0), value=float(m.get("value") or 0),
                     start_month=(m.get("start_month") or "")[:7] or None, end_month=(m.get("end_month") or "")[:7] or None, trigger_note=m.get("trigger_note"))
            if m.get("id"):
                db.update(con, "sub_milestone", m["id"], d)
                keep.append(m["id"])
            else:
                keep.append(db.insert(con, "sub_milestone", dict(subcontract_id=sid, **d)))
        if keep:
            con.execute(f"DELETE FROM sub_milestone WHERE subcontract_id=? AND id NOT IN ({','.join('?' * len(keep))})", [sid, *keep])
        else:
            con.execute("DELETE FROM sub_milestone WHERE subcontract_id=?", (sid,))
    return {"id": sid}


@router.post("/api/p/{pid}/subcontracts/{sid}/claims")
def sub_claim_create(pid: int, sid: int, body: dict, con=Depends(get_con)):
    if not body.get("month"):
        raise services.Problem("Choose the claim month")
    if db.one(con, "SELECT 1 x FROM sub_claim WHERE subcontract_id=? AND month=?", (sid, body["month"][:7])) and not body.get("allow_second"):
        raise services.Problem("There is already a claim for that month. Open it, or tick to allow a second claim in the same month.")
    return {"id": subcontracts.create_claim(con, sid, body["month"], body.get("claim_no"))}


@router.get("/api/p/{pid}/subcontracts/{sid}/claims/{cid}")
def sub_claim_get(pid: int, sid: int, cid: int, con=Depends(get_con)):
    d = subcontracts.claim_detail(con, sid, cid)
    if not d:
        raise HTTPException(404)
    return d


@router.put("/api/p/{pid}/subcontracts/{sid}/claims/{cid}")
def sub_claim_save(pid: int, sid: int, cid: int, body: dict, con=Depends(get_con)):
    if body.get("status") and body["status"] not in ("draft", "received", "approved", "paid"):
        raise services.Problem("Unknown claim status")
    subcontracts.save_claim(con, sid, cid, body, (identity.current() or {}).get("name"))
    return {"ok": True, "certificate": db.one(con, "SELECT cert_no, cert_date, cert_by FROM sub_claim WHERE id=?", (cid,))}


@router.post("/api/p/{pid}/subcontracts/{sid}/claims/{cid}/certificate")
def sub_certificate_issue(pid: int, sid: int, cid: int, body: dict, con=Depends(get_con)):
    try:
        return subcontracts.issue_certificate(con, sid, cid, (identity.current() or {}).get("name"), body.get("today"))
    except ValueError as e:
        raise services.Problem(str(e))


@router.get("/api/p/{pid}/subcontracts/{sid}/claims/{cid}/certificate.pdf")
def sub_certificate_pdf(pid: int, sid: int, cid: int, name: str = "", con=Depends(get_con)):
    data = exporters.sub_certificate_pdf(con, pid, sid, cid)
    if data is None:
        raise HTTPException(404, "This claim has no payment certificate yet: approve it first")
    base = re.sub(r"\s+", " ", re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", name or "")).strip(" .")[:120] or "payment-certificate"
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{base}.pdf"'})


@router.delete("/api/p/{pid}/subcontracts/{sid}/claims/{cid}")
def sub_claim_delete(pid: int, sid: int, cid: int, con=Depends(get_con)):
    con.execute("DELETE FROM sub_claim WHERE id=? AND subcontract_id=?", (cid, sid))
    return {"ok": True}


def _sub(con, pid, sid):
    s = db.one(con, "SELECT * FROM subcontract WHERE id=? AND project_id=?", (sid, pid))
    if not s:
        raise HTTPException(404)
    return s


@router.get("/api/p/{pid}/subcontracts/{sid}/sheet")
def sub_sheet(pid: int, sid: int, month: str = None, con=Depends(get_con)):
    _sub(con, pid, sid)
    M = month or engine.compute(con, pid)["status_month"]
    out = subcontracts.sheet(con, sid, M)
    snap, plan = review.planned(con, pid, M)
    out["planned_from"] = snap["label"] if snap else None
    return out


@router.put("/api/p/{pid}/subcontracts/{sid}/forecast")
def sub_forecast_save(pid: int, sid: int, body: dict, con=Depends(get_con)):
    return {"cells": subcontracts.save_forecast(con, _sub(con, pid, sid), body.get("cells") or {})}


@router.post("/api/p/{pid}/subcontracts/{sid}/forecast/{action}")
def sub_forecast_action(pid: int, sid: int, action: str, body: dict = None, con=Depends(get_con)):
    s = _sub(con, pid, sid)
    M = engine.compute(con, pid)["status_month"]
    if action == "seed":
        return {"cells": subcontracts.seed_forecast(con, s, M)}
    if action == "shift":
        return {"cells": subcontracts.shift_forecast(con, s, M, int((body or {}).get("months") or 1))}
    if action == "clear":
        con.execute("DELETE FROM sub_forecast WHERE subcontract_id=?", (sid,))
        return {"cells": 0}
    raise services.Problem("Unknown action")


@router.delete("/api/p/{pid}/subcontracts/{sid}")
def sub_delete(pid: int, sid: int, con=Depends(get_con)):
    con.execute("DELETE FROM subcontract WHERE id=? AND project_id=?", (sid, pid))
    return {"ok": True}


@router.get("/api/p/{pid}/milestones")
def ms_list(pid: int, con=Depends(get_con)):
    return db.rows(con, "SELECT * FROM milestone WHERE project_id=? ORDER BY sort_order, id", (pid,))


@router.post("/api/p/{pid}/milestones")
def ms_save(pid: int, body: dict, con=Depends(get_con)):
    d = {k: body.get(k) for k in ("phase", "name", "type", "baseline_start", "baseline_end", "forecast_start", "forecast_end",
                                  "actual_date", "pct", "pmr_row", "note", "sort_order") if k in body}
    for k in ("baseline_start", "baseline_end", "forecast_start", "forecast_end", "actual_date"):
        if k in d:
            d[k] = db.iso(d[k])
    if body.get("id"):
        db.update(con, "milestone", body["id"], d)
        return {"id": body["id"]}
    d.setdefault("sort_order", db.scalar(con, "SELECT COALESCE(MAX(sort_order),0)+1 FROM milestone WHERE project_id=?", (pid,)))
    return {"id": db.insert(con, "milestone", dict(project_id=pid, **d))}


@router.delete("/api/p/{pid}/milestones/{mid}")
def ms_delete(pid: int, mid: int, con=Depends(get_con)):
    con.execute("DELETE FROM milestone WHERE id=? AND project_id=?", (mid, pid))
    return {"ok": True}


@router.post("/api/p/{pid}/milestones/derive-dates")
def ms_derive(pid: int, con=Depends(get_con)):
    """Project start and end from the earliest and latest milestone dates."""
    r = db.one(con, "SELECT MIN(COALESCE(baseline_start, forecast_start)) a, MAX(COALESCE(forecast_end, baseline_end)) b FROM milestone WHERE project_id=?", (pid,))
    if r["a"]:
        db.update(con, "project", pid, {"project_start": r["a"], "project_end": r["b"]})
    return r


@router.get("/api/p/{pid}/claim-act")
def claim_act_get(pid: int, con=Depends(get_con)):
    """Whether this project's payment claims carry the Queensland BIF Act statement, and why."""
    p = need_project(con, pid)
    return {**exporters.claim_act_info(p), "laws": exporters.LAWS}


@router.get("/api/p/{pid}/claims/{cid}.pdf")
def claim_pdf(pid: int, cid: int, name: str = "", layout: str = "", con=Depends(get_con)):
    data = exporters.claim_pdf(con, pid, cid, layout or None)
    if data is None:
        raise HTTPException(404)
    base = re.sub(r"\s+", " ", re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", name or "")).strip(" .")[:120] or "progress-claim"
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{base}.pdf"'})


@router.get("/api/p/{pid}/claims/{cid}.xlsx")
def claim_xlsx(pid: int, cid: int, con=Depends(get_con)):
    return _xlsx(exporters.claim_xlsx(con, pid, cid), "progress-claim.xlsx")
