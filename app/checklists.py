"""Checklists that read the project's own data: the pre-flight before Initialise, the monthly routine, and close-out.

Each item is { key, title, state, detail, page, params, manual }:
  state  done | todo | warn | info   (done = nothing left to do; warn = look before you go on; info = a fact, no judgement)
  page   the page that does the job (the front end links to it)
  manual a close-out item the PM ticks by hand (stored in the project settings as closeout_checks); the rest read the data.
Nothing here writes except `tick`.
"""
import json
from datetime import datetime

from . import allowance, db, engine, gates, pronto_raw, review


def _item(key, title, state, detail, page=None, params=None, manual=False, **extra):
    return dict(key=key, title=title, state=state, detail=detail, page=page, params=params or {}, manual=manual, **extra)


def _money(v):
    return f"${v:,.0f}"


# ---- before Initialise ----------------------------------------------------------------------------------------------------
def preflight(con, pid):
    """What to look at before the baseline is locked (Initialise cannot be undone from the page)."""
    ov = allowance.overview(con, pid)
    todo = ov["resources"]
    parked = sum(b["parked"] for b in ov["buckets"])
    no_line = [r for r in todo if r["state"] == "cost_no_line"]
    unfunded = [r for r in todo if r["state"] == "unfunded_line"]
    lines = db.scalar(con, "SELECT COUNT(*) FROM cbs_node WHERE project_id=? AND kind='line' AND active=1 AND COALESCE(origin,'') NOT IN ('ctc','wip') "
                           "AND name NOT LIKE '%(Unallocated)%'", (pid,))
    # the same count as the Project schedule page: a task that drives the whole span of a line, or a start or stop link that is not suspended
    driven = db.scalar(con, "SELECT COUNT(*) FROM (SELECT link_node_id n FROM programme_task WHERE project_id=? AND link_node_id IS NOT NULL AND COALESCE(layer,'internal')='internal' "
                            "UNION SELECT node_id FROM window_link WHERE project_id=? AND suspended=0)", (pid, pid))
    default_m = db.scalar(con, "SELECT COUNT(*) FROM cbs_node WHERE project_id=? AND kind='line' AND active=1 AND method IS NULL", (pid,))
    out = [
        _item("resources", "Resources with cost not yet linked to an allowance bucket", "todo" if todo else "done",
              (f"{len(no_line)} have cost and no line, {len(unfunded)} have a line without enough allowance." if todo else "Every resource with cost has a line with allowance."),
              "setup", {"step": "allowance"}, count=len(todo)),
        _item("parked", "Cost parked on unallocated pools", "warn" if parked > 1 else "done",
              (f"{_money(parked)} of cost sits on pools instead of lines. It counts in the forecast, but it is not forecast by line." if parked > 1 else "No cost is parked on pools."),
              "setup", {"step": "allowance"}, amount=round(parked, 2)),
        _item("schedule", "Cost lines that do not follow the project schedule", "info",
              f"{driven} of {lines} cost lines are linked to a schedule task. Lines that are not linked start and stop on the project dates." if lines else "No cost lines yet.",
              "programme", {}, count=max(0, lines - driven)),
        _item("methods", "Lines that will take a default forecast method", "info",
              f"{default_m} lines get the default for their kind (labour: burn-rate; subcontractors: at-budget; materials: at-commit; expenses: burn-rate). Change them line by line afterwards on Cost control." if default_m else "Every line already has a method.",
              "costcontrol", {}, count=default_m),
    ]
    return out


