"""Project complexity: the score, the band, and what the band asks of the team.

Source: EPEC Project Complexity Matrix (workbook sheets "Scoring Tool", "Complexity Matrix", "Project Resourcing Requirement").
Ten dimensions are scored 0 to 5 and added up (0 to 50). The total gives the band, and the band the typical PM level.

Two readings are kept apart on purpose:
  cx_baseline   the project director's score (every revision is kept, the latest is current)
  assessment    the PM's monthly score (scores_json, total, band) with the client's difficulty; the PM never sees the baseline
The workload page still works with a 1 to 5 complexity: `equivalent(total)` is that number (0-10 = 1, 11-20 = 2, 21-30 = 3, 31-40 = 4, 41-50 = 5).
"""
import json
import re

from . import db
from .services import Problem

# key, label, definition (as written in the workbook's Scoring Tool)
DIMENSIONS = [
    ("scope", "Scope clarity & volatility", "How defined is the scope? Likelihood/impact of change."),
    ("schedule", "Schedule complexity & duration", "Duration, logic density, interfaces, recovery difficulty."),
    ("cost", "Cost / Budget magnitude & control", "Budget size/volatility; forecasting rigor needed."),
    ("contracting", "Contracting complexity", "Commercial constructs, claims/notice regime, disputes potential."),
    ("risk", "Risk & uncertainty", "Unknowns, QRA need, integration with controls."),
    ("quality", "Quality assurance demand", "QA planning, audits/ITPs, handover complexity."),
    ("hse", "HSE criticality", "Safety in Design, incident potential, regulatory exposure."),
    ("stakeholders", "Stakeholder complexity & sensitivity", "Volume/seniority of stakeholders; political sensitivity."),
    ("procurement", "Procurement criticality", "Package criticality, market tightness, surveillance needs."),
    ("governance", "Integration & Governance maturity", "PMO/governance rigor needed across disciplines/projects."),
]
KEYS = [d[0] for d in DIMENSIONS]
# band upper limits (inclusive) as in the workbook: <=15 C1, <=25 C2, <=35 C3, above C4
BANDS = [
    dict(code="C1", name="C1 – Low", upto=15, typical="PM Level 1", min_level=1),
    dict(code="C2", name="C2 – Moderate", upto=25, typical="PM Level 2–3", min_level=2),
    dict(code="C3", name="C3 – High", upto=35, typical="PM Level 4", min_level=4),
    dict(code="C4", name="C4 – Very High / Portfolio", upto=50, typical="PM Level 4–5 (Director)", min_level=5),
]
# who sees the director's baseline: Project Director and above (Vincent, 31/10/2026). The PM and Senior PM assess independently and never see it.
DIRECTOR = re.compile(r"director|general manager|operations manager|head of|chief|\bcoo\b|executive|chair", re.I)


# PM level expected per dimension and band, as written in the workbook's Complexity Matrix sheet (the "(L1-2)" and "(L3)" notes): (lowest, highest).
# None where the matrix names no level (Scope clarity at C1 and C4).
MATRIX_LEVELS = {
    "scope": {"C1": None, "C2": (2, 3), "C3": (4, 4), "C4": None},
    "schedule": {"C1": (1, 2), "C2": (3, 3), "C3": (4, 4), "C4": (4, 5)},
    "cost": {"C1": (1, 2), "C2": (3, 3), "C3": (4, 4), "C4": (4, 5)},
    "contracting": {"C1": (1, 1), "C2": (2, 2), "C3": (3, 4), "C4": (4, 4)},
    "risk": {"C1": (1, 2), "C2": (3, 3), "C3": (4, 4), "C4": (4, 5)},
    "quality": {"C1": (1, 2), "C2": (3, 3), "C3": (4, 4), "C4": (4, 4)},
    "hse": {"C1": (1, 2), "C2": (3, 3), "C3": (4, 4), "C4": (4, 4)},
    "stakeholders": {"C1": (1, 1), "C2": (2, 3), "C3": (4, 4), "C4": (4, 5)},
    "procurement": {"C1": (1, 2), "C2": (3, 3), "C3": (4, 4), "C4": (4, 4)},
    "governance": {"C1": (1, 2), "C2": (3, 3), "C3": (4, 4), "C4": (4, 5)},
}


def dimension_band(score):
    """The band one dimension's 0 to 5 score points to: the total's band limits (15, 25, 35 of 50) are averages of 1.5, 2.5 and 3.5 a dimension."""
    return "C1" if score <= 1 else "C2" if score == 2 else "C3" if score == 3 else "C4"


