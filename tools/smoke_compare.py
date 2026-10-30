"""Replay every GET route against a seeded demonstration database and write status, content type and body to a file.

Run it before and after a change to `app/main.py` (or to the routers) with the same seeded database and compare the two
output files with `diff`; identical files mean the same status and body for every GET endpoint.

    PMT_DB=/tmp/demo_seed.db PMT_SYNC_THREAD=0 .venv/bin/python -m demo.build_demo --seed    # one-off: build the seeded database
    .venv/bin/python tools/smoke_compare.py /tmp/demo_seed.db /tmp/before.json
    .venv/bin/python tools/smoke_compare.py /tmp/demo_seed.db /tmp/after.json && diff /tmp/before.json /tmp/after.json

(`demo.build_demo --db` does not redirect the database in this release, because `app/db.py` reads PMT_DB when it is
imported: use the environment variable as above.) To run against another checkout, for example a worktree of the commit
before a refactor, set PMT_CODE_ROOT to it: the same script and the same seeded database are then used for both runs.

The seeded database is copied first and the copy is used, so the original is never written to. Real ids are read from the
database for each route (see _override and _ids), so a route is not left proving only that an error message matches.
Binary downloads are compared by what a reader sees (tools/replay_common.py): the file name, every cell value of an xlsx,
the text of every page of a pdf, the paragraphs and tables of a docx. The summary at the end lists the routes that returned
an error or an empty body and checks that every money route has at least one non-error, non-empty response.
"""
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_common as rc  # noqa: E402

TABLE_FOR = {"nodes": "cbs_node", "items": "forecast_item", "claims": "claim", "variations": "variation", "subcontracts": "subcontract",
             "snapshots": "snapshot", "risk": "risk", "ledger": "allowance_ledger", "accruals": "accrual", "people": "person",
             "clients": "client", "kb": "kb_doc", "milestones": "milestone", "resources": "resource", "holidays": "holiday",
             "supplier-rates": "supplier_rate", "phases": "phase_log", "lifecycle-log": "lifecycle_log", "gates": "gate_log",
             "assessments": "assessment", "batches": "import_batch", "restore-points": "restore_point", "stakeholders": "project_stakeholder",
             "slots": "team_slot", "tasks": "programme_task", "companies": "company", "ratecard": "rate_card", "releases": "risk_release",
             "timesheet-requests": "timesheet_request", "tag": "risk_tag", "opportunities": "person"}
STRINGS = {"metric": "a", "what": "contract", "kind": "transactions", "token": "x", "key": "x", "code": "x", "gate": "1", "action": "x", "oid": "1"}
# query strings for routes that need them to return data (a "{...}" is filled by _fill from the database)
EXTRA = {"/api/directory/names": "kind=client", "/api/p/{pid}/history": "tbl=cbs_node&id={line}", "/api/p/{pid}/snapshots-compare": "a=live",
         "/api/p/{pid}/snapshots-series": "a=live", "/api/p/{pid}/snapshots-curves": "a=live", "/api/p/{pid}/cmt/report": "token=x",
         "/api/p/{pid}/cmt/updated": "token=x", "/api/p/{pid}/allowance/preview": "bucket_id={group}&kind=supplier&code={supplier}&option=2",
         "/api/p/{pid}/drill": "node={line}&metric=ctd", "/api/p/{pid}/history/{metric}": "node={line}",
         "/api/p/{pid}/accruals/people": "category=PL&month=2026-09"}
