"""Excel and printable outputs. Branded to the EPEC palette (navy header rows, pale grey banding)."""
import html
from datetime import date
import io

from pathlib import Path
import xlsxwriter

from . import db, engine, reports, revenue, risk as risk_mod, variations
from .taxonomy import PRICING_MODELS

NAVY, ORANGE, GOLD, GREY, SLATE = "#102361", "#e56210", "#ffb500", "#e0e6e8", "#335062"


def _formats(wb):
    base = {"font_name": "Calibri", "font_size": 10}
    mk = lambda **k: wb.add_format({**base, **k})
    return dict(
        title=mk(bold=True, font_size=16, font_color=ORANGE),
        sub=mk(font_color=SLATE, italic=True),
        head=mk(bold=True, font_color="#ffffff", bg_color=NAVY, border=1, text_wrap=True, valign="vcenter", align="center"),
        gp=mk(bold=True, font_color=ORANGE, bg_color=GREY), gp_n=mk(bold=True, font_color=ORANGE, bg_color=GREY, num_format="#,##0;[Red]-#,##0"),
        par=mk(bold=True, font_color=NAVY), par_n=mk(bold=True, font_color=NAVY, num_format="#,##0;[Red]-#,##0"),
        txt=mk(), num=mk(num_format="#,##0;[Red]-#,##0"), band=mk(bg_color=GREY), band_n=mk(bg_color=GREY, num_format="#,##0;[Red]-#,##0"),
        pct=mk(num_format="0.0%"), bold=mk(bold=True), date=mk(num_format="dd/mm/yyyy"),
        lab=mk(bold=True, font_color=NAVY), money=mk(num_format="$#,##0;[Red]-$#,##0"), money_b=mk(bold=True, num_format="$#,##0;[Red]-$#,##0"),
    )


def cost_control_xlsx(con, pid):
    res = engine.compute(con, pid)
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    out = io.BytesIO()
    wb = xlsxwriter.Workbook(out, {"in_memory": True})
    f = _formats(wb)
    ws = wb.add_worksheet("Cost Control")
    ws.write(0, 0, f"{p['name']}: cost control", f["title"])
    ws.write(1, 0, f"Status month {res['status_month']}. EAC = CTD + ACC + CTC. All values AUD excl. GST.", f["sub"])
    heads = ["CBS", "Name", "Function", "Method", "Allowance", "Outstanding PO", "CTD", "ACC", "CTC", "EAC", "Contingency", "Status"]
    for c, h in enumerate(heads):
        ws.write(3, c, h, f["head"])
    grid = res["grid"]
    for i, m in enumerate(grid):
        ws.write(3, len(heads) + i, m, f["head"])
    ws.set_row(3, 30)
    ws.set_column(0, 0, 14)
    ws.set_column(1, 1, 40)
    ws.set_column(2, 3, 18)
    ws.set_column(4, 10, 14)
    ws.set_column(11, 11, 14)
    ws.set_column(len(heads), len(heads) + len(grid), 11)
    r = 4
    for row in res["rows"]:
        lv = row["level"]
        kind = row["kind"]
        t = f["gp"] if lv == 1 else (f["par"] if kind == "group" else f["txt"])
        n = f["gp_n"] if lv == 1 else (f["par_n"] if kind == "group" else f["num"])
        if kind != "group" and r % 2 == 0:
            t, n = f["band"], f["band_n"]
        ws.write(r, 0, row["code"], t)
        ws.write(r, 1, ("    " * max(0, lv - 1)) + row["name"], t)
        ws.write(r, 2, row.get("function") or "", t)
        ws.write(r, 3, row.get("method") or "", t)
        for c, k in enumerate(["allowance", "outstanding", "ctd", "acc", "ctc", "eac", "contingency"], start=4):
            ws.write_number(r, c, row[k] or 0, n)
        ws.write(r, 11, row.get("budget_status") or "", t)
        for i in range(len(grid)):
            v = row["a"][i] + row["x"][i] + row["f"][i]
            ws.write_number(r, len(heads) + i, v, n)
        ws.set_row(r, None, None, {"level": min(max(lv - 1, 0), 6)})
        r += 1
    ws.freeze_panes(4, 2)
    wb.close()
    return out.getvalue()


def pmr_xlsx(con, pid):
    d = reports.pmr(con, pid)
    out = io.BytesIO()
    wb = xlsxwriter.Workbook(out, {"in_memory": True})
    f = _formats(wb)
    ws = wb.add_worksheet("PMR Output")
    ws.set_column(0, 0, 52)
    ws.set_column(1, 1, 18)
    ws.set_column(2, 2, 60)
    ws.write(0, 0, "PMR output: interface to the Project Monthly Report", f["title"])
    r = 2

    def sect(title, rows):
        nonlocal r
        ws.write(r, 0, title, f["head"]); ws.write(r, 1, "Value", f["head"]); ws.write(r, 2, "Note", f["head"]); r += 1
        for lab, v, note in rows:
            ws.write(r, 0, lab, f["txt"])
            if isinstance(v, (int, float)):
                ws.write_number(r, 1, v, f["money"])
            else:
                ws.write(r, 1, v or "", f["txt"])
            ws.write(r, 2, note or "", f["sub"])
            r += 1
        r += 1
    i = d["identity"]
    sect("IDENTITY & DATES", [("Project", i["project"], ""), ("Status date", i["status_date"], ""), ("Project start", i["project_start"], ""),
                              ("Project end", i["project_end"], "")])
    rv = d["revenue"]
    sect("REVENUE", [("Original contract value", rv["original"], ""), ("Approved variations", rv["approved_variations"], ""),
                     ("Revised contract value (official)", rv["revised_official"], ""), ("Recognised revenue", rv["recognised"], "Approved and agreed, including deed pending"),
                     ("Revenue claimed to date", rv["claimed_to_date"], ""), ("Residual to claim", rv["residual"], "")])
    c = d["cost"]
    sect("COST", [("Original budget (excl. risk)", c["original_budget"], ""), ("Approved variations allowance", c["variations_allowance"], ""),
                  ("Current allowance (budget + risk)", c["current_allowance"], ""), ("Cost to date (CTD)", c["ctd"], "All GL cost in Pronto"),
                  ("Accruals (ACC)", c["accruals"], "Open accruals and unposted timesheets"), ("Cost to complete (CTC)", c["ctc"], ""),
                  ("Estimate at completion (EAC)", c["eac"], "CTD + ACC + CTC")])
    k = d["contingency"]
    sect("CONTINGENCY", [("Risk, original", k["original_risk"], ""), ("Risk, current", k["current_risk"], ""),
                         ("Contingency at completion (allowance less EAC)", k["forecast_at_completion"], "Negative = overrun")])
    m = d["margin"]
    sect("MARGIN", [("Original gross profit", m["gp_original"], ""), ("Forecast gross profit", m["gp_forecast"], ""), ("Margin erosion", m["erosion"], "")])
    ws.write(r, 0, "MONTHLY", f["head"]); r += 1
    s = d["series"]
    for c0, h in enumerate(["Month", "Revenue (actual)", "Revenue (planned)", "Cost PS+PM+PE", "Cost labour", "Flag"]):
        ws.write(r, c0, h, f["head"])
    r += 1
    for i2, mth in enumerate(s["months"]):
        ws.write(r, 0, mth, f["txt"])
        for c0, key in enumerate(["revenue_actual", "revenue_planned", "cost_ps_pm_pe", "cost_labour"], start=1):
            ws.write_number(r, c0, s[key][i2], f["money"])
        ws.write(r, 5, s["flag"][i2], f["txt"])
        r += 1
    wb.close()
    return out.getvalue()


