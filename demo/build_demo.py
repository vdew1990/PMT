"""Builds a fictional demonstration project so the tool can be explored without real data.

Everything here is invented: the project, people, suppliers, rates and amounts. Running it writes two Excel files
(a project load template and a Pronto-style export) and, with --seed, loads them into the database through the same
code paths a real project uses.

    python -m demo.build_demo            # writes the two Excel files into demo/
    python -m demo.build_demo --seed     # also creates a project called "Demo: Greenfield Substation"
"""
import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import openpyxl
import xlsxwriter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import accruals, db, engine, pronto, reports, services, templates_io  # noqa: E402

DEMO = Path(__file__).resolve().parent
rnd = random.Random(20261015)

START, END, STATUS = date(2025, 2, 3), date(2026, 11, 30), date(2026, 9, 30)
PRONTO_PROJECT = "00000999"
SOV_SCALE = 1.33  # scales the schedule of values so the demo carries a healthy planned margin

ROLES = [  # code prefix, name, function, work rate code, cost rate, sell rate, category, days/month on the job
    ("PM", "Alex Marsden", "Senior Project Manager", "PJ09", 240, 283, "PL01"),
    ("PC", "Blair Okafor", "Project Coordinator", "PJ03", 95, 150, "PL01"),
    ("CM", "Casey Lindqvist", "Contract Manager", "PJ07", 200, 270, "PL01"),
    ("HS", "Dana Whitfield", "HSEQ Adviser", "PJ05", 130, 185, "PL01"),
    ("DM", "Eden Castellano", "Design Manager", "PJ08", 220, 280, "PL02"),
    ("SD", "Frankie Nowak", "Senior Designer", "PJ04", 110, 240, "PL02"),
    ("D1", "Gale Thornton", "Substation Design Engineer", "PJ06", 135, 210, "PL02"),
    ("D2", "Harper Quinn", "Engineer Designer", "PJ02", 80, 190, "PL02"),
    ("EN", "Indy Rasmussen", "Principal Engineer", "PJ09", 190, 300, "PL03"),
    ("E2", "Jules Abernathy", "Project Engineer", "PJ03", 100, 200, "PL03"),
    ("CO", "Kai Brennan", "Construction Manager", "PJ07", 175, 240, "PL04"),
    ("SS", "Lane Moreau", "Site Supervisor Electrical", "PJ05", 150, 215, "PL04"),
    ("SC", "Morgan Delacroix", "Site Supervisor Civil", "PJ05", 150, 215, "PL04"),
    ("SA", "Nico Valdez", "Site Admin", "PJ02", 80, 140, "PL04"),
    ("TC", "Oakley Baird", "Commissioning Engineer", "COME", 140, 210, "PL05"),
    ("TM", "Parker Linden", "Commissioning Manager", "COMM", 175, 270, "PL05"),
    ("SE", "Quinn Ashworth", "SCADA Engineer", "PJ05", 130, 220, "PL07"),
]

SUPPLIERS = [  # code, name, trade, category
    ("S30NBC01", "Northbridge Civil Pty Ltd", "Civil Contractor", "PS04"),
    ("S30LEC01", "Larkspur Electrical Pty Ltd", "Electrical Contractor", "PS04"),
    ("S30ARC01", "Arden Consulting Engineers", "Design Consultancy", "PS02"),
    ("S30TST01", "Tallowood Testing Services", "Testing", "PS05"),
    ("S30SCD01", "Meridian SCADA Systems", "SCADA", "PS07"),
    ("S30TRX01", "Corvus Transformers Pty Ltd", "Transformers", "PM02"),
    ("S30SWG01", "Halden Switchgear", "Primary Equipment", "PM03"),
    ("S30PRT01", "Quillon Protection", "Relays", "PM04"),
    ("S30CAB01", "Brightwater Cables", "Cables", "PM05"),
    ("S30CIV01", "Redgum Concrete and Steel", "Civil Materials", "PM07"),
    ("S30HIR01", "Westfield Plant Hire", "Equipment hire", "PE02"),
    ("S30ACC01", "Lakeside Motel", "Accommodation", "PE01"),
    ("S30FRT01", "Overland Freight", "Freight", "PE05"),
]


def workdays(a, b):
    d = a
    while d <= b:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def months(a, b):
    out, d = [], date(a.year, a.month, 1)
    while d <= b:
        out.append(d)
        d = date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)
    return out


def eom(d):
    nxt = date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)
    return nxt - timedelta(days=1)


# ---------------------------------------------------------------------------
# Allowances (the proposal): pots by role/trade plus named lines
# ---------------------------------------------------------------------------
POTS = {
    "PL01": [("Project Manager", 330000), ("Project Coordinator", 190000), ("Contract Manager", 120000), ("HSEQ", 150000)],
    "PL02": [("Design Manager", 120000), ("Senior Designer", 210000), ("Substation Design Engineer", 180000), ("Drafting", 90000)],
    "PL03": [("Principal Engineer", 160000), ("Project Engineer", 140000)],
    "PL04": [("Construction Manager", 300000), ("Site Supervision", 360000), ("Site Admin", 90000)],
    "PL05": [("Commissioning", 330000)],
    "PL07": [("SCADA Engineering", 110000)],
    "PS02": [("Detailed design", 420000)],
    "PS04": [("Civil works", 1650000), ("Electrical installation", 1250000)],
    "PS05": [("Independent testing", 180000)],
    "PS07": [("SCADA integration", 360000)],
    "PM02": [("Power transformers", 1450000)],
    "PM03": [("33kV and 132kV switchgear", 1380000)],
    "PM04": [("Protection and control", 520000)],
    "PM05": [("Power and control cables", 430000)],
    "PM06": [("Miscellaneous materials", 120000)],
    "PM07": [("Concrete, steel and civil materials", 520000)],
    "PE01": [("Travel and accommodation", 230000)],
    "PE02": [("Plant hire", 260000)],
    "PE03": [("Site indirects", 180000)],
    "PE05": [("Freight", 160000)],
    "PE07": [("Insurance", 70000)],
}


