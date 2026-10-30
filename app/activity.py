"""Readable history from the change log: who changed what, when, and what it was before."""
import time
import json

from . import db, sync

LABEL = {
    "project": "Project", "resource": "Resource", "rate_card": "Rate card", "supplier_rate": "Supplier rate",
    "cbs_node": "CBS item", "allowance_ledger": "Allowance entry", "forecast_item": "Forecast item",
    "forecast_manual": "Typed forecast month", "forecast_day": "Forecast day", "forecast_ms": "Forecast milestone",
    "accrual": "Accrual", "import_batch": "Pronto upload", "pronto_tx": "Pronto transaction", "pronto_labour": "Pronto timesheet",
    "pronto_po": "Pronto PO", "pronto_claim": "Pronto claim", "pronto_variation": "Pronto variation", "pronto_ctd": "Pronto CTD row",
    "contract_item": "Contract item", "revenue_plan": "Revenue plan month", "claim": "Client claim", "claim_line": "Client claim line",
    "variation": "Variation", "variation_rev": "Variation revision", "variation_line": "Variation pricing line",
    "variation_event": "Variation note", "subcontract": "Subcontract", "sub_milestone": "Subcontract schedule item",
    "sub_claim": "Subcontract claim", "sub_claim_line": "Subcontract claim line", "milestone": "Project schedule milestone",
    "snapshot": "Snapshot", "snapshot_line": "Snapshot line", "cmt_entry": "CMT entry", "programme_task": "Project schedule task",
    "risk": "Risk", "risk_alloc": "Risk allocation", "risk_tag": "Risk tag", "risk_release": "Risk release", "holiday": "Public holiday", "month_review": "Month-end review decision", "sub_forecast": "Claim forecast", "sub_plan": "Subcontractor planned claim", "variation_price": "Variation price item", "sub_timesheet": "Subcontractor timesheet",
}
OP = {"I": "added", "U": "changed", "D": "deleted"}
COL = {"amount": "amount", "status": "status", "inv_ref": "invoice ref", "month": "month", "note": "note", "reason": "reason",
       "method": "method", "hours": "hours", "rate": "rate", "qty": "quantity", "pct": "%", "name": "name", "start_date": "start",
       "end_date": "end", "matched_amount": "landed amount", "matched_date": "landed date", "spread": "spread", "day": "day"}
# bulk tables are summarised per action rather than listed row by row
BULK = {"pronto_tx", "pronto_labour", "pronto_po", "pronto_claim", "pronto_variation", "pronto_ctd", "snapshot_line", "forecast_day", "change_log"}


def _node_names(con, pid):
    return {r["id"]: (r["code"], r["name"]) for r in db.rows(con, "SELECT id, code, name FROM cbs_node WHERE project_id=?", (pid,))}