def claim_xlsx(con, pid, cid):
    sh = revenue.claim_sheet(con, pid, cid)
    d, rows, tot = sh["claim"], sh["rows"], sh["totals"]
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    out = io.BytesIO()
    wb = xlsxwriter.Workbook(out, {"in_memory": True})
    f = _formats(wb)
    grp = wb.add_format({"bold": True, "bg_color": "#e0e6e8", "font_color": "#335062"})
    grp_n = wb.add_format({"bold": True, "bg_color": "#e0e6e8", "font_color": "#335062", "num_format": "#,##0.00;[Red]-#,##0.00"})
    grp_p = wb.add_format({"bold": True, "bg_color": "#e0e6e8", "font_color": "#335062", "num_format": "0.0%"})
    ws = wb.add_worksheet("Progress claim")
    ws.set_column(0, 0, 10)
    ws.set_column(1, 1, 52)
    ws.set_column(2, 8, 16)
    ws.write(0, 0, f"{p['name']}: progress claim {d['claim_no']}", f["title"])
    ws.write(1, 0, f"Period {d['period']}. Status {d['status']}. AUD excl. GST.", f["sub"])
    heads = ["Ref", "Description", "Contract value", "Previously claimed", "This claim", "Claimed to date", "% complete", "Remaining"]
    for c, h in enumerate(heads):
        ws.write(3, c, h, f["head"])
    r = 4
    for l in rows:
        if l["leaf"]:
            band = r % 2 == 0
            tx, n, pc = (f["band"] if band else f["txt"]), (f["band_n"] if band else f["num"]), f["pct"]
        else:
            tx, n, pc = grp, grp_n, grp_p
        ws.write(r, 0, l["ref"], tx)
        ws.write(r, 1, ("   " * l["depth"]) + l["description"], tx)
        for c, k in ((2, "value"), (3, "prior"), (4, "this"), (5, "to_date")):
            ws.write_number(r, c, l[k], n)
        ws.write_number(r, 6, l["pct"], pc)
        ws.write_number(r, 7, l["remaining"], n)
        if not l["leaf"]:
            ws.set_row(r, None, None, {"level": min(l["depth"], 7)})
        r += 1
    ws.write(r, 1, "Total", f["lab"])
    for c, k in ((2, "value"), (3, "prior"), (4, "this"), (5, "to_date"), (7, "remaining")):
        ws.write_number(r, c, tot[k], f["money_b"])
    ws.write_number(r, 6, tot["pct"], f["pct"])
    ws.freeze_panes(4, 2)
    wb.close()
    return out.getvalue()


EPEC_ADDRESS = "L1/100 Melbourne St, South Brisbane QLD 4101"   # shown on claims (Settings > Company details overrides)
EPEC_NAME, EPEC_ABN = "EPEC Projects Pty Ltd", "34 640 363 686"      # as on EPEC's claim WDSF-FI-CL-0006 and tax invoice WA2-EPE-INV-0006
def company(con):
    """EPEC's details for documents: name, ABN and address (Settings > Company details; shared by everyone). The ABN stays blank until it is typed there."""
    import json
    r = db.one(con, "SELECT value FROM user_setting WHERE upn='*' AND key='company'")
    try:
        got = json.loads(r["value"]) if r and r["value"] else {}
    except ValueError:
        got = {}
    return dict(name=got.get("name") or EPEC_NAME, abn=got.get("abn") or EPEC_ABN, address=(got.get("address") or EPEC_ADDRESS).replace("Melbourne Street", "Melbourne St"), claim_layout=got.get("claim_layout") if got.get("claim_layout") in ("a", "b") else "a")


LOGO_REV = Path(__file__).resolve().parent.parent / "static" / "img" / "epec-logo-rev.png"   # for navy backgrounds


LAWS = ["Queensland", "New South Wales", "Victoria", "Western Australia", "South Australia", "Tasmania", "Northern Territory", "Australian Capital Territory", "Other"]
_STATES = {"QLD": "Queensland", "NSW": "New South Wales", "VIC": "Victoria", "WA": "Western Australia", "SA": "South Australia", "TAS": "Tasmania", "NT": "Northern Territory", "ACT": "Australian Capital Territory"}