def write_template_file(path):
    """A project load template, filled with the demo project's allowances."""
    out = templates_io.build_template(None, None)
    wb = openpyxl.load_workbook(__import__("io").BytesIO(out))
    pj = wb["Project"]
    vals = {"Project name": "Demo: Greenfield Substation", "EPEC project code": "DEMO", "EPEC project number": "0999",
            "Client": "Example Renewables Pty Ltd", "Client project name": "Greenfield Solar Farm", "Client project code": "GSF",
            "Client PO number": "PO-000123", "Client project manager": "Sam Client", "EPEC project manager": "Alex Marsden",
            "Contract reference": "EXAMPLE-EPC-2025-001", "Early works reference": "EXAMPLE-EW-2025-001",
            "Status date (YYYY-MM-DD)": STATUS.isoformat(), "Project start": START.isoformat(), "Project end": END.isoformat(),
            "Grid start (first month shown)": "2025-01-01", "Grid end (last month shown)": "2027-01-31",
            "Default risk % of budget (e.g. 0.07)": 0.07}
    for row in pj.iter_rows(min_row=2):
        if row[0].value in vals:
            row[1].value = vals[row[0].value]
    cb = wb["CBS & Allowance"]
    r = 2
    for cat, pots in POTS.items():
        for name, amt in pots:
            for c, v in enumerate([cat, "Group", None, name, None, None, None, amt], start=1):
                if v is not None:
                    cb.cell(r, c, v)
            r += 1
    for code, name, func, wrc, cost, sell, cat in ROLES:
        # a named line for each person; allowance drawn from the matching pot later by transfer
        for c, v in enumerate([cat, "Line", None, name, code + "01", name, func, 0], start=1):
            if v is not None:
                cb.cell(r, c, v)
        r += 1
    for scode, name, trade, cat in SUPPLIERS:
        if cat in ("PS04", "PS02", "PS05", "PS07", "PM02", "PM03", "PM04", "PM05", "PM07", "PE02", "PE01", "PE05"):
            for c, v in enumerate([cat, "Line", None, name, scode, name, trade, 0], start=1):
                if v is not None:
                    cb.cell(r, c, v)
            r += 1
    sv = wb["Payment Milestones"]
    sov = [
        ("1.01", "Preliminaries", "EPC", "base", 1580000, "Mobilisation", "2025-02-01", "2026-11-30", "even", "Monthly in arrears"),
        ("1.02", "Design", "EPC", "base", 1080000, "Design", "2025-02-01", "2025-11-30", "even", "Design milestones"),
        ("1.03", "Primary plant supply", "EPC", "base", 3350000, "Procurement", "2025-05-01", "2026-03-31", "even", "On delivery"),
        ("1.04", "Civil and structures", "EPC", "base", 2050000, "Construction", "2025-07-01", "2026-04-30", "even", "% complete"),
        ("1.05", "Electrical installation", "EPC", "base", 1850000, "Construction", "2025-10-01", "2026-08-31", "even", "% complete"),
        ("1.06", "SCADA and communications", "EPC", "base", 640000, "SCADA", "2026-02-01", "2026-09-30", "even", "% complete"),
        ("1.07", "Testing and commissioning", "EPC", "base", 520000, "Commissioning", "2026-06-01", "2026-11-30", "even", "% complete"),
        ("1.08", "Early works", "Early Works", "base", 380000, "Design", "2025-02-01", "2025-04-30", "even", "Monthly"),
        ("1.09", "Optional: spares package", "EPC", "optional", 140000, "Procurement", "2026-09-01", "2026-09-30", "lump", "On delivery"),
    ]
    for i, row in enumerate(sov, start=2):
        for c, v in enumerate(row[:4], start=1):
            sv.cell(i, c, v)
        sv.cell(i, 5, round(row[4] * SOV_SCALE, -3))
        sv.cell(i, 6, row[5]); sv.cell(i, 7, row[6]); sv.cell(i, 8, row[7]); sv.cell(i, 9, row[8]); sv.cell(i, 10, row[9])
        if row[3] == "optional":
            sv.cell(i, 11, "confirmed")
    rs = wb["Rate card"]
    cards = [("PROJECTS", "Project Coordinator", "PJ03", 95, 150), ("PROJECTS", "Project Engineer", "PJ04", 110, 200),
             ("PROJECTS", "Senior Project Manager", "PJ09", 240, 283), ("DESIGN", "Senior Designer", "PJ04", 110, 240),
             ("COMMISSIONING", "Commissioning Engineer", "COME", 140, 210), ("SITE", "Site Supervisor", "PJ05", 150, 215)]
    for i, row in enumerate(cards, start=2):
        for c, v in enumerate(row, start=1):
            rs.cell(i, c, v)
        rs.cell(i, 6, "26/27"); rs.cell(i, 7, "R00")
    pg = wb[next(n for n in ("Project schedule", "Schedule", "Programme") if n in wb.sheetnames)]
    prog = [("Award", "Early works award", "Milestone", "2025-02-03", "2025-02-03", "2025-02-03", "2025-02-03"),
            ("Award", "EPC award", "Milestone", "2025-05-02", "2025-05-02", "2025-05-02", "2025-05-02"),
            ("Design", "IFC design", "Phase", "2025-05-05", "2025-11-28", "2025-05-05", "2025-12-12"),
            ("Procurement", "Main transformer delivery", "Milestone", "2026-02-02", "2026-02-02", "2026-02-23", "2026-02-23"),
            ("Construction", "Civil works", "Phase", "2025-08-04", "2026-03-27", "2025-08-04", "2026-04-17"),
            ("Construction", "Electrical installation", "Phase", "2025-11-03", "2026-07-31", "2025-11-03", "2026-08-28"),
            ("Commissioning", "Energisation", "Milestone", "2026-08-31", "2026-08-31", "2026-10-30", "2026-10-30"),
            ("Completion", "Practical completion", "Milestone", "2026-10-30", "2026-10-30", "2026-11-27", "2026-11-27")]
    for i, row in enumerate(prog, start=2):
        for c, v in enumerate(row, start=1):
            pg.cell(i, c, v)
    wb.save(path)


# ---------------------------------------------------------------------------
# Pronto export (fictional)
# ---------------------------------------------------------------------------
TX_HEAD = ["Project", "Category", "Cat. Description", "Account Code", "Type", "Transaction", "Reference", "Trans Description",
           "Hrs/Qty", "Trans. Cost", "Charge", "Invoiced", "Hold Charge", "Override Charge", "Details", "Batch",
           "Account Description", "Document type", "Document no", "Document suffix", "Document seq", "Stock group",
           "Item Code", "CBS Sequence", "Description", "Variation No", "Financial Year", "Financial Period", "Journal Batch Ref"]
LAB_HEAD = ["EOM", "Project Code", "Project Description", "Resource Code", "Description", "Work Rate Code", "Work Rate",
            "Date Worked", "Status", "Approved?", "Cost Category", "Cost Category Description", "Timesheet Notes",
            "Hours Worked", "Cost Rate (if Posted)", "Total Cost", "Charge Rate (if Posted)", "Total Charge"]
PO_HEAD = ["Order No", "Backorder flag", "Status", "Order Type", "Supplier Name", "Supplier Trading Name and Address", "Whse",
           "Ordered", "Action", "Due", "Received", "Currency", "Order Total", "Transit Total", "Received Total", "Local Amount",
           "Charges", "Project", "Cost Category", "Terms", "Invoice details", "Invoice", "Invoiced (Inc. Tax)", "Officer",
           "Supplier", "Project", "Cost Category"]
CLAIM_HEAD = ["Claim No", "Claim Description", "Customer", "Status", "Status Description", "Date Created", "Date Approved",
              "Date Submitted", "Date Certified", "Date Paid", "Total Amount", "Certified Amount", "Deferred Amount",
              "Retained Amount", "Paid Amount", "Order No", "Project"]
VAR_HEAD = ["Variation No.", "Status", "Description", "Submitted", "Expected Amt", "Approved", "Instructed By",
            "Total Cost", "Total Hours", "Customer Ref"]
CTD_HEAD = ["Category", "Cat. Description", "Cat. Type", "Actual Amount", "Budget Amount", "Cost Variance", "Hrs Actual", "Hrs Budget", "Hours Variance"]

CAT_NAMES = dict(__import__("app.taxonomy", fromlist=["PARENTS"]).PARENTS)