# ---- the monthly routine ---------------------------------------------------------------------------------------------------
def month_end(con, pid, month=None):
    res = engine.compute(con, pid)
    M = month or res["status_month"]
    proj = db.one(con, "SELECT initialised FROM project WHERE id=?", (pid,))
    items = []
    # 1 Pronto loads: transactions and timesheets are dated by the period they post to, so they show whether the month is in. (A PO's date is when it was
    # ordered, and CTD and variation reports carry no date, so those are not judged.)
    kinds = []
    for kind in ("transactions", "labour"):
        if db.scalar(con, f"SELECT COUNT(*) FROM {pronto_raw.RAW[kind][0]} WHERE project_id=?", (pid,)):
            last, _ = pronto_raw.as_of(con, pid, kind)
            kinds.append((kind, last))
    stale = [f"{k} to {fmt_d(l)}" for k, l in kinds if not l or l[:7] < M]
    if not kinds:
        items.append(_item("pronto", "Load this month's Pronto reports", "todo", "No Pronto transactions or timesheets are loaded yet.", "pronto"))
    else:
        items.append(_item("pronto", "Load this month's Pronto reports", "warn" if stale else "done",
                           ("Not yet up to " + M + ": " + ", ".join(stale) + ".") if stale else "Reaches the status month: " + ", ".join(f"{k} to {fmt_d(l)}" for k, l in kinds) + ".", "pronto"))
    # 2 accruals
    acc = db.one(con, "SELECT COUNT(*) n, COALESCE(SUM(amount),0) a FROM accrual WHERE project_id=? AND status='open'", (pid,))
    inv = db.scalar(con, "SELECT COUNT(*) FROM accrual WHERE project_id=? AND status='investigate'", (pid,))
    items.append(_item("accruals", "Check accruals", "warn" if inv else ("info" if acc["n"] else "done"),
                       f"{acc['n']} open accruals ({_money(acc['a'])}); {inv} to investigate." if (acc["n"] or inv) else "No open accruals.", "accruals"))
    # 3 review each line
    try:
        rv = review.month_review(con, pid, M)
        total, done = len(rv["rows"]), rv["reviewed"]
        diff = sum(1 for r in rv["rows"] if abs(r["variance"]) > 1 and not r.get("decision"))
        items.append(_item("review", "Review each line: did it land as planned?", "done" if total and done >= total else ("warn" if diff else "info"),
                           f"{done} of {total} lines have a decision; {diff} differ from the plan and have none." if total else "No lines to review.", "review", {"month": M}))
    except ValueError:
        items.append(_item("review", "Review each line: did it land as planned?", "info", "This month is outside the project months.", "review"))
    # 4 the PM's complexity and client read for the month (complexity.py): the director follows it on their dashboard
    a = db.one(con, "SELECT total, band, pm_difficulty FROM assessment WHERE project_id=? AND month=?", (pid, M))
    items.append(_item("assessment", "Assess the project's complexity and the client's difficulty", "done" if a else "todo",
                       (f"Logged: {a['total']} points" + (f" ({a['band']})" if a["band"] else "") + (f", client difficulty {a['pm_difficulty']}." if a["pm_difficulty"] else ".")) if a and a["total"] is not None
                       else ("Logged as one 1 to 5 rating; rescore the ten dimensions." if a else "Not logged for this month: score the ten dimensions and the client's difficulty."),
                       "complexity", {"tab": "monthly", "month": M}))
    # 5 the team for the month (team.py): joiners, leavers and what the team means for the project's risk
    from . import team as team_mod
    tm = team_mod.team(con, pid)
    rev = db.one(con, "SELECT rating, created_at FROM team_review WHERE project_id=? AND month=?", (pid, M))
    gap = tm["ahead"]["first_gap"]
    rating = {"red": "Red", "amber": "Amber", "green": "Green", "unknown": "not rated yet"}[tm["risk"]["rating"]]
    items.append(_item("team", "Confirm the team", "done" if rev else ("warn" if tm["risk"]["rating"] in ("red", "amber") else "todo"),
                       (f"Confirmed. Team risk {rating}." if rev else f"Team risk {rating}.") + (f" From {gap['month']}: {gap['reasons'][0]}." if gap else "") + ("" if rev else " Record any joiners and leavers, then confirm."),
                       "projectteam", {}))
    # 6 close
    snap = db.one(con, "SELECT id, created_at FROM snapshot WHERE project_id=? AND kind='eom' AND period=?", (pid, M))
    items.append(_item("close", "Close the month", "done" if snap else "todo",
                       f"Stored {snap['created_at'][:10]}. Close again to replace it." if snap else "Not closed yet: closing stores the position as the month-end snapshot.",
                       "reports", {"tab": "snapshots"}, action="close"))
    # 7 reports
    items.append(_item("reports", "Send the reports", "info" if snap else "todo", "EOM report to finance, PMR to the board, PSR to the client.", "eom"))
    return dict(month=M, initialised=bool(proj and proj["initialised"]), items=items)


def fmt_d(s):
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "no date"


