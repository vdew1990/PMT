"""Replay a fixed, ordered sequence of POST, PUT and DELETE calls against a copy of the seeded demonstration database, then dump
the result so the same run on two versions of the code can be compared with `diff`.

    PMT_DB=/tmp/demo_seed.db PMT_SYNC_THREAD=0 .venv/bin/python -m demo.build_demo --seed     # one-off: the seeded database
    .venv/bin/python tools/write_replay.py /tmp/demo_seed.db /tmp/after                          # this checkout
    PMT_CODE_ROOT=/path/to/older/checkout .venv/bin/python tools/write_replay.py /tmp/demo_seed.db /tmp/before
    diff -r /tmp/before /tmp/after                                                               # empty: the same behaviour

The output directory receives:
  writes.json      each call (label, route, status, response body) in order;
  tables/<t>.txt   every table after the writes, one row per line, in rowid order;
  gets_after.json  the whole GET replay (tools/smoke_compare.py) run after the writes, so every figure the writes changed is read back
                   through the API, including EOM and claim downloads (cell values and page text);
  coverage.txt     which write routes answered without an error, which answered with an error (and why), which were not called.
Ids are read from the database as each step runs, never typed in as placeholders. Only the values in MASK_COLUMNS, MASK_KEYS and
TOKEN_COLUMNS are normalised, because they differ from run to run by design (clock times and generated tokens); see the comments there.
Set WRITE_REPLAY_SKIP to label fragments separated by | (for example "duplicate CBS") to leave steps out, so that one known difference does not
cascade into every later table and the rest can still be compared.
The money-moving calls are each checked for a non-error response and the script exits non-zero when one fails.
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_common as rc  # noqa: E402
import smoke_compare as sc  # noqa: E402

# Columns whose value is the wall-clock time of the write (or a time derived from it). They differ on every run and say nothing about
# the behaviour being compared. Everything not listed here is compared exactly.
MASK_COLUMNS = {"created_at", "uploaded_at", "updated_at", "requested_at", "done_at", "changed_at", "initialised_at", "reviewed_at", "ts", "at"}
# change_log.data holds a row as JSON, so the same clock-time keys (and pair_id, a generated token whose pairing is compared in allowance_ledger itself)
# inside it are masked too, and nothing else in it
JSON_TIME_KEYS = {"created_at", "uploaded_at", "updated_at", "requested_at", "done_at", "changed_at", "initialised_at", "reviewed_at", "at"}
# Columns that hold a generated token (uuid fragments, upload names). They are replaced by the order in which each distinct value
# first appears in that column, so equal values stay equal and distinct values stay distinct (the pairing of ledger legs is still compared).
TOKEN_COLUMNS = {"pair_id", "txn"}
# Keys in a response body that carry a generated token or a timestamp.
MASK_KEYS = {"token", "uploaded_at", "created_at", "changed_at", "requested_at", "done_at", "reviewed_at", "ts", "at", "txn", "pairs", "pair_id"}
rc.EXTRA_MASK_KEYS.update(MASK_KEYS)   # the GET replay run after the writes masks the same keys
TOKEN_RE = re.compile(r"^[0-9a-f]{10,32}$")

DEMO = rc.REPO / "demo"


class Ctx:
    def __init__(self, client, con, pid, tmp):
        self.client, self.con, self.pid, self.tmp = client, con, pid, tmp
        self.k = {}      # ids and values kept from earlier steps

    def q(self, sql, *a):
        return [dict(r) for r in self.con.execute(sql, a).fetchall()]

    def one(self, sql, *a):
        r = self.con.execute(sql, a).fetchone()
        return r[0] if r else None

    @property
    def p(self):
        return f"/api/p/{self.pid}"

    @property
    def p2(self):
        return f"/api/p/{self.k['pid2']}"

    def line(self, code):
        return self.one("SELECT id FROM cbs_node WHERE project_id=? AND code=?", self.pid, code)


STEPS = []


def step(label, method, route, build, save=None, expect_error=False, money=True):
    """build(c) returns (url, kwargs for the request); save(c, body) keeps ids for later steps."""
    STEPS.append(dict(label=label, method=method, route=route, build=build, save=save, expect_error=expect_error, money=money))


def keep(key, field="id"):
    return lambda c, b: c.k.__setitem__(key, b[field])


def xlsx_of(c, url):
    r = c.client.get(url)
    assert r.status_code == 200, (url, r.status_code, r.text[:200])
    return r.content


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# ---------------------------------------------------------------------------
# 1. Allowance, estimate and the ledger
# ---------------------------------------------------------------------------
step("project: create a second project (its estimates are not yet locked)", "POST", "/api/projects",
     lambda c: ("/api/projects", dict(json=dict(name="Replay project 2", status_date="2026-09-30", start_date="2026-01-01", end_date="2027-06-30"))), keep("pid2"), money=False)
step("nodes: add a line with an estimate (project 2)", "POST", "/api/p/{pid}/nodes",
     lambda c: (f"{c.p2}/nodes", dict(json=dict(parent_id=c.one("SELECT id FROM cbs_node WHERE project_id=? AND code='PL01'", c.k["pid2"]), name="Replay line A", kind="line", budget=1000, risk=70))), keep("p2a"))
step("nodes: add a second line (project 2)", "POST", "/api/p/{pid}/nodes",
     lambda c: (f"{c.p2}/nodes", dict(json=dict(parent_id=c.one("SELECT id FROM cbs_node WHERE project_id=? AND code='PL01'", c.k["pid2"]), name="Replay line B", kind="line"))), keep("p2b"))
step("estimate: set a line's original estimate (project 2)", "PUT", "/api/p/{pid}/nodes/{nid}/estimate",
     lambda c: (f"{c.p2}/nodes/{c.k['p2b']}/estimate", dict(json=dict(budget=5000, risk=100, note="Replay estimate"))))
step("allowance bulk: estimates for two lines (project 2)", "POST", "/api/p/{pid}/allowance/bulk",
     lambda c: (f"{c.p2}/allowance/bulk", dict(json=dict(rows=[dict(node_id=c.k["p2a"], budget=2000), dict(node_id=c.k["p2b"], budget=3000, risk=50)]))))
step("ledger: transfer between two lines", "POST", "/api/p/{pid}/ledger/transfer",
     lambda c: (f"{c.p}/ledger/transfer", dict(json=dict(from_id=c.line("PL01.005"), to_id=c.line("PL01.006"), budget=5000, risk=350, ref="TR-1",
                                                           note="Replay transfer", date="15/10/2026"))))
step("ledger: risk release on a node", "POST", "/api/p/{pid}/ledger/risk-release",
     lambda c: (f"{c.p}/ledger/risk-release", dict(json=dict(node_id=c.line("PL01.005"), amount=1000, ref="RR-1", note="Replay release", date="16/10/2026"))))
step("ledger: adjustment", "POST", "/api/p/{pid}/ledger/adjust",
     lambda c: (f"{c.p}/ledger/adjust", dict(json=dict(node_id=c.line("PL01.007"), budget=2500, risk=100, ref="ADJ-1", note="Replay adjustment", date="17/10/2026"))))
step("ledger: correct an entry", "PUT", "/api/p/{pid}/ledger/{lid}",
     lambda c: (f"{c.p}/ledger/{c.one('SELECT id FROM allowance_ledger WHERE project_id=? AND ref=? AND budget>0 ORDER BY id LIMIT 1', c.pid, 'TR-1')}",
                dict(json=dict(budget=5500, risk=350, ref="TR-1", note="Replay transfer corrected", reason="Replay correction", date="17/10/2026"))))
step("ledger: delete an entry", "DELETE", "/api/p/{pid}/ledger/{lid}",
     lambda c: (f"{c.p}/ledger/{c.one('SELECT id FROM allowance_ledger WHERE project_id=? AND ref=? ORDER BY id LIMIT 1', c.pid, 'RR-1')}?reason=Replay+reversal", {}))

# ---------------------------------------------------------------------------
# 2. CBS structure
# ---------------------------------------------------------------------------
step("nodes: add a line", "POST", "/api/p/{pid}/nodes",
     lambda c: (f"{c.p}/nodes", dict(json=dict(parent_id=c.one("SELECT id FROM cbs_node WHERE project_id=? AND kind='group' AND code LIKE 'PE%' ORDER BY id LIMIT 1", c.pid),
                                               name="Replay line", kind="line", method="MANUAL", notes="replay"))), keep("node"))
step("nodes: edit", "PUT", "/api/p/{pid}/nodes/{nid}",
     lambda c: (f"{c.p}/nodes/{c.k['node']}", dict(json=dict(name="Replay line edited", notes="edited"))))
step("nodes: window", "POST", "/api/p/{pid}/nodes/{nid}/window",
     lambda c: (f"{c.p}/nodes/{c.k['node']}/window", dict(json=dict(start=dict(mode="typed", date="01/11/2026"), stop=dict(mode="typed", date="30/11/2026")))))
step("nodes: manual forecast months", "PUT", "/api/p/{pid}/nodes/{nid}/manual",
     lambda c: (f"{c.p}/nodes/{c.k['node']}/manual", dict(json=dict(months={"2026-11": 4000, "2026-12": 6000}))))
step("nodes: forecast-set a month", "POST", "/api/p/{pid}/nodes/{nid}/forecast-set",
     lambda c: (f"{c.p}/nodes/{c.k['node']}/forecast-set", dict(json=dict(month="2026-12", value=7000))), keep("fset_before", "before"))
step("nodes: forecast-move a month", "POST", "/api/p/{pid}/nodes/{nid}/forecast-move",
     lambda c: (f"{c.p}/nodes/{c.k['node']}/forecast-move", dict(json=dict(src="2026-11", dst="2027-01"))))
step("nodes: forecast-restore", "POST", "/api/p/{pid}/nodes/{nid}/forecast-restore",
     lambda c: (f"{c.p}/nodes/{c.k['node']}/forecast-restore", dict(json=dict(before=c.k["fset_before"]))))
step("nodes: add a group to move", "POST", "/api/p/{pid}/nodes",
     lambda c: (f"{c.p}/nodes", dict(json=dict(parent_id=c.one("SELECT id FROM cbs_node WHERE project_id=? AND kind='group' AND code LIKE 'PE%' ORDER BY id LIMIT 1", c.pid),
                                               name="Replay group", kind="group"))), keep("group"))
step("nodes: move the line under the new group", "POST", "/api/p/{pid}/nodes/{nid}/move",
     lambda c: (f"{c.p}/nodes/{c.k['node']}/move", dict(json=dict(parent_id=c.k["group"]))))
step("nodes: reorder", "POST", "/api/p/{pid}/nodes/{nid}/reorder",
     lambda c: (f"{c.p}/nodes/{c.k['group']}/reorder", dict(json=dict(dir=-1))))

# ---------------------------------------------------------------------------
# 3. Forecast items
# ---------------------------------------------------------------------------
step("items: create a forecast item", "POST", "/api/p/{pid}/nodes/{nid}/items",
     lambda c: (f"{c.p}/nodes/{c.line('PL01.005')}/items",
                dict(json=dict(scope="Replay item", spread="Recurring", unit="hr", qty=8, rate=150, start_date="01/11/2026", end_date="30/11/2026", freq="Daily"))), keep("item"))
step("forecast: preview an item (nothing saved)", "POST", "/api/p/{pid}/forecast/preview",
     lambda c: (f"{c.p}/forecast/preview", dict(json=dict(node_id=c.line("PL01.005"), spread="Recurring", unit="hr", qty=8, rate=150,
                                                          start_date="01/11/2026", end_date="30/11/2026", freq="Daily"))))
step("items: set days", "PUT", "/api/p/{pid}/items/{iid}/days",
     lambda c: (f"{c.p}/items/{c.k['item']}/days", dict(json=dict(days={"2026-11-02": 8, "2026-11-03": 4}))))
step("items: accrue past days", "POST", "/api/p/{pid}/items/{iid}/accrue-past",
     lambda c: (f"{c.p}/items/{c.one('SELECT id FROM forecast_item WHERE project_id=? AND resource_id IS NOT NULL AND spread IN (?, ?) ORDER BY id LIMIT 1', c.pid, 'Roster', 'Calendar')}/accrue-past", {}))
step("items: delete", "DELETE", "/api/p/{pid}/items/{iid}",
     lambda c: (f"{c.p}/items/{c.k['item']}", {}))

# ---------------------------------------------------------------------------
# 4. Accruals
# ---------------------------------------------------------------------------
step("accruals: check a landed invoice (answers 200 with an error message)", "POST", "/api/p/{pid}/accruals/check",
     lambda c: (f"{c.p}/accruals/check", dict(json=dict(node_id=c.one("SELECT node_id FROM accrual WHERE id=1"), inv_ref="INV-7781"))), expect_error=True)
step("accruals: check a new invoice", "POST", "/api/p/{pid}/accruals/check",
     lambda c: (f"{c.p}/accruals/check", dict(json=dict(node_id=c.one("SELECT node_id FROM accrual WHERE id=1"), inv_ref="INV-REPLAY-1"))))
step("accruals: create", "POST", "/api/p/{pid}/accruals",
     lambda c: (f"{c.p}/accruals", dict(json=dict(node_id=c.one("SELECT node_id FROM accrual WHERE id=1"), month="2026-10", amount=12345.67, inv_ref="INV-REPLAY-1",
                                                  supplier_code="S30LEC01", supplier_name="LARKSPUR ELECTRICAL PTY LTD", reason="Work done, invoice not yet received"))), keep("accrual"))
step("accruals: edit with a reason", "POST", "/api/p/{pid}/accruals",
     lambda c: (f"{c.p}/accruals", dict(json=dict(id=c.k["accrual"], node_id=c.one("SELECT node_id FROM accrual WHERE id=1"), month="2026-10", amount=13000,
                                                  inv_ref="INV-REPLAY-1", reason="Work done, invoice not yet received", change_reason="Replay correction"))))
step("accruals: resolve an investigated accrual", "POST", "/api/p/{pid}/accruals/{aid}/resolve",
     lambda c: (f"{c.p}/accruals/{c.one('SELECT id FROM accrual WHERE status=? ORDER BY id LIMIT 1', 'investigate')}/resolve", dict(json=dict(resolution="accept"))))
step("accruals: hours for a person on a line", "POST", "/api/p/{pid}/accruals/hours",
     lambda c: (f"{c.p}/accruals/hours", dict(json=dict(resource_id=c.one("SELECT id FROM resource WHERE project_id=? AND code='PM01'", c.pid), node_id=c.line("PL01.005"),
                                                        days={"2026-10-05": 8, "2026-10-06": 8, "2026-10-07": 7.5}, rate=240, role="Senior Project Manager",
                                                        reason="Timesheet not yet posted", note="Replay hours"))))
step("accruals: give the open hour accruals an invoice reference", "POST", "/api/p/{pid}/accruals/invoice-ref",
     lambda c: (f"{c.p}/accruals/invoice-ref", dict(json=dict(resource_id=c.one("SELECT id FROM resource WHERE project_id=? AND code='PM01'", c.pid), month="2026-10", inv_ref="INV-REPLAY-2"))))
step("accruals: unposted timesheet hours", "POST", "/api/p/{pid}/accruals/unposted",
     lambda c: (f"{c.p}/accruals/unposted", dict(json=c.k["unposted"])),)
step("timesheet request: create", "POST", "/api/p/{pid}/timesheet-requests",
     lambda c: (f"{c.p}/timesheet-requests", dict(json=dict(resource_code="PM01", person="Alex Marsden", date_from="2026-10-01", date_to="2026-10-09", hours=20, target="Other project"))), keep("tsreq"))
step("timesheet request: mark done", "PUT", "/api/p/{pid}/timesheet-requests/{rid}",
     lambda c: (f"{c.p}/timesheet-requests/{c.k['tsreq']}", dict(json=dict(status="done"))))
step("accruals: delete with a reason", "DELETE", "/api/p/{pid}/accruals/{aid}",
     lambda c: (f"{c.p}/accruals/{c.k['accrual']}?reason=Replay+removal", {}))
step("month review: decide", "POST", "/api/p/{pid}/month-review",
     lambda c: (f"{c.p}/month-review", dict(json=dict(node_ref=c.line("PL01.005"), month="2026-09", decision=sorted(__import__("app.review", fromlist=["DECISIONS"]).DECISIONS)[0], note="Replay"))))

# ---------------------------------------------------------------------------
# 5. Risk
# ---------------------------------------------------------------------------
step("risk: create", "POST", "/api/p/{pid}/risk",
     lambda c: (f"{c.p}/risk", dict(json=dict(ref="R-REPLAY", title="Replay risk", estimate=50000, status="open", likelihood=0.3, owner="Replay"))), keep("risk"))
step("risk: allocate to a node", "PUT", "/api/p/{pid}/risk/alloc",
     lambda c: (f"{c.p}/risk/alloc", dict(json=dict(risk_id=c.k["risk"], node_id=c.line("PL01.005"), amount=15000))))
step("risk: contingency on a node", "POST", "/api/p/{pid}/risk/contingency",
     lambda c: (f"{c.p}/risk/contingency", dict(json=dict(node_id=c.line("PL01.005"), amount=20000))))
step("risk: fund by contingency", "POST", "/api/p/{pid}/risk/fund",
     lambda c: (f"{c.p}/risk/fund", dict(json=dict(kind="contingency", target_node_id=c.line("PL01.005"), amount=3000, date="18/10/2026", approved_by="Replay", ref="FUND-1"))))
step("risk: fund by infusion", "POST", "/api/p/{pid}/risk/fund",
     lambda c: (f"{c.p}/risk/fund", dict(json=dict(kind="infuse", target_node_id=c.k["fund_target"], amount=1000, date="19/10/2026", approved_by="Replay", ref="FUND-2", force=True))))
step("risk: fund by release", "POST", "/api/p/{pid}/risk/fund",
     lambda c: (f"{c.p}/risk/fund", dict(json=dict(kind="release", target_node_id=c.k["fund_target"], amount=500, date="20/10/2026", approved_by="Replay", ref="FUND-3", force=True))))
step("risk: undo a release", "DELETE", "/api/p/{pid}/risk/releases/{rid}",
     lambda c: (f"{c.p}/risk/releases/{c.one('SELECT id FROM risk_release WHERE project_id=? ORDER BY id DESC LIMIT 1', c.pid)}", {}))
step("risk: delete", "DELETE", "/api/p/{pid}/risk/{rid}",
     lambda c: (f"{c.p}/risk/{c.k['risk']}", {}))

# ---------------------------------------------------------------------------
# 6. Pronto
# ---------------------------------------------------------------------------
step("pronto: set the project code", "PUT", "/api/p/{pid}/pronto/project",
     lambda c: (f"{c.p}/pronto/project", dict(json=dict(code="00000999"))))
step("pronto: analyse the demonstration export", "POST", "/api/p/{pid}/pronto/analyse",
     lambda c: (f"{c.p}/pronto/analyse", dict(files={"file": ("demo_pronto_export.xlsx", (DEMO / "demo_pronto_export.xlsx").read_bytes(), XLSX)})), save=lambda c, b: c.k.__setitem__("pronto", b))
step("pronto: commit the transactions and labour sheets", "POST", "/api/p/{pid}/pronto/commit",
     lambda c: (f"{c.p}/pronto/commit", dict(json=dict(token=c.k["pronto"]["token"], filename="demo_pronto_export.xlsx", pronto_project="00000999",
                                                       items=[dict(sheet=s["sheet"], kind=s["kind"], header_row=s["header_row"], mode="replace", pronto_project="00000999")
                                                              for s in c.k["pronto"]["sheets"] if s["kind"] in ("transactions", "labour")]))))
step("pronto: resolve", "POST", "/api/p/{pid}/pronto/resolve", lambda c: (f"{c.p}/pronto/resolve", {}))
step("pronto: apply a suggestion", "POST", "/api/p/{pid}/pronto/suggestions/apply",
     lambda c: (f"{c.p}/pronto/suggestions/apply", dict(json=dict(items=c.k["suggestions"]))))
step("pronto: delete the newest batch", "DELETE", "/api/p/{pid}/pronto/batches/{bid}",
     lambda c: (f"{c.p}/pronto/batches/{c.one('SELECT MAX(id) FROM import_batch WHERE project_id=? AND kind=?', c.pid, 'labour')}", {}))
step("pronto: resolve again after the delete", "POST", "/api/p/{pid}/pronto/resolve", lambda c: (f"{c.p}/pronto/resolve", {}))

# ---------------------------------------------------------------------------
# 7. Allowance links
# ---------------------------------------------------------------------------
step("allowance: link a resource to a bucket", "POST", "/api/p/{pid}/allowance/link",
     lambda c: (f"{c.p}/allowance/link", dict(json=c.k["link"])))
step("allowance: link many", "POST", "/api/p/{pid}/allowance/link-many",
     lambda c: (f"{c.p}/allowance/link-many", dict(json=dict(rows=c.k["link_many"], option=2))))

# ---------------------------------------------------------------------------
# 8. Contract items and claims (revenue)
# ---------------------------------------------------------------------------
step("contract item: create", "POST", "/api/p/{pid}/contract/items",
     lambda c: (f"{c.p}/contract/items", dict(json=dict(description="Replay milestone", kind="base", value=100000, start_date="01/11/2026", end_date="31/12/2026", method="manual"))), keep("ci"))
step("contract items: bulk fill", "POST", "/api/p/{pid}/contract/items/bulk",
     lambda c: (f"{c.p}/contract/items/bulk", dict(json=dict(field="phase", value="Replay phase", ids=[c.k["ci"]]))))
step("contract item: window", "POST", "/api/p/{pid}/contract/items/{iid}/window",
     lambda c: (f"{c.p}/contract/items/{c.k['ci']}/window", dict(json=dict(start="2026-11", stop="2026-12"))))
step("contract item: plan", "PUT", "/api/p/{pid}/contract/items/{iid}/plan",
     lambda c: (f"{c.p}/contract/items/{c.k['ci']}/plan", dict(json=dict(months={"2026-11": 40000, "2026-12": 60000}))))
step("contract item: cell", "PUT", "/api/p/{pid}/contract/items/{iid}/cell",
     lambda c: (f"{c.p}/contract/items/{c.k['ci']}/cell", dict(json=dict(month="2026-12", amount=55000))))
step("contract item: move a month", "POST", "/api/p/{pid}/contract/items/{iid}/move",
     lambda c: (f"{c.p}/contract/items/{c.k['ci']}/move", dict(json={"from": "2026-12", "to": "2027-01"})))
step("contract: trim excess", "POST", "/api/p/{pid}/contract/trim-excess", lambda c: (f"{c.p}/contract/trim-excess", {}))
step("claim: create", "POST", "/api/p/{pid}/claims",
     lambda c: (f"{c.p}/claims", dict(json=dict(period="2026-10", prefill=True))), keep("claim"))
step("claim: save lines and certify", "PUT", "/api/p/{pid}/claims/{cid}",
     lambda c: (f"{c.p}/claims/{c.k['claim']}", dict(json=dict(status="submitted", submitted_date="31/10/2026", note="Replay",
                                                                lines=[dict(item_id=1, amount=125000), dict(item_id=2, amount=64000.5)],
                                                                action="certify_all", today="05/11/2026"))))
step("claim: delete", "DELETE", "/api/p/{pid}/claims/{cid}", lambda c: (f"{c.p}/claims/{c.k['claim']}", {}))
step("claim: create a second claim to keep for the pdf", "POST", "/api/p/{pid}/claims",
     lambda c: (f"{c.p}/claims", dict(json=dict(period="2026-11", prefill=True))), keep("claim2"))
step("claim: save lines on the kept claim", "PUT", "/api/p/{pid}/claims/{cid}",
     lambda c: (f"{c.p}/claims/{c.k['claim2']}", dict(json=dict(lines=[dict(item_id=3, amount=250000), dict(item_id=4, amount=100000)]))))
step("contract item: delete", "DELETE", "/api/p/{pid}/contract/items/{iid}", lambda c: (f"{c.p}/contract/items/{c.k['ci']}", {}))

# ---------------------------------------------------------------------------
# 9. Variations
# ---------------------------------------------------------------------------
step("variation: create", "POST", "/api/p/{pid}/variations",
     lambda c: (f"{c.p}/variations", dict(json=dict(title="Replay variation", stage="EPC", prepared_by="Replay", submission_date="20/10/2026", value=75000, funding="topup"))), keep("var"))
step("variation: preview the build-up (nothing saved)", "POST", "/api/p/{pid}/variations/{vid}/preview",
     lambda c: (f"{c.p}/variations/{c.k['var']}/preview", dict(json=dict(items=[dict(key="a", name="Labour", section="Labour")],
                                                                          lines=[dict(price_key="a", description="Design", unit="hr", qty=40, rate=135, risk_pct=0.07, markup_pct=0.2)]))))
step("variation: update with items, lines and revisions", "PUT", "/api/p/{pid}/variations/{vid}",
     lambda c: (f"{c.p}/variations/{c.k['var']}",
                dict(json=dict(client_status="Submitted", today="21/10/2026", who="Replay",
                               revs=[dict(rev=0, date="20/10/2026", value=75000, is_current=0), dict(rev=1, date="21/10/2026", value=82000, is_current=1)],
                               items=[dict(key="a", name="Labour", section="Labour", pricing_type="LS")],
                               lines=[dict(price_key="a", section="Labour", node_id=c.line("PL01.005"), description="Design", unit="hr", qty=40, rate=135, risk_pct=0.07, markup_pct=0.2)]))))
step("variation: funding", "PUT", "/api/p/{pid}/variations/{vid}/funding",
     lambda c: (f"{c.p}/variations/{c.k['var']}/funding", dict(json=dict(funding="separate"))))
step("variation: duplicate CBS", "POST", "/api/p/{pid}/variations/{vid}/duplicate-cbs",
     lambda c: (f"{c.p}/variations/{c.k['var']}/duplicate-cbs", dict(json=dict(node_ids=[c.line("PL01.005")]))))
step("variation: event", "POST", "/api/p/{pid}/variations/{vid}/events",
     lambda c: (f"{c.p}/variations/{c.k['var']}/events", dict(json=dict(date="22/10/2026", kind="note", text="Replay note", who="Replay"))))
step("variation: from-schedule", "POST", "/api/p/{pid}/variations/from-schedule", lambda c: (f"{c.p}/variations/from-schedule", {}))
step("variation: upload the register (check only)", "POST", "/api/p/{pid}/variations/upload",
     lambda c: (f"{c.p}/variations/upload", dict(files={"file": ("register.xlsx", xlsx_of(c, f"{c.p}/variations/template.xlsx"), XLSX)}, data=dict(apply="0", today="2026-10-30"))))
step("variation: upload the register (apply)", "POST", "/api/p/{pid}/variations/upload",
     lambda c: (f"{c.p}/variations/upload", dict(files={"file": ("register.xlsx", xlsx_of(c, f"{c.p}/variations/template.xlsx"), XLSX)}, data=dict(apply="1", today="2026-10-30"))))
step("variation: delete", "DELETE", "/api/p/{pid}/variations/{vid}", lambda c: (f"{c.p}/variations/{c.k['var']}", {}))

# ---------------------------------------------------------------------------
# 10. Subcontracts
# ---------------------------------------------------------------------------
step("subcontract: create", "POST", "/api/p/{pid}/subcontracts",
     lambda c: (f"{c.p}/subcontracts", dict(json=dict(name="Replay subcontract", contract_value=200000, retention_pct=0.05, status="active", node_id=c.line("PL01.005"),
                                                      milestones=[dict(name="Mobilise", type="Milestone", pct=0.5, value=100000, start_month="2026-10", end_month="2026-10"),
                                                                  dict(name="Complete", type="Milestone", pct=0.5, value=100000, start_month="2026-12", end_month="2026-12")]))), keep("sub"))
step("subcontract: match a supplier and PO", "POST", "/api/p/{pid}/subcontracts/{sid}/match",
     lambda c: (f"{c.p}/subcontracts/{c.k['sub']}/match", dict(json=dict(supplier_code="S30LEC01", po_no="1032"))))
step("subcontract: forecast save", "PUT", "/api/p/{pid}/subcontracts/{sid}/forecast",
     lambda c: (f"{c.p}/subcontracts/{c.k['sub']}/forecast", dict(json=dict(cells={str(m["id"]): {"2026-11": 25000, "2026-12": 10000} for m in c.q("SELECT id FROM sub_milestone WHERE subcontract_id=? ORDER BY id", c.k["sub"])[:1]}))))
step("subcontract: forecast seed", "POST", "/api/p/{pid}/subcontracts/{sid}/forecast/{action}",
     lambda c: (f"{c.p}/subcontracts/{c.k['sub']}/forecast/seed", dict(json={})))
step("subcontract: forecast shift", "POST", "/api/p/{pid}/subcontracts/{sid}/forecast/{action}",
     lambda c: (f"{c.p}/subcontracts/{c.k['sub']}/forecast/shift", dict(json=dict(months=1))))
step("subcontract: forecast clear", "POST", "/api/p/{pid}/subcontracts/{sid}/forecast/{action}",
     lambda c: (f"{c.p}/subcontracts/{c.k['sub']}/forecast/clear", dict(json={})))
step("subcontract claim: create", "POST", "/api/p/{pid}/subcontracts/{sid}/claims",
     lambda c: (f"{c.p}/subcontracts/{c.k['sub']}/claims", dict(json=dict(month="2026-10"))), keep("sclaim"))
step("subcontract claim: approve", "PUT", "/api/p/{pid}/subcontracts/{sid}/claims/{cid}",
     lambda c: (f"{c.p}/subcontracts/{c.k['sub']}/claims/{c.k['sclaim']}", dict(json=dict(status="approved", approved_date="30/10/2026", inv_ref="SUB-INV-1"))))
step("subcontract claim: issue the certificate", "POST", "/api/p/{pid}/subcontracts/{sid}/claims/{cid}/certificate",
     lambda c: (f"{c.p}/subcontracts/{c.k['sub']}/claims/{c.k['sclaim']}/certificate", dict(json=dict(today="30/10/2026"))))
step("subcontract claim: issue a certificate on a seeded paid claim", "POST", "/api/p/{pid}/subcontracts/{sid}/claims/{cid}/certificate",
     lambda c: (f"{c.p}/subcontracts/1/claims/1/certificate", dict(json=dict(today="30/10/2026"))))
step("subcontract claim: a second claim to delete", "POST", "/api/p/{pid}/subcontracts/{sid}/claims",
     lambda c: (f"{c.p}/subcontracts/{c.k['sub']}/claims", dict(json=dict(month="2026-10", allow_second=True))), keep("sclaim2"))
step("subcontract claim: delete", "DELETE", "/api/p/{pid}/subcontracts/{sid}/claims/{cid}",
     lambda c: (f"{c.p}/subcontracts/{c.k['sub']}/claims/{c.k['sclaim2']}", {}))
step("subcontract: delete the replay subcontract", "DELETE", "/api/p/{pid}/subcontracts/{sid}", lambda c: (f"{c.p}/subcontracts/{c.k['sub']}", {}))

# ---------------------------------------------------------------------------
# 11. Small registers (milestones, supplier rates, holidays) and delete of the replay line
# ---------------------------------------------------------------------------
step("milestone: create", "POST", "/api/p/{pid}/milestones",
     lambda c: (f"{c.p}/milestones", dict(json=dict(name="Replay milestone", type="Milestone", baseline_end="30/11/2026", forecast_end="15/12/2026"))), keep("ms"), money=False)
step("milestone: delete", "DELETE", "/api/p/{pid}/milestones/{mid}", lambda c: (f"{c.p}/milestones/{c.k['ms']}", {}), money=False)
step("supplier rate: create", "POST", "/api/p/{pid}/supplier-rates",
     lambda c: (f"{c.p}/supplier-rates", dict(json=dict(resource_id=c.one("SELECT id FROM resource WHERE project_id=? AND kind='supplier' ORDER BY id LIMIT 1", c.pid), role="Replay role", unit="hr", rate=123.45, ot_rate=150, nt_hours=7.6, ref="RR-1"))), keep("srate"), money=False)
step("supplier rate: delete", "DELETE", "/api/p/{pid}/supplier-rates/{sid}", lambda c: (f"{c.p}/supplier-rates/{c.k['srate']}", {}), money=False)
step("nodes: delete the replay line", "DELETE", "/api/p/{pid}/nodes/{nid}", lambda c: (f"{c.p}/nodes/{c.k['node']}", {}))


# ---------------------------------------------------------------------------
# 12. Resources, rates, methods, pools, baselines, programme, imports, revert
# ---------------------------------------------------------------------------
step("resource: create", "POST", "/api/p/{pid}/resources",
     lambda c: (f"{c.p}/resources", dict(json=dict(kind="employee", code="RP01", name="REPLAY PERSON", function="Replay engineer", work_rate_code="PJ03", cost_rate=111.11, sell_rate=150))), keep("res"))
step("resource: edit the cost rate", "PUT", "/api/p/{pid}/resources/{rid}",
     lambda c: (f"{c.p}/resources/{c.k['res']}", dict(json=dict(cost_rate=122.22, status="active"))))
step("rate card: create", "POST", "/api/p/{pid}/ratecard",
     lambda c: (f"{c.p}/ratecard", dict(json=dict(department="Replay", role="Replay role", work_rate_code="RPL1", cost_rate=99, sell_rate=140, fy="2026-27"))), keep("rate"))
step("rate card: delete", "DELETE", "/api/p/{pid}/ratecard/{rid}", lambda c: (f"{c.p}/ratecard/{c.k['rate']}", {}))
step("resource: delete", "DELETE", "/api/p/{pid}/resources/{rid}", lambda c: (f"{c.p}/resources/{c.k['res']}", {}))
step("methods: set a group's forecast method", "POST", "/api/p/{pid}/methods",
     lambda c: (f"{c.p}/methods", dict(json=dict(node_id=c.line("PE"), method="BURN-RATE", include_pots=True))))
step("pools: set every pool's method", "POST", "/api/p/{pid}/pools/method", lambda c: (f"{c.p}/pools/method", dict(json=dict(method="AT-BUDGET"))))
step("pools: allocate", "POST", "/api/p/{pid}/pools/allocation", lambda c: (f"{c.p}/pools/allocation", dict(json={})))
step("ctc lines: ensure", "POST", "/api/p/{pid}/ctc-lines", lambda c: (f"{c.p}/ctc-lines", {}))
step("category: add", "POST", "/api/p/{pid}/categories", lambda c: (f"{c.p}/categories", dict(json=dict(code="PE20", name="Replay category"))), keep("cat"))
step("snapshot: create", "POST", "/api/p/{pid}/snapshots", lambda c: (f"{c.p}/snapshots", dict(json=dict(label="Replay snapshot"))), keep("snap"))
step("snapshot: delete", "DELETE", "/api/p/{pid}/snapshots/{sid}", lambda c: (f"{c.p}/snapshots/{c.k['snap']}", {}))
step("cmt: record an entry", "POST", "/api/p/{pid}/cmt",
     lambda c: (f"{c.p}/cmt", dict(json=dict(as_of="30/09/2026", revenue=1000000, eac=900000, ctd=500000, note="Replay"))), money=False)
step("holiday: add", "POST", "/api/p/{pid}/holidays",
     lambda c: (f"{c.p}/holidays", dict(json=dict(day="2026-12-28", name="Replay holiday"))), keep("hol"), money=False)
step("holiday: delete", "DELETE", "/api/p/{pid}/holidays/{hid}", lambda c: (f"{c.p}/holidays/{c.k['hol']}", {}), money=False)
step("programme: upload the demonstration schedule", "POST", "/api/p/{pid}/programme/upload",
     lambda c: (f"{c.p}/programme/upload", dict(files={"file": ("demo_programme.xml", (DEMO / "demo_programme.xml").read_bytes(), "application/xml")})), money=False)
step("programme: link a task to the replay line", "POST", "/api/p/{pid}/programme/links",
     lambda c: (f"{c.p}/programme/links", dict(json=dict(node_id=c.line("PL01.006"), task_id=c.one("SELECT id FROM programme_task WHERE project_id=? ORDER BY id LIMIT 1 OFFSET 3", c.pid), role="span"))), money=False)
step("programme: auto-link", "POST", "/api/p/{pid}/programme/auto-link", lambda c: (f"{c.p}/programme/auto-link", {}), money=False)
step("programme: apply dates to costs and claims", "POST", "/api/p/{pid}/programme/apply",
     lambda c: (f"{c.p}/programme/apply", dict(json=dict(targets=["claims", "costs"], only_empty=True))))
step("nodes: window driven by the schedule", "POST", "/api/p/{pid}/nodes/{nid}/window",
     lambda c: (f"{c.p}/nodes/{c.line('PL01.007')}/window", dict(json=dict(start=dict(mode="schedule", task_id=c.one("SELECT id FROM programme_task WHERE project_id=? ORDER BY id LIMIT 1 OFFSET 4", c.pid), edge="start"),
                                                                              stop=dict(mode="typed", date="31/12/2026")))))
step("nodes: window reset to the schedule", "POST", "/api/p/{pid}/nodes/{nid}/window-reset",
     lambda c: (f"{c.p}/nodes/{c.line('PL01.007')}/window-reset", dict(json=dict(role="start"))))
step("programme: remove a link", "DELETE", "/api/p/{pid}/programme/links",
     lambda c: (f"{c.p}/programme/links?task_id={c.one('SELECT id FROM programme_task WHERE project_id=? ORDER BY id LIMIT 1 OFFSET 3', c.pid)}&node_id={c.line('PL01.006')}", {}), money=False)
step("schedule: analyse the claim schedule template", "POST", "/api/p/{pid}/schedule/analyse",
     lambda c: (f"{c.p}/schedule/analyse", dict(files={"file": ("claim-schedule.xlsx", xlsx_of(c, f"{c.p}/schedule/template.xlsx?grid=1"), XLSX)})), save=lambda c, b: c.k.__setitem__("sched", b))
step("schedule: commit (merge)", "POST", "/api/p/{pid}/schedule/commit",
     lambda c: (f"{c.p}/schedule/commit", dict(json=dict(token=c.k["sched"]["token"], mode="merge", filename="claim-schedule.xlsx"))))
step("subcontracts: upload the payment schedules (apply)", "POST", "/api/p/{pid}/subcontracts/upload",
     lambda c: (f"{c.p}/subcontracts/upload", dict(files={"file": ("subs.xlsx", xlsx_of(c, f"{c.p}/subcontracts/template.xlsx?sid=all"), XLSX)}, data=dict(apply="1"))))
step("sub-timesheets: upload the template", "POST", "/api/p/{pid}/sub-timesheets",
     lambda c: (f"{c.p}/sub-timesheets", dict(files={"file": ("ts.xlsx", xlsx_of(c, f"{c.p}/sub-timesheets/template.xlsx"), XLSX)}, data=dict(replace="0"))), money=False)
step("ledger: spread a group's allowance", "POST", "/api/p/{pid}/ledger/spread",
     lambda c: (f"{c.p}/ledger/spread", dict(json=spread_args(c))), save=lambda c, b: c.k.__setitem__("spread_pairs", b["pairs"]))
step("ledger: undo the spread", "POST", "/api/p/{pid}/ledger/spread/undo",
     lambda c: (f"{c.p}/ledger/spread/undo", dict(json=dict(pairs=c.k["spread_pairs"]))))
step("revert: put back the last action", "POST", "/api/p/{pid}/revert", lambda c: (f"{c.p}/revert", {}))
step("redo: apply it again", "POST", "/api/p/{pid}/redo", lambda c: (f"{c.p}/redo", {}))


# ---------------------------------------------------------------------------
# Running and dumping
# ---------------------------------------------------------------------------
def spread_args(c):
    """A group whose own pool has allowance left and a line under it, found when the step runs (earlier steps change what is left)."""
    from app import allowance
    pots, _lines = allowance._rows(c.con, c.pid)
    for i, pt in sorted(pots.items()):
        line = c.one("SELECT id FROM cbs_node WHERE parent_id=? AND kind='line' ORDER BY id LIMIT 1", i)
        if line and pt.get("budget", 0) - pt.get("ctd", 0) - pt.get("acc", 0) > 100:
            return dict(from_id=i, moves=[dict(to_id=line, budget=100)], note="Replay spread")
    return dict(from_id=c.line("PL01"), moves=[])


def prepare(c):
    """Real ids for steps that depend on the seeded data (found by query, not typed in)."""
    from app import forecast
    cands = c.q("SELECT l.resource_code, l.month, l.node_id, r.id rid FROM pronto_labour l JOIN resource r ON r.project_id=l.project_id AND r.code=l.resource_code AND r.kind='employee' "
                "WHERE l.project_id=? AND l.posted=0 AND l.node_id IS NOT NULL GROUP BY l.resource_code, l.month, l.node_id ORDER BY SUM(l.hours) DESC, l.resource_code", c.pid)
    ctx = forecast.load_ctx(c.con, c.pid)
    r = [x for x in cands if forecast._f(forecast.rate_for(ctx, dict(resource_id=x["rid"], rate_mode="auto"))["rate"])][:1]
    c.k["unposted"] = dict(resource_code=r[0]["resource_code"], month=r[0]["month"], node_id=r[0]["node_id"], note="Replay unposted") if r else dict(resource_code="PM01", month="2026-09", node_id=c.line("PL01.005"))
    c.k["fund_target"] = c.one("SELECT target_node_id FROM risk_release WHERE project_id=? ORDER BY id LIMIT 1", c.pid) or c.line("PL01.005")
    grp = c.one("SELECT id FROM cbs_node WHERE project_id=? AND kind='group' AND code LIKE 'PS%' ORDER BY id LIMIT 1", c.pid)
    sup = c.one("SELECT supplier_code FROM pronto_po WHERE project_id=? AND supplier_code IS NOT NULL ORDER BY supplier_code LIMIT 1", c.pid)
    c.k["link"] = dict(bucket_id=grp, kind="supplier", code=sup, option=2, amount=0)
    c.k["link_many"] = [dict(kind="supplier", code=s["supplier_code"], name=s["supplier_name"], bucket_id=grp)
                        for s in c.q("SELECT supplier_code, MAX(supplier_name) supplier_name FROM pronto_po WHERE project_id=? AND supplier_code IS NOT NULL GROUP BY supplier_code ORDER BY supplier_code LIMIT 2 OFFSET 1", c.pid)]


def mask_json_text(text):
    """A JSON text with its clock-time keys masked (any other key is kept as it is)."""
    try:
        o = json.loads(text)
    except (TypeError, ValueError):
        return text

    def walk(x):
        if isinstance(x, dict):
            return {k: ("<masked>" if k in JSON_TIME_KEYS else "<token>" if k in TOKEN_COLUMNS else walk(v)) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str) and x[:1] in "{[":
            return mask_json_text(x)       # a row that holds another JSON text (settings_json)
        return x
    return json.dumps(walk(o), sort_keys=True)


def mask_body(o):
    if isinstance(o, dict):
        return {k: ("<masked>" if k in MASK_KEYS else mask_body(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [mask_body(v) for v in o]
    return o


def dump_tables(con, out_dir):
    tdir = Path(out_dir) / "tables"
    tdir.mkdir(parents=True, exist_ok=True)
    seen = {}
    for t in rc.table_names(con):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        try:
            rows = con.execute(f"SELECT rowid AS _rowid_, * FROM {t} ORDER BY rowid").fetchall()
        except Exception:
            rows = con.execute(f"SELECT * FROM {t}").fetchall()
        lines = []
        for r in rows:
            d = dict(r)
            for col in list(d):
                if col in MASK_COLUMNS:
                    d[col] = "<masked>" if d[col] is not None else None
                elif t == "change_log" and col == "data" and d[col]:
                    d[col] = mask_json_text(d[col])
                elif col in TOKEN_COLUMNS and d[col] is not None:
                    d[col] = f"<token {seen.setdefault((t, col, d[col]), len([k for k in seen if k[:2] == (t, col)]) + 1)}>"
            lines.append(json.dumps(d, sort_keys=True, default=str))
        (tdir / f"{t}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def run(seed_db, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    client, app, con, pid, tmp = rc.bootstrap(seed_db, "pmt-writes-")
    c = Ctx(client, con, pid, tmp)
    prepare(c)
    # the suggestions to apply come from the API, as the page does it
    sugg = client.get(f"{c.p}/pronto/suggestions").json().get("items", [])
    c.k["suggestions"] = sugg[:3]
    registered = {(m, re.sub(r"\{(\w+):\w+\}", r"{\1}", r.path)) for r in rc.api_routes(app) for m in r.methods if m in ("POST", "PUT", "DELETE", "PATCH")}
    results, coverage, failed = [], {}, []
    skip = [x for x in os.environ.get("WRITE_REPLAY_SKIP", "").split("|") if x]     # label fragments of steps to leave out, for example one known to differ
    for s in STEPS:
        if any(x in s["label"] for x in skip):
            results.append(dict(label=s["label"], route=f"{s['method']} {s['route']}", url=None, status=None, body="skipped"))
            continue
        if (s["method"], s["route"]) not in registered:
            raise SystemExit(f"step '{s['label']}': {s['method']} {s['route']} is not a registered route")
        # a step that needs ids from the pronto commit (suggestions) is re-read just before it runs
        if s["route"].endswith("/pronto/suggestions/apply"):
            c.k["suggestions"] = client.get(f"{c.p}/pronto/suggestions").json().get("items", [])[:3]
        try:
            url, kw = s["build"](c)
        except (KeyError, TypeError, IndexError) as e:      # an earlier step that creates what this one needs did not succeed
            cov = coverage.setdefault(f"{s['method']} {s['route']}", dict(ok=0, error=[], money=s["money"]))
            cov["error"].append(f"{s['label']}: not run, an earlier step did not give it what it needs ({type(e).__name__} {e})")
            results.append(dict(label=s["label"], route=f"{s['method']} {s['route']}", url=None, status=None, body="not run"))
            failed.append(s["label"])
            continue
        resp = client.request(s["method"], url, **kw)
        try:
            body = resp.json()
        except ValueError:
            body = resp.text[:200]
        bad = resp.status_code >= 400 or (isinstance(body, dict) and body.get("error"))
        results.append(dict(label=s["label"], route=f"{s['method']} {s['route']}", url=url, status=resp.status_code, body=mask_body(body)))
        cov = coverage.setdefault(f"{s['method']} {s['route']}", dict(ok=0, error=[], money=s["money"]))
        if bad:
            cov["error"].append(f"{s['label']}: {resp.status_code} {json.dumps(body)[:160]}")
            if not s["expect_error"]:
                failed.append(s["label"])
        else:
            cov["ok"] += 1
            if s["save"]:
                s["save"](c, body)
        con.rollback()                       # drop any read snapshot so the next query sees what the app committed
    (out / "writes.json").write_text(json.dumps(results, indent=1, sort_keys=True, default=str), encoding="utf-8")
    dump_tables(con, out)
    get_result, verdict = sc.replay_gets(client, app, con, pid)
    (out / "gets_after.json").write_text(json.dumps(get_result, indent=1, sort_keys=True, default=str), encoding="utf-8")
    lines = [f"{len(STEPS)} write calls; {len(coverage)} distinct write routes called of {len(registered)} registered write routes", ""]
    lines.append("Routes with at least one non-error response:")
    lines += [f"  {k} ({v['ok']}x)" for k, v in sorted(coverage.items()) if v["ok"]]
    lines.append("")
    lines.append("Routes called whose every response was an error (or an error message in a 200):")
    lines += [f"  {k}: {'; '.join(v['error'])}" for k, v in sorted(coverage.items()) if not v["ok"]]
    lines.append("")
    lines.append("Calls that returned an error as designed (the step expects it):")
    lines += [f"  {k}: {'; '.join(v['error'])}" for k, v in sorted(coverage.items()) if v["ok"] and v["error"]]
    lines.append("")
    lines.append("Write routes not called:")
    lines += [f"  {m} {p}" for m, p in sorted(registered, key=lambda x: (x[1], x[0])) if f"{m} {p}" not in coverage]
    lines.append("")
    sc.summarise(verdict, get_result, after_writes=True, out=lambda s: lines.append(s))
    (out / "coverage.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:1] + [l for l in lines if l.startswith("  MONEY")]))
    shutil.rmtree(tmp, ignore_errors=True)
    if failed:
        print("UNEXPECTED ERROR RESPONSES in:", "; ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
