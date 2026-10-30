"""Portfolio: the running projects side by side, for a project manager (the projects they manage) or a project
director (the program they direct), with the figures and monthly series the analytics need.

One row per running project (not archived, not a template), each computed by the engine as the dashboard does (the
engine caches per project version, so a portfolio of unchanged projects is quick). Who a project belongs to comes from
Project setup: EPEC project manager and EPEC project director. The page filters and sums; the server only reports.
"""
from . import challenge, complexity, db, gates, engine, reports, revenue, workload


def _pct(a, b):
    return (a / b) if b else None


def project_row(con, p):
    res = engine.compute(con, p["id"])
    t, grid, M = res["total"], res["grid"], res["status_month"]
    m = reports.project_margin(con, p["id"], res)
    rc = revenue.revenue_curve(con, p["id"], grid, M)
    G = len(grid)
    landed = [t["a"][i] + t["x"][i] for i in range(G)]
    lines = [r for r in res["rows"] if r["kind"] == "line"]
    tol = max(res.get("tolerance") or 1, 1)
    over = [r for r in lines if (r.get("contingency") or 0) < -tol]
    # time elapsed: start to end against the status date; cost progress: landed cost against EAC
    elapsed = None
    if p.get("project_start") and p.get("project_end") and p.get("status_date"):
        from datetime import date
        s, e, sd = (date.fromisoformat(p[k][:10]) for k in ("project_start", "project_end", "status_date"))
        if e > s:
            elapsed = min(1.0, max(0.0, (sd - s).days / (e - s).days))
    return dict(
        id=p["id"], name=p["name"], code=p.get("code"), number=p.get("number"), client=p.get("client_name"), location=p.get("location"),
        project_type=p.get("project_type"), mw=p.get("capacity_mw"), mwh=p.get("storage_mwh"), voltage=p.get("voltage"), kv=workload.max_kv(p.get("voltage")),
        lat=p.get("lat"), lon=p.get("lon"),
        complexity=p.get("complexity") or workload.suggest_complexity(m["revenue_recognised"], p.get("project_type"), p.get("voltage")),
        complexity_set=bool(p.get("complexity")), cx_band=complexity.current_band(con, p["id"]),
        pm=(p.get("epec_pm") or "").strip(), director=(p.get("project_director") or "").strip(),
        start=p.get("project_start"), end=p.get("project_end"), status_date=p.get("status_date"), status_month=M, initialised=bool(p.get("initialised")),
        contract_original=m["revenue_original"], contract_value=m["revenue_recognised"], claimed=rc["claimed_to_date"],
        allowance=t["allowance"], ctd=t["ctd"], acc=t["acc"], ctc=t["ctc"], eac=t["eac"], contingency=t["contingency"],
        margin_original=m["gp_original"], margin_original_pct=m["gp_original_pct"], margin=m["gp_forecast"], margin_pct=m["gp_forecast_pct"],
        erosion=m["erosion"], risk_provision=m["cost_forecast"] - m["eac"], lines=len(lines), lines_over=len(over), overrun=sum(r["contingency"] for r in over),
        spent_pct=_pct(t["ctd"] + t["acc"], t["eac"]), elapsed_pct=elapsed,
        # monthly series by calendar month: cost landed (actual + accrued) up to the status month, forecast after it; revenue
        months={grid[i]: [round(landed[i], 2) if grid[i] <= M else 0.0, round(t["f"][i], 2), round(rc["series"][i]["actual"] + rc["series"][i]["planned"], 2)]
                for i in range(G) if landed[i] or t["f"][i] or rc["series"][i]["actual"] or rc["series"][i]["planned"]},
    )


def run(con):
    """projects: the projects that hold data (child and stand-alone), so totals never count a parent and its children
    twice; parents: the parent projects, each the sum of its children (for the nesting and a director's program)."""
    out, parents, errors = [], [], []
    allp = db.rows(con, "SELECT * FROM project WHERE archived_at IS NULL AND COALESCE(is_template,0)=0 ORDER BY name")
    names = {p["id"]: p for p in allp}
    summ, per_project = challenge.summaries(con)
    stand = gates.standings(con)
    phases = gates.phase_standings(con)
    for p in allp:
        try:
            r = project_row(con, p)
        except Exception as e:   # a half set-up project must not break the portfolio
            errors.append(dict(id=p["id"], name=p["name"], error=str(e)))
            continue
        r["is_parent"] = bool(p.get("is_parent"))
        # how challenging this project's client is, and what the PMs last recorded for the client PM and the project's complexity
        cs = summ.get(workload._norm(p.get("client_name"))) or {}
        a = per_project.get(p["id"]) or {}
        r.update(client_challenge=cs.get("score"), client_band=cs.get("band"), client_quadrant=cs.get("quadrant"), client_knowledge=cs.get("knowledge"),
                 client_difficulty=cs.get("difficulty"), client_pm_name=a.get("client_pm") or p.get("client_pm"), client_pm_difficulty=a.get("latest_pm_difficulty"),
                 assessed_complexity=a.get("latest_complexity"), assessed_month=a.get("latest_month"), assessment_trend=a.get("trend"))
        g = stand.get(p["id"]) or {}
        r.update(gate=g.get("gate"), gate_label=g.get("label"), gate_phase=g.get("phase"), gate_stage=g.get("stage"), gate_date=g.get("date"), delivery_phase=(phases.get(p["id"]) or {}).get("phase"))
        par = names.get(p.get("parent_project_id"))
        r["parent_id"], r["parent_name"] = (par["id"], par["name"]) if par else (None, None)
        # a child with no director named takes its parent's: the director's program covers the parent's children
        if par and not r["director"]:
            r["director"] = (par.get("project_director") or "").strip()
        (parents if r["is_parent"] else out).append(r)
    people = sorted({x for r in out + parents for x in (r["pm"], r["director"]) if x})
    return dict(projects=out, parents=parents, people=people, pms=sorted({r["pm"] for r in out if r["pm"]}),
                directors=sorted({r["director"] for r in out + parents if r["director"]}), errors=errors)


def rollup(con, ids):
    """The CBS of several projects lumped together (a portfolio or a program), with each project's share per row."""
    from . import linking
    kids = []
    for i in ids:
        p = db.one(con, "SELECT * FROM project WHERE id=?", (i,))
        if not p:
            continue
        # a parent in the list stands for its children (never count both)
        kids.extend(linking.children(con, p["id"]) if p.get("is_parent") else [p])
    seen, uniq = set(), []
    for k in kids:
        if k["id"] not in seen:
            seen.add(k["id"]); uniq.append(k)
    res = linking.combine(con, uniq)
    return res