def band_of(total):
    for b in BANDS:
        if total <= b["upto"]:
            return b
    return BANDS[-1]


def equivalent(total):
    """The 1 to 5 complexity the workload page and the client challenge use."""
    return max(1, min(5, -(-int(total) // 10))) if total else 1


def clean_scores(scores, need_all=True):
    """{key: {score 0..5, note}} from what the page sends. A baseline needs every dimension; the notes are optional."""
    out = {}
    for k in KEYS:
        v = (scores or {}).get(k)
        s, n = (v.get("score"), v.get("note")) if isinstance(v, dict) else (v, None)
        if s in (None, ""):
            if need_all:
                raise Problem("Score every dimension from 0 to 5: " + next(d[1] for d in DIMENSIONS if d[0] == k) + " has no score")
            continue
        try:
            s = int(float(s))
        except (TypeError, ValueError):
            raise Problem("Scores are whole numbers from 0 to 5")
        if not 0 <= s <= 5:
            raise Problem("Scores are whole numbers from 0 to 5")
        out[k] = dict(score=s, note=(n or "").strip() or None)
    return out


def total_of(scores):
    return sum(v["score"] for v in scores.values())


def _row(r):
    if not r:
        return None
    r = dict(r)
    r["scores"] = json.loads(r.pop("scores_json") or "{}")
    return r


def baseline(con, pid):
    """(current revision, all revisions newest first)."""
    rows = [_row(r) for r in db.rows(con, "SELECT * FROM cx_baseline WHERE project_id=? ORDER BY id DESC", (pid,))]
    return (rows[0] if rows else None), rows


def current_band(con, pid):
    b, _ = baseline(con, pid)
    return band_of(b["total"])["code"] if b else None


def save_baseline(con, pid, scores, summary, by):
    sc = clean_scores(scores)
    tot = total_of(sc); b = band_of(tot)
    rid = db.insert(con, "cx_baseline", dict(project_id=pid, scores_json=json.dumps(sc), total=tot, band=b["name"], summary=(summary or "").strip() or None, by=by))
    db.update(con, "project", pid, {"complexity": equivalent(tot)})
    return rid


def assessments(con, pid):
    out = []
    for r in db.rows(con, "SELECT * FROM assessment WHERE project_id=? ORDER BY month", (pid,)):
        r = dict(r)
        r["scores"] = json.loads(r.pop("scores_json") or "{}")     # an older assessment (one 1 to 5 number) has no dimensions
        out.append(r)
    return out


def save_assessment(con, pid, month, scores, client_pm, pm_difficulty, note, by):
    month = (month or "")[:7]
    if len(month) != 7 or month[4] != "-":
        raise Problem("Choose the month this assessment is for")
    sc = clean_scores(scores)
    tot = total_of(sc)
    diff = int(float(pm_difficulty)) if pm_difficulty not in (None, "") else None
    if diff is not None and not 1 <= diff <= 5:
        raise Problem("Client difficulty is 1 (easy) to 5 (difficult)")
    con.execute("DELETE FROM assessment WHERE project_id=? AND month=?", (pid, month))
    db.insert(con, "assessment", dict(project_id=pid, month=month, client_pm=(client_pm or "").strip() or None, pm_difficulty=diff, complexity=equivalent(tot),
                                      scores_json=json.dumps(sc), total=tot, band=band_of(tot)["name"], note=(note or "").strip() or None, by=by))
    if not baseline(con, pid)[0]:          # with no baseline yet the latest assessment still drives the 1 to 5 complexity, as before
        db.update(con, "project", pid, {"complexity": equivalent(tot)})
    return tot


def view(con, pid, role):
    """What this person may see. The director side (baseline, revisions, the comparison) is for director roles; anyone else sees only the assessments."""
    director = bool(DIRECTOR.search(role or ""))
    cur, revs = baseline(con, pid)
    rows = assessments(con, pid)
    out = dict(dimensions=[dict(key=k, label=l, definition=d) for k, l, d in DIMENSIONS], bands=BANDS, director=director, assessments=rows)
    if director:
        out["baseline"] = cur
        out["revisions"] = [dict(id=r["id"], total=r["total"], band=r["band"], summary=r["summary"], by=r["by"], created_at=r["created_at"]) for r in revs]
        if cur and rows:
            last = next((r for r in reversed(rows) if r.get("scores")), None)
            if last:
                out["compare"] = dict(month=last["month"], total=last["total"], band=last["band"], delta=last["total"] - cur["total"],
                                      by_dimension={k: last["scores"][k]["score"] - cur["scores"][k]["score"] for k in KEYS if k in last["scores"] and k in cur["scores"]})
    return out
