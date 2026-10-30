"""EOM cost and revenue report: totals tie to cost control, revenue stages add up, PDF and Excel build."""
import io

import openpyxl
import pypdf

from app import engine, eom_report


def test_eom_report_ties_and_exports(demo):
    con, pid = demo[0], demo[1]
    d = eom_report.build(con, pid)
    t = engine.compute(con, pid)["total"]
    assert abs(d["cost"]["total"]["eac"] - t["eac"]) < 1 and abs(d["cost"]["total"]["ctd"] - t["ctd"]) < 1
    for s in d["revenue"]["stages"]:
        base, var, tot = s["rows"]
        assert abs(base["to_date"] + var["to_date"] - tot["to_date"]) < 0.01
        assert abs(tot["previous"] + tot["this_month"] - tot["to_date"]) < 0.01
    cf = d["cashflow"]
    assert abs(cf["cum_cost"][-1] - t["eac"]) < 1                       # the cashflow spends the EAC
    assert abs(cf["cum_net"][-1] - (cf["cum_revenue"][-1] - cf["cum_cost"][-1])) < 0.01
    gm = next(r for r in d["margin"] if r["metric"] == "Gross margin $")
    assert abs(gm["at_completion"] - (d["margin"][0]["at_completion"] - t["eac"])) < 1
    assert pypdf.PdfReader(io.BytesIO(eom_report.pdf(d))).pages
    ws = openpyxl.load_workbook(io.BytesIO(eom_report.xlsx(d)))["EOM Report"]
    assert "EOM COST & REVENUE REPORT" in ws["A1"].value


def test_hide_zero_lines_keeps_the_totals(demo):
    con, pid = demo[0], demo[1]
    a, b = eom_report.build(con, pid, hide_zero=True), eom_report.build(con, pid, hide_zero=False)
    assert len(a["cost"]["rows"]) < len(b["cost"]["rows"])
    assert abs(a["cost"]["total"]["eac"] - b["cost"]["total"]["eac"]) < 0.01
