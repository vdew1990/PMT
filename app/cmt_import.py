"""Read an EPEC Cost Management Tool (CMT) workbook, compare it with cost control in the app and, item by item, align the app.

The CMT sheets used: "Project Summary" (period ending, revenue, cost by category), "Financial Summary" (read for the period only)
and "Forecast Costs & Revenue" (one row per resource, supplier or PO under each category total row, with CTD, CTC, EAC and the
forecast month columns). Aligning a line sets its forecast method to MANUAL and loads the CMT forecast months from the status month on.
"""
import json
import re

import openpyxl

from . import db, engine, programme, revenue

TOL = 1.0   # dollars below which two figures are treated as the same


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _txt(v):
    return re.sub(r"\s+", " ", str(v if v is not None else "").replace("\xa0", " ")).strip()


def _month(v):
    s = str(v)[:7]
    return s if re.match(r"\d{4}-\d{2}$", s) else None


def _sheet(wb, name):
    for ws in wb.worksheets:
        if ws.title.strip().lower() == name.lower():
            return ws
    return None


def parse(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ps, fc = _sheet(wb, "Project Summary"), _sheet(wb, "Forecast Costs & Revenue")
    if not ps or not fc:
        raise ValueError("This does not look like a CMT: the sheets 'Project Summary' and 'Forecast Costs & Revenue' were not found")
    out = dict(project=None, period=None, revenue={}, categories=[], lines=[], forecast_months=[])
    for r in ps.iter_rows(max_row=80, values_only=True):
        r = list(r) + [None] * 12
        if _txt(r[2]).startswith("Period Ending") or (r[1] and not out["project"] and _month(r[2])):
            pass
        if r[1] and _month(r[2]) and not out["period"]:
            out["project"], out["period"] = _txt(r[1]), _month(r[2])
        code = _txt(r[1])
        if code == "000" and _txt(r[2]) == "Revenue":
            out["revenue"] = dict(original=_num(r[3]), variations=_num(r[4]), revised=_num(r[5]), claimed=_num(r[6]), to_claim=_num(r[8]), total=_num(r[9]))
        elif re.match(r"^P[LSME]\d\d$", code):
            out["categories"].append(dict(cat=code, name=_txt(r[2]), budget=_num(r[5]), ctd=_num(r[6]), commit=_num(r[7]), ctc=_num(r[8]), eac=_num(r[9])))
    rows = list(fc.iter_rows(values_only=True))
    hdr = next((i for i, r in enumerate(rows) if len(r) > 5 and _txt(r[1]) == "Category" and _txt(r[3]).startswith("Resource/Task")), None)
    if hdr is None:
        raise ValueError("The forecast sheet has no 'Category / Resource/Task' heading row")
    H = {_txt(v): j for j, v in enumerate(rows[hdr]) if v not in (None, "")}
    fcols = [(j, _month(rows[hdr][j])) for j in range(len(rows[hdr])) if _month(rows[hdr][j])
             and any(k >= 0 and j < len(rows[k]) and _txt(rows[k][j]) == "Forecast" for k in (hdr - 1, hdr - 2))]
    out["forecast_months"] = [m for _, m in fcols]
    out["sheet"] = fc.title
    out["fcols"] = {m: j + 1 for j, m in fcols}      # month -> sheet column (1-based), for writing the app's figures back
    col = lambda name: next((j for k, j in H.items() if k.startswith(name)), None)
    cName, cPO, cRes, cSup = col("Resource/Task"), col("PO Number"), col("Resource Code"), col("Subbie")
    cBud, cCTD, cCTC, cEAC = H.get("New Budget"), H.get("CTD"), H.get("CTC"), H.get("EAC")
    cat = None
    for i, r in enumerate(rows[hdr + 1:], hdr + 2):
        r = list(r) + [None] * 70
        if _txt(r[0]) == "Total" and re.match(r"^P[LSME]\d\d$", _txt(r[1])):
            cat = _txt(r[1]); continue
        if not cat or all(r[j] in (None, "") for j in (cName, cPO, cRes, cSup)):
            continue
        months = {}
        for j, m in fcols:
            if _num(r[j]):
                months[m] = months.get(m, 0.0) + _num(r[j])
        ctc, eac = _num(r[cCTC]), _num(r[cEAC])
        if not months and not ctc and not eac:
            continue
        out["lines"].append(dict(row=i, cat=cat, task=_txt(r[cName]), po=_txt(r[cPO]), rcode=_txt(r[cRes]), supplier=_txt(r[cSup]),
                                 budget=_num(r[cBud]) if cBud is not None else 0.0, ctd=_num(r[cCTD]), ctc=ctc, eac=eac, months=months))
    return out


# ---- comparing with the app ---------------------------------------------------------------------------
def _cat_of(row):
    return (row.get("code") or "").split(".")[0]


def _label(l):
    return " / ".join(x for x in (l["task"], l["supplier"] if l["rcode"] in ("", "\xa0") else l["po"] or l["supplier"]) if x) or l["rcode"] or f"row {l['row']}"


def _cands(l, cands):
    """The app lines a CMT line could be: (score, how, row), best first. A resource code or PO number match is exact (how code/po)."""
    out = []
    tk = programme._tok(f"{l['task']} {l['supplier']} {l['po'] if not l['rcode'] else ''}")
    for r in cands:
        if l["rcode"] and r.get("resource_code") and r["resource_code"].lower() == l["rcode"].lower():
            out.append((1.0, "code", r)); continue
        if l["po"] and r.get("po_no") and l["po"] in str(r["po_no"]).replace(" ", "").split(","):
            out.append((1.0, "po", r)); continue
        out.append((programme._score(tk, programme._tok(f"{r['name']} {r.get('function') or ''} {r.get('scope') or ''}")), "name", r))
    return sorted(out, key=lambda x: -x[0])


def compare(con, pid, cmt):
    """Items to review. A match is 'exact' only when a resource code or PO number ties one CMT line to one app line; every other
    match (by name, or several CMT lines on one app line) is 'weak' and carries the candidate app lines for the user to choose from."""
    res = engine.compute(con, pid)
    sm, grid = res["status_month"], res["grid"]
    rows = res["rows"]
    lines = [r for r in rows if r["kind"] == "line"]
    by_cat = {}
    for r in lines:
        by_cat.setdefault(_cat_of(r), []).append(r)
    ranked = []
    for l in cmt["lines"]:
        cs = _cands(l, by_cat.get(l["cat"], []))
        top = cs[0] if cs and (cs[0][1] != "name" or cs[0][0] >= 0.6) else None
        ranked.append((l, top, cs[:5]))
    hits = {}
    for l, top, _ in ranked:
        if top:
            hits[top[2]["node_id"]] = hits.get(top[2]["node_id"], 0) + 1
    items, matched_nodes = [], set()
    months_of = lambda l: {m: round(v, 2) for m, v in l["months"].items() if m >= sm and abs(v) > 0.004}
    for l, top, cs in ranked:
        cm = months_of(l)
        cand = [dict(node_id=r["node_id"], label=f"{r['code']} {r['name']}", score=round(sc, 2)) for sc, _, r in cs if sc >= 0.3]
        if top:
            sc, how, r = top
            matched_nodes.add(r["node_id"])
            exact = how in ("code", "po") and hits[r["node_id"]] == 1
            am = {grid[i]: round(v, 2) for i, v in enumerate(r["f"]) if grid[i] >= sm and abs(v) > 0.004}
            diff = [m for m in sorted(set(cm) | set(am)) if abs(cm.get(m, 0) - am.get(m, 0)) > TOL] if exact else sorted(set(cm) | set(am))
            if exact and not diff and r.get("method"):
                continue
            if not exact and not cm:
                continue
            why = None if exact else ("several CMT lines point to this app line" if hits[r["node_id"]] > 1 else "matched by name only")
            items.append(dict(id=f"f{r['node_id']}" if exact else f"w{l['row']}", kind="forecast", node_id=r["node_id"], title=f"{r['code']} {r['name']}", cat=_cat_of(r), cmt_label=_label(l), method=r.get("method"),
                              row=l["row"], app_months=am, cmt_ok=hits[r["node_id"]] == 1,
                              match="exact" if exact else "weak", why=why, candidates=cand,
                              app_total=round(sum(am.values()), 2), cmt_total=round(sum(cm.values()), 2),
                              months=[dict(month=m, app=am.get(m, 0.0), cmt=cm.get(m, 0.0)) for m in diff], cmt_months=cm))
        elif cm:
            parent = next((r for r in rows if r["kind"] == "group" and r.get("category") == l["cat"]), None)
            items.append(dict(id=f"n{l['row']}", kind="new_line", title=_label(l), cat=l["cat"], parent_id=parent["node_id"] if parent else None, match="weak", row=l["row"], app_months={}, cmt_ok=True, why="no app line found" + (" (possible lines listed)" if cand else ""),
                              candidates=cand, cmt_label=f"CMT row {l['row']}", app_total=0.0, cmt_total=round(sum(cm.values()), 2), months=[dict(month=m, app=0.0, cmt=v) for m, v in sorted(cm.items())],
                              cmt_months=cm, rcode=l["rcode"], po=l["po"], supplier=l["supplier"], note=None if parent else f"No CBS group for {l['cat']} in the app: this can only be reported"))
    items = [i for i in items if i["months"]]
    groups = matched_nodes
    # category budgets: aligning posts an adjustment on the category's CBS group for the difference
    for c in cmt["categories"]:
        a = [x for x in lines if _cat_of(x) == c["cat"]]
        app_budget = round(sum(x["allowance"] for x in a), 2)
        parent = next((r for r in rows if r["kind"] == "group" and r.get("category") == c["cat"]), None)
        if abs(c["budget"] - app_budget) > TOL and c["cat"] != "PE09":
            items.append(dict(id=f"b{c['cat']}", kind="budget", title=f"{c['cat']} {c['name']}: budget", cat=c["cat"], parent_id=parent["node_id"] if parent else None, match="exact",
                              cmt_label="CMT revised budget", app_total=app_budget, cmt_total=round(c["budget"], 2), months=[], cmt_months={}, delta=round(c["budget"] - app_budget, 2),
                              note=None if parent else f"No CBS group for {c['cat']} in the app: reported only"))
    # app lines with forecast that the CMT does not carry
    for r in lines:
        if r["node_id"] in groups:
            continue
        am = {grid[i]: round(v, 2) for i, v in enumerate(r["f"]) if grid[i] >= sm and abs(v) > TOL}
        if am:
            items.append(dict(id=f"o{r['node_id']}", kind="app_only", title=f"{r['code']} {r['name']}", cat=_cat_of(r), cmt_label="not in the CMT", app_total=round(sum(am.values()), 2), cmt_total=0.0,
                              months=[dict(month=m, app=v, cmt=0.0) for m, v in sorted(am.items())], cmt_months={}, note="Reported only: the app keeps this forecast"))
    # category and project level: reported, not aligned (budgets move by transfers, claims by the claim schedule)
    cats = []
    for c in cmt["categories"]:
        a = [x for x in lines if _cat_of(x) == c["cat"]]
        cats.append(dict(cat=c["cat"], name=c["name"], budget_cmt=c["budget"], budget_app=round(sum(x["allowance"] for x in a), 2), ctd_cmt=c["ctd"], ctd_app=round(sum(x["ctd"] for x in a), 2),
                         ctc_cmt=c["ctc"], ctc_app=round(sum(x["ctc"] for x in a), 2), eac_cmt=c["eac"], eac_app=round(sum(x["eac"] for x in a), 2)))
    rv = revenue.summary(con, pid)
    proj = db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,))
    last = db.project_settings(con, pid).get("cmt_decisions") or {}
    for i in items:
        i["key"] = f"{i['kind']}:{i['title']}"
        i["last"] = last.get(i["key"])
    meta = dict(sheet=cmt.get("sheet"), fcols=cmt.get("fcols") or {})
    summary = dict(project=cmt["project"], period_cmt=cmt["period"], period_app=sm, categories=cats,
                   revenue=dict(cmt_revised=cmt["revenue"].get("revised"), app_recognised=rv.get("recognised"), cmt_claimed=cmt["revenue"].get("claimed"), cmt_total=cmt["revenue"].get("total")),
                   cmt_lines=len(cmt["lines"]), matched=sum(1 for _, t, _c in ranked if t), exact=sum(1 for i in items if i.get("match") == "exact"), review=sum(1 for i in items if i.get("match") == "weak"))
    return dict(items=items, summary=summary, meta=meta)