def build_pronto_file(path):
    tx, lab, pos, claims = [], [], [], []
    docno = 100000
    # ---- labour -----------------------------------------------------------
    emp_code = {}
    for pref, name, func, wrc, cost, sell, cat in ROLES:
        emp_code[pref] = pref + "01"
    plan = {  # employee -> (start, end, intensity)
        "PM": (START, END, 0.55), "PC": (START, END, 0.8), "CM": (date(2025, 5, 2), END, 0.2), "HS": (date(2025, 7, 1), END, 0.45),
        "DM": (START, date(2025, 12, 31), 0.5), "SD": (START, date(2026, 1, 30), 0.9), "D1": (START, date(2026, 2, 27), 0.8),
        "D2": (date(2025, 3, 3), date(2026, 3, 31), 0.85), "EN": (START, END, 0.3), "E2": (date(2025, 5, 2), END, 0.7),
        "CO": (date(2025, 8, 4), END, 0.9), "SS": (date(2025, 10, 1), END, 1.0), "SC": (date(2025, 8, 4), date(2026, 5, 29), 1.0),
        "SA": (date(2025, 8, 4), END, 0.9), "TC": (date(2026, 5, 4), END, 1.0), "TM": (date(2026, 5, 4), END, 0.6),
        "SE": (date(2026, 2, 2), END, 0.7),
    }
    for pref, name, func, wrc, cost, sell, cat in ROLES:
        a, b, k = plan[pref]
        sur = name.split()[-1].upper()
        for d in workdays(max(a, START), min(b, STATUS)):
            if rnd.random() > k * 0.78:
                continue
            hrs = rnd.choice([7.6, 7.6, 7.6, 3.8, 11.4, 9.5])
            posted = d <= STATUS - timedelta(days=4)
            docno += 1
            total = round(hrs * cost, 2)
            lab.append([eom(d), PRONTO_PROJECT, "Demo Greenfield Substation", emp_code[pref], name.upper(), wrc, func.upper(), d,
                        "Time Posted" if posted else "Time Translated", "Approved" if posted else "Pending", cat, CAT_NAMES[cat],
                        "", hrs, cost if posted else None, total, sell if posted else None, round(hrs * sell, 2)])
            if posted:
                tx.append([PRONTO_PROJECT, cat, CAT_NAMES[cat], f"{emp_code[pref]} {d:%d%m%y}", "PY", d, "NORMAL LAB", sur, hrs, total,
                           round(hrs * sell, 2), None, None, None, f"Ty:1:Wcat:{wrc}", "00110P", func.upper(), "TS", docno, None, 1,
                           None, None, None, None, None, d.year, d.month, None])
    # ---- suppliers and POs -------------------------------------------------
    po_no = 1000
    spec = [  # supplier, category, [(order value, start month, end month, share invoiced to date)]
        ("S30ARC01", "PS02", [(380000, "2025-02", "2025-10")]),
        ("S30NBC01", "PS04", [(1580000, "2025-08", "2026-04")]),
        ("S30LEC01", "PS04", [(1190000, "2025-11", "2026-08")]),
        ("S30TST01", "PS05", [(165000, "2026-06", "2026-10")]),
        ("S30SCD01", "PS07", [(345000, "2026-02", "2026-09")]),
        ("S30TRX01", "PM02", [(1420000, "2025-05", "2026-02")]),
        ("S30SWG01", "PM03", [(1310000, "2025-06", "2026-03"), (92000, "2026-01", "2026-04")]),
        ("S30PRT01", "PM04", [(515000, "2025-07", "2026-03")]),
        ("S30CAB01", "PM05", [(448000, "2025-09", "2026-05")]),
        ("S30CIV01", "PM07", [(310000, "2025-08", "2026-03"), (260000, "2026-03", "2026-10")]),
        ("S30HIR01", "PE02", [(240000, "2025-08", "2026-10")]),
        ("S30ACC01", "PE01", [(215000, "2025-08", "2026-10")]),
        ("S30FRT01", "PE05", [(150000, "2025-08", "2026-09")]),
    ]
    names = {s[0]: s[1] for s in SUPPLIERS}
    var_sup = {"S30NBC01": 0, "S30LEC01": 0}
    accrual_invoice = None
    for scode, cat, orders in spec:
        for value, m0, m1 in orders:
            po_no += rnd.randint(7, 40)
            ms = months(date.fromisoformat(m0 + "-01"), date.fromisoformat(m1 + "-01"))
            invoiced = 0.0
            done_months = [m for m in ms if m <= date(STATUS.year, STATUS.month, 1)]
            frac_done = len(done_months) / len(ms)
            # supplier pace: a few over, a few under
            pace = {"S30NBC01": 1.12, "S30TRX01": 1.0, "S30SWG01": 0.97, "S30HIR01": 1.2, "S30ACC01": 1.18}.get(scode, 1.0)
            target = min(value * 1.15, value * frac_done * pace)
            if frac_done >= 1.0 and scode not in ("S30CIV01",):
                target = value * pace
            lines = 3
            for m in done_months:
                amt = round(target / len(done_months) * rnd.uniform(0.7, 1.3), 2)
                if m == done_months[-1]:
                    amt = round(target - invoiced, 2)
                if amt <= 0:
                    continue
                invoiced += amt
                d = min(eom(m) - timedelta(days=rnd.randint(1, 9)), STATUS)
                docno += 1
                suffix = chr(65 + rnd.randint(0, 5)) + chr(65 + rnd.randint(0, 5))
                tx.append([PRONTO_PROJECT, cat, CAT_NAMES[cat], scode, "PP", d, f"{po_no}{suffix}", f"{names[scode]} progress {m:%b %y}",
                           1, amt, round(amt * 1.18, 2), None, None, None, f"Progress {m:%b %y}", "0011JR", names[scode].upper(), "PO",
                           po_no, suffix, 1, None, "Special Item", None, None, None, d.year, d.month, None])
            open_po = frac_done < 1.0 or scode in ("S30CIV01", "S30HIR01", "S30ACC01", "S30FRT01", "S30SCD01")
            status = "On Order" if open_po else "Completed"
            per = value / lines
            for i in range(lines):
                recv = invoiced / lines
                pos.append([po_no, None, status, "Normal Order", names[scode].upper(), names[scode].upper() + " 1 EXAMPLE ST", "EPEC Projects",
                            date.fromisoformat(m0 + "-01"), date.fromisoformat(m0 + "-01"), eom(date.fromisoformat(m1 + "-01")), None, "AUD",
                            round(recv, 2), 0, round(recv, 2), round(per, 2), 0, "Demo Greenfield Substation", CAT_NAMES[cat], None, None,
                            None, round(recv * 1.1, 2), "officer.demo", scode, PRONTO_PROJECT, cat])
    # ---- non-PO invoices (card/expenses), indirect costs and a few journals --------
    for m in months(date(2025, 8, 1), date(STATUS.year, STATUS.month, 1)):
        for cat, base in (("PE03", 11000), ("PE01", 9000), ("PE04", 800), ("PE06", 2500)):
            d = min(eom(m) - timedelta(days=rnd.randint(2, 12)), STATUS)
            amt = round(base * rnd.uniform(0.6, 1.5), 2)
            docno += 1
            tx.append([PRONTO_PROJECT, cat, CAT_NAMES[cat], "S30CARD01", "CC", d, f"CARD-{docno}", f"Card expenses {m:%b %y}", 1, amt, amt,
                       None, None, None, "", "0021CC", "CORPORATE CARD", "CV", docno, None, 1, None, None, None, None, None, d.year, d.month, None])
    # misc materials & spares with no supplier line: they will land on the unallocated pot
    for m in months(date(2025, 10, 1), date(2026, 8, 1)):
        d = eom(m) - timedelta(days=4)
        amt = round(rnd.uniform(3000, 14000), 2)
        docno += 1
        tx.append([PRONTO_PROJECT, "PM06", CAT_NAMES["PM06"], "S30MSC01", "CI", d, f"INV-{docno}", f"Consumables {m:%b %y}", 1, amt, amt,
                   None, None, None, "", "0021CC", "SITE SUPPLIES PTY LTD", "CV", docno, None, 1, None, None, None, None, None, d.year, d.month, None])
    # a month-end accrual journal and its reversal, plus a manual-accrual target invoice
    docno += 1
    tx.append([PRONTO_PROJECT, "PS04", CAT_NAMES["PS04"], "3000B1125", "JE", date(2026, 8, 31), "1100", "Aug 26 Acc Northbridge Civil", 1, 64000, 64000,
               None, None, None, "", "0099JE", "Work in Progress", "GJ", docno, None, 1, None, None, None, None, None, 2026, 8, None])
    docno += 1
    tx.append([PRONTO_PROJECT, "PS04", CAT_NAMES["PS04"], "3000B1125", "RJ", date(2026, 9, 1), "1100", "Aug 26 Acc Northbridge Civil reversal", 1, -64000, -64000,
               None, None, None, "", "0099JE", "Work in Progress", "GV", docno, None, 1, None, None, None, None, None, 2026, 9, None])
    # finance's accruals still open at the status date: a supplier (PO reference) and the month's timesheets
    docno += 1
    tx.append([PRONTO_PROJECT, "PM07", CAT_NAMES["PM07"], "3000B1125", "JE", date(2026, 9, 30), "1243", "Sep 26 Acc Redgum Concrete", 1, 18500, 18500,
               None, None, None, "", "0099JE", "Work in Progress", "GJ", docno, None, 1, None, None, None, None, None, 2026, 9, None])
    docno += 1
    tx.append([PRONTO_PROJECT, "PL04", CAT_NAMES["PL04"], "3000B1125", "JE", date(2026, 9, 30), "TIMESHEET ACCRUAL", "SEP 26 Timesheet Accrual", 1, 2400, 2400,
               None, None, None, "", "0099JE", "Work in Progress", "GJ", docno, None, 1, None, None, None, None, None, 2026, 9, None])
    docno += 1
    tx.append([PRONTO_PROJECT, "PS04", CAT_NAMES["PS04"], "S30LEC01", "CI", date(2026, 9, 24), "INV-7781", "Larkspur Electrical claim 7", 1, 118500.00, 118500.00,
               None, None, None, "", "0021CC", "LARKSPUR ELECTRICAL PTY LTD", "CV", docno, None, 1, None, None, None, None, None, 2026, 9, None])
    # ---- revenue (invoices to the client) ------------------------------------
    rev_months = months(date(2025, 3, 1), date(2026, 9, 1))
    total_contract = 11590000 * SOV_SCALE
    shape = [0.01, 0.02, 0.03, 0.04, 0.05, 0.05, 0.06, 0.07, 0.07, 0.08, 0.08, 0.08, 0.07, 0.07, 0.06, 0.06, 0.05, 0.05, 0.05]
    scale = 0.93  # a little behind the full claim plan
    cum = 0.0
    for i, m in enumerate(rev_months):
        amt = round(total_contract * shape[i] * scale, 2)
        d = eom(m) - timedelta(days=3)
        cum += amt
        cno = f"CLAIM{i + 1:03d}"
        paid = d + timedelta(days=35) <= STATUS
        certified = d + timedelta(days=10) <= STATUS
        claims.append([cno, "Greenfield Substation", "30EXR01", "P" if paid else ("C" if certified else "S"),
                       "Paid" if paid else ("Certified" if certified else "Submitted"), d, d, d,
                       d + timedelta(days=10) if certified else None, d + timedelta(days=35) if paid else None, amt, amt if certified else None,
                       0, 0, amt if paid else 0, 3000 + i, PRONTO_PROJECT])
        docno += 1
        tx.append([PRONTO_PROJECT, "000", "Revenue", "30EXR01", "IN", d, str(3000 + i), cno, 1, -amt, -amt, None, None, None, "", "0031IN",
                   "EXAMPLE RENEWABLES PTY LTD", "SO", 3000 + i, None, 1, None, None, None, None, None, d.year, d.month, None])
    # ---- write Excel ---------------------------------------------------------
    wb = xlsxwriter.Workbook(str(path))
    head = wb.add_format({"bold": True})
    dt = wb.add_format({"num_format": "yyyy-mm-dd"})

    def sheet(name, headers, rows, date_cols=()):
        ws = wb.add_worksheet(name)
        ws.write_row(0, 0, headers, head)
        for r, row in enumerate(rows, start=1):
            for c, v in enumerate(row):
                if isinstance(v, date):
                    ws.write_datetime(r, c, __import__("datetime").datetime(v.year, v.month, v.day), dt)
                elif v is not None:
                    ws.write(r, c, v)
        ws.set_column(0, len(headers), 16)

    sheet("Transactions", TX_HEAD, tx)
    sheet("Labour", LAB_HEAD, lab)
    sheet("Purchase Orders", PO_HEAD, pos)
    sheet("Claims", CLAIM_HEAD, claims)
    sheet("Variations", VAR_HEAD, [["VAR1", "Approved", "Additional fibre route", None, 0, 148500, "Sam Client", 118000, 0, "CVAR-1"],
                                   ["VAR2", "Entered", "Revised earthing design", None, 62000, 0, "Sam Client", 51000, 0, "CVAR-2"]])
    # CTD overview from the GL
    sums = {}
    for r in tx:
        if r[1] not in ("000", "999"):
            sums[r[1]] = sums.get(r[1], 0.0) + r[9]
    sheet("CTD Overview", CTD_HEAD, [[c, CAT_NAMES.get(c, c), "Cost", round(v, 2), 0, round(v, 2), 0, 0, 0] for c, v in sorted(sums.items())])
    wb.close()
    return len(tx), len(lab), len(pos), len(claims)