def site_state(p):
    """The state or territory of the site, from its address or location text (state names and abbreviations), else from the coordinates for Queensland."""
    import re
    loc = p.get("location") or ""
    for ab, name in _STATES.items():
        if re.search(rf"\b{ab}\b", loc) or re.search(name, loc, re.I):
            return name
    lat, lon = p.get("lat"), p.get("lon")
    if lat is not None and lon is not None and -29.2 <= float(lat) <= -10.5 and 138.0 <= float(lon) <= 153.6 and not (float(lat) < -28.0 and float(lon) < 141.0):
        return "Queensland"
    return None


def claim_act_info(p):
    """Does the payment claim carry the Queensland BIF Act statement, and why. It follows the site address together with the law that governs the contract:
    work carried out in Queensland (s 61(4) BIF Act) under a contract governed by Queensland law, or by none stated. A Queensland site under another state's
    law is flagged for checking, and the project can force the statement on or off."""
    mode, site, law = p.get("claim_act") or "", site_state(p), p.get("contract_law") or ""
    if mode == "qld":
        return dict(show=True, site=site, law=law, reason="The project is set to always show the statement.")
    if mode == "none":
        return dict(show=False, site=site, law=law, reason="The project is set to never show the statement.")
    if site != "Queensland":
        return dict(show=False, site=site, law=law, reason=f"The site is {'in ' + site if site else 'not identified as Queensland (add the state to the site address)'}: the Queensland Act applies to work carried out in Queensland.")
    if law in ("", "Queensland"):
        return dict(show=True, site=site, law=law, reason="Site in Queensland" + (", contract governed by Queensland law." if law else "; no governing law stated, so Queensland is assumed."))
    return dict(show=False, site=site, law=law, reason=f"The site is in Queensland but the contract is governed by {law} law: check with your legal contact whether the BIF Act applies, then set the statement to Always if it does.")


def claim_act(p):
    return "qld" if claim_act_info(p)["show"] else "none"


def _dmy(v):
    """2026-10-23 as 23/10/2026 (dates on documents are DD/MM/YYYY)."""
    t = str(v or "")[:10]
    return f"{t[8:10]}/{t[5:7]}/{t[:4]}" if len(t) == 10 and t[4] == "-" and t[7] == "-" else (v or "")


def _tag(stage):
    st = (stage or "").strip()
    return {"early works": "EW", "early work": "EW"}.get(st.lower(), st if len(st) <= 5 else st[:5])


BIF_STATEMENT = "This is a payment claim made under the Building Industry Fairness (Security of Payment) Act 2017"


