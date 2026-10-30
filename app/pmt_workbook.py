"""Load a project from the PMT Excel workbook (the .xlsm the app replaces), so the app starts where the workbook stands.

What is read (sheet > table):
  Cost Control   one row per resource line (CC key 'cc.cat.1.nnn'): Budget [src], Risk [src], dates, the month grid.
                 'cat.1.999' Bulk - Future / CTC (Unallocated) and 'cat.1.998' Work in Progress rows are the category's pot.
  Allowance      the estimate items (AL key 'cc.cat.0.nnn'): current budget and risk left on each.
  Ledger         every Allocation to child / Return to pot / Budget Transfer between those keys.
  Accruals       tbl_Accruals (the PM register, columns A:N).

What it does in the app (apply):
  - lines the workbook has and the app does not get created under their category (with the resource code);
  - the Ledger is replayed as transfers, then each node is trued up to the workbook's figures (approved variations on
    the category, any other difference as an adjustment), so allowance per line equals Cost Control's;
  - forecast: each line becomes MANUAL with the workbook grid from the status month on (CURRENT (F) + FUTURE);
  - accruals: the register is loaded (invoice accruals where it has an invoice or PO number, so the app's matcher
    reverses them when the invoice lands, as the workbook's did); the PM's unposted-timesheet rows (Source "Pronto")
    are kept as Timesheet accruals and the app's automatic accrual stands down for that line and month.
Re-applying replaces what an earlier import wrote (ref / note "PMT workbook"); nothing else is touched.
"""
import io
import re
import uuid
from collections import defaultdict
from datetime import date, datetime

from . import accruals, db, services

REF = "PMT workbook"
GPS = ("PL", "PS", "PM", "PE")


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _s(v):
    return "" if v is None else str(v).strip()


def _month(v):
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m")
    if isinstance(v, (int, float)) and 20000 < v < 80000:   # an Excel serial left as a number
        return date.fromordinal(date(1899, 12, 30).toordinal() + int(v)).strftime("%Y-%m")
    s = _s(v)
    return s[:7] if re.match(r"\d{4}-\d\d", s) else None


def _day(v):
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    return None


