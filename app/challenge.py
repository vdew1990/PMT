"""How challenging a client is: where the client sits on knowledge against difficulty, and what EPEC's PMs have recorded
about the client's PMs and the projects' complexity through each project's life (the assessment table).

Position: the client card places the client on a 5 x 5 grid. X is the client's knowledge of what they are buying (1 clueless
to 5 expert), Y how difficult they are to work with (1 easy to 5 difficult). An expert who is easy is the best client; a
clueless difficult client and an expert difficult client are both challenging, in different ways (they need educating and
holding to scope, or they push back on every detail and price).

Evidence: each assessment records, for one project and month, the client PM's difficulty (1 to 5) and the project's complexity
(1 to 5). A difficult PM on a simple project and an easy PM on a complex one both count, each as half of that month's figure.
A project's figure is the mean across its assessments; the client's evidence is the mean across its projects.

Challenge score (0 to 100) = the position score when there is no evidence yet, else half position and half evidence.
Position score = 60% difficulty + 40% lack of knowledge. Bands: under 25 easy, 25 to 44 manageable, 45 to 64 challenging, 65 and over very challenging.
"""
from collections import defaultdict

from . import db
from .workload import _norm

KNOWLEDGE = {1: "Clueless", 2: "Limited", 3: "Typical", 4: "Informed", 5: "Expert"}
DIFFICULTY = {1: "Easy", 2: "Fairly easy", 3: "Typical", 4: "Demanding", 5: "Difficult"}
W_DIFFICULTY, W_KNOWLEDGE = 0.6, 0.4


def _n(v):          # 1..5 as 0..1
    return (float(v) - 1) / 4


def band(score):
    if score is None:
        return None
    return "Easy" if score < 25 else "Manageable" if score < 45 else "Challenging" if score < 65 else "Very challenging"


def quadrant(knowledge, difficulty):
    """A short name for the spot on the grid, and what it asks of the PM."""
    if not knowledge or not difficulty:
        return None
    exp, clue = knowledge >= 4, knowledge <= 2
    hard, easy = difficulty >= 4, difficulty <= 2
    if exp and easy:
        return ("Ideal client", "Knows what they want and is easy to deal with.")
    if exp and hard:
        return ("Demanding expert", "Knows the detail and pushes back on scope, price and process.")
    if clue and hard:
        return ("Hands-on and hard", "Needs educating and also contests decisions: the most PM time.")
    if clue and easy:
        return ("Needs guidance", "Pleasant, but relies on EPEC to explain and steer.")
    if exp:
        return ("Capable", "Knows the work; the working relationship is typical.")
    if clue:
        return ("Needs education", "Limited knowledge; allow time to explain.")
    if hard:
        return ("Demanding", "Typical knowledge but hard to work with.")
    if easy:
        return ("Easy going", "Typical knowledge and easy to work with.")
    return ("Typical", "Neither knowledge nor difficulty stands out.")


def position_score(knowledge, difficulty):
    if difficulty and knowledge:
        return round(100 * (W_DIFFICULTY * _n(difficulty) + W_KNOWLEDGE * (1 - _n(knowledge))))
    if difficulty:
        return round(100 * _n(difficulty))
    if knowledge:
        return round(100 * (1 - _n(knowledge)))
    return None


def _month_figure(a):
    parts = [_n(v) for v in (a.get("pm_difficulty"), a.get("complexity")) if v]
    return sum(parts) / len(parts) if parts else None


def project_summary(rows):
    """One project's assessments (any order) as mean figures, the latest, and the direction since the first."""
    rows = sorted(rows, key=lambda r: r["month"])
    figs = [f for f in (_month_figure(r) for r in rows) if f is not None]
    pmd = [r["pm_difficulty"] for r in rows if r.get("pm_difficulty")]
    cx = [r["complexity"] for r in rows if r.get("complexity")]
    last = rows[-1] if rows else {}
    return dict(n=len(rows), score=round(100 * sum(figs) / len(figs)) if figs else None,
                pm_difficulty=round(sum(pmd) / len(pmd), 1) if pmd else None, complexity=round(sum(cx) / len(cx), 1) if cx else None,
                latest_pm_difficulty=pmd[-1] if pmd else None, latest_complexity=cx[-1] if cx else None, latest_month=last.get("month"),
                client_pm=last.get("client_pm"),
                trend=(None if len(figs) < 2 else round(100 * (figs[-1] - figs[0]))))


def summaries(con):
    """normalised client name -> the client's position, evidence and challenge score; and by project id, the project's own summary."""
    cards = {_norm(c["name"]): c for c in db.rows(con, "SELECT * FROM client")}
    projects = db.rows(con, "SELECT id, name, client_name, client_pm, archived_at FROM project WHERE COALESCE(is_template,0)=0")
    by_proj = defaultdict(list)
    for a in db.rows(con, "SELECT * FROM assessment ORDER BY month"):
        by_proj[a["project_id"]].append(a)
    per_project = {pid: project_summary(rs) for pid, rs in by_proj.items()}
    by_client = defaultdict(list)
    for p in projects:
        if p["client_name"]:
            by_client[_norm(p["client_name"])].append(p)
    out = {}
    for k in set(cards) | set(by_client):
        card = cards.get(k) or {}
        know, diff = card.get("knowledge"), card.get("complexity")
        pos = position_score(know, diff)
        ev_projects = [(p, per_project[p["id"]]) for p in by_client.get(k, []) if p["id"] in per_project and per_project[p["id"]]["score"] is not None]
        ev = round(sum(s["score"] for _, s in ev_projects) / len(ev_projects)) if ev_projects else None
        score = pos if ev is None else ev if pos is None else round((pos + ev) / 2)
        # the client's own PMs: how difficult each has been, and how complex the projects they ran with us were
        pms = defaultdict(lambda: dict(difficulty=[], complexity=[], projects=set()))
        for p in by_client.get(k, []):
            for a in by_proj.get(p["id"], []):
                name = (a.get("client_pm") or p.get("client_pm") or "").strip()
                if not name:
                    continue
                if a.get("pm_difficulty"):
                    pms[name]["difficulty"].append(a["pm_difficulty"])
                if a.get("complexity"):
                    pms[name]["complexity"].append(a["complexity"])
                pms[name]["projects"].add(p["name"])
        pm_list = sorted(({"name": n, "difficulty": round(sum(v["difficulty"]) / len(v["difficulty"]), 1) if v["difficulty"] else None,
                           "complexity": round(sum(v["complexity"]) / len(v["complexity"]), 1) if v["complexity"] else None,
                           "projects": sorted(v["projects"]), "assessments": max(len(v["difficulty"]), len(v["complexity"]))} for n, v in pms.items()),
                         key=lambda x: -(x["difficulty"] or 0))
        q = quadrant(know, diff)
        out[k] = dict(knowledge=know, difficulty=diff, position=pos, quadrant=q[0] if q else None, quadrant_note=q[1] if q else None,
                      evidence=ev, evidence_projects=len(ev_projects), score=score, band=band(score), client_pms=pm_list,
                      projects={p["id"]: per_project.get(p["id"]) for p in by_client.get(k, [])})
    return out, per_project
