"""Diagnostics: every place where PMT and Pronto disagree, in one list to review.

Each check gives a section, a level (error = numbers do not tie, warn = to review or to match, ok = checked and fine),
a title, the detail rows (each with what PMT says, what Pronto says and the difference where that applies) and the
page that fixes it. Subcontract suppliers and POs entered ahead of Pronto get a one-click match when Pronto has a
supplier with a similar name.
"""
from collections import defaultdict

from . import accruals, db, engine, eom_report, pronto_raw, reports, revenue, suppliers

SECTIONS = ["Pronto data", "Subcontract suppliers and purchase orders", "Cost", "Accruals", "Timesheets", "Revenue"]


def run(con, pid):
    res = engine.compute(con, pid)
    M = res["status_month"]
    tol = max(res.get("tolerance") or 1, 1)
    out = []

    def add(section, id_, level, title, detail="", rows=None, link=None, count=None, amount=None):
        rows = rows or []
        out.append(dict(section=section, id=id_, level=level, title=title, detail=detail, rows=rows, link=link,
                        count=count if count is not None else len(rows), amount=amount))

    # ---- Pronto data --------------------------------------------------------------------------------------------
    h = {c["id"]: c for c in reports.health(con, pid, res)}
    for k in ("pronto_future", "pronto_none", "pronto_stale", "pronto_ok"):
        if k in h:
            rows = [dict(item=f"{r['tx_date']} {r['doc_type']} {r['doc_no']} {r['account_desc'] or ''}".strip(), pmt=f"{r['category']}: {r['description'] or ''}",
                         pronto=f"{r['cost']:,.2f}") for r in pronto_raw.future_rows(con, pid)] if k == "pronto_future" else None
            add("Pronto data", k, h[k]["level"], h[k]["title"], h[k]["detail"], rows=rows, link=h[k]["link"])

    # ---- subcontract suppliers and POs ---------------------------------------------------------------------------
    kn, pos = suppliers.known(con, pid), suppliers.all_pos(con, pid)
    sup_rows, po_rows, po_diff, nolink = [], [], [], []
    for s in db.rows(con, "SELECT s.*, n.code AS node_code FROM subcontract s LEFT JOIN cbs_node n ON n.id=s.node_id WHERE s.project_id=? AND s.status!='closed' ORDER BY s.name", (pid,)):
        ls = suppliers.link_state(con, pid, s, kn, pos)
        if ls["supplier"] != "pronto":
            sug = suppliers.suggest(con, pid, s.get("supplier_name") or s["name"])
            sup_rows.append(dict(sub_id=s["id"], item=s["name"], pmt=s.get("supplier_name") or s.get("supplier_code") or "(none)",
                                 pronto=", ".join(f"{n} ({c})" for c, n, _ in sug) or "no similar supplier yet",
                                 match=[dict(code=c, name=n, score=x) for c, n, x in sug]))
        if ls["po"] != "pronto":
            have = sorted((kn.get(s.get("supplier_code") or "") or {}).get("pos", {}).values(), key=lambda p: p["order_no"])
            po_rows.append(dict(sub_id=s["id"], item=s["name"], pmt=s.get("po_no") or "(none)",
                                pronto=", ".join(f"{p['order_no']} ({p['committed']:,.0f})" for p in have[:5]) or "no PO for this supplier yet",
                                match_po=[p["order_no"] for p in have]))
        for n in ls["notes"]:
            po_diff.append(dict(sub_id=s["id"], item=s["name"], pmt=s.get("po_no") or "", pronto=n))
        if not s.get("node_id"):
            nolink.append(dict(sub_id=s["id"], item=s["name"], pmt="no CBS line", pronto=""))
    sec = "Subcontract suppliers and purchase orders"
    add(sec, "sub_supplier", "warn" if sup_rows else "ok", "Subcontract suppliers not yet matched to Pronto" if sup_rows else "Every subcontract supplier is in Pronto",
        "Entered ahead of the Pronto data. Match each to the Pronto supplier once it comes through (closest names suggested)." if sup_rows else "", sup_rows, "subcontracts")
    add(sec, "sub_po", "warn" if po_rows else "ok", "Subcontract purchase orders not yet in Pronto" if po_rows else "Every subcontract PO is in Pronto",
        "PO numbers typed ahead of Pronto, or no PO yet. Pick the Pronto PO once it is raised." if po_rows else "", po_rows, "subcontracts")
    if po_diff:
        add(sec, "sub_po_diff", "error", "Subcontract PO differs from Pronto", "The PO belongs to another supplier in Pronto, or its value differs from the subcontract.", po_diff, "subcontracts")
    if nolink:
        add(sec, "sub_nocbs", "warn", "Subcontracts not linked to a CBS line", "Their claims cannot reach cost control.", nolink, "subcontracts")

    # ---- cost ------------------------------------------------------------------------------------------------------
    rec = reports.reconcile(con, pid, res)
    tie = [dict(item=t["category"], pmt=t["pmt"], pronto=t["pronto"], diff=t["diff"]) for t in rec["tie"] if t["diff"] is not None and abs(t["diff"]) > tol]
    if any(t["pronto"] is not None for t in rec["tie"]):
        add("Cost", "ctd_tie", "error" if tie else "ok", "Cost to date does not tie to the Pronto CTD overview" if tie else "Cost to date ties to the Pronto CTD overview",
            "By category: PMT's cost to date against Pronto's CTD overview." if tie else "", tie, "reconcile", amount=sum(abs(t["diff"]) for t in tie))
    if res["unplaced"]:
        add("Cost", "unplaced", "error", "Pronto cost on categories that are not in the CBS", "These rows are not counted anywhere until the category is added.",
            [dict(item=u["category"], pmt="not in the CBS", pronto=u["cost"], diff=u["cost"], note=f"{u['n']} rows") for u in res["unplaced"]], "cbs")
    for k in ("parked", "po_missing", "ctc_short"):
        if k in h:
            add("Cost", k, h[k]["level"], h[k]["title"], h[k]["detail"], link=h[k]["link"], count=h[k]["count"])

    # ---- accruals ----------------------------------------------------------------------------------------------------
    inv = db.rows(con, "SELECT a.*, n.code FROM accrual a LEFT JOIN cbs_node n ON n.id=a.node_id WHERE a.project_id=? AND a.status='investigate' ORDER BY a.month", (pid,))
    if inv:
        add("Accruals", "acc_investigate", "error", "Invoice or timesheet landed for a different amount than accrued", "Accrued in PMT against what landed in Pronto.",
            [dict(item=f"{a.get('code') or ''} {a.get('reason') or a.get('inv_ref') or ''}".strip(), pmt=a["amount"], pronto=a.get("matched_amount"),
                  diff=(a.get("matched_amount") or 0) - (a["amount"] or 0), acc_id=a["id"]) for a in inv], "accruals")
    part = db.rows(con, "SELECT a.*, n.code FROM accrual a LEFT JOIN cbs_node n ON n.id=a.node_id WHERE a.project_id=? AND a.status='partial' ORDER BY a.month", (pid,))
    if part:
        add("Accruals", "acc_partial", "warn", "Hour accruals only partly covered by posted timesheets", "The rest still counts as accrued.",
            [dict(item=f"{a.get('code') or ''} {a.get('day') or a['month']}", pmt=a["amount"], pronto=a.get("matched_amount"), diff=(a.get("matched_amount") or 0) - (a["amount"] or 0), acc_id=a["id"]) for a in part], "accruals")
    if "accr_old" in h:
        add("Accruals", "accr_old", "warn", h["accr_old"]["title"], "Nothing has landed in Pronto for them yet. Reverse or confirm them.", link="accruals", count=h["accr_old"]["count"])

    # ---- timesheets -------------------------------------------------------------------------------------------------
    un = db.rows(con, f"SELECT l.resource_code, MAX(l.name) AS resource_name, COUNT(*) n, SUM(l.hours) hrs, SUM({accruals.UNPOSTED_COST}) cost FROM pronto_labour l "
                      f"WHERE l.project_id=? AND l.posted=0 AND {accruals.UNPOSTED_NOT_ACCRUED} GROUP BY l.resource_code ORDER BY l.resource_code", (pid,))
    if un:
        add("Timesheets", "unposted", "warn", "Unposted Pronto timesheets you have not accrued", "PMT accrues them automatically at Pronto's cost (or hours x cost rate) until you accrue them on the labour calendar.",
            [dict(item=f"{u['resource_code']} {u.get('resource_name') or ''}".strip(), pmt="not accrued by you", pronto=u["cost"], note=f"{u['n']} day(s), {u['hrs']:.1f} h") for u in un], "calendar")

    # ---- revenue -----------------------------------------------------------------------------------------------------
    checks, has_pronto = eom_report._claims_check(con, pid)
    if has_pronto:
        bad = [c for c in checks if c["status"] not in ("OK", "Fully paid")]
        add("Revenue", "claims", "error" if any(c["status"] == "CHECK" for c in bad) else ("warn" if bad else "ok"),
            "Client claims: PMT and Pronto differ" if bad else "Client claims agree with Pronto", "Certified and paid amounts in PMT against the Pronto claims export." if bad else "",
            [dict(item=c["check"], pmt=c["pmt"], pronto=c["pronto"], diff=c["diff"], note=c["status"]) for c in bad], "revenue")
    items = revenue.items_tree(con, pid)
    var = [v for v in eom_report._variations(con, pid, M, items) if v["state"] != "ok"]
    if var:
        add("Revenue", "variations", "warn", "Approved variations missing from Pronto or at a different value", "",
            [dict(item=f"{v['ref']} {v['title']}".strip(), pmt=v["approved"], pronto=v["pronto"]) for v in var], "variations")
    for c in out:
        c["section_order"] = SECTIONS.index(c["section"]) if c["section"] in SECTIONS else 99
    out.sort(key=lambda c: (c["section_order"], {"error": 0, "warn": 1, "ok": 2}.get(c["level"], 3)))
    return dict(status_month=M, checks=out, errors=sum(1 for c in out if c["level"] == "error"), warnings=sum(1 for c in out if c["level"] == "warn"),
                sections=SECTIONS)


def match_subcontract(con, pid, sid, supplier_code=None, po_no=None):
    """Tie a subcontract entered ahead of Pronto to the Pronto supplier and / or PO."""
    s = db.one(con, "SELECT * FROM subcontract WHERE id=? AND project_id=?", (sid, pid))
    if not s:
        raise ValueError("Subcontract not found")
    d = {}
    if supplier_code:
        kn = suppliers.known(con, pid)
        if supplier_code not in kn:
            raise ValueError(f"{supplier_code} is not a Pronto supplier")
        d.update(supplier_code=supplier_code, supplier_name=kn[supplier_code]["name"])
    if po_no:
        d["po_no"] = po_no
    if d:
        db.update(con, "subcontract", sid, d)
    return d