# ---------------------------------------------------------------------------
# Seeding (uses the same code paths as the app)
# ---------------------------------------------------------------------------
def seed(con, name="Demo: Greenfield Substation"):
    tpl = DEMO / "demo_project_template.xlsx"
    exp = DEMO / "demo_pronto_export.xlsx"
    pid = services.create_project(con, {"name": name})
    with open(tpl, "rb") as f:
        rep = templates_io.import_template(con, pid, f)
    # move allowances from the role/trade pots onto the named lines, so the demo shows both pots and lines
    transfers = {
        "PL01": {"Alex Marsden": 330000, "Blair Okafor": 190000, "Casey Lindqvist": 120000, "Dana Whitfield": 150000},
        "PL02": {"Eden Castellano": 120000, "Frankie Nowak": 210000, "Gale Thornton": 180000, "Harper Quinn": 90000},
        "PL03": {"Indy Rasmussen": 160000, "Jules Abernathy": 140000},
        "PL04": {"Kai Brennan": 300000, "Lane Moreau": 230000, "Morgan Delacroix": 130000, "Nico Valdez": 90000},
        "PL05": {"Oakley Baird": 200000, "Parker Linden": 130000},
        "PL07": {"Quinn Ashworth": 110000},
        "PS02": {"Arden Consulting Engineers": 420000},
        "PS04": {"Northbridge Civil Pty Ltd": 1650000, "Larkspur Electrical Pty Ltd": 1250000},
        "PS05": {"Tallowood Testing Services": 180000},
        "PS07": {"Meridian SCADA Systems": 360000},
        "PM02": {"Corvus Transformers Pty Ltd": 1450000},
        "PM03": {"Halden Switchgear": 1380000},
        "PM04": {"Quillon Protection": 520000},
        "PM05": {"Brightwater Cables": 430000},
        "PM07": {"Redgum Concrete and Steel": 520000},
        "PE02": {"Westfield Plant Hire": 260000},
        "PE01": {"Lakeside Motel": 230000},
        "PE05": {"Overland Freight": 160000},
    }
    for cat, mp in transfers.items():
        parent = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND category=?", (pid, cat))
        pots = db.rows(con, "SELECT id, name FROM cbs_node WHERE project_id=? AND parent_id=? AND kind='group'", (pid, parent["id"]))
        for nm, amt in mp.items():
            line = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND name=? AND kind='line'", (pid, nm))
            if line and pots:
                # draw from the pot that holds the most allowance for this category
                best = max(pots, key=lambda p: db.scalar(con, "SELECT COALESCE(SUM(budget),0) FROM allowance_ledger WHERE node_id=?", (p["id"],)))
                have = db.scalar(con, "SELECT COALESCE(SUM(budget),0) FROM allowance_ledger WHERE node_id=?", (best["id"],))
                take = min(amt, have)
                if take > 0:
                    # estimate is locked once initialised, so estimate lines directly here
                    services.set_estimate(con, pid, line["id"], take)
                    cur = db.one(con, "SELECT budget FROM allowance_ledger WHERE node_id=? AND kind='estimate'", (best["id"],))
                    services.set_estimate(con, pid, best["id"], (cur["budget"] if cur else 0) - take)
    # the demo's lines follow the project window (a line only forecasts once it has one)
    pr = db.one(con, "SELECT project_start, project_end FROM project WHERE id=?", (pid,))
    con.execute("UPDATE cbs_node SET start_date=?, end_date=? WHERE project_id=? AND parent_id IS NULL", (pr["project_start"], pr["project_end"], pid))
    services.initialise(con, pid, force=True)
    db.bump(con, pid)
    reports.create_snapshot(con, pid, "Day zero (baseline)", kind="baseline")
    # Pronto
    found = pronto.analyse(exp)
    for it in found:
        mode = "replace"
        pronto.import_sheet(con, pid, exp, exp.name, it["sheet"], it["kind"], it["header_row"], mode,
                            PRONTO_PROJECT if it["kind"] in ("transactions", "labour", "po") else None)
    s = db.project_settings(con, pid)
    s["pronto_project"] = PRONTO_PROJECT
    db.update(con, "project", pid, {"settings_json": __import__("json").dumps(s)})
    return pid, rep