def _money(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def _val(k, v):
    if v is None or v == "":
        return "blank"
    if k in ("amount", "matched_amount", "rate", "budget", "risk", "value", "cost", "contract_value"):
        return _money(v)
    return str(v)


def _what(e, cur, nodes):
    """One-line description of the record an entry is about."""
    d = e["_d"] or {}
    row = {**(cur or {}), **({k: v for k, v in d.items() if not isinstance(v, list)} if e["op"] != "U" else {})}
    t = e["tbl"]
    nid = row.get("node_id")
    where = ""
    if nid in nodes:
        where = f" on {nodes[nid][0]} {nodes[nid][1]}"
    if t == "accrual":
        hrs = f"{row.get('hours'):g} h " if row.get("hours") else ""
        return f"Accrual {hrs}{_money(row.get('amount'))} {row.get('day') or row.get('month') or ''}{where}".strip()
    if t == "forecast_item":
        return f"Forecast item '{row.get('scope') or row.get('spread') or ''}'{where}"
    if t == "cbs_node":
        return f"CBS {row.get('code', '')} {row.get('name', '')}".strip()
    if t == "allowance_ledger":
        return f"Allowance {row.get('kind', '')} {_money(row.get('budget'))}{where}"
    if t in ("variation", "risk"):
        return f"{LABEL[t]} {row.get('ref', '')} {row.get('title', '')}".strip()
    if t == "month_review":
        ref = str(row.get("node_ref") or "")
        nd = nodes.get(int(ref.lstrip("p"))) if ref.lstrip("p").isdigit() else None
        return f"Month-end review {row.get('month', '')} of {(nd[0] + (' (pool)' if ref.startswith('p') else '')) if nd else ref}: {row.get('decision') or 'cleared'}"
    if t == "project":
        return f"Project {row.get('name', '')}".strip()
    if t == "resource":
        return f"Resource {row.get('code', '')} {row.get('name', '')}".strip()
    nm = row.get("name") or row.get("title") or row.get("description") or row.get("ref") or ""
    return f"{LABEL.get(t, t)} {nm}".strip() + where


def describe(con, pid, entries):
    nodes = _node_names(con, pid)
    cache = {}
    out = []
    for e in entries:
        e["_d"] = json.loads(e["data"]) if e.get("data") else None
        key = (e["tbl"], e["row_id"])
        if key not in cache:
            try:
                cache[key] = db.one(con, f"SELECT * FROM {e['tbl']} WHERE id=?", (e["row_id"],))
            except Exception:
                cache[key] = None
        changes = []
        if e["op"] == "U" and e["_d"]:
            for k, (o, n) in e["_d"].items():
                changes.append(dict(field=COL.get(k, k.replace("_", " ")), old=_val(k, o), new=_val(k, n)))
        out.append(dict(id=e["id"], at=e["at"], ts=e["ts"], user=_who(con, e["user_name"], e["user_upn"]), upn=e["user_upn"], via=e.get("via"),
                        txn=e.get("txn"), tbl=e["tbl"], kind=LABEL.get(e["tbl"], e["tbl"]), row_id=e["row_id"], op=e["op"],
                        action=OP[e["op"]], what=_what(e, cache[key], nodes), changes=changes, remote=e.get("remote", 0),
                        exists=cache[key] is not None))
    return out


def activity(con, pid, user=None, tbl=None, q=None, limit=300, before=None):
    """Project-wide activity, newest first. Bulk rows (Pronto, snapshots, day grids) are folded into one line per action."""
    where, args = ["project_id=?"], [pid]
    if user:
        where.append("user_upn=?")
        args.append(user)
    if tbl:
        where.append("tbl=?")
        args.append(tbl)
    if before:
        where.append("id<?")
        args.append(int(before))
    sql = f"SELECT * FROM change_log WHERE {' AND '.join(where)} ORDER BY ts DESC, id DESC LIMIT ?"
    raw = db.rows(con, sql, args + [int(limit) * 4])
    folded, plain = {}, []
    for e in raw:
        if e["tbl"] in BULK:
            k = (e["txn"] or (e["user_upn"], (e["at"] or "")[:19]), e["tbl"], e["op"])
            f = folded.get(k)
            if f is None:
                f = folded[k] = dict(id=e["id"], at=e["at"], ts=e["ts"], user=_who(con, e["user_name"], e["user_upn"]), upn=e["user_upn"], via=e["via"],
                                     txn=e["txn"], tbl=e["tbl"], kind=LABEL.get(e["tbl"], e["tbl"]), row_id=None, op=e["op"],
                                     action=OP[e["op"]], n=0, changes=[], remote=e["remote"], exists=False)
                plain.append(f)
            f["n"] += 1
            f["what"] = f"{f['n']} × {LABEL.get(e['tbl'], e['tbl'])}"
        else:
            plain.append(e)
    done = {d["id"]: d for d in describe(con, pid, [x for x in plain if "action" not in x])}
    out = [x if "action" in x else done[x["id"]] for x in plain]
    if q:
        ql = q.lower()
        out = [x for x in out if ql in (x.get("what") or "").lower() or ql in (x.get("user") or "").lower()
               or any(ql in (c["old"] + " " + c["new"]).lower() for c in x.get("changes", []))]
    roles = {k: v.get("role") for k, v in sync.people(con).items()}
    for x in out:
        x["role"] = roles.get(x.get("upn")) or ""
    return out[:int(limit)]


def row_history(con, pid, tbl, row_id, related=True):
    """Every change to one record, oldest first. For a CBS line, also its forecast items, days, milestones and accruals."""
    keys = [(tbl, int(row_id))]
    if related and tbl == "cbs_node":
        for t in ("forecast_item", "accrual", "allowance_ledger", "forecast_manual"):
            ids = {r["row_id"] for r in db.rows(con, "SELECT DISTINCT row_id FROM change_log WHERE tbl=? AND op IN ('I','D') "
                                                     "AND json_extract(data, '$.node_id')=?", (t, int(row_id)))}
            keys += [(t, i) for i in ids]
        items = [k[1] for k in keys if k[0] == "forecast_item"]
        for t in ("forecast_ms",):
            for i in items:
                ids = {r["row_id"] for r in db.rows(con, "SELECT DISTINCT row_id FROM change_log WHERE tbl=? AND op='I' AND json_extract(data, '$.item_id')=?", (t, i))}
                keys += [(t, x) for x in ids]
    entries = []
    for t, i in keys:
        entries += db.rows(con, "SELECT * FROM change_log WHERE tbl=? AND row_id=?", (t, i))
    entries.sort(key=lambda e: (e["ts"], e["id"]))
    out = describe(con, pid, entries)
    roles = {k: v.get("role") for k, v in sync.people(con).items()}
    for x in out:
        x["role"] = roles.get(x.get("upn")) or ""
    return out


def stamps(con, tbl, ids):
    """Created by / last changed by for a list of rows: {id: {created_by, created_at, changed_by, changed_at, changed_via}}."""
    out = {}
    ids = list(ids)
    for k in range(0, len(ids), 500):
        part = ids[k:k + 500]
        q = ",".join("?" * len(part))
        for r in db.rows(con, f"SELECT row_id, op, user_name, user_upn, at, via FROM change_log WHERE tbl=? AND row_id IN ({q}) ORDER BY ts, id", [tbl, *part]):
            s = out.setdefault(r["row_id"], {})
            who = _who(con, r["user_name"], r["user_upn"])
            if r["op"] == "I" and "created_by" not in s:
                s.update(created_by=who, created_at=r["at"])
            s.update(changed_by=who, changed_at=r["at"], changed_via=r["via"])
    return out


_people = (0.0, {})


def _who(con, recorded, upn):
    """The name to show for a change. Before the identity fix, OneDrive's organisation ("EPEC Group Pty Ltd") was
    recorded instead of the person: show the person's current name for those."""
    from . import identity, sync
    if recorded and not identity.looks_like_org(recorded):
        return recorded
    global _people
    if time.time() - _people[0] > 30:
        try:
            _people = (time.time(), {k: v.get("name") for k, v in sync.people(con).items()})
        except Exception:
            _people = (time.time(), {})
    cache = _people[1]
    nm = cache.get(upn)
    return nm if nm and not identity.looks_like_org(nm) else (identity._pretty(upn) if upn else recorded)