def claim_pdf(con, pid, cid, layout=None):
    """The progress claim for a month as a PDF to send to the client: every group and line, this claim, to date, remaining."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    sh = revenue.claim_sheet(con, pid, cid)
    if not sh:
        return None
    d, rows, tot = sh["claim"], sh["rows"], sh["totals"]
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    C = colors.HexColor
    NAVY, ORANGE, SLATE, GREY = "#102361", "#e56210", "#335062", "#e0e6e8"
    page = landscape(A4)
    margin = 12 * mm
    money = lambda x: f"{x:,.2f}"
    per = d["period"][:7]
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    per_label = f"{months[int(per[5:7]) - 1]} {per[:4]}"
    title = f"Progress claim {d['claim_no']}"
    buf = io.BytesIO()

    band = 14 * mm
    _co = company(con)
    co_foot = f"{_co['name']}{'  |  ABN ' + _co['abn'] if _co['abn'] else ''}  |  {_co['address']}"

    def frame(c, doc):
        c.saveState()
        c.setFillColor(C(NAVY))
        c.rect(0, page[1] - band, page[0], band, stroke=0, fill=1)
        try:                                   # the EPEC logo made for navy backgrounds
            lh = 8.5 * mm
            c.drawImage(str(LOGO_REV), margin, page[1] - band + (band - lh) / 2, width=lh * 900 / 281, height=lh, mask="auto")
        except Exception:                      # no logo file: the name instead
            c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 12); c.drawString(margin, page[1] - 9 * mm, "EPEC")
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(page[0] - margin, page[1] - 6.2 * mm, f"{title}  |  Period {per_label}")
        c.setFont("Helvetica", 8)
        c.drawRightString(page[0] - margin, page[1] - 10.4 * mm, f"{p['name']}")
        c.setFillColor(C(SLATE))
        c.setFont("Helvetica", 7)
        c.drawString(margin, 6 * mm, f"{co_foot}  |  Commercial in Confidence  |  AUD excl. GST")
        c.drawRightString(page[0] - margin, 6 * mm, f"Page {doc.page}")
        c.restoreState()
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=band + 6 * mm, bottomMargin=12 * mm, title=f"{p['name']} {title}", author="EPEC")
    st_title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=18, textColor=C(ORANGE), leading=22)
    st_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=9, textColor=C(SLATE), leading=12)
    st_cell = ParagraphStyle("c", fontName="Helvetica", fontSize=7.5, leading=9)
    st_grp = ParagraphStyle("g", fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=C(SLATE))
    # who is claiming, from whom, and what for: EPEC and client project identity, and the claim itself
    cl = db.one(con, "SELECT * FROM client WHERE lower(trim(name))=lower(trim(?))", (p.get("client_name") or "",)) or {}
    esc = lambda v: str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    st_id = ParagraphStyle("id", fontName="Helvetica", fontSize=8, textColor=C(SLATE), leading=10)

    def block_rows(title_, pairs):
        out = [Paragraph(f"<font color='{ORANGE}'><b>{title_}</b></font>", st_id)]
        out += [Paragraph(f"<font color='{SLATE}'>{k}</font> <b>{esc(v)}</b>", st_id) for k, v in pairs if v not in (None, "")]
        return out
    co = company(con)
    layout = layout if layout in ("a", "b") else co["claim_layout"]
    cproj = " ".join(x for x in (p.get("client_project_number"), p.get("client_project_name")) if x)
    if p.get("client_project_code"):
        cproj = f"{cproj} ({p['client_project_code']})".strip()
    client_blk = block_rows("Client", [("Client", p.get("client_name")), ("ABN", cl.get("abn")), ("Address", cl.get("hq")), ("Project", cproj), ("Project manager", p.get("client_pm"))])
    contract_pairs = [("Contract", p.get("contract_ref")), ("Client PO / reference", p.get("client_po")), ("Early works ref", p.get("early_works_ref"))]
    rev = f"{d.get('revision') or 0}" + (f" ({_dmy(d['revision_date'])})" if d.get("revision_date") else "")
    sub_date = d.get("submitted_date") or date.today().isoformat()      # an unsubmitted claim is dated the day it is issued
    deadline = revenue.review_deadline(con, p, sub_date)
    claim_pairs = [("EPEC claim no.", f"{d['claim_no']}, revision {rev}"), ("Client claim no.", d.get("client_claim_no"))]
    contract_blk = block_rows("Contract", contract_pairs)
    claim_blk = block_rows("Claim", claim_pairs)
    both_blk = block_rows("Contract and claim", contract_pairs + claim_pairs)
    epec_blk = block_rows("EPEC", [("Company", co["name"]), ("ABN", co["abn"]), ("Address", co["address"]), ("Project", " ".join(x for x in (p.get("number"), p.get("name")) if x) + (f" ({p['code']})" if p.get("code") else "")),
                                   ("Project manager", p.get("epec_pm")), ("Project director", p.get("project_director"))])
    W = page[0] - 2 * margin

    def stack(top, bottom, w):               # two tiles in one column, a rule between them
        t = Table([[top], [bottom]], colWidths=[w])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (0, 0), 0.5, C(GREY)), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t
    if layout == "b":     # client with the contract tile below it | claim | EPEC
        cols = [.38, .24, .38]
        cells = [stack(client_blk, contract_blk, W * cols[0] - 16), claim_blk, epec_blk]
    else:                 # client | contract and claim together in the middle | EPEC: three columns of about the same height
        cols = [.34, .30, .36]
        cells = [client_blk, both_blk, epec_blk]
    ident = Table([cells], colWidths=[W * x for x in cols])
    ident.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, C(GREY)), ("LINEAFTER", (0, 0), (1, 0), 0.5, C(GREY)),
                               ("BACKGROUND", (0, 0), (-1, -1), C("#f6f8f9")), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    head_left = [Paragraph(title, st_title)]
    if claim_act(p) == "qld":
        head_left.append(Paragraph(f"<b>{BIF_STATEMENT}</b>", ParagraphStyle("bif", fontName="Helvetica", fontSize=9, textColor=C(NAVY), leading=12)))
    # the two dates the client acts on, top right beside the title
    st_dt = ParagraphStyle("dt", fontName="Helvetica", fontSize=8.5, textColor=C(SLATE), leading=12, alignment=2)
    st_dv = ParagraphStyle("dv", fontName="Helvetica-Bold", fontSize=11, textColor=C(NAVY), leading=14, alignment=2)
    dates = [[Paragraph("Submission date", st_dt), Paragraph(esc(_dmy(sub_date)), st_dv)]]
    if deadline:
        dates.append([Paragraph("Review deadline", st_dt), Paragraph(esc(_dmy(deadline)), st_dv)])
    dbox = Table(dates, colWidths=[28 * mm, 26 * mm])
    dbox.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, C(NAVY)), ("BACKGROUND", (0, 0), (-1, -1), C("#f6f8f9")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("LINEBELOW", (0, 0), (-1, -2), 0.25, C(GREY)), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    top_row = Table([[head_left, dbox]], colWidths=[W - 58 * mm, 58 * mm])
    top_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    story = [top_row]
    story += [Spacer(1, 4), ident, Spacer(1, 8)]
    rv = revenue.summary(con, pid)
    revised = rv.get("official") or tot["value"]
    summ = [["Original contract value", "Variations and optional prices", "Revised contract value", "Claimed to date (excl. GST)", "This claim (excl. GST)"],
            [money(rv.get("original") or 0), money(revised - (rv.get("original") or 0)), money(revised), money(tot["to_date"]), money(tot["this"])]]
    t = Table(summ, colWidths=[(page[0] - 2 * margin) / 5] * 5)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(NAVY)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                           ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 10), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("BACKGROUND", (0, 1), (-1, 1), C(GREY)),
                           ("TEXTCOLOR", (0, 1), (-1, 1), C(SLATE)), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [t, Spacer(1, 8)]
    pc = lambda a_, b_: f"{(a_ / b_ if b_ else 0):.0%}"
    data = [["Tag", "Item", "Description", "Price", "% this\nclaim", "This claim", "% previous", "Previously\nclaimed", "% to date", "Total claimed\nto date"]]
    style = [("BACKGROUND", (0, 0), (-1, 0), C(NAVY)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.2),
             ("ALIGN", (3, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("FONT", (0, 1), (-1, -1), "Helvetica", 7.5),
             ("LINEBELOW", (0, 1), (-1, -1), 0.25, C(GREY)), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    for l in rows:
        r = len(data)
        st = st_cell if l["leaf"] else st_grp
        data.append([_tag(l.get("stage")), l["ref"], Paragraph(("&nbsp;" * 3 * l["depth"]) + l["description"].replace("&", "&amp;"), st), money(l["value"]), pc(l["this"], l["value"]), money(l["this"]),
                     pc(l["prior"], l["value"]), money(l["prior"]), pc(l["to_date"], l["value"]), money(l["to_date"])])
        if not l["leaf"]:
            style += [("BACKGROUND", (0, r), (-1, r), C(GREY)), ("FONT", (0, r), (-1, r), "Helvetica-Bold", 7.5), ("TEXTCOLOR", (0, r), (-1, r), C(SLATE))]
    r = len(data)
    data.append(["", "", "TOTAL CLAIM", money(tot["value"]), pc(tot["this"], tot["value"]), money(tot["this"]), pc(tot["prior"], tot["value"]), money(tot["prior"]), pc(tot["to_date"], tot["value"]), money(tot["to_date"])])
    style += [("FONT", (0, r), (-1, r), "Helvetica-Bold", 8), ("LINEABOVE", (0, r), (-1, r), 0.8, C(NAVY))]
    w = page[0] - 2 * margin
    tbl = LongTable(data, colWidths=[w * .04, w * .09, w * .24, w * .10, w * .06, w * .10, w * .07, w * .10, w * .07, w * .13], repeatRows=1)
    tbl.setStyle(TableStyle(style))
    story.append(tbl)
    story.append(Spacer(1, 6))
    thisc = Table([["This claim (excl. GST)", money(tot["this"])]], colWidths=[w * .30, w * .17], hAlign="RIGHT")
    thisc.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(NAVY)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(thisc)
    story.append(Spacer(1, 8))
    appr = Table([["Approved by:", "Signature:", "Date:"]], colWidths=[w * .38, w * .38, w * .24], rowHeights=[13 * mm])
    appr.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, C(SLATE)), ("INNERGRID", (0, 0), (-1, -1), 0.5, C(GREY)), ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 8.5), ("TEXTCOLOR", (0, 0), (-1, -1), C(SLATE)), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(KeepTogether(appr))
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()


def sub_certificate_pdf(con, pid, sid, cid):
    """The payment certificate EPEC issues to a subcontractor when it approves their claim (portrait A4).
    Page 1: parties, the certified amount and the notes (why approved differs from claimed). Page 2: the detail of the approved amounts.
    There is no invoice reference: the subcontractor invoices after the certificate is issued."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from . import subcontracts
    d = subcontracts.claim_detail(con, sid, cid)
    if not d or not d.get("cert_no"):
        return None
    sub = db.one(con, "SELECT * FROM subcontract WHERE id=?", (sid,))
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    sup = d.get("supplier") or {}
    co = company(con)
    C = colors.HexColor
    NAVY, ORANGE, SLATE, GREY = "#102361", "#e56210", "#335062", "#e0e6e8"
    page = A4
    margin = 14 * mm
    band = 16 * mm
    money = lambda x: f"{x:,.2f}"
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    per_label = f"{months[int(d['month'][5:7]) - 1]} {d['month'][:4]}"
    title = f"Payment certificate {d['cert_no']}"
    buf = io.BytesIO()
    foot = f"{co['name']}{'  |  ABN ' + co['abn'] if co['abn'] else ''}  |  {co['address']}"

    def frame(c, doc):
        c.saveState()
        c.setFillColor(C(NAVY)); c.rect(0, page[1] - band, page[0], band, stroke=0, fill=1)
        try:
            lh = 9 * mm
            c.drawImage(str(LOGO_REV), margin, page[1] - band + (band - lh) / 2, width=lh * 900 / 281, height=lh, mask="auto")
        except Exception:
            c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 12); c.drawString(margin, page[1] - 10 * mm, "EPEC")
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 11); c.drawRightString(page[0] - margin, page[1] - 7 * mm, "Payment certificate")
        c.setFont("Helvetica", 8); c.drawRightString(page[0] - margin, page[1] - 11.5 * mm, f"{d['cert_no']}  |  {p['name']}")
        c.setFillColor(C(SLATE)); c.setFont("Helvetica", 7)
        c.drawString(margin, 8 * mm, f"{foot}  |  Commercial in Confidence  |  AUD excl. GST"); c.drawRightString(page[0] - margin, 8 * mm, f"Page {doc.page}")
        c.restoreState()
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=band + 8 * mm, bottomMargin=16 * mm, title=f"{p['name']} {title}", author="EPEC")
    st_title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=17, textColor=C(ORANGE), leading=21)
    st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=10.5, textColor=C(ORANGE), leading=14)
    st_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=8.5, textColor=C(SLATE), leading=11.5)
    st_note = ParagraphStyle("n", fontName="Helvetica", fontSize=8.5, textColor=colors.black, leading=11.5, leftIndent=8, bulletIndent=0)
    st_cell = ParagraphStyle("c", fontName="Helvetica", fontSize=8, leading=10)
    esc = lambda v: str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    NR = "<font color='#b03a2e'>not recorded</font>"

    def block(title_, pairs):
        out = [Paragraph(f"<font color='{ORANGE}'><b>{title_}</b></font>", st_sub)]
        for k, v, req in pairs:
            if v not in (None, ""):
                out.append(Paragraph(f"<font color='{SLATE}'>{k}</font> <b>{esc(v)}</b>", st_sub))
            elif req:
                out.append(Paragraph(f"<font color='{SLATE}'>{k}</font> {NR}", st_sub))
        return out
    w = page[0] - 2 * margin
    left = block("To: Subcontractor", [("Company", sup.get("name") or sub.get("supplier_name") or sub["name"], True), ("ABN", sup.get("abn"), True), ("Address", sup.get("address"), True), ("Contact", sup.get("contacts"), False)])
    mid = block("Subcontract", [("Subcontract", sub["name"], True), ("Order / contract no.", sub.get("po_no"), False), ("Contract value", money(sub.get("contract_value") or 0), True),
                                ("Retention held", f"{(sub.get('retention_pct') or 0):.1%}" if sub.get("retention_pct") else None, False)])
    right = block("From: EPEC", [("Company", co["name"], True), ("ABN", co["abn"], False), ("Address", co["address"], True), ("Project", " ".join(x for x in (p.get("number"), p.get("name")) if x), True),
                                 ("Project manager", p.get("epec_pm"), False)])
    cert = block("Certificate", [("Certificate number", d["cert_no"], True), ("Issued", _dmy(d.get("cert_date")), True), ("Claim", d["claim_no"], True), ("Claim period", per_label, True),
                                 ("Claim received", _dmy(d.get("received_date")), False), ("Approved", _dmy(d.get("approved_date")), False)])
    ident = Table([[left, right], [mid, cert]], colWidths=[w / 2, w / 2])
    ident.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, C(GREY)), ("LINEAFTER", (0, 0), (0, -1), 0.5, C(GREY)), ("LINEBELOW", (0, 0), (-1, 0), 0.5, C(GREY)),
                               ("BACKGROUND", (0, 0), (-1, -1), C("#f6f8f9")), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story = [Paragraph(title, st_title), Spacer(1, 5), ident, Spacer(1, 12)]

    # the lines: what was claimed and what was approved
    rows, tot = [], dict(value=0.0, prior=0.0, claimed=0.0, cert=0.0)
    for l in d["lines"]:
        cert_amt = l["approved"] if l["approved"] is not None else l["claimed"]
        if not (l["claimed"] or l["prior"] or cert_amt):
            continue
        rows.append(dict(name=l["name"], value=l["value"], prior=l["prior"], claimed=l["claimed"], cert=cert_amt, note=(l.get("note") or "").strip(), approved=l["approved"] is not None))
        tot["value"] += l["value"]; tot["prior"] += l["prior"]; tot["claimed"] += l["claimed"]; tot["cert"] += cert_amt
    if not rows:
        rows.append(dict(name="Claim recorded as a lump amount", value=0.0, prior=0.0, claimed=d["claimed"], cert=d["effective"], note="", approved=True))
        tot["claimed"], tot["cert"] = d["claimed"], d["effective"]
    diff = round(tot["cert"] - tot["claimed"], 2)

    # page 1: the amount payable
    held, rel = d["retention"], d.get("retention_release") or 0
    pay = [["Amount claimed this period", money(tot["claimed"])], ["Amount approved (certified) this period", money(d["effective"])]]
    if abs(diff) > 0.004:
        pay.append(["Difference between claimed and approved", f"{'-' if diff < 0 else ''}{money(abs(diff))}"])
    pay.append([f"Less retention held{(' at ' + format(sub['retention_pct'], '.1%')) if sub.get('retention_pct') else ''}", f"-{money(held)}"])
    if rel:
        pay.append(["Plus retention released", money(rel)])
    pay.append(["Net amount payable (AUD excl. GST)", money(d["net"])])
    pt = Table(pay, colWidths=[w * .72, w * .28])
    pt.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 10.5), ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                            ("BACKGROUND", (0, -1), (-1, -1), C(NAVY)), ("LINEBELOW", (0, 0), (-1, -2), 0.25, C(GREY)), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [Paragraph("Amount payable", st_h), Spacer(1, 3), pt, Spacer(1, 12)]

    # notes: why approved differs from claimed
    story += [Paragraph("Notes", st_h), Spacer(1, 3)]
    notes = []
    if (d.get("cert_note") or "").strip():
        notes += [Paragraph(esc(x), st_sub) for x in d["cert_note"].strip().split("\n") if x.strip()]
    for r in rows:
        if r["approved"] and abs(r["cert"] - r["claimed"]) > 0.004:
            why = esc(r["note"]) if r["note"] else "no reason recorded"
            notes.append(Paragraph(f"<b>{esc(r['name'])}</b>: claimed {money(r['claimed'])}, approved {money(r['cert'])} (difference {'-' if r['cert'] < r['claimed'] else ''}{money(abs(r['cert'] - r['claimed']))}). Reason: {why}.", st_note, bulletText="\u2022"))
    if not notes:
        notes.append(Paragraph("The claim has been approved as claimed." if abs(diff) <= 0.004 else "No notes were recorded.", st_sub))
    story += notes + [Spacer(1, 12), Paragraph(f"Please quote certificate number <b>{esc(d['cert_no'])}</b> on your tax invoice. The line-by-line detail of the approved amounts follows on page 2.", st_sub), Spacer(1, 22)]
    sign = Table([[Paragraph(f"Certified by <b>{esc(d.get('cert_by') or '')}</b>", st_sub), Paragraph(f"Date <b>{esc(_dmy(d.get('cert_date')))}</b>", st_sub)]], colWidths=[w * .6, w * .4])
    sign.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.5, C(SLATE)), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    story.append(sign)

    # page 2: the detail of the approved amounts
    story += [PageBreak(), Paragraph(f"Detail of approved amounts: {esc(sub['name'])}, {esc(d['claim_no'])} ({per_label})", st_h), Spacer(1, 5)]
    data = [["Schedule line", "Contract\nvalue", "Previously\ncertified", "Claimed", "Approved", "Difference", "Reason if different"]]
    for r in rows:
        dif = r["cert"] - r["claimed"] if r["approved"] else 0.0
        data.append([Paragraph(esc(r["name"]), st_cell), money(r["value"]), money(r["prior"]), money(r["claimed"]), money(r["cert"]),
                     (f"{'-' if dif < 0 else ''}{money(abs(dif))}" if abs(dif) > 0.004 else ""), Paragraph(esc(r["note"]), st_cell) if r["note"] else ""])
    data.append(["Total", money(tot["value"]), money(tot["prior"]), money(tot["claimed"]), money(tot["cert"]), (f"{'-' if diff < 0 else ''}{money(abs(diff))}" if abs(diff) > 0.004 else ""), ""])
    r_ = len(data) - 1
    t = Table(data, colWidths=[w * .24, w * .11, w * .12, w * .11, w * .11, w * .09, w * .22], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(NAVY)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5), ("ALIGN", (1, 0), (5, -1), "RIGHT"),
                           ("FONT", (0, 1), (-1, -1), "Helvetica", 7.8), ("FONT", (0, r_), (-1, r_), "Helvetica-Bold", 8.2), ("LINEBELOW", (0, 1), (-1, -2), 0.25, C(GREY)), ("LINEABOVE", (0, r_), (-1, r_), 0.8, C(NAVY)),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(t)
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()