# money routes: each must answer without an error and with data at least once (checked in the summary)
MONEY = ("/api/p/{pid}/cost-control", "/api/p/{pid}/ledger", "/api/p/{pid}/accruals", "/api/p/{pid}/accruals/master", "/api/p/{pid}/accruals/timelines",
         "/api/p/{pid}/claims", "/api/p/{pid}/claims/{cid:int}", "/api/p/{pid}/claims/{cid}.pdf", "/api/p/{pid}/claims/{cid}.xlsx",
         "/api/p/{pid}/contract", "/api/p/{pid}/variations", "/api/p/{pid}/variations/{vid}", "/api/p/{pid}/variations/{vid}/funding",
         "/api/p/{pid}/subcontracts", "/api/p/{pid}/subcontracts/{sid}/claims/{cid}", "/api/p/{pid}/subcontracts/{sid}/sheet",
         "/api/p/{pid}/risk", "/api/p/{pid}/risk/buckets", "/api/p/{pid}/risk/releases", "/api/p/{pid}/risk/transactions",
         "/api/p/{pid}/eom-report", "/api/p/{pid}/eom-report.xlsx", "/api/p/{pid}/eom-report.pdf", "/api/p/{pid}/pmr", "/api/p/{pid}/pmr.xlsx",
         "/api/p/{pid}/cost-control.xlsx", "/api/p/{pid}/commitments", "/api/p/{pid}/dashboard", "/api/p/{pid}/margin-bridge", "/api/p/{pid}/month-end",
         "/api/p/{pid}/month-review", "/api/p/{pid}/allowance/overview", "/api/p/{pid}/pools/allocation", "/api/p/{pid}/drill", "/api/p/{pid}/calendar",
         "/api/p/{pid}/nodes/{nid}", "/api/p/{pid}/nodes/{nid}/budget-buildup", "/api/p/{pid}/nodes/{nid}/what-if", "/api/p/{pid}/items/{iid}",
         "/api/p/{pid}/pronto/status", "/api/p/{pid}/pronto/tx", "/api/p/{pid}/pronto/suggestions", "/api/p/{pid}/reconcile", "/api/p/{pid}/snapshots-compare",
         "/api/p/{pid}/history/{metric}", "/api/p/{pid}/invoices", "/api/p/{pid}/invoices.xlsx", "/api/p/{pid}/variations/{vid}/proposal",
         "/api/p/{pid}/supplier-rates", "/api/p/{pid}/ratecard")
# money routes that only have data once a write has created it (the payment certificate is issued by the write replay)
MONEY_AFTER_WRITES = ("/api/p/{pid}/subcontracts/{sid}/claims/{cid}/certificate.pdf",)


def _one(con, q, *a):
    try:
        r = con.execute(q, a).fetchone()
    except sqlite3.Error:
        return None
    return r[0] if r else None


def _ids(con, table, pid):
    for q in (f"SELECT id FROM {table} WHERE project_id=? ORDER BY id LIMIT 1", f"SELECT id FROM {table} ORDER BY id LIMIT 1"):
        v = _one(con, q, *((pid,) if "?" in q else ()))
        if v is not None:
            return v
    return 1


def _line(con, pid):
    """The CBS line with the most Pronto cost: a node that has data in every drill and cost view."""
    return (_one(con, "SELECT node_id FROM pronto_tx WHERE project_id=? AND node_id IS NOT NULL GROUP BY node_id ORDER BY SUM(ABS(cost)) DESC, node_id LIMIT 1", pid)
            or _one(con, "SELECT id FROM cbs_node WHERE project_id=? AND kind='line' ORDER BY id LIMIT 1", pid) or 1)


def _fill(text, con, pid):
    """Replace {line}, {group} and {supplier} in a query string by real values."""
    vals = dict(line=_line(con, pid),
                group=_one(con, "SELECT id FROM cbs_node WHERE project_id=? AND kind='group' AND parent_id IS NOT NULL ORDER BY id LIMIT 1", pid) or 1,
                supplier=_one(con, "SELECT supplier_code FROM pronto_po WHERE project_id=? AND supplier_code IS NOT NULL ORDER BY supplier_code LIMIT 1", pid) or "x")
    return re.sub(r"\{(\w+)\}", lambda m: str(vals.get(m.group(1), m.group(0))), text)


