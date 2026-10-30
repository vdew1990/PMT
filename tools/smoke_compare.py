"""Replay every GET route against a seeded demonstration database and write status, content type and body to a file.

Run it before and after a change to `app/main.py` (or to the routers) with the same seeded database and compare the two
output files with `diff`; identical files mean the same status and JSON for every GET endpoint.

    PMT_DB=/tmp/demo_seed.db .venv/bin/python -m demo.build_demo --seed       # one-off: build the seeded database
    .venv/bin/python tools/smoke_compare.py /tmp/demo_seed.db /tmp/before.json
    .venv/bin/python tools/smoke_compare.py /tmp/demo_seed.db /tmp/after.json && diff /tmp/before.json /tmp/after.json

The seeded database is copied first and the copy is used, so the original is never written to. Binary downloads
(xlsx, pdf, docx) are compared on status and content type only, because their bytes carry timestamps.
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE_FOR = {"nodes": "cbs_node", "items": "forecast_item", "claims": "claim", "variations": "variation", "subcontracts": "subcontract",
             "snapshots": "snapshot", "risk": "risk", "ledger": "allowance_ledger", "accruals": "accrual", "people": "person",
             "clients": "client", "kb": "kb_doc", "milestones": "milestone", "resources": "resource", "holidays": "holiday",
             "supplier-rates": "supplier_rate", "phases": "phase_log", "lifecycle-log": "lifecycle_log", "gates": "gate_log",
             "assessments": "assessment", "batches": "import_batch", "restore-points": "restore_point", "stakeholders": "project_stakeholder",
             "slots": "team_slot", "tasks": "programme_task", "companies": "company", "ratecard": "rate_card", "releases": "risk_release",
             "timesheet-requests": "timesheet_request", "tag": "risk_tag", "opportunities": "person"}
STRINGS = {"metric": "f", "what": "contract", "kind": "tx", "token": "x", "key": "x", "code": "x", "gate": "1", "action": "x", "oid": "1"}
# query strings for routes that need them to return data
EXTRA = {"/api/directory/names": "kind=client", "/api/p/{pid}/history": "tbl=cbs_node&id=1", "/api/p/{pid}/snapshots-compare": "a=live",
         "/api/p/{pid}/snapshots-series": "a=live", "/api/p/{pid}/snapshots-curves": "a=live", "/api/p/{pid}/cmt/report": "token=x",
         "/api/p/{pid}/cmt/updated": "token=x", "/api/p/{pid}/allowance/preview": "option=1", "/api/p/{pid}/drill": "node=1&metric=CTD",
         "/api/p/{pid}/pronto/raw/{kind}": "", "/api/p/{pid}/history/{metric}": "node=1"}
BINARY = ("spreadsheet", "pdf", "wordprocessing", "octet-stream", "zip")


def _ids(con, table, pid):
    for q in (f"SELECT id FROM {table} WHERE project_id=? ORDER BY id LIMIT 1", f"SELECT id FROM {table} ORDER BY id LIMIT 1"):
        try:
            r = con.execute(q, (pid,) if "?" in q else ()).fetchone()
        except sqlite3.Error:
            continue
        if r:
            return r[0]
    return 1


def _url(path, con, pid):
    segs = path.split("/")
    out = []
    for i, s in enumerate(segs):
        m = re.fullmatch(r"\{(\w+)(?::\w+)?\}(.*)", s)
        if not m:
            out.append(s)
            continue
        name, tail = m.group(1), m.group(2)
        prev = segs[i - 1] if i else ""
        if name == "pid":
            v = _ids(con, "person", pid) if prev == "people" else pid
        elif name in STRINGS:
            v = STRINGS[name]
        else:
            if prev == "items" and "contract" in segs:
                table = "contract_item"
            elif prev == "claims" and "subcontracts" in segs:
                table = "sub_claim"
            elif prev == "directory":
                table = "company"
            else:
                table = TABLE_FOR.get(prev, prev.rstrip("s"))
            v = _ids(con, table, pid)
        out.append(f"{v}{tail}")
    return "/".join(out)


MASK = ("build", "build_now")   # the program-file fingerprint changes with any file edit, by design (app/build.py)


def _norm(o):
    if isinstance(o, dict):
        return {k: ("<fingerprint>" if k in MASK else _norm(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_norm(v) for v in o]
    return o


def run(seed_db, out_file):
    tmp = Path(tempfile.mkdtemp(prefix="pmt-smoke-"))
    db_copy = tmp / "smoke.db"
    shutil.copy(seed_db, db_copy)
    os.environ.update(PMT_DB=str(db_copy), PMT_SYNC_THREAD="0", PMT_NO_JAVA_DOWNLOAD="1")
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from app.main import app
    from fastapi.routing import APIRoute
    con = sqlite3.connect(db_copy)
    pid = con.execute("SELECT id FROM project ORDER BY id LIMIT 1").fetchone()[0]
    client = TestClient(app)
    result = {}
    for r in app.routes:
        if not isinstance(r, APIRoute) or "GET" not in r.methods:
            continue
        url = _url(r.path, con, pid)
        if EXTRA.get(r.path):
            url += "?" + EXTRA[r.path]
        resp = client.get(url)
        ct = resp.headers.get("content-type", "")
        if any(b in ct for b in BINARY):
            body = f"<binary {ct}>"
        elif "json" in ct:
            try:
                body = _norm(resp.json())
            except ValueError:
                body = resp.text
        else:
            body = hashlib.sha256(resp.content).hexdigest()
        result[f"GET {r.path}"] = dict(url=url, status=resp.status_code, content_type=ct, body=body)
    Path(out_file).write_text(json.dumps(result, indent=1, sort_keys=True, default=str), encoding="utf-8")
    ok = sum(1 for v in result.values() if v["status"] == 200)
    print(f"{len(result)} GET routes replayed, {ok} returned 200; written to {out_file}")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