LEVEL_LABEL = {"items": "Price items only", "scope": "Price items and their scope", "contributions": "Price items and each line's contribution",
               "full": "Full detail (quantities and rates)"}


def variation_proposal_html(con, pid, vid, breakdown=True, level=None):
    """The client's variation proposal. What is shown under each price item follows the detail level (the variation's,
    or a price item's own): items = price only; scope = the lines that make it up, without prices; contributions =
    each line's price, without quantities and rates; full = quantities, units, rates and prices. Spread items are not
    shown (their price sits in the items that carry it); options and provisional sums are listed apart."""
    v = variations.get(con, pid, vid)
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    e = lambda x: html.escape(str(x if x is not None else ""))
    money = lambda x: f"${x:,.2f}"
    b = v["build"]
    default = level or (v.get("detail_level") or "scope") if breakdown else "items"
    if default not in variations.DETAIL:
        default = "scope"
    shown = [i for i in b["items"] if not i["spread_out"]]
    main = [i for i in shown if not i.get("optional") or i.get("selected") == "Yes"]
    opts = [i for i in shown if i.get("optional") and i.get("selected") != "Yes"]

    def item_rows(it, is_opt=False):
        lv = it.get("detail") if (it.get("detail") in variations.DETAIL and level is None) else default
        tag = " [OPTIONAL]" if is_opt else (" [PROVISIONAL]" if it.get("pricing_type") == "PS" else "")
        out = f"<tr class='item'><td></td><td>{e(it.get('name'))}{tag}</td><td class='n'></td><td></td><td class='n'></td><td class='n'>{money(it['price'])}</td></tr>"
        for c in it["lines"]:
            if c.get("description") in (None, "", it.get("name")) and lv != "full":
                continue
            if lv == "scope":
                out += f"<tr class='ln'><td></td><td class='ind'>{e(c['description'])}</td><td></td><td></td><td></td><td></td></tr>"
            elif lv == "contributions":
                out += f"<tr class='ln'><td></td><td class='ind'>{e(c['description'])}</td><td></td><td></td><td></td><td class='n'>{money(c['shown_price'])}</td></tr>"
            elif lv == "full":
                q = c["qty"] or 0
                rate = (c["shown_price"] / q) if q else c["shown_price"]
                out += (f"<tr class='ln'><td></td><td class='ind'>{e(c['description'])}</td><td class='n'>{q:,.2f}</td><td>{e(c.get('unit'))}</td>"
                        f"<td class='n'>{money(rate)}</td><td class='n'>{money(c['shown_price'])}</td></tr>")
        return out
    rows = ""
    for sec in dict.fromkeys((i.get("section") or "Works") for i in main):
        its = [i for i in main if (i.get("section") or "Works") == sec]
        rows += f"<tr class='sec'><td colspan='5'>{e(sec)}</td><td class='n'>{money(sum(i['price'] for i in its))}</td></tr>"
        rows += "".join(item_rows(i) for i in its)
    orows = "".join(item_rows(i, True) for i in opts)
    t = b["total"]
    total = t["base"] + t["provisional"]
    totals = f"<tr class='total'><td colspan='5'>Base price</td><td class='n'>{money(t['base'])}</td></tr>"
    if abs(t["provisional"]) > 0.005:
        totals += f"<tr class='total'><td colspan='5'>Provisional sums</td><td class='n'>{money(t['provisional'])}</td></tr>"
    totals += f"<tr class='total'><td colspan='5'>Total price ({e(PRICING_MODELS.get(v['pricing_model'], v['pricing_model']))})</td><td class='n'>{money(total)}</td></tr>"
    if not b["items"]:  # nothing built up: the value as entered
        rows, totals = "", f"<tr class='total'><td colspan='5'>Total price</td><td class='n'>{money(v['value'] or 0)}</td></tr>"
    rev = v["current_rev"] or {}
    return f"""<!doctype html><html lang="en-AU"><head><meta charset="utf-8"><title>{e(v['ref'])} variation proposal</title>
<style>
@font-face{{font-family:Mulish;src:url('/static/vendor/fonts/mulish-latin-400-normal.woff2');font-weight:400}}
@font-face{{font-family:Mulish;src:url('/static/vendor/fonts/mulish-latin-700-normal.woff2');font-weight:700}}
body{{font-family:Mulish,Calibri,sans-serif;color:#000;margin:0;padding:32px;max-width:900px}}
h1{{color:#e56210;margin:0 0 4px;font-size:24px}} h2{{color:#102361;font-size:15px;margin:22px 0 6px}}
.band{{background:#102361;color:#fff;padding:10px 14px;font-weight:700}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th{{background:#102361;color:#fff;text-align:left;padding:6px 8px}}
td{{padding:5px 8px;border-bottom:1px solid #e0e6e8}} tr:nth-child(even) td{{background:#e0e6e8}}
tr.sec td{{background:#fff;color:#102361;font-weight:700;border-top:2px solid #102361}} td.n,th.n{{text-align:right}}
tr.item td{{font-weight:700;background:#f4f6fb}} tr.ln td{{background:#fff;font-size:12px;color:#333}} td.ind{{padding-left:22px}}
.kv td{{border:0;background:#fff!important;padding:2px 8px}} .total td{{font-weight:700;background:#fff!important;border-top:2px solid #102361}}
.foot{{margin-top:30px;font-size:11px;color:#335062;border-top:3px solid #ffb500;padding-top:8px}}
@media print{{body{{padding:0}}}}
</style></head><body>
<div class="band">VARIATION PROPOSAL</div>
<h1 style="margin-top:14px">{e(v['ref'])}{(' Rev ' + str(rev.get('rev'))) if rev else ''}: {e(v['title'])}</h1>
<table class="kv"><tr><td>Client</td><td>{e(p['client_name'])}</td><td>Contractor</td><td>EPEC</td></tr>
<tr><td>Project</td><td>{e(p['client_project_name'] or p['name'])}</td><td>Project</td><td>{e(p['name'])}</td></tr>
<tr><td>Submission date</td><td>{e(v['submission_date'])}</td><td>Project number</td><td>{e(p['number'])}</td></tr>
<tr><td>Contract reference</td><td>{e(p['contract_ref'])}</td><td>Project manager</td><td>{e(p['epec_pm'])}</td></tr>
<tr><td>Client PO number</td><td>{e(p['client_po'])}</td><td>Validity</td><td>{e(v['validity'])}</td></tr></table>
<h2>Scope</h2><p>{e(v['description'] or v['title'])}</p>
{('<h2>Exclusions</h2><p>' + e(v.get('exclusions')) + '</p>') if v.get('exclusions') else ''}
<h2>Price (AUD, excl. GST)</h2>
<table><tr><th style="width:3%"></th><th>Item</th><th class="n">Qty</th><th>Unit</th><th class="n">Rate</th><th class="n">Price</th></tr>{rows}
{totals}</table>
{('<h2>Options (not included in the total)</h2><table><tr><th style="width:3%"></th><th>Item</th><th class="n">Qty</th><th>Unit</th><th class="n">Rate</th><th class="n">Price</th></tr>' + orows + '</table>') if orows else ''}
<div class="foot">Commercial in Confidence. EPEC Group. Prices exclude GST.</div></body></html>"""