def _override(path, con, pid):
    """Real ids for the routes where the first row of the obvious table is not the one that proves the route."""
    p = path.replace("{pid}", str(pid))
    if path == "/api/forms/{code}":
        f = next(iter(sorted((rc.CODE_ROOT / "app" / "lifecycle_forms").glob("*_*.docx"))), None)
        return f"/api/forms/{f.name.split('_')[0]}" if f else None
    if path == "/api/help/topic/{tid}":
        return "/api/help/topic/faq0"
    if path in ("/api/p/{pid}/claims/{cid:int}", "/api/p/{pid}/claims/{cid}.pdf", "/api/p/{pid}/claims/{cid}.xlsx"):
        cid = _one(con, "SELECT claim_id FROM claim_line GROUP BY claim_id ORDER BY COUNT(*) DESC, claim_id DESC LIMIT 1") or 1
        return p.replace("{cid:int}", str(cid)).replace("{cid}", str(cid))
    if path == "/api/p/{pid}/subcontracts/{sid}/claims/{cid}/certificate.pdf":
        row = con.execute("SELECT subcontract_id, id FROM sub_claim WHERE cert_no IS NOT NULL ORDER BY id LIMIT 1").fetchone()
        if row:
            return p.replace("{sid}", str(row[0])).replace("{cid}", str(row[1]))
    if path in ("/api/p/{pid}/variations/{vid}/proposal", "/api/p/{pid}/variations/{vid}", "/api/p/{pid}/variations/{vid}/funding"):
        v = _one(con, "SELECT variation_id FROM variation_line GROUP BY variation_id ORDER BY COUNT(*) DESC, variation_id LIMIT 1") or 1
        return p.replace("{vid}", str(v))
    if path == "/api/p/{pid}/subcontracts/{sid}/claims/{cid}":
        row = con.execute("SELECT subcontract_id, id FROM sub_claim ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            return p.replace("{sid}", str(row[0])).replace("{cid}", str(row[1]))
    if path in ("/api/p/{pid}/nodes/{nid}", "/api/p/{pid}/nodes/{nid}/budget-buildup", "/api/p/{pid}/nodes/{nid}/what-if"):
        return p.replace("{nid}", str(_line(con, pid)))
    if path == "/api/p/{pid}/ledger/{lid}/edits":
        lid = (_one(con, "SELECT ledger_id FROM ledger_edit GROUP BY ledger_id ORDER BY COUNT(*) DESC LIMIT 1")
               or _one(con, "SELECT id FROM allowance_ledger WHERE project_id=? ORDER BY id LIMIT 1", pid) or 1)
        return p.replace("{lid}", str(lid))
    return None


def _url(path, con, pid):
    ov = _override(path, con, pid)
    if ov:
        return ov
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


def replay_gets(client, app, con, pid):
    """Run every GET route once. Returns (results keyed 'GET path', verdicts keyed the same: ok | empty | error)."""
    result, verdict = {}, {}
    for r in rc.api_routes(app):
        if "GET" not in r.methods:
            continue
        url = _url(r.path, con, pid)
        if EXTRA.get(r.path):
            url += ("&" if "?" in url else "?") + _fill(EXTRA[r.path], con, pid)
        resp = client.get(url)
        result[f"GET {r.path}"] = dict(url=url, status=resp.status_code, content_type=resp.headers.get("content-type", ""), body=rc.body_of(resp))
        verdict[f"GET {r.path}"] = "error" if rc.is_error(resp) else ("empty" if rc.is_empty(resp) else "ok")
    return result, verdict


def summarise(verdict, result, after_writes=False, out=print):
    ok = sum(1 for v in verdict.values() if v == "ok")
    out(f"{len(verdict)} GET routes replayed: {ok} non-error with data, {sum(1 for v in verdict.values() if v == 'empty')} non-error but empty, "
        f"{sum(1 for v in verdict.values() if v == 'error')} error responses")
    for tag in ("error", "empty"):
        for k, v in sorted(verdict.items()):
            if v == tag:
                body = result[k]["body"]
                msg = body.get("detail") if isinstance(body, dict) else ""
                out(f"  {tag:5} {result[k]['status']} {k}  ({result[k]['url']}) {msg or ''}")
    need = MONEY + (MONEY_AFTER_WRITES if after_writes else ())
    missing = [m for m in need if verdict.get(f"GET {m}") != "ok"]
    out(f"money routes checked: {len(need)}; without a non-error response carrying data: {len(missing)}")
    for m in missing:
        out(f"  MONEY ROUTE WITHOUT DATA: {m} -> {verdict.get('GET ' + m, 'not registered')}")
    return missing


def run(seed_db, out_file):
    client, app, con, pid, tmp = rc.bootstrap(seed_db, "pmt-smoke-")
    result, verdict = replay_gets(client, app, con, pid)
    Path(out_file).write_text(json.dumps(result, indent=1, sort_keys=True, default=str), encoding="utf-8")
    summarise(verdict, result)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"written to {out_file}")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