# ---- close-out ------------------------------------------------------------------------------------------------------------------
MANUAL = [
    ("dlp", "Defects liability period", "Date the DLP ends and every defect closed out with the client."),
    ("gate7_paper", "Gate 7 paper: Approval of Project Completion", "Complete and file the paper (EPEC-PD-FR-0004)."),
    ("handover", "Handover documents delivered", "As-builts, manuals, test records and warranties handed to the client."),
    ("lessons", "Lessons learnt recorded", "The close-out for the estimator and the project review meeting."),
    ("archive", "Archive the project", "Move it to the project library once everything above is done."),
]


def _checks(con, pid):
    return db.project_settings(con, pid).get("closeout_checks", {})


def close_out(con, pid):
    items = []
    cl = db.rows(con, "SELECT * FROM claim WHERE project_id=? ORDER BY period", (pid,))
    unpaid = [c for c in cl if (c["status"] or "") != "paid" and not c["paid_date"]]
    items.append(_item("claims", "Client claims all paid", "done" if cl and not unpaid else ("todo" if cl else "info"),
                       (f"{len(cl)} claims raised, {len(unpaid)} not paid yet (last period {cl[-1]['period']})." if cl else "No progress claims in PMT."), "revenue"))
    ret = db.one(con, "SELECT COALESCE(SUM(retention),0) r FROM claim WHERE project_id=?", (pid,))["r"]
    items.append(_item("retention", "Client retention", "info", f"{_money(ret)} of retention recorded on the claims. Confirm the release with the client." if ret else "No retention recorded on the claims.", "revenue"))
    subs = db.rows(con, "SELECT s.id, s.name, s.status, COALESCE((SELECT SUM(retention - retention_release) FROM sub_claim c WHERE c.subcontract_id=s.id),0) held "
                        "FROM subcontract s WHERE s.project_id=?", (pid,))
    openx = [s for s in subs if (s["status"] or "active") not in ("closed", "complete", "completed")]
    held = sum(s["held"] for s in subs)
    items.append(_item("subs", "Subcontract final claims and retention released", "done" if subs and not openx and held < 1 else ("todo" if openx or held >= 1 else "info"),
                       (f"{len(openx)} of {len(subs)} subcontracts not closed; {_money(held)} retention still held." if subs else "No subcontracts."), "subcontracts"))
    var = db.scalar(con, "SELECT COUNT(*) FROM variation WHERE project_id=? AND client_status NOT IN ('Approved','Denied','Withdrawn') AND COALESCE(epec_status,'') <> 'Dropped'", (pid,))
    items.append(_item("variations", "Variations settled", "done" if not var else "todo", f"{var} variations are still open (not approved, denied, withdrawn or dropped)." if var else "Every variation is settled.", "variations"))
    acc = db.scalar(con, "SELECT COUNT(*) FROM accrual WHERE project_id=? AND status IN ('open','investigate')", (pid,))
    items.append(_item("accruals", "No open accruals", "done" if not acc else "todo", f"{acc} accruals are still open." if acc else "Every accrual has landed or been cancelled.", "accruals"))
    cur = gates.current(gates.log(con, pid))
    items.append(_item("gate", "Where the project stands on EPEC's gates", "info", (f"Currently {cur['label']} on {fmt_d(cur['date'])}." if cur else "No gate recorded."), "gates"))
    ticks = _checks(con, pid)
    for k, t, d in MANUAL:
        c = ticks.get(k) or {}
        items.append(_item(k, t, "done" if c.get("done") else "todo", d + (f" Ticked {fmt_d(c['date'])}" + (f" by {c['by']}" if c.get("by") else "") + "." if c.get("done") else ""),
                           "library" if k == "archive" else ("closeout" if k == "lessons" else "gates" if k == "gate7_paper" else None), manual=True))
    return dict(items=items)


def tick(con, pid, key, done, who=None, date=None):
    if key not in {k for k, _, _ in MANUAL}:
        raise ValueError("Unknown close-out item")
    s = db.project_settings(con, pid)
    c = s.setdefault("closeout_checks", {})
    if done:
        c[key] = dict(done=True, date=date or datetime.now().strftime("%Y-%m-%d"), by=who)
    else:
        c.pop(key, None)
    db.update(con, "project", pid, {"settings_json": json.dumps(s)})
    db.log(con, pid, "closeout.tick", f"{key} {'ticked' if done else 'cleared'}")
    return c
