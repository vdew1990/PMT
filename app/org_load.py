"""Loading the people of the org chart, and keeping names straight: duplicates, other spellings, merging.

The load only records what the chart says (people_seed.py): name, business title, reporting line, group, engagement, serving notice. The ECF role comes from the
business title (the allowable titles table) or, in a team list, from the grade word on the chart. It never sets a PM level (a competency, set per person), an
individual's ECF level (the chart does not state it), or contact details. Where a person already exists, only blank fields are filled.
"""
import json
import re

from . import db, ecf, people_seed
from .services import Problem
from .workload import _norm

PRIORITY = ["pd"]          # where one title belongs to two roles ("Project Director" is also a Business Unit Manager title) the first listed wins (Vincent: level 8)


def _t(s):
    return (s or "").replace("–", "-").replace("—", "-").strip().lower()


def _index(con):
    roles = ecf.roles(con)
    by_title, by_name = {}, {}
    for r in roles:
        for t in r["titles"]:
            by_title.setdefault(_t(t), []).append(r)
        by_name.setdefault(_t(r["name"]), r)
    return roles, by_title, by_name


def classify(con, title, grade_key=None, idx=None):
    """{ecf_role, how, on_list}: by the business title, else the ECF role's own name, else the grade word on the chart."""
    roles, by_title, by_name = idx or _index(con)
    key = _t(title)
    if key and key in by_title:
        c = by_title[key]
        r = next((x for k in PRIORITY for x in c if x["key"] == k), c[0])
        return dict(ecf_role=r["key"], how="title", on_list=True)
    if key and key in by_name:
        r = by_name[key]
        return dict(ecf_role=r["key"], how="role name", on_list=not r["titles"])     # a role with no allowed titles can only go by its name
    if grade_key:
        return dict(ecf_role=grade_key, how="grade on the chart", on_list=None)
    return dict(ecf_role=None, how=None, on_list=None)


def _pmt_role(ecf_role):
    return {"pd": "Project Director", "spm": "Project Manager", "pm": "Project Manager"}.get(ecf_role, "Employee")


# ---- names ----------------------------------------------------------------------------------------------------------------------
def _tokens(name):
    return [t for t in re.sub(r"\([^)]*\)", " ", (name or "").lower()).replace("-", " ").split() if t]


def _edit1(x, y):
    """Are the two words one letter apart (one changed, added or missing)?"""
    if abs(len(x) - len(y)) > 1:
        return False
    if len(x) == len(y):
        return sum(1 for p, q in zip(x, y) if p != q) == 1
    s, l = (x, y) if len(x) < len(y) else (y, x)
    i = 0
    while i < len(s) and s[i] == l[i]:
        i += 1
    return s[i:] == l[i + 1:]