def read(data):
    """Parse the workbook into plain lists (no database). Raises services.Problem when a sheet is missing."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001
        raise services.Problem(f"Cannot open the workbook: {e}")
    need = ("Cost Control", "Allowance", "Ledger", "Accruals")
    missing = [s for s in need if s not in wb.sheetnames]
    if missing:
        raise services.Problem("This does not look like the PMT workbook: missing sheet(s) " + ", ".join(missing))
    out = dict(status_month=None, lines=[], items=[], ledger=[], accruals=[])

    # ---- Cost Control: header on row 8 (month-end dates from column AF), PAST/CURRENT/FUTURE tags on row 9
    ws = wb["Cost Control"]
    rows = ws.iter_rows(min_row=6, max_col=100, values_only=True)
    r6 = next(rows); next(rows)
    hdr, tag = next(rows), next(rows)
    out["status_month"] = _month(r6[3])
    fut = [(j, _month(hdr[j])) for j in range(31, len(hdr)) if _s(tag[j]).upper().startswith(("FUTURE", "CURRENT (F)")) and _month(hdr[j])]
    for r in rows:
        if not r[0] or not r[1]:
            continue
        grid = defaultdict(float)
        for j, m in fut:
            if _n(r[j]):
                grid[m] += _n(r[j])
        out["lines"].append(dict(cat=_s(r[0]), key=_s(r[1]), function=_s(r[3]), code=_s(r[4]), name=_s(r[5]),
                                 budget=_n(r[6]), risk=_n(r[7]), allowance=_n(r[8]), ctd=_n(r[10]), acc=_n(r[12]), ctc=_n(r[13]),
                                 eac=_n(r[18]), method=_s(r[26]) or _s(r[24]), start=_day(r[27]), end=_day(r[28]), grid=dict(grid)))

    # ---- Allowance: estimate items and variation pots (row 5 header)
    for r in wb["Allowance"].iter_rows(min_row=6, max_col=29, values_only=True):
        if not r[1] or not r[2]:
            continue
        out["items"].append(dict(key=_s(r[1]), cat=_s(r[2]), name=_s(r[4]), orig=_n(r[5]), budget=_n(r[8]),
                                 risk=_n(r[11]) - _n(r[12]), variations=_n(r[20]), origin=_s(r[21])))

    # ---- Ledger (row 7 header)
    for r in wb["Ledger"].iter_rows(min_row=8, max_col=12, values_only=True):
        if not r[1] or not _n(r[8]):
            continue
        out["ledger"].append(dict(date=_day(r[0]), type=_s(r[1]), src=_s(r[2]), dst=_s(r[5]), amount=_n(r[8]), reason=_s(r[9]),
                                  src_desc=_s(r[4]), dst_desc=_s(r[7])))

    # ---- Accruals register tbl_Accruals (A:N, row 5 header)
    for r in wb["Accruals"].iter_rows(min_row=6, max_col=14, values_only=True):
        if not r[0] or not _n(r[8]):
            continue
        out["accruals"].append(dict(cat=_s(r[0]), month=_month(r[2]), source=_s(r[3]), function=_s(r[4]), resource=_s(r[5]),
                                    po=_s(r[6]).split(".")[0] if isinstance(r[6], float) else _s(r[6]), inv=_s(r[7]), amount=_n(r[8]),
                                    note=_s(r[9]), entered=_day(r[10]), key=_s(r[11]), quote=_s(r[13])))
    wb.close()
    return out


def _bulk(key):
    return key.endswith((".999", ".998"))


def plan(con, pid, wbd):
    """How the workbook maps onto the project: {key: node_id}, lines to create, and what cannot be placed."""
    nodes = db.rows(con, "SELECT n.*, r.code rcode FROM cbs_node n LEFT JOIN resource r ON r.id=n.resource_id WHERE n.project_id=?", (pid,))
    cat_node = {n["category"]: n for n in nodes if n["category"] and n["kind"] == "group"}
    by_id = {n["id"]: n for n in nodes}

    def cat_of(n):
        while n and not n["category"]:
            n = by_id.get(n["parent_id"])
        return n["category"] if n else None

    line_of = {}
    for n in nodes:
        if n["kind"] == "line" and n["rcode"]:
            line_of.setdefault((cat_of(n), n["rcode"].strip().upper()), n["id"])
    item_of = {}
    for n in nodes:
        if n["kind"] == "group" and not n["category"] and cat_of(n):   # an estimate item, at whatever depth below its category
            item_of.setdefault((cat_of(n), n["name"].strip().lower()), n["id"])

    key_node, create, unplaced, matched = {}, [], [], 0
    for ln in wbd["lines"]:
        c = cat_node.get(ln["cat"])
        if not c:
            unplaced.append(dict(key=ln["key"], what=f"{ln['cat']} {ln['name']}", why="category not in the CBS"))
            continue
        if _bulk(ln["key"]) or not ln["code"]:
            key_node[ln["key"]] = c["id"]
            continue
        nid = line_of.get((ln["cat"], ln["code"].upper()))
        if nid:
            key_node[ln["key"]] = nid
            matched += 1
        else:
            create.append(ln)
    for it in wbd["items"]:
        c = cat_node.get(it["cat"])
        if c:
            key_node[it["key"]] = item_of.get((it["cat"], it["name"].lower()), c["id"])
    return dict(key_node=key_node, create=create, unplaced=unplaced, matched=matched, cat_node={k: v["id"] for k, v in cat_node.items()})


def preview(con, pid, data):
    wbd = read(data)
    pl = plan(con, pid, wbd)
    return _summary(con, pid, wbd, pl)


def _summary(con, pid, wbd, pl):
    L = wbd["lines"]
    p = db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,)) or {}
    sm = (p.get("status_date") or "")[:7]
    led_keys = {k for e in wbd["ledger"] for k in (e["src"], e["dst"])}
    return dict(
        status_month=wbd["status_month"], project_status_month=sm,
        lines=len(L), matched=pl["matched"], create=[dict(cat=x["cat"], code=x["code"], name=x["name"], budget=x["budget"]) for x in pl["create"] if _keep(x)],
        skipped=[dict(cat=x["cat"], code=x["code"], name=x["name"]) for x in pl["create"] if not _keep(x)],
        unplaced=pl["unplaced"], ledger=len(wbd["ledger"]), ledger_unmapped=sorted(k for k in led_keys if k not in pl["key_node"]),
        accruals=len(wbd["accruals"]), accrual_total=round(sum(a["amount"] for a in wbd["accruals"]), 2),
        totals=dict(budget=round(sum(x["budget"] for x in L), 2), risk=round(sum(x["risk"] for x in L), 2), allowance=round(sum(x["allowance"] for x in L), 2),
                    ctd=round(sum(x["ctd"] for x in L), 2), acc=round(sum(x["acc"] for x in L), 2), ctc=round(sum(x["ctc"] for x in L), 2),
                    eac=round(sum(x["eac"] for x in L), 2), grid_forecast=round(sum(sum(x["grid"].values()) for x in L), 2)))


def _keep(ln):
    """A workbook line the app lacks is created when it carries allowance or a forecast (an empty one is left out)."""
    return abs(ln["budget"]) + abs(ln["risk"]) + sum(abs(v) for v in ln["grid"].values()) > 0.5


def apply(con, pid, data, today=None):
    wbd = read(data)
    p = db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,))
    sm = (p["status_date"] or "")[:7]
    when = today or date.today().isoformat()
    # undo an earlier import
    con.execute("DELETE FROM allowance_ledger WHERE project_id=? AND ref=?", (pid, REF))
    con.execute("DELETE FROM accrual WHERE project_id=? AND note=?", (pid, REF))
    pl = plan(con, pid, wbd)
    created = 0
    for ln in pl["create"]:
        if not _keep(ln):
            continue
        cat = pl["cat_node"][ln["cat"]]
        nid = services.add_node(con, pid, cat, ln["name"] or ln["code"], kind="line", resource_code=ln["code"], resource_name=ln["name"],
                                function=ln["function"] or None, origin="workbook")
        pl["key_node"][ln["key"]] = nid
        created += 1
    K = pl["key_node"]

    # ---- allowance: replay the Ledger, then true each node up to the workbook ------------------------------------
    def post(nid, kind, budget=0.0, risk=0.0, note="", pair=None, dt=None):
        if abs(budget) > 0.004 or abs(risk) > 0.004:
            db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=nid, date=dt or when, kind=kind, budget=round(budget, 2), risk=round(risk, 2),
                                                    ref=REF, note=note, pair_id=pair))
    for e in wbd["ledger"]:
        a, b = K.get(e["src"]), K.get(e["dst"])
        if not a or not b or a == b:
            continue
        pair = uuid.uuid4().hex[:10]
        note = f"{e['type']}: {e['src_desc'] or e['src']} > {e['dst_desc'] or e['dst']}" + (f". {e['reason']}" if e["reason"] else "")
        post(a, "transfer", -e["amount"], note=note, pair=pair, dt=e["date"])
        post(b, "transfer", e["amount"], note=note, pair=pair, dt=e["date"])
    target_b, target_r = defaultdict(float), defaultdict(float)
    for ln in wbd["lines"]:
        nid = K.get(ln["key"])
        if nid:
            target_b[nid] += ln["budget"]
            target_r[nid] += ln["risk"]
    # the category's pot (Bulk) is spread back over the estimate items as the Allowance sheet leaves them; the rest stays on the category
    var_by_cat = defaultdict(float)
    for it in wbd["items"]:
        nid = K.get(it["key"])
        cat = pl["cat_node"].get(it["cat"])
        if it["origin"] == "Variation":
            var_by_cat[cat] += it["variations"]
        if nid and cat and nid != cat:
            target_b[nid] += it["budget"]
            target_r[nid] += it["risk"]
            target_b[cat] -= it["budget"]
            target_r[cat] -= it["risk"]
    for cat, v in var_by_cat.items():
        if cat and abs(v) > 0.5:
            post(cat, "variation", v, note="Approved variations (PMT workbook, Allowance sheet)")
    cur = defaultdict(lambda: [0.0, 0.0])
    for r in con.execute("SELECT node_id, SUM(budget) b, SUM(risk) k FROM allowance_ledger WHERE project_id=? GROUP BY node_id", (pid,)):
        cur[r["node_id"]] = [r["b"] or 0.0, r["k"] or 0.0]
    cleared = 0
    for nid in set(target_b) | set(target_r) | set(cur):
        if nid not in target_b and nid not in target_r:
            # a node the workbook does not know: the workbook holds the whole allowance, so this one ends at nothing
            if abs(cur[nid][0]) > 0.004 or abs(cur[nid][1]) > 0.004:
                post(nid, "adjustment", -cur[nid][0], -cur[nid][1], note="Not in the PMT workbook: its allowance is with the workbook's lines")
                cleared += 1
            continue
        post(nid, "adjustment", target_b[nid] - cur[nid][0], target_r[nid] - cur[nid][1], note="Trued up to the PMT workbook (budget I/O, risk)")

    # ---- forecast: the workbook grid as MANUAL amounts, from the status month on ---------------------------------
    grid = defaultdict(lambda: defaultdict(float))
    meta = {}
    for ln in wbd["lines"]:
        nid = K.get(ln["key"])
        if not nid:
            continue
        for m, v in ln["grid"].items():
            if m >= sm:
                grid[nid][m] += v
        if not _bulk(ln["key"]) and ln["code"]:
            meta[nid] = ln
    touched = set(K.values())
    for nid in touched:
        con.execute("DELETE FROM forecast_manual WHERE project_id=? AND node_id=? AND item_id IS NULL", (pid, nid))
        for m, v in grid.get(nid, {}).items():
            if abs(v) > 0.004:
                db.insert(con, "forecast_manual", dict(project_id=pid, node_id=nid, item_id=None, month=m, amount=round(v, 2)))
        n = db.one(con, "SELECT kind FROM cbs_node WHERE id=?", (nid,))
        if n["kind"] == "line":
            ln = meta.get(nid)
            upd = {"method": "MANUAL"}
            if ln and ln["start"]:
                upd["start_date"] = ln["start"]
            if ln and ln["end"]:
                upd["end_date"] = ln["end"]
            db.update(con, "cbs_node", nid, upd)
        else:
            db.update(con, "cbs_node", nid, {"unalloc_method": "MANUAL"})

    # ---- accruals ------------------------------------------------------------------------------------------------
    acc_n = 0
    for a in wbd["accruals"]:
        nid = K.get(a["key"]) or pl["cat_node"].get(a["cat"])
        if not nid or not a["month"]:
            continue
        ts = a["source"].lower() == "pronto"
        kind = "invoice" if (a["inv"] or a["po"] or a["quote"]) and not ts else "work"
        db.insert(con, "accrual", dict(project_id=pid, node_id=nid, month=a["month"], amount=round(a["amount"], 2), kind=kind,
                                       source="Timesheet" if ts else "PM", inv_ref=a["inv"] or None, po_no=a["po"] or None, quote_ref=a["quote"] or None,
                                       supplier_name=a["resource"] or None, reason=(a["note"] or a["source"])[:500], note=REF))
        acc_n += 1
    accruals.match(con, pid)
    s = _summary(con, pid, wbd, pl)
    s.update(created=created, accruals_loaded=acc_n, cleared=cleared)
    return s


def tieout(con, pid, data):
    """Per category: the workbook's Cost Control against the app after the import (allowance, CTD, ACC, CTC, EAC)."""
    from . import engine
    wbd = read(data)
    wb = defaultdict(lambda: defaultdict(float))
    for ln in wbd["lines"]:
        for k in ("budget", "risk", "ctd", "acc", "ctc", "eac"):
            wb[ln["cat"]][k] += ln[k]
        wb[ln["cat"]]["grid"] += sum(ln["grid"].values())
    res = engine.compute(con, pid)
    app = defaultdict(lambda: defaultdict(float))
    for r in res["rows"]:
        if r["kind"] in ("line", "pot") and r.get("category"):
            c = r["category"]
            app[c]["budget"] += r["budget"]
            app[c]["risk"] += r["risk"]
            for k in ("ctd", "acc", "ctc", "eac"):
                app[c][k] += r[k]
    out = []
    for c in sorted(set(wb) | set(app)):
        out.append(dict(category=c, **{f"wb_{k}": round(wb[c][k], 2) for k in ("budget", "risk", "ctd", "acc", "ctc", "eac", "grid")},
                        **{f"app_{k}": round(app[c][k], 2) for k in ("budget", "risk", "ctd", "acc", "ctc", "eac")}))
    return out