def apply(con, pid, analysis, decisions, targets=None):
    """Apply the items the user chose to align. A weak match is applied to the CBS line the user picked for it (targets: item id -> node id);
    without a pick it is skipped. Items aligned onto the same line add up. Returns counts; an undo record is kept on the project."""
    from . import services
    targets = targets or {}
    res = engine.compute(con, pid)
    sm = res["status_month"]
    valid = {r["node_id"] for r in res["rows"] if r["kind"] == "line"}
    valid_groups = {r["node_id"] for r in res["rows"] if r["kind"] == "group"}
    budgets, n_b = [], 0
    plan, skipped = {}, []        # node id -> months; new lines are made first
    new = []
    for it in analysis["items"]:
        if decisions.get(it["id"]) != "align":
            continue
        pick = targets.get(it["id"])
        pick = int(pick) if str(pick or "").isdigit() else None
        if it["kind"] == "forecast":
            nid = pick if (it.get("match") == "weak" and pick) else it["node_id"] if it.get("match") == "exact" else None
        elif it["kind"] == "new_line":
            nid = pick
        elif it["kind"] == "budget" and it.get("parent_id") in valid_groups:
            pair = services.post_ledger(con, pid, "adjustment", [(it["parent_id"], it["delta"], 0)], ref="CMT", note=f"Aligned to the CMT revised budget ({it['cat']})")
            budgets.append(pair); n_b += 1
            continue
        else:
            skipped.append(it["title"]); continue
        if nid is None and it["kind"] == "new_line" and it.get("parent_id"):
            new.append(it); continue
        if nid is None or nid not in valid:
            skipped.append(f"{it['title']} (choose the CBS line it belongs to)"); continue
        acc = plan.setdefault(nid, {})
        for m, a in it["cmt_months"].items():
            acc[m] = acc.get(m, 0.0) + a
    undo, n_f, n_new = [], 0, 0
    for it in new:
        nid = services.add_node(con, pid, it["parent_id"], it["title"].split(" / ")[0] if not it.get("rcode") else (it["title"] or it["rcode"]), kind="line", method="MANUAL",
                                resource_code=None, po_no=it.get("po") or None, origin="cmt")
        undo.append(dict(node_id=nid, created=True)); n_new += 1
        plan[nid] = dict(it["cmt_months"])
    for nid, months in plan.items():
        created = any(u["node_id"] == nid and u.get("created") for u in undo)
        if not created:
            node = db.one(con, "SELECT method FROM cbs_node WHERE id=? AND project_id=?", (nid, pid))
            before = db.rows(con, "SELECT month, amount FROM forecast_manual WHERE project_id=? AND node_id=? AND item_id IS NULL", (pid, nid))
            undo.append(dict(node_id=nid, method=node["method"], months=before, created=False)); n_f += 1
        con.execute("DELETE FROM forecast_manual WHERE node_id=? AND item_id IS NULL AND month>=?", (nid, sm))
        for m, a in months.items():
            if m >= sm and a:
                db.insert(con, "forecast_manual", dict(project_id=pid, node_id=nid, item_id=None, month=m, amount=round(float(a), 2)))
        db.update(con, "cbs_node", nid, {"method": "MANUAL"})
    s = db.project_settings(con, pid)
    s["cmt_undo"] = undo + [dict(pair_id=p_, budget=True) for p_ in budgets]
    keep = s.get("cmt_decisions") or {}
    for it in analysis["items"]:
        if it.get("key") and it["id"] in decisions:
            keep[it["key"]] = decisions[it["id"]]
    s["cmt_decisions"] = dict(list(keep.items())[-600:])
    db.update(con, "project", pid, {"settings_json": json.dumps(s)})
    return dict(forecast=n_f, new_lines=n_new, budgets=n_b, skipped=skipped)