def similar(a, b):
    """Could these two names be the same person? Same surname and first names that are one another's start (Brad, Bradley), or one letter apart (Thomson, Thompson)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb or _norm(a) == _norm(b):
        return False
    if len(ta) < 2 or len(tb) < 2:
        return False
    fa, fb, la, lb = ta[0], tb[0], ta[-1], tb[-1]

    def near(x, y):
        if x == y:
            return True
        return len(x) >= 4 and len(y) >= 4 and _edit1(x, y)
    first_ok = fa == fb or (min(len(fa), len(fb)) >= 3 and (fa.startswith(fb) or fb.startswith(fa))) or near(fa, fb)
    last_ok = near(la, lb) or la in tb or lb in ta        # "Larissa Oliveira" against "Larrissa Cordeiro de Oliveira"
    return first_ok and last_ok


def _aliases(p):
    try:
        return json.loads(p.get("aliases_json") or "[]")
    except ValueError:
        return []


def find(people, name):
    """An existing person with this name or one of their other spellings."""
    n = _norm(name)
    for p in people:
        if _norm(p["name"]) == n or any(_norm(a) == n for a in _aliases(p)):
            return p
    return None


def duplicates(con):
    people = db.rows(con, "SELECT * FROM person ORDER BY name")
    out = []
    for i, a in enumerate(people):
        for b in people[i + 1:]:
            if similar(a["name"], b["name"]) and not any(_norm(b["name"]) == _norm(x) for x in _aliases(a)) and not any(_norm(a["name"]) == _norm(x) for x in _aliases(b)):
                out.append(dict(a=dict(id=a["id"], name=a["name"], role=a["role"], title=a.get("business_title"), ecf_role=a.get("ecf_role")),
                                b=dict(id=b["id"], name=b["name"], role=b["role"], title=b.get("business_title"), ecf_role=b.get("ecf_role"))))
    return out


def merge(con, keep_id, drop_id):
    """Two records of one person become one: the dropped name is kept as another spelling, roles, levels and team entries move across, project fields that name them are updated."""
    if keep_id == drop_id:
        raise Problem("Choose two different people")
    keep, drop = db.one(con, "SELECT * FROM person WHERE id=?", (keep_id,)), db.one(con, "SELECT * FROM person WHERE id=?", (drop_id,))
    if not keep or not drop:
        raise Problem("No such person")
    fill = {k: drop[k] for k in ("role", "pm_level", "fte", "base", "lat", "lon", "reports_to", "email", "notes", "employee_code", "function", "phone", "ecf_role", "ecf_level", "business_title",
                                 "leaving_date", "employment_status", "engagement") if keep.get(k) in (None, "") and drop.get(k) not in (None, "")}
    aliases = list(dict.fromkeys(_aliases(keep) + [drop["name"]] + _aliases(drop)))
    if fill:
        db.update(con, "person", keep_id, fill)
    db.update(con, "person", keep_id, {"aliases_json": json.dumps([a for a in aliases if _norm(a) != _norm(keep["name"])])})
    con.execute("UPDATE team_slot SET person_id=? WHERE person_id=?", (keep_id, drop_id))
    for table, col in (("person_role", "role_key"), ("person_dimension", "dim_key")):
        have = {r[col] for r in db.rows(con, f"SELECT {col} FROM {table} WHERE person_id=?", (keep_id,))}
        for r in db.rows(con, f"SELECT id, {col} FROM {table} WHERE person_id=?", (drop_id,)):
            if r[col] in have:
                con.execute(f"DELETE FROM {table} WHERE id=?", (r["id"],))
            else:
                con.execute(f"UPDATE {table} SET person_id=? WHERE id=?", (keep_id, r["id"]))
    n = 0
    for col in ("epec_pm", "project_director"):
        for p in db.rows(con, f"SELECT id, {col} v FROM project WHERE {col} IS NOT NULL"):
            if _norm(p["v"]) == _norm(drop["name"]):
                db.update(con, "project", p["id"], {col: keep["name"]}); n += 1
    con.execute("UPDATE person SET reports_to=? WHERE reports_to=?", (keep["name"], drop["name"]))
    con.execute("DELETE FROM person WHERE id=?", (drop_id,))
    return dict(kept=keep["name"], merged=drop["name"], projects_updated=n)


# ---- the org chart load ---------------------------------------------------------------------------------------------------------
def preview(con):
    people = db.rows(con, "SELECT * FROM person")
    idx = _index(con)
    new, exist, near, off_list, no_title, graded, ranged, notice, contractors = [], [], [], [], [], [], [], [], []
    for name, title, reports, group, o in people_seed.S:
        c = classify(con, title, o.get("ecf"), idx)
        ex = find(people, name)
        (exist if ex else new).append(name)
        if not ex:
            for p in people:
                if similar(name, p["name"]):
                    near.append(dict(chart=name, existing=p["name"]))
        if title and c["ecf_role"] is None:
            off_list.append(dict(name=name, title=title, why="not matched to an ECF role"))
        elif title and c["on_list"] is False:
            off_list.append(dict(name=name, title=title, why=f"{next(r['name'] for r in idx[0] if r['key'] == c['ecf_role'])} by name; not an allowed title"))
        if not title and not o.get("ecf"):
            no_title.append(name)
        if c["how"] == "grade on the chart":
            graded.append(name)
        r = next((x for x in idx[0] if x["key"] == c["ecf_role"]), None)
        if r and r["level_to"] and r["level_to"] != r["level_from"]:
            ranged.append(dict(name=name, role=r["name"], levels=f"{r['level_from']} to {r['level_to']}"))
        if o.get("status") == "serving notice":
            notice.append(name)
        if o.get("engagement"):
            contractors.append(dict(name=name, engagement=o["engagement"]))
    return dict(source=people_seed.SOURCE, people=len(people_seed.S), to_create=len(new), already_there=len(exist), possible_duplicates=near, titles_to_review=off_list, no_title=no_title,
                from_grade_word=graded, level_to_confirm=ranged, serving_notice=notice, engagement=contractors)


def load(con):
    people = db.rows(con, "SELECT * FROM person")
    idx = _index(con)
    created = filled = 0
    for name, title, reports, group, o in people_seed.S:
        c = classify(con, title, o.get("ecf"), idx)
        row = dict(name=name, role=_pmt_role(c["ecf_role"]), business_title=title, ecf_role=c["ecf_role"], reports_to=reports, function=group, engagement=o.get("engagement"),
                   employment_status=o.get("status"), fte=1.0, active=1, notes=f"From the {people_seed.SOURCE}")
        ex = find(people, name)
        if not ex:
            db.insert(con, "person", {k: v for k, v in row.items() if v is not None})
            created += 1
            continue
        fill = {k: v for k, v in row.items() if k not in ("name", "role", "fte", "active", "notes") and v is not None and ex.get(k) in (None, "")}
        if fill:
            db.update(con, "person", ex["id"], fill); filled += 1
    return dict(created=created, filled=filled)