def seed_extras(con, pid):
    """Forecast items, a subcontract, accruals, a variation and claims, so every screen has something to show."""
    from app import variations
    node = lambda name: db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND name=?", (pid, name))["id"]
    # ground-up forecast for the transformer line: remaining payments on milestones
    n = node("Corvus Transformers Pty Ltd")
    db.update(con, "cbs_node", n, {"method": "GROUND-UP"})
    db.insert(con, "forecast_item", dict(project_id=pid, node_id=n, scope="Retention release", spread="Lump", unit="ea", qty=1, rate=30000, pct=1, start_date="2026-11-15"))
    # labour ground-up for the site supervisor
    n = node("Lane Moreau")
    db.update(con, "cbs_node", n, {"method": "GROUND-UP"})
    db.insert(con, "forecast_item", dict(project_id=pid, node_id=n, scope="Site supervision to PC", spread="Recurring", unit="hr", qty=7.6, rate=150, pct=1,
                                         start_date="2026-10-01", end_date="2026-11-30", freq="Daily"))
    # subcontract with a milestone schedule feeding the CLAIM method
    n = node("Larkspur Electrical Pty Ltd")
    sid = db.insert(con, "subcontract", dict(project_id=pid, name="Larkspur Electrical: electrical installation", supplier_code="S30LEC01", po_no="1032",
                                             node_id=n, contract_value=1190000, retention_pct=0.05, retention_release_month="2026-11"))
    for i, (nm, typ, pct, a, b) in enumerate([("Deposit on order", "Milestone", 0.10, "2025-11", None), ("Execution", "Progress", 0.80, "2025-12", "2026-10"),
                                               ("Testing and handover", "Milestone", 0.10, "2026-11", None)]):
        db.insert(con, "sub_milestone", dict(subcontract_id=sid, seq=i + 1, name=nm, type=typ, pct=pct, value=0, start_month=a, end_month=b))
    # monthly claims built from the schedule: paid months are approved as claimed; September is received and still awaiting approval
    from app import subcontracts
    months_paid = ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
    for i, m in enumerate(months_paid):
        cid = subcontracts.create_claim(con, sid, m, f"C{i + 1}")
        subcontracts.approve_all(con, cid)
        db.update(con, "sub_claim", cid, dict(status="paid" if m != "2026-08" else "approved", inv_ref="INV-7781" if m == "2026-08" else f"INV-{7770 + i}", approved_date=m + "-28"))
        subcontracts.refresh_cache(con, cid)
    cid = subcontracts.create_claim(con, sid, "2026-09", "C11")
    db.update(con, "sub_claim", cid, dict(inv_ref="INV-7790", received_date="2026-09-29"))
    db.update(con, "cbs_node", n, {"method": "CLAIM"})
    # accruals: one that will auto-match the landed invoice INV-7781, one that stays open
    pc = node("Northbridge Civil Pty Ltd")
    db.insert(con, "accrual", dict(project_id=pid, node_id=n, month="2026-08", amount=118500.0, source="PM", inv_ref="INV-7781", kind="invoice", supplier_code="S30LEC01",
                                   supplier_name="LARKSPUR ELECTRICAL PTY LTD", reason="Work done, invoice not yet received", note="Invoice sent for approval in August, landed in Pronto in September"))
    db.insert(con, "accrual", dict(project_id=pid, node_id=pc, month="2026-09", amount=82000.0, source="PM", kind="work", reason="Work done, invoice not yet received", note="September valuation"))
    # invoice accruals by PO: one the next invoice on the PO matches (for a different amount: to review), and one
    # finance has also accrued in Pronto this month (PMT counts only the part above finance's accrual)
    rg = db.one(con, "SELECT n.id, p.order_no FROM cbs_node n JOIN pronto_po p ON p.node_id=n.id AND p.project_id=n.project_id WHERE n.project_id=? AND p.supplier_code='S30CIV01' ORDER BY p.order_no DESC LIMIT 1", (pid,))
    if rg:
        db.insert(con, "accrual", dict(project_id=pid, node_id=rg["id"], month="2026-07", amount=30000.0, source="PM", kind="invoice", po_no=rg["order_no"], supplier_code="S30CIV01",
                                       supplier_name="REDGUM CONCRETE AND STEEL", reason="Work done, invoice not yet received", note="July pour, invoice in approval"))
        con.execute("UPDATE pronto_tx SET reference=? WHERE project_id=? AND description='Sep 26 Acc Redgum Concrete'", (rg["order_no"], pid))
        db.insert(con, "accrual", dict(project_id=pid, node_id=rg["id"], month="2026-09", amount=20000.0, source="PM", kind="work", po_no=rg["order_no"], supplier_code="S30CIV01",
                                       supplier_name="REDGUM CONCRETE AND STEEL", reason="Work done, invoice not yet received", note="September pours, site estimate"))
    accruals.match(con, pid)
    # a variation that is recognised, with a build-up
    vid = db.insert(con, "variation", dict(project_id=pid, ref="EPC-VAR-001", stage="EPC", title="Additional fibre route", description="Supply and install an additional fibre route to the point of connection.",
                                           client_status="Approved", client_status_date="2026-05-20", epec_status="Agreed", epec_status_date="2026-05-20",
                                           contract_change="No", contract_status="n/a", prepared_by="Alex Marsden", validity="30 days", pricing_model="LS",
                                           submission_date="2026-04-28", pronto_ref="VAR1"))
    db.insert(con, "variation_rev", dict(variation_id=vid, rev=0, date="2026-04-28", value=148500, is_current=1))
    cat = lambda c: db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND category=?", (pid, c))["id"]
    for sec, code, desc, unit, qty, rate in [("Labour", "PL03", "Design and engineering", "hr", 160, 135), ("Materials", "PM05", "Fibre and accessories", "ea", 1, 41000),
                                            ("Subcontractors", "PS04", "Installation", "ea", 1, 52000)]:
        db.insert(con, "variation_line", dict(variation_id=vid, section=sec, node_id=cat(code), description=desc, unit=unit, qty=qty, rate=rate, risk_pct=0.07, markup_pct=0.2))
    vid2 = db.insert(con, "variation", dict(project_id=pid, ref="EPC-VAR-002", stage="EPC", title="Revised earthing design", description="Revised earthing grid following geotechnical results.",
                                            client_status="In Discussion", epec_status="Pursuing", contract_change="Yes", contract_status="Not started",
                                            prepared_by="Casey Lindqvist", validity="30 days", pricing_model="T&M", submission_date="2026-08-14"))
    db.insert(con, "variation_rev", dict(variation_id=vid2, rev=0, date="2026-08-14", value=62000, is_current=1))
    variations.sync(con, pid, vid)
    variations.sync(con, pid, vid2)
    # claims (app side): the first claims issued from the schedule
    from app import revenue
    for i, per in enumerate(["2025-03", "2025-04", "2025-05", "2025-06", "2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12",
                             "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]):
        cid = db.insert(con, "claim", dict(project_id=pid, claim_no=f"CLAIM{i + 1:03d}", period=per, status="paid" if per <= "2026-06" else "certified",
                                           pronto_claim_no=f"CLAIM{i + 1:03d}"))
        d = revenue.claim_detail(con, pid, cid)
        for l in d["lines"]:
            if l["suggested"] > 0:
                amt = round(l["suggested"] * 0.94, 2)
                db.insert(con, "claim_line", dict(claim_id=cid, item_id=l["item_id"], amount=amt, certified=amt))
    cid = db.insert(con, "claim", dict(project_id=pid, claim_no="CLAIM019", period="2026-09", status="draft"))
    d = revenue.claim_detail(con, pid, cid)
    for l in d["lines"]:
        if l["suggested"] > 0:
            db.insert(con, "claim_line", dict(claim_id=cid, item_id=l["item_id"], amount=l["suggested"]))
    db.insert(con, "cmt_entry", dict(project_id=pid, as_of="2026-08-31", revenue=15350000, eac=13400000, ctd=11100000, note="From the Finance CMT (demo figure)"))
    seed_forecast_detail(con, pid)
    db.bump(con, pid)
    seed_risk(con, pid)
    reports.create_snapshot(con, pid, "EOM " + STATUS.strftime("%Y-%m"))
    simulate_history(con, pid)


def seed_forecast_detail(con, pid):
    """One of each forecast detail type: a roster priced from supplier rates, milestone payments, a resource calendar."""
    from datetime import date, timedelta
    from app import forecast
    from app.holidays import QLD_HOLIDAYS
    for d, nm in QLD_HOLIDAYS:
        if "2025-01-01" <= d <= "2027-12-31":
            db.insert(con, "holiday", dict(project_id=pid, day=d, name=nm))
    node = lambda name: db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND name=?", (pid, name))["id"]
    res = lambda code: db.one(con, "SELECT id FROM resource WHERE project_id=? AND code=?", (pid, code))["id"]
    civ = res("S30NBC01")
    for role, rate, ot, al in [("Civil labourer", 78, 117, 160), ("Plant operator", 96, 144, 160), ("Leading hand", 105, 157.5, 160)]:
        db.insert(con, "supplier_rate", dict(project_id=pid, resource_id=civ, role=role, unit="hr", rate=rate, ot_rate=ot, nt_hours=8, allowance=al,
                                             ref="Northbridge SOR rev 2 (fictional)", valid_from="2026-07-01"))
    n = node("Northbridge Civil Pty Ltd")
    db.update(con, "cbs_node", n, {"method": "GROUND-UP"})
    db.insert(con, "forecast_item", dict(project_id=pid, node_id=n, scope="Bulk earthworks crew", spread="Roster", resource_id=civ, role="Civil labourer", rate_mode="auto",
                                         pattern="10:4", swings=4, headcount=6, hours_day=10, start_date="2026-10-05", skip_holidays=0, qty=1, pct=1, basis="hours"))
    db.insert(con, "forecast_item", dict(project_id=pid, node_id=n, scope="Leading hand", spread="Roster", resource_id=civ, role="Leading hand", rate_mode="auto",
                                         pattern="10:4", swings=4, headcount=1, hours_day=10, start_date="2026-10-05", qty=1, pct=1, basis="hours"))
    db.insert(con, "forecast_item", dict(project_id=pid, node_id=n, scope="Demobilisation", spread="Lump", qty=1, rate=18000, pct=1, start_date="2026-12-10"))
    # switchgear paid on milestones
    n = node("Halden Switchgear")
    db.update(con, "cbs_node", n, {"method": "GROUND-UP"})
    iid = db.insert(con, "forecast_item", dict(project_id=pid, node_id=n, scope="33 kV switchboard (PO 1045)", spread="Milestones", qty=1, rate=640000, pct=1, po_no="1045", resource_id=res("S30SWG01")))
    forecast.save_milestones(con, pid, iid, [dict(name="On order", pct=0.10, month="2025-07", status="invoiced"), dict(name="Drawing approval", pct=0.15, month="2025-10", status="invoiced"),
                                            dict(name="FAT", pct=0.20, month="2026-08", note="FAT slipped, witness booked for October"), dict(name="Delivery to site", pct=0.45, month="2026-11"),
                                            dict(name="SAT and documentation", pct=0.10, month="2027-01")])
    # a commissioning engineer forecast day by day
    oak = res("TC01")
    db.update(con, "resource", oak, {"cost_rate": 140})
    n = node("Oakley Baird")
    db.update(con, "cbs_node", n, {"method": "GROUND-UP"})
    iid = db.insert(con, "forecast_item", dict(project_id=pid, node_id=n, scope="Commissioning on site", spread="Calendar", basis="hours", resource_id=oak, rate_mode="auto", qty=1, pct=1))
    hol = {d for d, _ in QLD_HOLIDAYS}
    days, d = {}, date(2026, 9, 21)
    while d <= date(2026, 11, 27):
        if d.weekday() < 5 and d.isoformat() not in hol:
            days[d.isoformat()] = 10 if date(2026, 10, 26) <= d <= date(2026, 10, 30) else 8  # long days around energisation
        d += timedelta(days=1)
    forecast.save_days(con, pid, iid, days)
    forecast.save_hour_accruals(con, pid, oak, n, {"2026-09-28": 8}, note="Site sign-in sheet, timesheet late")
    # engineering hours held in the PL03 pool, part of them now given to a named engineer (taken out of the pool)
    n = node("Indy Rasmussen")
    db.update(con, "cbs_node", n, {"method": "GROUND-UP"})
    iid = db.insert(con, "forecast_item", dict(project_id=pid, node_id=n, scope="Protection settings review (from the PL03 pool)", spread="Calendar", basis="hours",
                                               resource_id=res("EN01"), rate_mode="auto", qty=1, pct=1, from_pool=1))
    forecast.save_days(con, pid, iid, {d: 6 for d in ("2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16",
                                                      "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23")})
    # two accruals whose timesheets have since landed: one for the same hours (matched), one for different hours
    for code, delta in (("HS01", 0), ("EN01", 2)):
        rid = res(code)
        t = db.one(con, "SELECT date_worked, node_id, SUM(hours) h FROM pronto_labour WHERE project_id=? AND resource_code=? AND posted=1 AND month='2026-09' "
                        "GROUP BY date_worked, node_id ORDER BY date_worked DESC LIMIT 1", (pid, code))
        if t and t["node_id"]:
            forecast.save_hour_accruals(con, pid, rid, t["node_id"], {t["date_worked"]: t["h"] + delta}, note="Accrued from the site diary before the timesheet was posted")
    # schedule-of-rates subcontractor: Northbridge's timesheets for the last fortnight of September (uploaded from the
    # template); the first week is accrued, the last days are waiting to be accrued
    nb = node("Northbridge Civil Pty Ltd")
    d = date(2026, 9, 14)
    while d <= date(2026, 9, 30):
        if d.weekday() < 5:
            for w in ("J. Harlow", "M. Ortega", "S. Pike", "T. Quinn"):
                db.insert(con, "sub_timesheet", dict(project_id=pid, batch="demo upload", resource_id=civ, role="Civil labourer", worker=w, day=d.isoformat(),
                                                     hours=10, node_id=nb, docket=f"NB-{d.strftime('%d%m')}", row_hash=f"demo-{d}-{w}"))
        d += timedelta(days=1)
    acc_days = {x: 40 for x in ("2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25")}
    forecast.save_hour_accruals(con, pid, civ, nb, acc_days, role="Civil labourer", heads=4, reason="Work done, invoice not yet received", note="From Northbridge timesheets")
    from app import accruals
    accruals.match(con, pid)


# ---------------------------------------------------------------------------
# Fictional programme in MS Project XML and PDF, to try the optional programme upload
# ---------------------------------------------------------------------------
PROGRAMME = [  # outline level, name, start, finish
    (1, "GREENFIELD SUBSTATION", "2025-02-03", "2026-11-27"),
    (2, "Preliminaries and site establishment", "2025-02-03", "2026-11-27"),
    (2, "Design", "2025-02-03", "2025-11-28"),
    (3, "IFC design", "2025-05-05", "2025-11-28"),
    (2, "Primary plant supply", "2025-05-05", "2026-03-27"),
    (3, "Power transformers delivery", "2025-06-02", "2026-02-23"),
    (3, "Switchgear delivery", "2025-06-02", "2026-03-27"),
    (2, "Civil and structures", "2025-08-04", "2026-04-17"),
    (2, "Electrical installation", "2025-11-03", "2026-08-28"),
    (2, "SCADA and communications", "2026-02-02", "2026-09-30"),
    (2, "Testing and commissioning", "2026-06-01", "2026-11-27"),
    (3, "Energisation", "2026-10-30", "2026-10-30"),
    (3, "Practical completion", "2026-11-27", "2026-11-27"),
]


def write_programme_files():
    from xml.sax.saxutils import escape
    tasks = []
    for i, (lv, name, s, f) in enumerate(PROGRAMME, start=1):
        ms = 1 if s == f else 0
        tasks.append(f"<Task><UID>{i}</UID><ID>{i}</ID><Name>{escape(name)}</Name><WBS>{i}</WBS><OutlineLevel>{lv}</OutlineLevel>"
                     f"<Summary>{1 if i < len(PROGRAMME) and PROGRAMME[i][0] > lv else 0}</Summary>"
                     f"<Milestone>{ms}</Milestone><Start>{s}T08:00:00</Start><Finish>{f}T17:00:00</Finish><PercentComplete>0</PercentComplete></Task>")
    (DEMO / "demo_programme.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><Project xmlns="http://schemas.microsoft.com/project"><Tasks>'
                                             '<Task><UID>0</UID><ID>0</ID><Name>Project summary</Name></Task>' + "".join(tasks) + "</Tasks></Project>")
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfgen import canvas
    except Exception:  # noqa: BLE001
        return
    c = canvas.Canvas(str(DEMO / "demo_programme.pdf"), pagesize=landscape(A4))
    c.setFont("Helvetica-Bold", 12); c.drawString(40, 560, "Greenfield Substation: programme (fictional)")
    c.setFont("Helvetica", 9)
    c.drawString(40, 535, "WBS"); c.drawString(90, 535, "Task name"); c.drawString(430, 535, "Duration"); c.drawString(500, 535, "Start"); c.drawString(600, 535, "Finish")
    y = 518
    for i, (lv, name, s, f) in enumerate(PROGRAMME, start=1):
        sd, fd = date.fromisoformat(s), date.fromisoformat(f)
        c.drawString(40, y, f"WBS-{i:03d}"); c.drawString(90 + (lv - 1) * 12, y, name); c.drawString(430, y, f"{(fd - sd).days}d")
        c.drawString(500, y, sd.strftime("%a %d/%m/%y")); c.drawString(600, y, fd.strftime("%a %d/%m/%y")); y -= 16
    c.save()


def seed_risk(con, pid):
    """Three risk events, bucket breakdowns, tagged costs and one General Manager release."""
    from app import risk as risk_mod
    ids = {}
    for ref, title, cause, est, lik, treat, eff in (("R-001", "Inclement weather", "Rain days during civil works", 180000, 0.5, "Accept", 0.0),
                                                    ("R-002", "Liquidated damages", "Late energisation exposure", 300000, 0.25, "Mitigate", 0.3),
                                                    ("R-003", "Factory delays", "Transformer and switchgear delivery slip", 160000, 0.3, "Mitigate", 0.25)):
        ids[ref] = db.insert(con, "risk", dict(project_id=pid, ref=ref, title=title, cause=cause, owner="Alex Marsden", status="materialised" if ref != "R-002" else "open", raised_date="2025-03-01",
                                               kind="Risk", category="Delivery" if ref != "R-002" else "Commercial", area="Construction" if ref == "R-001" else "Procurement" if ref == "R-003" else "Client",
                                               estimate=est, likelihood=lik, treatment=treat, effectiveness=eff, last_reviewed="2026-09-15",
                                               **{"R-001": dict(delay_days=20, delay_actual=12, revenue_impact=0, revenue_actual=0), "R-002": dict(delay_days=0, delay_actual=0, revenue_impact=300000, revenue_actual=0),
                                                  "R-003": dict(delay_days=30, delay_actual=21, revenue_impact=90000, revenue_actual=45000)}[ref]))
    # break the buckets down: every node that holds risk gets a share across the three events
    for b in risk_mod.buckets(con, pid):
        if b["bucket"] <= 0:
            continue
        cat = b["category"] or ""
        split = {"R-001": 0.5, "R-003": 0.5} if cat.startswith(("PM", "PS")) else {"R-001": 0.3, "R-002": 0.4, "R-003": 0.3}
        for ref, sh in split.items():
            db.insert(con, "risk_alloc", dict(project_id=pid, risk_id=ids[ref], node_id=b["node_id"], amount=round(b["bucket"] * sh, 2)))
    # tag costs that landed because of a risk: plant standby (weather), expedited freight (factory delay), a card-expense accommodation overrun
    def tag(cat, like, ref, n, amount):
        # only part of each invoice is a risk cost (standby days, expedite charges), so the tags carry part amounts
        for r in db.rows(con, "SELECT row_hash FROM pronto_tx WHERE project_id=? AND category=? AND class='actual' AND (description LIKE ? OR reference LIKE ?) ORDER BY tx_date DESC LIMIT ?",
                         (pid, cat, like, like, n)):
            db.insert(con, "risk_tag", dict(project_id=pid, risk_id=ids[ref], row_hash=r["row_hash"], amount=amount))
    tag("PE02", "%progress%", "R-001", 4, 5200)
    tag("PE05", "%progress%", "R-003", 3, 2400)
    tag("PE01", "%Card%", "R-001", 3, 1500)
    node = lambda name: db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND name=?", (pid, name))["id"]
    db.insert(con, "accrual", dict(project_id=pid, node_id=node("Westfield Plant Hire"), month="2026-09", amount=14000.0, source="PM", risk_id=ids["R-001"], reason="Other", note="Standby after rain"))
    pe05 = node("Overland Freight")
    db.insert(con, "forecast_item", dict(project_id=pid, node_id=pe05, scope="Expedited freight for late switchgear", spread="Lump", unit="ea", qty=1, rate=22000, pct=1, start_date="2026-10-10", risk_id=ids["R-003"]))
    db.update(con, "cbs_node", pe05, {"method": "GROUND-UP"})
    db.bump(con, pid)
    # the PM separates contingency from the budgets that carry risk costs, then funds the occurred risk cost in the agreed order:
    # contingency first, then a release from the company bucket
    plant, freight, travel = node("Westfield Plant Hire"), pe05, node("Lakeside Motel")
    risk_mod.set_contingency(con, pid, plant, 30000)
    risk_mod.set_contingency(con, pid, freight, 3000)
    risk_mod.contingency_to_risk(con, pid, plant, plant, 15000, date="2026-09-20", by="Alex Marsden", ref="PM-CT-01", note="Weather standby covered from contingency")
    # contingency exhausted for the invoices that have landed: the company releases the rest (the accrued standby waits for its invoice)
    risk_mod.release(con, pid, plant, 5800, date="2026-09-25", approved_by="General Manager", ref="GM-REL-01", note="Weather standby beyond contingency")
    risk_mod.set_contingency(con, pid, travel, 8000)
    risk_mod.contingency_to_risk(con, pid, travel, travel, 6000, date="2026-09-26", by="Alex Marsden", ref="PM-CT-03", note="Covers accommodation costs and saves a little for the next wet spell")
    risk_mod.contingency_to_risk(con, pid, freight, freight, 3000, date="2026-09-22", by="Alex Marsden", ref="PM-CT-02", note="Expedite freight")
    db.bump(con, pid)

def simulate_history(con, pid):
    """Month-end snapshots for July and August, rebuilt by temporarily rolling the project back to those months.

    Real projects build this history by closing each month as it happens; this only gives the demo something to compare.
    """
    from app import engine
    for label, status, keep in (("EOM 2026-07", "2026-07-31", "2026-07"), ("EOM 2026-08", "2026-08-31", "2026-08")):
        con.execute("SAVEPOINT hist")
        for t, col in (("pronto_tx", "month"), ("pronto_labour", "month")):
            con.execute(f"DELETE FROM {t} WHERE project_id=? AND {col} > ?", (pid, keep))
        con.execute("DELETE FROM pronto_po WHERE project_id=? AND ordered > ?", (pid, keep + "-31"))
        con.execute("DELETE FROM accrual WHERE project_id=? AND month > ?", (pid, keep))
        con.execute("DELETE FROM sub_claim WHERE month > ?", (keep,))
        con.execute("UPDATE project SET status_date=? WHERE id=?", (status, pid))
        db.bump(con, pid)
        sid = reports.create_snapshot(con, pid, label)
        con.execute("UPDATE snapshot SET created_at=? WHERE id=?", (status + " 17:00:00", sid))
        keepdata = db.one(con, "SELECT summary_json, curve_json FROM snapshot WHERE id=?", (sid,))
        lines = db.rows(con, "SELECT * FROM snapshot_line WHERE snapshot_id=?", (sid,))
        snap = db.one(con, "SELECT * FROM snapshot WHERE id=?", (sid,))
        con.execute("ROLLBACK TO hist")
        con.execute("RELEASE hist")
        engine._cache.clear()
        # the savepoint also rolled the snapshot back: write it again from the captured copy
        snap.pop("id")
        nid = db.insert(con, "snapshot", snap)
        for l in lines:
            l.pop("id"); l["snapshot_id"] = nid
            db.insert(con, "snapshot_line", l)
    con.execute("UPDATE project SET status_date=? WHERE id=?", (STATUS.isoformat(), pid))
    db.bump(con, pid)
    engine._cache.clear()



# ---- a demo team: one project director over a junior PM, two PMs and a senior PM ---------------------------------------
TEAM_DIRECTOR = dict(name="Taylor Brooks", role="Project Director", pm_level=4, base="Brisbane QLD", lat=-27.47, lon=153.03)
TEAM = [   # name, role, PM level, base, lat, lon
    ("Riley Chen", "Junior Project Manager", 1, "Brisbane QLD", -27.47, 153.03),
    ("Jordan Reyes", "Project Manager", 2, "Toowoomba QLD", -27.56, 151.95),
    ("Priya Nair", "Project Manager", 2, "Brisbane QLD", -27.47, 153.03),
    ("Sam Whitlock", "Senior Project Manager", 3, "Rockhampton QLD", -23.38, 150.51),
]
TEAM_CLIENTS = [("Sunfield Energy", "Developer", "Medium", 3), ("GridCo Networks", "Utility / network", "Low", 4), ("Bellbird Renewables", "IPP", "High", 4)]
# name, PM, client, type, MW, MWh, kV, place, lat, lon, complexity, then factors on the base demo project: size (all
# amounts), allowance (budget against the same work: above ~1.23 under-runs, below over-runs), revenue (contract value)
# and cost (what was spent: actuals and accruals)
TEAM_PROJECTS = [
    ("Kingaroy Solar Farm", "Riley Chen", "Sunfield Energy", "Solar farm", 60, None, "33/132", "Kingaroy QLD", -26.54, 151.84, 1, 0.35, 1.32, 1.35, 0.96),
    ("Ridgeway BESS", "Jordan Reyes", "GridCo Networks", "BESS", 100, 200, "33/132", "Dalby QLD", -27.18, 151.26, 3, 0.80, 1.24, 1.24, 1.00),
    ("Coolamon Substation", "Jordan Reyes", "GridCo Networks", "Substation", None, None, "132/275", "Chinchilla QLD", -26.74, 150.63, 4, 0.60, 1.08, 1.07, 1.05),
    ("Bellbird Wind Farm", "Priya Nair", "Bellbird Renewables", "Wind farm", 220, None, "33/275", "Biloela QLD", -24.40, 150.51, 4, 1.30, 1.30, 1.33, 0.98),
    ("Bellbird Wind Connection", "Priya Nair", "Bellbird Renewables", "Substation", None, None, "275", "Biloela QLD", -24.45, 150.60, 3, 0.50, 1.12, 1.12, 1.04),
    ("Bellbird BESS", "Sam Whitlock", "Bellbird Renewables", "BESS", 150, 300, "33/275", "Biloela QLD", -24.42, 150.55, 4, 0.90, 1.26, 1.27, 1.00),
    ("Tarong Grid Upgrade", "Sam Whitlock", "GridCo Networks", "Substation", None, None, "275/330", "Nanango QLD", -26.68, 151.99, 5, 0.70, 1.02, 1.02, 1.08),
    ("Wilga Solar Stage 2", "Sam Whitlock", "Sunfield Energy", "Solar farm", 120, None, "33/132", "Roma QLD", -26.57, 148.79, 3, 0.45, 1.36, 1.40, 0.94),
]
TEAM_PARENT = ("Bellbird Hybrid Program", ["Bellbird Wind Connection", "Bellbird BESS"])   # a PM's and the senior PM's project
TEAM_PREFIX = "Demo team: "

# every amount of a project, scaled together so each project stays consistent (cost factor on what was spent only)
_ALLOW = [("allowance_ledger", ("budget", "risk", "contingency", "risk_cover"), "project_id=?")]
_REV = [
    ("pronto_claim", ("total", "certified", "retained", "paid"), "project_id=?"),
    ("contract_item", ("value",), "project_id=?"),
    ("revenue_plan", ("amount",), "item_id IN (SELECT id FROM contract_item WHERE project_id=?)"),
    ("claim", ("certified_amount", "paid_amount", "retention"), "project_id=?"),
    ("claim_line", ("amount", "certified"), "claim_id IN (SELECT id FROM claim WHERE project_id=?)"),
    ("variation_rev", ("value",), "variation_id IN (SELECT id FROM variation WHERE project_id=?)"),
]
_SCALE = [
    ("pronto_po", ("committed", "received", "invoiced_inc_tax"), "project_id=?"),
    ("pronto_ctd", ("budget",), "project_id=?"),
    ("subcontract", ("contract_value",), "project_id=?"),
    ("sub_milestone", ("value",), "subcontract_id IN (SELECT id FROM subcontract WHERE project_id=?)"),
    ("sub_claim", ("gross", "retention", "retention_release"), "subcontract_id IN (SELECT id FROM subcontract WHERE project_id=?)"),
    ("sub_claim_line", ("claimed", "approved"), "claim_id IN (SELECT c.id FROM sub_claim c JOIN subcontract s ON s.id=c.subcontract_id WHERE s.project_id=?)"),
    ("variation_line", ("rate",), "variation_id IN (SELECT id FROM variation WHERE project_id=?)"),
    ("forecast_item", ("rate",), "project_id=?"),
    ("forecast_manual", ("amount",), "project_id=?"),
    ("cbs_node", ("eac_override", "uncommitted", "unalloc_eac"), "project_id=?"),
]
_SPENT = [("pronto_tx", ("cost", "charge"), "project_id=?"), ("pronto_ctd", ("actual",), "project_id=?"), ("accrual", ("amount", "matched_amount"), "project_id=?")]


def _scale(con, pid, size, allow, rev, cost):
    have = lambda t: {r[1] for r in con.execute(f"PRAGMA table_info({t})")}  # noqa: E731
    for group, f in ((_SCALE, size), (_ALLOW, size * allow), (_REV, size * rev), (_SPENT, size * cost)):
        for t, cols, where in group:
            cols = [c for c in cols if c in have(t)]
            if cols:
                con.execute(f"UPDATE {t} SET " + ", ".join(f"{c}=ROUND({c}*?,2)" for c in cols) + f" WHERE {where}", (*[f] * len(cols), pid))


def seed_team(con):
    """Eight demo projects for a team of four PMs under one project director, two of them children of a parent project.
    Each is the full demo project scaled to its own size, with its own cost performance. Returns the project ids."""
    from app import directory, linking
    if db.scalar(con, "SELECT COUNT(*) FROM project WHERE name LIKE ?", (TEAM_PREFIX + "%",)):
        raise ValueError("The demo team is already loaded (projects named 'Demo team: ...')")
    for nm, sector, risk, cx in TEAM_CLIENTS:
        cid = directory.add(con, "client", nm)["id"]
        db.update(con, "client", cid, dict(sector=sector, risk=risk, complexity=cx))
    pid_d = directory.add(con, "director", TEAM_DIRECTOR["name"])["id"]
    db.update(con, "person", pid_d, {k: v for k, v in TEAM_DIRECTOR.items() if k != "name"})
    for nm, role, lvl, base, la, lo in TEAM:
        x = directory.add(con, "pm", nm)["id"]
        db.update(con, "person", x, dict(role=role, pm_level=lvl, base=base, lat=la, lon=lo, fte=1.0, reports_to=TEAM_DIRECTOR["name"], active=1))
    ids = {}
    for k, (nm, pm, client, typ, mw, mwh, kv, place, la, lo, cx, size, allow, rev, cost) in enumerate(TEAM_PROJECTS, 1):
        pid, _ = seed(con, TEAM_PREFIX + nm)
        seed_extras(con, pid)
        _scale(con, pid, size, allow, rev, cost)
        db.update(con, "project", pid, dict(name=TEAM_PREFIX + nm, code=f"DT{k:02d}", number=f"09{k:02d}", client_name=client, epec_pm=pm, project_director=TEAM_DIRECTOR["name"],
                                            project_type=typ, capacity_mw=mw, storage_mwh=mwh, voltage=kv, location=place, lat=la, lon=lo, complexity=cx))
        # the baseline snapshot again, at this project's scale
        con.execute("DELETE FROM snapshot WHERE project_id=?", (pid,))
        db.bump(con, pid)
        engine._cache.clear()
        reports.create_snapshot(con, pid, "Day zero (baseline)", kind="baseline")
        ids[nm] = pid
    pname, kids = TEAM_PARENT
    parent = linking.link(con, TEAM_PREFIX + pname, [ids[k] for k in kids], director=TEAM_DIRECTOR["name"])
    engine._cache.clear()
    return dict(projects=ids, parent=parent)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--db")
    a = ap.parse_args()
    write_template_file(DEMO / "demo_project_template.xlsx")
    write_programme_files()
    counts = build_pronto_file(DEMO / "demo_pronto_export.xlsx")
    print("Wrote demo files. Transactions, labour, PO lines, claims:", counts)
    if a.seed:
        if a.db:
            import os
            os.environ["PMT_DB"] = a.db
        db.init_db()
        con = db.connect()
        pid, rep = seed(con)
        seed_extras(con, pid)
        con.commit()
        print("Seeded project id", pid, rep)


if __name__ == "__main__":
    main()