def undo(con, pid):
    s = db.project_settings(con, pid)
    recs = s.pop("cmt_undo", None) or []
    for u in recs:
        if u.get("budget"):
            con.execute("DELETE FROM allowance_ledger WHERE project_id=? AND pair_id=?", (pid, u["pair_id"])); continue
        nid = u["node_id"]
        if u.get("created"):
            con.execute("DELETE FROM cbs_node WHERE id=? AND project_id=?", (nid, pid)); continue
        con.execute("DELETE FROM forecast_manual WHERE node_id=? AND item_id IS NULL", (nid,))
        for m in u["months"]:
            db.insert(con, "forecast_manual", dict(project_id=pid, node_id=nid, item_id=None, month=m["month"], amount=m["amount"]))
        db.update(con, "cbs_node", nid, {"method": u["method"]})
    db.update(con, "project", pid, {"settings_json": json.dumps(s)})
    return len(recs)


def report_xlsx(analysis):
    """The gap analysis as a workbook: category totals and every difference with its match quality."""
    import io
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Categories"
    s = analysis["summary"]
    ws.append(["Category", "Budget CMT", "Allowance app", "CTD CMT", "CTD app", "CTC CMT", "CTC app", "EAC CMT", "EAC app"])
    for c in s["categories"]:
        ws.append([f"{c['cat']} {c['name']}", c["budget_cmt"], c["budget_app"], c["ctd_cmt"], c["ctd_app"], c["ctc_cmt"], c["ctc_app"], c["eac_cmt"], c["eac_app"]])
    ws.append([]); ws.append(["Revenue", "CMT revised contract", s["revenue"]["cmt_revised"], "CMT claimed", s["revenue"]["cmt_claimed"], "App recognised", s["revenue"]["app_recognised"]])
    d = wb.create_sheet("Differences")
    d.append(["Kind", "Category", "Item", "CMT line", "Match", "Why", "Forecast or budget app", "Forecast or budget CMT", "Months that differ (app to CMT)"])
    for i in analysis["items"]:
        d.append([i["kind"], i.get("cat"), i["title"], i.get("cmt_label"), i.get("match") or "", i.get("why") or i.get("note") or "", i["app_total"], i["cmt_total"],
                  "; ".join(f"{m['month']} {m['app']:.0f} to {m['cmt']:.0f}" for m in i["months"])])
    for w in (ws, d):
        for col in w.columns:
            w.column_dimensions[col[0].column_letter].width = 22
    out = io.BytesIO(); wb.save(out)
    return out.getvalue()


