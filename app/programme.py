"""Optional schedule import.

Supported: MS Project XML (File, Save As, XML), an Excel or CSV export of the task list, and a PDF print of the
schedule (best effort: tasks are read from text lines that carry a start and a finish date, so the preview must be
checked). Native .mpp is read through MPXJ (Java); XML, Excel, CSV and PDF need nothing extra.

The tasks are only a starting point. Each can be linked to a claim schedule item and/or a CBS line; applying the links
copies the dates across, and every date can still be edited by hand afterwards.
"""
import csv
import json
import re
import subprocess
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

import openpyxl

from . import db

MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
DATE_RES = [
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b"),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})"),
    re.compile(r"\b(\d{1,2})[ -]([A-Za-z]{3})[a-z]*[ -,]*(\d{2,4})\b"),
]


def parse_date(v):
    if v in (None, ""):
        return None
    if isinstance(v, (datetime, date)):
        return db.iso(v)
    s = str(v).strip()
    s = re.sub(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+", "", s, flags=re.I)
    m = DATE_RES[1].search(s)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    m = DATE_RES[0].search(s)
    if m:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        y += 2000 if y < 100 else 0
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    m = DATE_RES[2].search(s)
    if m and m[2].lower()[:3] in MONTHS:
        y = int(m[3]); y += 2000 if y < 100 else 0
        try:
            return date(y, MONTHS[m[2].lower()[:3]], int(m[1])).isoformat()
        except ValueError:
            return None
    return None


def _first_date(text):
    out = []
    for rx in DATE_RES:
        for m in rx.finditer(text):
            d = parse_date(m.group(0))
            if d:
                out.append((m.start(), m.end(), d))
    out.sort()
    return out


# ---- readers ---------------------------------------------------------------
def read_xml(path):
    root = ET.parse(path).getroot()
    loc = lambda e: e.tag.split("}")[-1]
    tasks = []
    for t in root.iter():
        if loc(t) != "Task":
            continue
        d = {loc(c): (c.text or "").strip() for c in t}
        name = d.get("Name")
        if not name or d.get("UID") == "0":
            continue
        s, f = parse_date(d.get("Start")), parse_date(d.get("Finish"))
        if not s:
            continue
        tasks.append(dict(wbs=d.get("WBS") or d.get("OutlineNumber"), name=name, start_date=s, finish_date=f or s,
                          pct=float(d.get("PercentComplete") or 0) / 100, outline=int(d.get("OutlineLevel") or 1),
                          summary=1 if d.get("Summary") == "1" else 0, milestone=1 if d.get("Milestone") == "1" else 0))
    return tasks


HEAD = {
    "name": ["taskname", "name", "activity", "activityname", "description", "task"],
    "start": ["start", "startdate", "plannedstart", "baselinestart"],
    "finish": ["finish", "finishdate", "end", "enddate", "plannedfinish", "baselinefinish"],
    "wbs": ["wbs", "id", "activityid", "outlinenumber"],
    "pct": ["complete", "completed", "percentcomplete", "pctcomplete", "complete"],
    "outline": ["outlinelevel", "level"],
}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower().replace("%", "percent"))


