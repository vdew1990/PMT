"""The project library: finished projects, archived for the record, apart from the running ones.

Archiving keeps every record of the project and takes it off the project list. Its key figures at that moment (contract
value, final cost, margin, dates) are saved with it, so the library lists and searches them without recomputing each
project. A project archived before this existed gets its figures the first time the library lists it.
"""
import json
from datetime import datetime

from . import db, engine, identity, reports


def figures(con, pid):
    """The figures the library shows for a project, as they stand now."""
    res = engine.compute(con, pid)
    m = reports.project_margin(con, pid, res)
    t = res["total"]
    return dict(contract_original=round(m["revenue_original"], 2), contract_value=round(m["revenue_recognised"], 2),
                allowance=round(t["allowance"], 2), ctd=round(t["ctd"], 2), final_cost=round(m["eac"], 2),
                margin=round(m["gp_forecast"], 2), margin_pct=m["gp_forecast_pct"], margin_original_pct=m["gp_original_pct"],
                status_month=res["status_month"], taken=datetime.now().strftime("%Y-%m-%d"))


def archive(con, pid, value=True):
    if value:
        try:
            summ = json.dumps(figures(con, pid))
        except Exception:   # an empty or half set-up project still archives
            summ = None
        db.update(con, "project", pid, {"archived_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                        "archived_by": identity.current().get("name"), "archive_summary": summ})
    else:
        db.update(con, "project", pid, {"archived_at": None, "archived_by": None})
    return db.one(con, "SELECT id, archived_at, archived_by FROM project WHERE id=?", (pid,))


COLS = ("id, name, code, number, client_name, client_project_name, location, epec_pm, project_director, client_pm, contract_ref, "
        "project_start, project_end, status_date, archived_at, archived_by, archive_summary, lat, lon, project_type")


def listing(con):
    """Every archived project with its saved figures."""
    out = []
    for p in db.rows(con, f"SELECT {COLS} FROM project WHERE archived_at IS NOT NULL ORDER BY COALESCE(project_end, archived_at) DESC"):
        s = None
        try:
            s = json.loads(p.pop("archive_summary") or "null")
        except ValueError:
            pass
        if s is None:
            try:
                s = figures(con, p["id"])
                db.update(con, "project", p["id"], {"archive_summary": json.dumps(s)})
                con.commit()
            except Exception:
                s = {}
        p.update({k: s.get(k) for k in ("contract_original", "contract_value", "final_cost", "margin", "margin_pct", "margin_original_pct", "ctd")})
        out.append(p)
    return out
