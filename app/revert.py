"""Revert: put back the last thing the signed-in user changed on a project, using the change log (changelog.py).

Every request is one action (one txn). The log holds, per record, what was inserted, the old and new value of each field
that changed, and the old row of what was deleted, so an action can be run backwards: inserted rows are removed, changed fields
go back to their old value, deleted rows are put back. Reverting does not stack: a reverted action is marked and the next
Revert takes the action before it. Actions that deleted bulk Pronto rows keep no copy and cannot be reverted here."""
import json

from . import changelog, db, identity, services

LABEL = {"allowance_ledger": "allowance ledger", "cbs_node": "CBS", "forecast_manual": "forecast months", "forecast_item": "forecast items",
         "accrual": "accruals", "claim": "claims", "claim_line": "claim lines", "contract_item": "contract value", "revenue_plan": "claim schedule",
         "risk": "risks", "variation": "variations", "programme_task": "project schedule", "project": "project details", "resource": "resources",
         "milestone": "payment milestones", "subcontract": "subcontracts", "pronto_tx": "Pronto cost"}


def _last(con, pid):
    me = identity.current()["upn"]
    return db.one(con, "SELECT txn, MIN(at) at, MAX(id) last_id, COUNT(*) n FROM change_log WHERE project_id=? AND txn IS NOT NULL AND remote=0 AND user_upn=? "
                       "AND COALESCE(via,'') NOT IN ('Revert','Redo') AND txn NOT IN (SELECT txn FROM revert_mark) GROUP BY txn ORDER BY last_id DESC LIMIT 1", (pid, me))


def _redo_candidate(con, pid):
    """The most recently reverted action, if the user has not made a new change since (a new change ends the redo trail)."""
    m = db.one(con, "SELECT txn, rev_id FROM revert_mark WHERE project_id=? ORDER BY rev_id DESC LIMIT 1", (pid,))
    if not m:
        return None
    me = identity.current()["upn"]
    newer = db.one(con, "SELECT 1 x FROM change_log WHERE project_id=? AND id>? AND txn IS NOT NULL AND remote=0 AND user_upn=? AND COALESCE(via,'') NOT IN ('Revert','Redo')", (pid, m["rev_id"] or 0, me))
    return None if newer else m


def preview(con, pid):
    a = _last(con, pid)
    rc = _redo_candidate(con, pid)
    redo = {"txn": rc["txn"], "summary": _summary(con, rc["txn"], pid)} if rc else None
    if not a:
        return {"txn": None, "redo": redo}
    return {"txn": a["txn"], "at": a["at"], "summary": _summary(con, a["txn"], pid), "redo": redo}


def _summary(con, txn, pid):
    parts = db.rows(con, "SELECT tbl, op, COUNT(*) n FROM change_log WHERE txn=? AND project_id=? GROUP BY tbl, op ORDER BY tbl", (txn, pid))
    bits = {}
    for r in parts:
        bits.setdefault(LABEL.get(r["tbl"], r["tbl"].replace("_", " ")), []).append(f"{r['n']} {dict(I='added', U='changed', D='removed')[r['op']]}")
    return "; ".join(f"{k}: {', '.join(v)}" for k, v in bits.items())


def revert(con, pid):
    a = _last(con, pid)
    if not a:
        raise services.Problem("Nothing to revert")
    rows = db.rows(con, "SELECT * FROM change_log WHERE txn=? AND project_id=? ORDER BY id DESC", (a["txn"], pid))
    ok_tables = set(changelog.data_tables(con))
    for r in rows:
        if r["tbl"] not in ok_tables:
            raise services.Problem("That change cannot be reverted here")
        if r["op"] == "D" and not r["data"]:
            raise services.Problem("That action removed imported records and kept no copy. Use the undo on the import itself.")
    con.execute("PRAGMA defer_foreign_keys = ON")
    with changelog.via("Revert"):
        for r in rows:
            t = r["tbl"]
            if r["op"] == "I":
                con.execute(f"DELETE FROM {t} WHERE id=?", (r["row_id"],))
            elif r["op"] == "U":
                cols = {k: v[0] for k, v in json.loads(r["data"]).items()}
                con.execute(f"UPDATE {t} SET " + ", ".join(f"{k}=?" for k in cols) + " WHERE id=?", (*cols.values(), r["row_id"]))
            else:
                old = json.loads(r["data"])
                con.execute(f"INSERT OR REPLACE INTO {t}(" + ",".join(old) + ") VALUES (" + ",".join("?" * len(old)) + ")", tuple(old.values()))
        con.execute("INSERT OR IGNORE INTO revert_mark(txn, project_id) VALUES (?,?)", (a["txn"], pid))
    con.execute("UPDATE revert_mark SET rev_id=(SELECT MAX(id) FROM change_log) WHERE txn=?", (a["txn"],))
    db.bump(con, pid)
    return {"reverted": len(rows), "summary": preview_of(con, a, pid)}


def preview_of(con, a, pid):
    parts = db.rows(con, "SELECT tbl, COUNT(*) n FROM change_log WHERE txn=? AND project_id=? GROUP BY tbl", (a["txn"], pid))
    return "; ".join(f"{LABEL.get(r['tbl'], r['tbl'].replace('_', ' '))}: {r['n']}" for r in parts)


def redo(con, pid):
    """Apply the most recently reverted action again (the forward direction of revert)."""
    m = _redo_candidate(con, pid)
    if not m:
        raise services.Problem("Nothing to redo")
    rows = db.rows(con, "SELECT * FROM change_log WHERE txn=? AND project_id=? ORDER BY id", (m["txn"], pid))
    ok_tables = set(changelog.data_tables(con))
    con.execute("PRAGMA defer_foreign_keys = ON")
    with changelog.via("Redo"):
        for r in rows:
            t = r["tbl"]
            if t not in ok_tables:
                continue
            if r["op"] == "I":
                new = json.loads(r["data"])
                con.execute(f"INSERT OR REPLACE INTO {t}(" + ",".join(new) + ") VALUES (" + ",".join("?" * len(new)) + ")", tuple(new.values()))
            elif r["op"] == "U":
                cols = {k: v[1] for k, v in json.loads(r["data"]).items()}
                con.execute(f"UPDATE {t} SET " + ", ".join(f"{k}=?" for k in cols) + " WHERE id=?", (*cols.values(), r["row_id"]))
            else:
                con.execute(f"DELETE FROM {t} WHERE id=?", (r["row_id"],))
        con.execute("DELETE FROM revert_mark WHERE txn=?", (m["txn"],))
    db.bump(con, pid)
    return {"redone": len(rows), "summary": _summary(con, m["txn"], pid)}