def read_table(rows):
    rows = list(rows)
    hi, idx = None, {}
    for i, row in enumerate(rows[:25]):
        keys = [_norm(c) for c in row]
        m = {}
        for field, syns in HEAD.items():
            for s in syns:
                if s in keys:
                    m[field] = keys.index(s)
                    break
        if {"name", "start", "finish"} <= set(m):
            hi, idx = i, m
            break
    if hi is None:
        raise ValueError("Could not find Task Name, Start and Finish columns in this file")
    out = []
    for row in rows[hi + 1:]:
        g = lambda k: row[idx[k]] if k in idx and idx[k] < len(row) else None
        name = str(g("name") or "").strip()
        s, f = parse_date(g("start")), parse_date(g("finish"))
        if not name or not s:
            continue
        pct = g("pct")
        try:
            pct = float(str(pct).replace("%", "")) if pct not in (None, "") else 0
            pct = pct / 100 if pct > 1 else pct
        except ValueError:
            pct = 0
        lead = len(str(g("name"))) - len(str(g("name")).lstrip())
        out.append(dict(wbs=str(g("wbs") or "") or None, name=name, start_date=s, finish_date=f or s, pct=pct,
                        outline=int(float(g("outline") or (lead // 2 + 1))), summary=0, milestone=1 if (f or s) == s else 0))
    return out


def read_excel(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = [list(ws.iter_rows(values_only=True)) for ws in wb.worksheets]
    finally:
        wb.close()              # Windows will not delete a file that is still open
    last = None
    for rows in sheets:
        try:
            return read_table(iter(rows))
        except ValueError as e:
            last = e
    raise last or ValueError("No task list found")


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return read_table(csv.reader(f))


def read_pdf(path):
    try:
        text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=60).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        text = ""
    if not text.strip():
        try:
            from pypdf import PdfReader
            text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"Could not read text from this PDF ({e}). Scanned PDFs are not supported; export the project schedule to XML or Excel.")
    tasks = []
    for line in text.splitlines():
        ds = _first_date(line)
        if not ds:
            continue
        s = ds[0]
        f = ds[1] if len(ds) > 1 else ds[0]
        head = re.sub(r"\s+(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\s*$", "", line[: s[0]], flags=re.I)
        head = re.sub(r"\b\d+(\.\d+)?\s*(d|days?|w|wks?|mons?|h|hrs?)\b\??", " ", head, flags=re.I)
        m = re.match(r"^\s*((?:WBS-)?\d[\d.\-]*)\s+(.*)$", head, flags=re.I)
        wbs, name = (m.group(1), m.group(2)) if m else (None, head)
        name = re.sub(r"\s{2,}", " ", name).strip(" -|:•")
        if len(name) < 3 or not re.search(r"[A-Za-z]{3}", name):
            continue
        lead = len(head) - len(head.lstrip())
        tasks.append(dict(wbs=wbs, name=name, start_date=s[2], finish_date=f[2], pct=0, outline=max(1, lead // 3 + 1), summary=0,
                          milestone=1 if f[2] == s[2] else 0))
    if not tasks:
        raise ValueError("No tasks with start and finish dates were found in this PDF. Export the schedule to XML or Excel instead.")
    return tasks


def read_mpp(path):
    """A native MS Project file (.mpp), read with MPXJ (Java) and passed through the XML reader as MSPDI.
    Needs Java and the mpxj Python package (requirements.txt); without them the message says how to export XML instead."""
    fallback = " Or in MS Project use File, Save As, XML (or export the task list to Excel) and upload that."
    try:
        import jpype
        import jpype.imports
        import mpxj  # noqa: F401  (puts the MPXJ jars on the class path)
    except Exception as e:
        raise ValueError("Reading .mpp files needs the mpxj package (pip install mpxj). Start PMT with PMT.exe or run.bat once so it is installed." + fallback) from e
    try:
        if not jpype.isJVMStarted():
            from . import javaenv
            home = javaenv.ensure()      # uses the Java on this PC, or fetches a private copy the first time
            os.environ["JAVA_HOME"] = str(home)
            jvm = javaenv.jvm_path(home)
            jpype.startJVM(jvm) if jvm else jpype.startJVM()
        from org.mpxj.mspdi import MSPDIWriter
        from org.mpxj.reader import UniversalProjectReader
    except Exception as e:
        raise ValueError(f"Reading .mpp files needs Java, and it could not be set up automatically: {e}." + fallback) from e
    import tempfile
    try:
        proj = UniversalProjectReader().read(str(path))
    except Exception as e:
        raise ValueError("MS Project could not be read from this .mpp file (" + str(e).splitlines()[0][:120] + ")." + fallback) from e
    if proj is None:
        raise ValueError("This file is not a readable MS Project file." + fallback)
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as t:
        out = t.name
    try:
        MSPDIWriter().write(proj, out)
        return read_xml(out)
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


def parse(path, filename):
    ext = Path(filename).suffix.lower()
    if ext == ".mpp":
        return "mpp", read_mpp(path)
    if ext == ".xml":
        return "xml", read_xml(path)
    if ext in (".xlsx", ".xlsm"):
        return "excel", read_excel(path)
    if ext == ".csv":
        return "csv", read_csv(path)
    if ext == ".pdf":
        return "pdf", read_pdf(path)
    raise ValueError("Upload MS Project XML, an Excel or CSV task list, or a PDF of the project schedule")


# ---- matching ----------------------------------------------------------------
STOP = {"the", "and", "of", "for", "to", "a", "in", "on", "at", "works", "work", "install", "installation", "supply", "complete", "completion", "stage", "ssy", "nsy"}


def _tok(s):
    return {w for w in re.findall(r"[a-z0-9]+", str(s or "").lower()) if w not in STOP and len(w) > 2}


def _score(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b)) * (len(a & b) / len(a | b)) ** 0.25


def _candidates(con, pid):
    """Name matches between the internal schedule's tasks and the claim items / CBS lines, for the fields a task has not linked yet."""
    items = [i for i in db.rows(con, "SELECT id, ref, description FROM contract_item WHERE project_id=? AND kind!='variation'", (pid,))
             if not db.scalar(con, "SELECT COUNT(*) FROM contract_item WHERE parent_id=?", (i["id"],))]
    nodes = db.rows(con, "SELECT id, code, name, COALESCE(function,'') f, COALESCE(scope,'') s, kind FROM cbs_node WHERE project_id=? AND active=1", (pid,))
    it_tok = [(i, _tok(i["description"])) for i in items]
    nd_tok = [(n, _tok(f"{n['name']} {n['f']} {n['s']}")) for n in nodes]
    out = []
    for t in db.rows(con, "SELECT * FROM programme_task WHERE project_id=? AND COALESCE(layer,'internal')='internal' ORDER BY seq", (pid,)):
        tk = _tok(t["name"])
        base = dict(task_id=t["id"], wbs=t["wbs"], task=t["name"], start=t["start_date"], finish=t["finish_date"])
        if not t["link_item_id"] and it_tok:
            sc, best = max(((_score(tk, tt), i) for i, tt in it_tok), key=lambda x: x[0])
            if sc >= 0.6:
                out.append(dict(base, kind="item", target_id=best["id"], target_code=best["ref"], target_name=best["description"], score=round(sc, 2)))
        if not t["link_node_id"] and nd_tok:
            sc, best = max(((_score(tk, tt), n) for n, tt in nd_tok), key=lambda x: x[0])
            if sc >= 0.6:
                out.append(dict(base, kind="node", target_id=best["id"], target_code=best["code"], target_name=best["name"], score=round(sc, 2)))
    return out


REJECTED = "programme_suggest_rejected"     # project settings: suggestions the user turned down, by task WBS and name, so a re-upload does not offer them again


def _key(s):
    return f"{s['wbs'] or ''}|{s['task']}|{s['kind']}|{s['target_id']}"


def suggestions(con, pid):
    """Links the schedule suggests by name match. Nothing is linked until the user accepts them (one by one or all)."""
    rejected = set(db.project_settings(con, pid).get(REJECTED) or [])
    return [s for s in _candidates(con, pid) if _key(s) not in rejected]


def _picked(con, pid, picks):
    cur = suggestions(con, pid)
    if picks is None:
        return cur
    want = {(int(p["task_id"]), p["kind"], int(p["target_id"])) for p in picks if p.get("task_id") and p.get("kind") in ("item", "node") and p.get("target_id")}
    return [s for s in cur if (s["task_id"], s["kind"], s["target_id"]) in want]


def accept_suggestions(con, pid, picks=None):
    """Link the accepted suggestions (picks: [{task_id, kind, target_id}]; None = accept all). Only current suggestions are linked,
    so a task linked meanwhile is not overwritten. The dates then follow the schedule as for any link."""
    n_upd = 0
    picked = _picked(con, pid, picks)
    for s in picked:
        db.update(con, "programme_task", s["task_id"], {"link_item_id" if s["kind"] == "item" else "link_node_id": s["target_id"]})
        n_upd += 1
    clear_link_lost(con, pid, [s["target_id"] for s in picked if s["kind"] == "node"])
    warnings = []
    if n_upd:
        warnings = apply(con, pid, targets=("costs",)).get("warnings", [])
        apply(con, pid, targets=("claims",))
    return {"linked": n_upd, "warnings": warnings, "suggestions": suggestions(con, pid)}


def reject_suggestions(con, pid, picks=None):
    """Turn suggestions down (None = all): they are not offered again, also after a re-upload of the same tasks."""
    got = _picked(con, pid, picks)
    st = db.project_settings(con, pid)
    st[REJECTED] = sorted(set(st.get(REJECTED) or []) | {_key(s) for s in got})
    db.update(con, "project", pid, {"settings_json": json.dumps(st)})
    return {"rejected": len(got), "suggestions": suggestions(con, pid)}


def suggest(con, pid):
    """The "Link by name" button: link every current suggestion at once. Returns the number of tasks linked."""
    got = suggestions(con, pid)
    for s in got:
        db.update(con, "programme_task", s["task_id"], {"link_item_id" if s["kind"] == "item" else "link_node_id": s["target_id"]})
    clear_link_lost(con, pid, [s["target_id"] for s in got if s["kind"] == "node"])
    return len({s["task_id"] for s in got})


def save_window_links(con, pid, layer):
    """Before a schedule re-upload deletes the layer's tasks (and, by cascade, every window_link on them): the links with the
    WBS and name of their task, so they can be put back on the new tasks."""
    return db.rows(con, "SELECT w.node_id, w.role, w.edge, w.suspended, t.wbs, t.name AS task, n.code, n.name, n.start_date, n.end_date "
                        "FROM window_link w JOIN programme_task t ON t.id=w.task_id JOIN cbs_node n ON n.id=w.node_id "
                        "WHERE w.project_id=? AND COALESCE(t.layer,'internal')=? ORDER BY w.node_id, w.role", (pid, layer))


def flag_link_lost(con, pid, lost):
    """Q13: mark every line in `lost` (from a schedule re-upload) as having lost its schedule item. The flag is a column on
    the line, so it syncs to every copy through the change log, and it stays until the line is linked again or the flag is
    dismissed. Several lost items on one line (Start and Stop) are kept together, newest last."""
    if not lost:
        return
    from . import changelog
    today = date.today().isoformat()
    by_node = {}
    for x in lost:
        by_node.setdefault(x["node_id"], []).append(dict(date=today, task=x.get("task"), wbs=x.get("wbs"), role=x.get("role")))
    for nid, new in sorted(by_node.items()):
        have = link_lost(db.scalar(con, "SELECT schedule_link_lost FROM cbs_node WHERE id=?", (nid,), None)) or []
        with changelog.via("Schedule re-upload: schedule item gone"):
            db.update(con, "cbs_node", nid, {"schedule_link_lost": json.dumps(have + new)})
    db.bump(con, pid)


def link_lost(raw):
    """The stored flag as a list of {date, task, wbs, role}, or None when the line is not flagged."""
    if not raw:
        return None
    try:
        v = json.loads(raw)
    except (TypeError, ValueError):
        return [dict(date=None, task=str(raw), wbs=None, role=None)]
    return v if isinstance(v, list) and v else None


def clear_link_lost(con, pid, nids, why="Linked to the schedule again"):
    """Take the lost-link flag off these lines (a new link to the schedule, or the user dismissed it). Returns how many were cleared."""
    from . import changelog
    n = 0
    for nid in {int(x) for x in nids if x}:
        if db.scalar(con, "SELECT schedule_link_lost FROM cbs_node WHERE id=? AND project_id=?", (nid, pid), None):
            with changelog.via(why):
                db.update(con, "cbs_node", nid, {"schedule_link_lost": None})
            n += 1
    if n:
        db.bump(con, pid)
    return n


def restore_window_links(con, pid, layer, saved):
    """After the re-upload: each saved link goes back on the new task with the same WBS and name, else the same name alone
    (the key the task links use), with its edge and suspended (typed override) state. A link whose task is gone is dropped,
    not re-pointed: the line keeps its current dates as typed values. Returns the lines that lost a link."""
    new = db.rows(con, "SELECT id, wbs, name FROM programme_task WHERE project_id=? AND COALESCE(layer,'internal')=? ORDER BY seq", (pid, layer))
    by_key, by_name = {}, {}
    for t in new:
        by_key.setdefault((t["wbs"], t["name"]), t["id"])
        by_name.setdefault(t["name"], t["id"])
    lost = []
    for w in saved:
        tid = by_key.get((w["wbs"], w["task"])) or by_name.get(w["task"])
        if tid:
            db.insert(con, "window_link", dict(project_id=pid, node_id=w["node_id"], role=w["role"], task_id=tid, edge=w["edge"], suspended=w["suspended"]))
            continue
        lost.append(dict(kind="window", node_id=w["node_id"], code=w["code"], name=w["name"], role=w["role"], task=w["task"], wbs=w["wbs"],
                         start=w["start_date"], end=w["end_date"]))
    from . import changelog
    for nid in sorted({x["node_id"] for x in lost}):
        n = db.one(con, "SELECT window_months FROM cbs_node WHERE id=?", (nid,))
        if n and n["window_months"]:          # a duration only lasts while a schedule item drives the other end: both dates are now static
            with changelog.via("Schedule re-upload: schedule item gone"):
                db.update(con, "cbs_node", nid, {"window_months": None})
    for x in lost:
        db.log(con, pid, "Schedule item gone", f"{x['code']} {x['name']}: {x['role']} no longer follows '{x['task']}' (WBS {x['wbs'] or '-'}); "
                                               f"the window {x['start'] or '-'} to {x['end'] or '-'} is kept as typed dates")
    return lost


def apply(con, pid, targets=("claims", "costs"), only_empty=False):
    """Copy dates from linked tasks. Several tasks on one target widen it to the earliest start and latest finish."""
    tasks = db.rows(con, "SELECT * FROM programme_task WHERE project_id=? AND COALESCE(layer,'internal')='internal'", (pid,))
    res = {"items": 0, "nodes": 0}
    if "claims" in targets:
        # a claim line follows the client facing (upstream) tasks linked to it; with none, the internal tasks linked to it as before
        up = db.rows(con, "SELECT * FROM programme_task WHERE project_id=? AND layer='upstream' AND link_item_id IS NOT NULL", (pid,))
        agg, from_up = {}, set()
        for t in tasks + up:
            if t["link_item_id"] and t["start_date"] and t["finish_date"]:
                if t.get("layer") == "upstream" and t["link_item_id"] not in from_up:
                    from_up.add(t["link_item_id"]); agg.pop(t["link_item_id"], None)
                elif t["link_item_id"] in from_up and t.get("layer") != "upstream":
                    continue
                a = agg.setdefault(t["link_item_id"], [t["start_date"], t["finish_date"]])
                a[0], a[1] = min(a[0], t["start_date"]), max(a[1], t["finish_date"])
        for iid, (s, f) in agg.items():
            it = db.one(con, "SELECT * FROM contract_item WHERE id=?", (iid,))
            if not it or (only_empty and it["start_date"]):
                continue
            patch = {"start_date": s, "end_date": f}
            if it["method"] != "manual":
                patch["method"] = "window" if iid in from_up else ("lump" if s == f else "even")
            db.update(con, "contract_item", iid, patch)
            res["items"] += 1
    if "costs" in targets:
        ids = {t["link_node_id"] for t in tasks if t["link_node_id"]} | {r["node_id"] for r in db.rows(con, "SELECT node_id FROM window_link WHERE project_id=?", (pid,))}
        res["kept"], res["changed"] = 0, []
        for nid in sorted(ids):
            n = db.one(con, "SELECT * FROM cbs_node WHERE id=?", (nid,))
            if not n or (only_empty and n["start_date"]):
                continue
            r = apply_node(con, pid, nid)
            res["kept"] += 1 if r["kept"] else 0
            res["nodes"] += 1 if r["driven"] else 0
            if r["changed"]:
                res["changed"].append(nid)
        res["warnings"] = window_warnings(con, pid, res["changed"])
    db.bump(con, pid)
    return res


def window_warnings(con, pid, node_ids):
    """Typed (MANUAL) forecast months that sit outside the activity window of the lines whose window just moved."""
    out = []
    sm = (db.scalar(con, "SELECT status_date FROM project WHERE id=?", (pid,)) or "")[:7]
    for nid in node_ids:
        n = db.one(con, "SELECT * FROM cbs_node WHERE id=?", (nid,))
        if not n or n["method"] != "MANUAL" or not n["start_date"] or not n["end_date"]:
            continue
        a, b = n["start_date"][:7], n["end_date"][:7]
        cells = [r["month"] for r in db.rows(con, "SELECT month, amount FROM forecast_manual WHERE node_id=? AND item_id IS NULL AND month>=? ORDER BY month", (nid, sm))
                 if abs(r["amount"] or 0) > 0.005 and (r["month"] < a or r["month"] > b)]
        if cells:
            out.append(dict(node_id=nid, code=n["code"], name=n["name"], start=n["start_date"], end=n["end_date"], months=cells))
    return out


def services_problem(msg):
    from .services import Problem
    return Problem(msg)


# ---- the activity window of a CBS line: Start, Stop and Duration; Start and Stop can each follow a schedule task -------------------
def _ym(d):
    y, m = str(d)[:7].split("-")
    return int(y) * 12 + int(m) - 1


def _first(n):
    return f"{n // 12}-{n % 12 + 1:02d}-01"


def _last(n):
    import calendar
    y, m = n // 12, n % 12 + 1
    return f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def window_state(con, pid, nid):
    """For Start and Stop: what drives it (a schedule task and its start or finish, or typed), whether that link is suspended by a typed
    override, and the date. A line linked to a task the old way (task drives the line) counts as Start = its start, Stop = its finish."""
    n = db.one(con, "SELECT * FROM cbs_node WHERE id=?", (nid,))
    tasks = {t["id"]: t for t in db.rows(con, "SELECT * FROM programme_task WHERE project_id=? AND COALESCE(layer,'internal')='internal'", (pid,))}
    span = [t for t in tasks.values() if t["link_node_id"] == nid and t["start_date"] and t["finish_date"]]
    rows = {r["role"]: r for r in db.rows(con, "SELECT * FROM window_link WHERE node_id=?", (nid,))}
    out = {}
    for role, edge, pick in (("start", "start", lambda: min(span, key=lambda t: t["start_date"])), ("stop", "finish", lambda: max(span, key=lambda t: t["finish_date"]))):
        r = rows.get(role)
        if r and r["task_id"] in tasks:
            t = tasks[r["task_id"]]
            out[role] = dict(task_id=t["id"], task=t["name"], edge=r["edge"], date=t["start_date"] if r["edge"] == "start" else t["finish_date"],
                             suspended=bool(r["suspended"]), stored=True, milestone=bool(t["milestone"]))
        elif span:
            t = pick()
            out[role] = dict(task_id=t["id"], task=t["name"], edge=edge, date=t["start_date"] if edge == "start" else t["finish_date"],
                             suspended=bool(n.get("window_manual")), stored=False, milestone=bool(t["milestone"]))
        else:
            out[role] = None
    return n, out


def apply_node(con, pid, nid):
    """Work out the line's window from its drivers and typed values, and store it. Returns whether it changed, was kept (a typed
    override is suspending a link) and whether a schedule item drives it now."""
    n, st = window_state(con, pid, nid)
    act = {k: (v if v and not v["suspended"] else None) for k, v in st.items()}
    s, e = (act["start"] or {}).get("date") or n["start_date"], (act["stop"] or {}).get("date") or n["end_date"]
    months = n.get("window_months")
    if months and act["start"] and not act["stop"]:           # the other end follows from the typed duration
        e = _last(_ym(s) + int(months) - 1)
    if months and act["stop"] and not act["start"]:
        s = _first(_ym(e) - int(months) + 1)
    kept = any(v and v["suspended"] for v in st.values())
    driven = any(act.values())
    changed = (s, e) != (n["start_date"], n["end_date"])
    if changed and driven:
        # a duration-driven end is not stored as a typed date: the anchor moves it
        db.update(con, "cbs_node", nid, {"start_date": s, "end_date": e})
    return dict(changed=changed and driven, kept=kept, driven=driven, start=s, end=e)


def set_window(con, pid, nid, start, stop, months=None):
    """Save a window from the editor. start / stop: {mode: 'typed'|'schedule'|'duration', date, task_id, edge}. Typing over a schedule-driven
    field suspends the link (kept, so it can be returned to); choosing a task makes the schedule drive it."""
    start, stop = start or {}, stop or {}
    n, st = window_state(con, pid, nid)
    patch = {"window_manual": 0}
    for role, spec in (("start", start), ("stop", stop)):
        mode = spec.get("mode", "typed")
        row = db.one(con, "SELECT * FROM window_link WHERE node_id=? AND role=?", (nid, role))
        if mode == "schedule":
            t = db.one(con, "SELECT * FROM programme_task WHERE id=? AND project_id=?", (spec.get("task_id"), pid))
            if not t:
                raise services_problem("Choose a task from the project schedule")
            edge = spec.get("edge") or "start"
            if row:
                db.update(con, "window_link", row["id"], {"task_id": t["id"], "edge": edge, "suspended": 0})
            else:
                db.insert(con, "window_link", dict(project_id=pid, node_id=nid, role=role, task_id=t["id"], edge=edge, suspended=0))
            clear_link_lost(con, pid, [nid])
        else:
            cur = st.get(role)
            if cur and not row:                            # a link made the old way: keep it as a suspended anchor so "Return to schedule" works
                db.insert(con, "window_link", dict(project_id=pid, node_id=nid, role=role, task_id=cur["task_id"], edge=cur["edge"], suspended=1))
            elif row:
                db.update(con, "window_link", row["id"], {"suspended": 1})
            patch["start_date" if role == "start" else "end_date"] = (spec.get("date") or None) if mode == "typed" else None
    sched = {r: (start if r == "start" else stop).get("mode") == "schedule" for r in ("start", "stop")}
    dur = {r: (start if r == "start" else stop).get("mode") == "duration" for r in ("start", "stop")}
    # the duration is kept only while a schedule item drives the other end; otherwise both dates are stored and it is just their difference
    patch["window_months"] = int(months) if months and ((dur["stop"] and sched["start"]) or (dur["start"] and sched["stop"])) else None
    db.update(con, "cbs_node", nid, patch)
    n2, st2 = window_state(con, pid, nid)
    act = {k: (v if v and not v["suspended"] else None) for k, v in st2.items()}
    p2 = {}
    if start.get("mode") == "duration" and not act["start"] and n2["end_date"] and months:     # no schedule driver: work the date out now
        p2["start_date"] = _first(_ym(n2["end_date"]) - int(months) + 1)
    if stop.get("mode") == "duration" and not act["stop"] and n2["start_date"] and months:
        p2["end_date"] = _last(_ym(n2["start_date"]) + int(months) - 1)
    if p2:
        db.update(con, "cbs_node", nid, p2)
    apply_node(con, pid, nid)
    db.bump(con, pid)
    return window_warnings(con, pid, [nid])


def reset_window(con, pid, nid, role=None):
    """Return a line's Start and/or Stop to the schedule: the suspended links drive again."""
    n, st = window_state(con, pid, nid)
    got = False
    for r in ("start", "stop"):
        if role not in (None, r) or not st.get(r):
            continue
        row = db.one(con, "SELECT * FROM window_link WHERE node_id=? AND role=?", (nid, r))
        if row:
            db.update(con, "window_link", row["id"], {"suspended": 0})
        got = True
    if not got:
        raise services_problem("This line is not linked to an item on the project schedule")
    db.update(con, "cbs_node", nid, {"window_manual": 0})
    apply_node(con, pid, nid)
    db.bump(con, pid)
    return window_warnings(con, pid, [nid])