# ---- the CMT aligned to the app: the updated workbook --------------------------------------------------------------
def cmt_edits(analysis, decisions):
    """{(row, column): value} for every item the user chose to align the CMT to the app: that CMT line's forecast months get the app's figures."""
    cols = (analysis.get("meta") or {}).get("fcols") or {}
    out = {}
    for it in analysis["items"]:
        if decisions.get(it["id"]) != "cmt" or not it.get("cmt_ok") or not it.get("row"):
            continue
        for m, c in cols.items():
            out[(int(it["row"]), int(c))] = round(float((it.get("app_months") or {}).get(m, 0.0)), 2)
    return out


_CELL = re.compile(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', re.S)
_F = re.compile(r'<f([^>]*?)(?:/>|>(.*?)</f>)', re.S)


def _col_no(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _col_letters(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def edit_sheet_xml(xml, edits):
    """Put numbers into cells of a worksheet's XML without touching anything else. Formulas shared with an edited cell are
    written out cell by cell first (so no other cell loses its formula). edits: {(row, column): value}."""
    import html
    from xml.sax.saxutils import escape
    from openpyxl.formula.translate import Translator
    want = {f"{_col_letters(c)}{r}" for r, c in edits}
    # which shared-formula groups does an edited cell belong to, and what is each group's master formula?
    touched, masters = set(), {}
    for m in _CELL.finditer(xml):
        inner = m.group(4) or ""
        fm = _F.search(inner)
        if not fm:
            continue
        attrs, text = fm.group(1), fm.group(2)
        if 't="shared"' not in attrs:
            continue
        si = re.search(r'si="(\d+)"', attrs).group(1)
        if f"{m.group(1)}{m.group(2)}" in want:
            touched.add(si)
        if text and 'ref="' in attrs:
            masters[si] = (f"{m.group(1)}{m.group(2)}", text)

    def expand(m):
        inner = m.group(4)
        fm = _F.search(inner or "")
        if not fm or 't="shared"' not in fm.group(1):
            return m.group(0)
        si = re.search(r'si="(\d+)"', fm.group(1)).group(1)
        if si not in touched or si not in masters:
            return m.group(0)
        ref = f"{m.group(1)}{m.group(2)}"
        origin, text = masters[si]
        f = text if ref == origin else escape(Translator("=" + html.unescape(text), origin=origin).translate_formula(ref)[1:])
        keep = re.sub(r'\s*(t|ref|si)="[^"]*"', "", fm.group(1))
        return f'<c r="{ref}"{m.group(3)}>' + inner[:fm.start()] + f"<f{keep}>{f}</f>" + inner[fm.end():] + "</c>"
    if touched:
        xml = _CELL.sub(expand, xml)

    by_row = {}
    for (r, c), v in edits.items():
        by_row.setdefault(r, {})[c] = v
    for r, cells in by_row.items():
        rm = re.search(rf'<row r="{r}"([^>]*?)(?:/>|>(.*?)</row>)', xml, re.S)
        if not rm:
            continue
        body = rm.group(2) or ""
        have = {_col_no(m.group(1)): m for m in _CELL.finditer(body)}
        new = []
        for c in sorted(set(have) | set(cells)):
            if c in cells:
                st = re.search(r'\ss="(\d+)"', have[c].group(3)).group(0) if c in have and re.search(r'\ss="(\d+)"', have[c].group(3)) else ""
                new.append(f'<c r="{_col_letters(c)}{r}"{st}><v>{cells[c]!r}</v></c>')
            else:
                new.append(have[c].group(0))
        rowattrs = rm.group(1).rstrip("/")
        xml = xml[:rm.start()] + f'<row r="{r}"{rowattrs}>' + "".join(new) + "</row>" + xml[rm.end():]
    return xml


def updated_workbook(src_path, sheet_name, edits):
    """The original CMT with the app's figures written into the chosen forecast cells, as bytes. Done on the file's XML, so charts,
    pivot tables, comments and form controls are kept exactly; the calculation chain is dropped and Excel recalculates on opening."""
    import io
    import zipfile
    from html import unescape
    with zipfile.ZipFile(src_path) as zin:
        wb = zin.read("xl/workbook.xml").decode("utf8")
        rels = zin.read("xl/_rels/workbook.xml.rels").decode("utf8")
        rid = next((re.search(r'r:id="([^"]+)"', m).group(1) for m in re.findall(r"<sheet [^>]*>", wb) if unescape(re.search(r'name="([^"]*)"', m).group(1)) == sheet_name), None)
        if not rid:
            raise ValueError("The forecast sheet was not found in the CMT")
        tgt = next(re.search(r'Target="([^"]+)"', m).group(1) for m in re.findall(r"<Relationship [^>]*>", rels) if f'Id="{rid}"' in m)
        sheet_part = "xl/" + tgt.lstrip("/").replace("xl/", "", 1)
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == sheet_part:
                    data = edit_sheet_xml(data.decode("utf8"), edits).encode("utf8")
                elif item.filename == "xl/calcChain.xml":
                    continue
                elif item.filename == "[Content_Types].xml":
                    data = re.sub(r'<Override[^>]*calcChain[^>]*/>', "", data.decode("utf8")).encode("utf8")
                elif item.filename == "xl/_rels/workbook.xml.rels":
                    data = re.sub(r'<Relationship [^>]*calcChain[^>]*/>', "", data.decode("utf8")).encode("utf8")
                elif item.filename == "xl/workbook.xml":
                    t = data.decode("utf8")
                    t = re.sub(r"<calcPr ", '<calcPr fullCalcOnLoad="1" ', t, count=1) if "<calcPr " in t and "fullCalcOnLoad" not in t else t
                    data = t.encode("utf8")
                zout.writestr(item, data)
    return out.getvalue()