def risk_closeout_xlsx(con, pid):
    """Estimator feedback: per CBS category the risk that was needed, and how it splits across the risk events that occurred."""
    d = risk_mod.closeout(con, pid)
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    out = io.BytesIO()
    wb = xlsxwriter.Workbook(out, {"in_memory": True})
    f = _formats(wb)
    ws = wb.add_worksheet("By CBS")
    ws.set_column(0, 0, 10); ws.set_column(1, 1, 36); ws.set_column(2, 12, 15)
    ws.write(0, 0, f"{p['name']}: risk close-out for the estimator", f["title"])
    ws.write(1, 0, "Risk that occurred = tagged risk cost already landed in Pronto or accrued. Funded in order: PM contingency, company release from the bucket, company infusion.", f["sub"])
    heads = ["CBS", "Name", "Estimated budget", "Estimated risk", "Estimated risk %", "Risk that occurred", "Occurred % of budget", "Funded from contingency", "Released from bucket", "Infused", "Suggested risk % next job"]
    for c, h in enumerate(heads):
        ws.write(3, c, h, f["head"])
    ws.set_row(3, 30)
    for i, r in enumerate(d["rows"], start=4):
        band = i % 2 == 1
        t, n = (f["band"], f["band_n"]) if band else (f["txt"], f["num"])
        ws.write(i, 0, r["category"], t); ws.write(i, 1, r["name"], t)
        for c, k in ((2, "orig_budget"), (3, "orig_risk"), (5, "risk_needed"), (7, "from_contingency"), (8, "released"), (9, "infused")):
            ws.write_number(i, c, r[k] or 0, n)
        ws.write_number(i, 4, r["risk_pct_estimated"] or 0, f["pct"]); ws.write_number(i, 6, r["risk_needed_pct_of_budget"] or 0, f["pct"]); ws.write_number(i, 10, r["suggested_risk_pct"] or 0, f["pct"])
    t = d["totals"]
    last = 4 + len(d["rows"])
    ws.write(last, 1, "Whole project", f["lab"])
    for c, k in ((2, "orig_budget"), (3, "orig_risk"), (5, "risk_needed"), (7, "from_contingency"), (8, "released"), (9, "infused")):
        ws.write_number(last, c, t[k] or 0, f["money_b"])
    ws.write_number(last, 4, t["estimated_pct"] or 0, f["pct"]); ws.write_number(last, 6, t["actual_pct"] or 0, f["pct"]); ws.write_number(last, 10, t["suggested_overall_pct"] or 0, f["pct"])
    be = risk_mod.closeout_by_event(con, pid, None, d)
    ev = wb.add_worksheet("By risk event")
    ev.set_column(0, 0, 10); ev.set_column(1, 1, 34); ev.set_column(2, 2, 10); ev.set_column(3, 3, 34); ev.set_column(4, 11, 16)
    ev.write(0, 0, "Each risk event broken into the CBS items it hit", f["title"])
    for c, h in enumerate(["Risk", "Event", "CBS", "Name", "Tagged cost", "% of event cost", "Risk funded", "% of CBS estimated budget", "Delay estimated (days)", "Delay occurred (days)", "Revenue impact estimated", "Revenue impact occurred"]):
        ev.write(2, c, h, f["head"])
    r0 = 3
    for x in be["events"]:
        ev.write(r0, 0, x["ref"], f["par"]); ev.write(r0, 1, x["title"], f["par"]); ev.write(r0, 3, f"Planned reserve {x['planned']:,.0f}", f["sub"])
        ev.write_number(r0, 4, x["tagged"], f["par_n"]); ev.write_number(r0, 6, x["risk_funded"], f["par_n"])
        ev.write_number(r0, 8, x["delay_days"], f["par_n"]); ev.write_number(r0, 9, x["delay_actual"], f["par_n"]); ev.write_number(r0, 10, x["revenue_impact"], f["par_n"]); ev.write_number(r0, 11, x["revenue_actual"], f["par_n"]); r0 += 1
        for c in x["categories"]:
            ev.write(r0, 2, c["category"], f["txt"]); ev.write(r0, 3, c["name"], f["txt"]); ev.write_number(r0, 4, c["tagged"], f["num"])
            ev.write_number(r0, 5, c["pct_of_event"] or 0, f["pct"]); ev.write_number(r0, 6, c["risk_funded"], f["num"]); ev.write_number(r0, 7, c["pct_of_budget"] or 0, f["pct"])
            r0 += 1
    mx = wb.add_worksheet("Matrix")
    mx.set_column(0, 0, 10); mx.set_column(1, 1, 34); mx.set_column(2, 40, 14)
    mx.write(0, 0, "Tagged risk cost: CBS by risk event", f["title"])
    heads = ["CBS", "Name"] + be["refs"] + ["Total"]
    for c, h in enumerate(heads):
        mx.write(2, c, h, f["head"])
    names = {r["category"]: r["name"] for r in d["rows"]}
    for i, (cat, vals) in enumerate(be["matrix"].items(), start=3):
        mx.write(i, 0, cat, f["txt"]); mx.write(i, 1, names.get(cat, ""), f["txt"])
        for j, ref in enumerate(be["refs"], start=2):
            mx.write_number(i, j, vals.get(ref, 0.0), f["num"])
        mx.write_number(i, 2 + len(be["refs"]), sum(vals.values()), f["par_n"])
    wb.close()
    return out.getvalue()
