"""Accruals: cost incurred that is not yet in Pronto, and how each one ties out when the cost lands.

Four ways an accrual arises (EPEC PMT workbook, Accruals sheet; Vincent 20/10):
  work      the PM's estimate of work done in a month. The least certain: nothing to match it with but the PM.
  invoice   an invoice the PM has been asked to approve, not yet in Pronto. Carries the supplier, PO number, invoice
            number and / or quote number, so it matches by itself when the invoice lands.
  hours     hours for a person on a day (labour calendar): reverses when the posted timesheet lands.
  claim     a subcontractor's claim received in PMT (automatic, see subcontracts.claim_accruals).
Plus two that live in Pronto and must not be accrued twice:
  Pronto accruals finance posts on the Work in Progress account ("Aug 26 Acc <supplier>", reference = PO; and
  "<month> Timesheet Accrual"), journalled one month and reversed the next. Shown per CBS line and supplier; a PM accrual
  on the same line and PO / supplier counts only above what finance already accrued (the workbook's MAX rule).
  Unposted timesheets: hours entered in Pronto with no cost yet. Accrued automatically at Pronto's cost or hours x the
  person's cost rate, unless the PM accrued that person-day or asked for the hours to be journalled to another project.

Timing (the work-performed view). An invoice accrual made in month X whose invoice lands in month Y is matched to the
invoice: month X shows the invoice amount (trued up), month Y shows the invoice plus a reversal of the same amount, so Y
nets to zero. When was what work done stays right; Pronto's month (billing) is on the Timelines view.
"""
import json
import re
from collections import defaultdict
from datetime import date, timedelta

from . import changelog, db

KINDS = {"work": "Estimate of work done", "invoice": "Invoice awaiting approval", "hours": "Timesheet hours", "claim": "Subcontract claim"}


def _n(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def _digits(s):
    d = re.sub(r"\D", "", str(s or ""))
    return d.lstrip("0") if len(d) >= 4 else ""


def _kind(a):
    return a.get("kind") or ("hours" if a.get("hours") is not None else "invoice" if (a.get("inv_ref") or a.get("quote_ref")) else "work")


# ---- supplier invoices in the GL, one per invoice --------------------------------------------------------------
def gl_invoices(con, pid):
    """Supplier invoices posted in Pronto (PO receipts and direct invoices), GL lines grouped back into invoices."""
    inv = {}
    for r in con.execute("SELECT resource_code, doc_type, doc_no, doc_suffix, reference, tx_date, month, po_no, node_id, description, account_desc, cost "
                         "FROM pronto_tx WHERE project_id=? AND class='actual' AND doc_type IN ('PO','CV') ORDER BY tx_date, id", (pid,)):
        key = (r["resource_code"], r["doc_type"], r["doc_no"], r["doc_suffix"], r["reference"], r["tx_date"])
        i = inv.get(key)
        if i is None:
            i = inv[key] = dict(key="|".join(str(x or "") for x in key), supplier=r["resource_code"], supplier_name=r["account_desc"], doc_no=r["doc_no"],
                                ref=r["reference"] or f"{r['doc_no'] or ''}{r['doc_suffix'] or ''}", date=r["tx_date"], month=r["month"], po=r["po_no"],
                                text=f"{r['reference'] or ''} {r['description'] or ''}", amount=0.0, nodes=set())
        i["amount"] += r["cost"] or 0
        if r["node_id"]:
            i["nodes"].add(r["node_id"])
    return list(inv.values())


def match(con, pid):
    """Tie every invoice-type accrual (and every hours accrual) to what has landed in Pronto.

    An accrual matches an invoice by, in order: its invoice number (the GL reference or document number; leading zeros
    and punctuation ignored), its quote number (found in the invoice reference or description), or its PO number (the
    first invoice on that PO dated in or after the accrual month that no other accrual has taken). Accruals sharing one
    invoice number are matched together against it.
      open         nothing has landed: counts in full in its month
      matched      landed within the tolerance: counts the invoice amount in its month, reversed in the landing month
      investigate  landed for a different amount: counted as matched (trued up to the invoice) until the PM decides
                   ("accept" = matched; "rest_open" = the difference stays accrued: status partial)
      partial      hours accruals: a timesheet covered part of the hours (the rest still counts); invoice accruals: the
                   PM said the rest of the work is still to be invoiced
    """
    s = db.project_settings(con, pid)
    if not s.get("accrual_auto_reverse", True):
        return 0
    tol = float(s.get("accrual_tolerance", 1.0))
    invs = gl_invoices(con, pid)
    by_ref, by_digits, by_po = defaultdict(list), defaultdict(list), defaultdict(list)
    for i in invs:
        for k in {_n(i["ref"]), _n(i["doc_no"])}:
            if k:
                by_ref[k].append(i)
        for k in {_digits(i["ref"]), _digits(i["doc_no"])}:
            if k:
                by_digits[k].append(i)
        if i["po"]:
            by_po[_n(i["po"])].append(i)
    # every accrual but employees' hours (those tie to their posted timesheet, see _match_hours); a subcontractor's hours
    # carry the invoice number of their monthly invoice
    acc = db.rows(con, "SELECT * FROM accrual WHERE project_id=? AND status!='cancelled' AND (hours IS NULL OR COALESCE(inv_ref,'')!='') ORDER BY month, id", (pid,))
    used = set()
    found = {}
    # 1. invoice number (accruals sharing one number go together)
    groups = defaultdict(list)
    for a in acc:
        if a.get("inv_ref") and _n(a["inv_ref"]):
            groups[_n(a["inv_ref"])].append(a)
    for k, members in groups.items():
        hits = by_ref.get(k) or by_digits.get(_digits(members[0]["inv_ref"])) or []
        if hits:
            for a in members:
                found[a["id"]] = (hits, "invoice number")
            used.update(i["key"] for i in hits)
    # 2. quote number in the invoice reference or description
    for a in acc:
        if a["id"] in found or not a.get("quote_ref") or len(_n(a["quote_ref"])) < 4:
            continue
        q = _n(a["quote_ref"])
        hits = [i for i in invs if i["key"] not in used and q in _n(i["text"])]
        if hits:
            found[a["id"]] = (hits[:1], "quote number")
            used.add(hits[0]["key"])
    # 3. PO number, for invoice accruals only (an estimate of work done is not one invoice): the first invoice on the PO
    #    from the accrual month on that nobody has taken (same line first). A negative row reverses an accrual (e.g. the
    #    PM taking back finance's stale accrual once the invoice is in): it is never an invoice to wait for.
    for a in acc:
        if a["id"] in found or not a.get("po_no") or a.get("inv_ref") or _kind(a) != "invoice" or (a["amount"] or 0) <= 0:
            continue
        cands = [i for i in by_po.get(_n(a["po_no"]), []) if i["key"] not in used and i["month"] >= a["month"]
                 and (not a.get("supplier_code") or not i["supplier"] or i["supplier"] == a["supplier_code"])]
        cands.sort(key=lambda i: (a["node_id"] not in i["nodes"], i["date"]))
        if cands:
            found[a["id"]] = ([cands[0]], "PO number")
            used.add(cands[0]["key"])
    group_amt = {k: sum(x["amount"] or 0 for x in m) for k, m in groups.items()}
    changed = 0
    for a in acc:
        hit = found.get(a["id"])
        if not hit:
            new = dict(status="open", matched_amount=None, matched_date=None, matched_month=None, matched_via=None, matched_refs=None)
        else:
            hits, via = hit
            landed = sum(i["amount"] for i in hits)
            mine = group_amt.get(_n(a.get("inv_ref")), a["amount"]) if via == "invoice number" else a["amount"]
            share = landed * ((a["amount"] or 0) / mine) if via == "invoice number" and mine else landed
            last = max(i["date"] for i in hits)
            if abs(landed - mine) <= tol:
                st = "matched"
            elif a.get("resolution") == "accept":
                st = "matched"
            elif a.get("resolution") == "rest_open" and share < (a["amount"] or 0):
                st = "partial"
            else:
                st = "investigate"
            new = dict(status=st, matched_amount=round(share, 2), matched_date=last, matched_month=last[:7], matched_via=via,
                       matched_refs=json.dumps(sorted({i["ref"] for i in hits})))
        if any((a.get(k) or None) != (v or None) for k, v in new.items()):
            label = {"open": "Automatic: invoice no longer in Pronto", "matched": "Automatic: invoice landed in Pronto",
                     "investigate": "Automatic: invoice landed for a different amount", "partial": "Automatic: invoice landed for part of the accrual"}[new["status"]]
            with changelog.via(label):
                db.update(con, "accrual", a["id"], new)
            changed += 1
    changed += _match_hours(con, pid)
    changed += _close_requests(con, pid)
    if changed:
        db.bump(con, pid)
    return changed


# ---- what each accrual counts, month by month (the engine's ACC series) ----------------------------------------
def counted(con, pid):
    """[(node_id, month, amount, source)] for every accrual that counts: open PM accruals (above any Pronto accrual
    already covering them), matched invoice accruals as invoice amount in the work month and its reversal in the
    landing month, unposted timesheets, and subcontract claims (same timing as invoices)."""
    from . import subcontracts
    st = db.project_settings(con, pid)
    shift = st.get("accrual_work_timing", True)
    out = []
    cover = pronto_cover(con, pid)
    for a in db.rows(con, "SELECT * FROM accrual WHERE project_id=? AND status IN ('open','partial','matched','investigate')", (pid,)):
        amt, m = a["amount"] or 0, a["month"]
        if a["hours"] is not None and not a.get("inv_ref"):   # employees' hours: the timesheet lands as an actual in its own month
            if a["status"] == "open":
                out.append((a["node_id"], m, amt, "PM"))
            elif a["status"] == "partial":
                out.append((a["node_id"], m, max(0.0, amt - (a["matched_amount"] or 0)), "PM"))
            continue
        if a["status"] == "open":
            out.append((a["node_id"], m, amt - cover.get(a["id"], 0.0), "PM"))
            continue
        landed = a["matched_amount"] or 0
        if a["status"] == "partial":        # the rest of the work is still to be invoiced: it stays accrued
            out.append((a["node_id"], m, max(0.0, amt - landed), "PM"))
        if shift and a["matched_month"] and a["matched_month"] != m:   # (same month: the invoice itself is the cost)
            out.append((a["node_id"], m, landed, "Matched"))
            out.append((a["node_id"], a["matched_month"], -landed, "Matched"))
    for r in con.execute(f"SELECT l.node_id, l.month, SUM({UNPOSTED_COST}) a FROM pronto_labour l WHERE l.project_id=? AND l.posted=0 "
                         f"AND l.node_id IS NOT NULL AND {UNPOSTED_NOT_ACCRUED} GROUP BY l.node_id, l.month", (pid,)):
        out.append((r["node_id"], r["month"], r["a"] or 0, "Timesheet"))
    # finance's own timesheet accrual for a month covers the automatic one for that month and line
    # (finance posts it on the category, e.g. PL04; PMT's automatic ones sit on each person's line under it)
    ts_cover = defaultdict(float)
    for p in pronto_accruals(con, pid):
        if p["kind"] == "timesheet" and p["open"] > 0.5:
            ts_cover[(p["category"], p["month"])] += p["open"]
    if ts_cover:
        codes = {r["id"]: r["code"] or "" for r in db.rows(con, "SELECT id, code FROM cbs_node WHERE project_id=?", (pid,))}
        adj = []
        for i, (nid, m, amt, src) in enumerate(out):
            k = next(((c, mm) for (c, mm) in ts_cover if mm == m and c and codes.get(nid, "").startswith(c) and ts_cover[(c, mm)] > 0), None)
            if src == "Timesheet" and k:
                take = min(amt, ts_cover[k])
                ts_cover[k] -= take
                adj.append((i, amt - take))
        for i, amt in adj:
            out[i] = (out[i][0], out[i][1], amt, "Timesheet")
    landed = landed_refs(con, pid)
    for c in subcontracts.claim_accruals(con, pid, landed):
        out.append((c["node_id"], c["month"], c["amount"], "Claim"))
    if shift:
        for c in claim_landings(con, pid):
            out.append((c["node_id"], c["month"], c["landed"], "Matched"))
            out.append((c["node_id"], c["landed_month"], -c["landed"], "Matched"))
    return [x for x in out if abs(x[2]) > 0.004]


def claim_landings(con, pid):
    """Subcontract claims whose invoice has landed: the invoice amount, the claim month and the landing month."""
    from . import subcontracts
    by = defaultdict(lambda: [0.0, ""])
    for i in gl_invoices(con, pid):
        for k in {_n(i["ref"]), _n(i["doc_no"])}:
            if k:
                by[k][0] += i["amount"]
                by[k][1] = max(by[k][1], i["month"] or "")
    out = []
    for s in db.rows(con, "SELECT * FROM subcontract WHERE project_id=? AND node_id IS NOT NULL", (pid,)):
        for c in subcontracts.claims_of(con, s["id"]):
            if c["status"] == "draft" or not c.get("inv_ref"):
                continue
            hit = by.get(_n(c["inv_ref"]))
            if hit and hit[1] and hit[1] != c["month"][:7]:
                out.append(dict(node_id=s["node_id"], month=c["month"][:7], landed=round(hit[0], 2), landed_month=hit[1], claim_id=c["id"], sub_id=s["id"]))
    return out


# ---- accruals finance posted in Pronto (Work in Progress) -----------------------------------------------------
WIP_RE = re.compile(r"\bACC\b|ACCRU", re.I)


def pronto_accruals(con, pid):
    """Finance's accruals in the GL: Work in Progress journals that are accruals ("<month> Acc <supplier>", reference =
    PO or invoice; "<month> Timesheet Accrual"). One row per line x reference x accrual month: accrued, reversed, open."""
    rows = db.rows(con, "SELECT t.*, n.code AS cbs FROM pronto_tx t LEFT JOIN cbs_node n ON n.id=t.node_id WHERE t.project_id=? AND t.class='journal' "
                        "AND (LOWER(COALESCE(t.account_desc,'')) LIKE '%work in progress%' OR t.reference LIKE '%ACCRUAL%') ORDER BY t.tx_date, t.id", (pid,))
    out = {}
    for r in rows:
        text = f"{r['description'] or ''} {r['reference'] or ''}"
        if not WIP_RE.search(text):
            continue
        ts = "TIMESHEET" in text.upper() or "PAYROLL" in text.upper()
        m = re.search(r"\bAcc(?:rual)?\s+(.+)$", r["description"] or "", re.I)
        who = "Timesheets (payroll)" if ts else re.sub(r"\s+[\d.,]+$", "", m.group(1)).strip().title() if m else (r["description"] or "").strip()
        # the month accrued: the month named in the description, else the journal's own month
        mon = _named_month(r["description"]) or r["month"]
        key = (r["node_id"], _n(r["reference"]) if not ts else "TS", mon)
        p = out.get(key)
        if p is None:
            p = out[key] = dict(node_id=r["node_id"], cbs=r["cbs"], category=r["category"], kind="timesheet" if ts else "supplier", supplier=who,
                                reference=r["reference"], po=_po(r["reference"]), month=mon, accrued=0.0, reversed=0.0, lines=[])
        if (r["cost"] or 0) >= 0:
            p["accrued"] += r["cost"] or 0
        else:
            p["reversed"] += r["cost"] or 0
        p["lines"].append(dict(date=r["tx_date"], type=r["doc_type"], amount=r["cost"], text=r["description"]))
    res = []
    for p in out.values():
        p["open"] = round(p["accrued"] + p["reversed"], 2)
        p["accrued"], p["reversed"] = round(p["accrued"], 2), round(p["reversed"], 2)
        p["reversed_on"] = next((l["date"] for l in p["lines"] if (l["amount"] or 0) < 0), None)
        res.append(p)
    # a reversal journal can name another month than its accrual ("April 26 Acc X - Reversal" against "May 26 Acc X"):
    # on the same line and reference, an over-reversed month offsets the open ones, oldest first
    groups = defaultdict(list)
    for p in res:
        if p["kind"] == "supplier" and p["reference"] not in (None, "", "0"):
            groups[(p["node_id"], p["reference"])].append(p)
    for ps in groups.values():
        neg = -sum(p["open"] for p in ps if p["open"] < -0.5)
        for p in sorted((p for p in ps if p["open"] > 0.5), key=lambda p: p["month"]):
            if neg <= 0.5:
                break
            take = min(neg, p["open"])
            p["open"] = round(p["open"] - take, 2)
            neg -= take
        for p in ps:
            if p["open"] < -0.5:
                p["open"] = round(min(0.0, -neg), 2) if neg > 0.5 else 0.0
                neg = 0.0
    res.sort(key=lambda p: (p["open"] == 0, p["month"]), reverse=False)
    return res


MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def _named_month(text):
    m = re.match(r"\s*([A-Za-z]{3})[a-z]*\.?\s+(\d{2,4})\b", str(text or ""))
    if not m or m.group(1).upper() not in MONTHS:
        return None
    y = int(m.group(2))
    y = y + 2000 if y < 100 else y
    return f"{y:04d}-{MONTHS[m.group(1).upper()]:02d}"


def _po(ref):
    m = re.match(r"^(\d{3,7})[A-Za-z]{0,3}$", str(ref or "").strip())
    return m.group(1) if m else None


def pronto_cover(con, pid):
    """accrual id -> the part of an open PM accrual that finance's open Pronto accrual already covers (same CBS line and
    the same PO, invoice reference or supplier). The workbook's rule: the line's accrual is the larger of the two."""
    left = {}
    for p in pronto_accruals(con, pid):
        if p["kind"] == "supplier" and p["open"] > 0.5:
            left[id(p)] = [p, p["open"]]
    if not left:
        return {}
    cover = {}
    for a in db.rows(con, "SELECT * FROM accrual WHERE project_id=? AND status='open' AND hours IS NULL ORDER BY month, id", (pid,)):
        for k, (p, rest) in left.items():
            if rest <= 0.5 or p["node_id"] != a["node_id"]:
                continue
            same = (a.get("po_no") and p["po"] and _n(a["po_no"]) == _n(p["po"])) or (a.get("inv_ref") and _n(a["inv_ref"]) == _n(p["reference"])) \
                or (a.get("supplier_name") and _n(a["supplier_name"])[:8] and _n(a["supplier_name"])[:8] in _n(p["supplier"]))
            if same:
                take = min(rest, a["amount"] or 0)
                cover[a["id"]] = cover.get(a["id"], 0.0) + take
                left[k][1] -= take
    return cover


def overlaps(con, pid, node_id, po_no=None, inv_ref=None, supplier=None):
    """Finance's open accruals in Pronto on this line for this PO / invoice / supplier (warn before accruing twice)."""
    out = []
    for p in pronto_accruals(con, pid):
        if p["kind"] != "supplier" or p["open"] <= 0.5 or p["node_id"] != node_id:
            continue
        if (po_no and p["po"] and _n(po_no) == _n(p["po"])) or (inv_ref and _n(inv_ref) == _n(p["reference"])) or (supplier and _n(supplier)[:8] and _n(supplier)[:8] in _n(p["supplier"])):
            out.append(p)
    return out


# ---- unposted timesheets ----------------------------------------------------------------------------------------
# Unposted timesheets (entered in Pronto, waiting for approval, no cost rate yet) accrue automatically unless the PM
# has accrued that person-day by hand (the PM's accrual stands), accrued the line's unposted timesheets for the month
# (source Timesheet, e.g. from the PMT workbook's register), or asked for the hours to be journalled to another
# project (they do not belong here: nothing accrues while the request is open).
UNPOSTED_NOT_ACCRUED = ("NOT EXISTS (SELECT 1 FROM accrual ha JOIN resource hr ON hr.id=ha.resource_id WHERE ha.project_id=l.project_id "
                        "AND hr.code=l.resource_code AND ha.day=l.date_worked AND ha.hours IS NOT NULL AND ha.status IN ('open','partial')) "
                        "AND NOT EXISTS (SELECT 1 FROM accrual ta WHERE ta.project_id=l.project_id AND ta.node_id=l.node_id AND ta.month=l.month "
                        "AND ta.source='Timesheet' AND ta.status IN ('open','partial')) "
                        "AND NOT EXISTS (SELECT 1 FROM timesheet_request tq WHERE tq.project_id=l.project_id AND tq.resource_code=l.resource_code "
                        "AND l.date_worked BETWEEN tq.date_from AND tq.date_to AND tq.status='requested')")
# what an unposted timesheet is worth: Pronto's cost when it has one, else hours x the person's cost rate
UNPOSTED_COST = ("COALESCE(NULLIF(l.total_cost, 0), l.hours * (SELECT er.cost_rate FROM resource er WHERE er.project_id=l.project_id "
                 "AND er.kind='employee' AND er.code=l.resource_code), 0)")


def unposted(con, pid):
    """Unposted timesheets per person and month: hours, what they are worth, and what is happening to them."""
    rows = db.rows(con, f"SELECT l.resource_code, MAX(l.name) person, l.month, l.node_id, n.code, n.name AS line, MIN(l.date_worked) d0, MAX(l.date_worked) d1, "
                        f"SUM(l.hours) hours, SUM({UNPOSTED_COST}) amount, SUM(CASE WHEN {UNPOSTED_NOT_ACCRUED} THEN {UNPOSTED_COST} ELSE 0 END) auto, "
                        f"SUM(CASE WHEN {UNPOSTED_NOT_ACCRUED} THEN 0 ELSE l.hours END) handled_h, MAX(CASE WHEN COALESCE(l.total_cost,0)=0 THEN 1 ELSE 0 END) no_cost "
                        f"FROM pronto_labour l LEFT JOIN cbs_node n ON n.id=l.node_id WHERE l.project_id=? AND l.posted=0 "
                        f"GROUP BY l.resource_code, l.month, l.node_id ORDER BY l.month DESC, person", (pid,))
    reqs = db.rows(con, "SELECT * FROM timesheet_request WHERE project_id=? ORDER BY requested_at DESC", (pid,))
    for r in rows:
        r["requests"] = [q for q in reqs if q["resource_code"] == r["resource_code"] and q["date_from"] <= r["d1"] and q["date_to"] >= r["d0"]]
        live = [q for q in r["requests"] if q["status"] == "requested"]
        r["state"] = "journal requested" if live else ("accrued by you" if r["handled_h"] and not r["auto"] else "accrued automatically" if r["auto"] else "accrued by you")
    return rows, reqs


def _close_requests(con, pid):
    """A journal request is done once Pronto no longer has those hours on this project."""
    n = 0
    for q in db.rows(con, "SELECT * FROM timesheet_request WHERE project_id=? AND status='requested'", (pid,)):
        left = db.scalar(con, "SELECT COUNT(*) FROM pronto_labour WHERE project_id=? AND resource_code=? AND date_worked BETWEEN ? AND ?",
                         (pid, q["resource_code"], q["date_from"], q["date_to"]))
        if not left:
            with changelog.via("Automatic: the hours are no longer on this project in Pronto"):
                db.update(con, "timesheet_request", q["id"], dict(status="done", done_at=date.today().isoformat()))
            n += 1
    return n


def _match_hours(con, pid):
    """Hours accrued for a person on a day stop counting once a POSTED timesheet for that person and day is in Pronto
    (posted = approved and costed, so the $ is an actual). An unposted timesheet has no cost yet: the accrual stands."""
    landed = {}
    for r in con.execute("SELECT resource_code, date_worked, SUM(hours) h, SUM(total_cost) c FROM pronto_labour WHERE project_id=? AND posted=1 GROUP BY resource_code, date_worked", (pid,)):
        landed[(r["resource_code"], r["date_worked"])] = (r["h"] or 0, r["c"] or 0)
    n = 0
    for a in db.rows(con, "SELECT a.*, r.code rcode, r.kind rkind FROM accrual a JOIN resource r ON r.id=a.resource_id WHERE a.project_id=? "
                          "AND a.hours IS NOT NULL AND a.day IS NOT NULL AND a.status IN ('open','partial','matched','investigate') AND COALESCE(a.inv_ref,'')=''", (pid,)):
        if a["rkind"] != "employee":
            continue
        hit = landed.get((a["rcode"], a["day"]))
        acc_h = a["hours"] or 0
        if not hit:
            new, via = ("open", None, None), "Automatic: timesheet no longer in Pronto"
        elif hit[0] >= acc_h - 0.01:
            # the timesheet covers the accrual: reversed (matched when the hours are equal, flagged when the timesheet is more)
            new = ("matched" if abs(hit[0] - acc_h) < 0.01 else "investigate", round(hit[1], 2), a["day"])
            via = "Automatic: timesheet landed in Pronto" if new[0] == "matched" else "Automatic: timesheet landed for more hours than accrued"
        else:
            # the timesheet covers part of it: that part reverses, the rest stays accrued (actual + accrual on one day)
            new = ("partial", round(hit[0] * (a["rate"] or 0), 2), a["day"])
            via = "Automatic: timesheet landed for fewer hours than accrued; the rest stays accrued"
        if (a["status"], a["matched_amount"]) != (new[0], new[1]):
            with changelog.via(via):
                db.update(con, "accrual", a["id"], dict(status=new[0], matched_amount=new[1], matched_date=new[2]))
            n += 1
    return n


def landed_refs(con, pid):
    """Normalised invoice and document references already in the GL (used to retire claim-driven accruals)."""
    refs = set()
    for r in con.execute("SELECT reference, doc_no FROM pronto_tx WHERE project_id=? AND class='actual' AND doc_type IN ('CV','PO')", (pid,)):
        for k in (_n(r["reference"]), _n(r["doc_no"])):
            if k:
                refs.add(k)
    return refs


def already_landed(con, pid, inv_ref):
    """The GL invoice(s) carrying this invoice number, if it has already landed (then there is nothing to accrue)."""
    k, d = _n(inv_ref), _digits(inv_ref)
    if not k:
        return []
    return [i for i in gl_invoices(con, pid) if k in (_n(i["ref"]), _n(i["doc_no"])) or (d and d in (_digits(i["ref"]), _digits(i["doc_no"])))]


# ---- three timelines: work performed, billing, cash ------------------------------------------------------------
def timelines(con, pid, group=None):
    """Cost by month three ways, for the project or one category group (PL / PS / PM / PE):
      work     when the work was done: Pronto cost by GL month plus accruals in their work month (matched invoices in the
               month accrued, reversed when they land), unposted timesheets, subcontract claims;
      billed   when the cost was billed: supplier invoices by invoice date, posted timesheets, journals, by GL month;
      paid     when the money leaves: supplier invoices at invoice date + supplier terms (Settings), labour the month it
               is billed. Pronto's GL carries no payment dates, so payments are modelled from terms."""
    st = db.project_settings(con, pid)
    terms = int(float(st.get("supplier_terms_days") or 30))
    p = db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,)) or {}
    M = (p.get("status_date") or date.today().isoformat())[:7]
    nodes = {r["id"]: r["code"] for r in db.rows(con, "SELECT id, code FROM cbs_node WHERE project_id=?", (pid,))}
    ok = (lambda nid: True) if not group else (lambda nid: (nodes.get(nid) or "").startswith(group))
    work, billed, paid = defaultdict(float), defaultdict(float), defaultdict(float)
    for r in db.rows(con, "SELECT node_id, month, tx_date, doc_type, class, cost, account_desc, description, reference FROM pronto_tx "
                          "WHERE project_id=? AND class IN ('actual','journal') AND node_id IS NOT NULL", (pid,)):
        if not ok(r["node_id"]):
            continue
        c = r["cost"] or 0
        work[r["month"]] += c
        if r["class"] == "journal" and _is_pronto_accrual_line(r):
            continue                       # finance's accruals are work timing, not bills
        billed[r["month"]] += c
        if r["doc_type"] in ("PO", "CV") and r["tx_date"]:
            paid[(date.fromisoformat(r["tx_date"][:10]) + timedelta(days=terms)).isoformat()[:7]] += c
        else:
            paid[r["month"]] += c
    acc_by = defaultdict(float)
    for nid, m, amt, src in counted(con, pid):
        if ok(nid):
            work[m] += amt
            acc_by[m] += amt
    months = sorted(set(work) | set(billed) | set(paid))
    cum = lambda d: [round(sum(d.get(x, 0.0) for x in months[:i + 1]), 2) for i in range(len(months))]
    return dict(months=months, status_month=M, terms_days=terms, group=group,
                work=[round(work.get(m, 0.0), 2) for m in months], billed=[round(billed.get(m, 0.0), 2) for m in months], paid=[round(paid.get(m, 0.0), 2) for m in months],
                accrued=[round(acc_by.get(m, 0.0), 2) for m in months], cum_work=cum(work), cum_billed=cum(billed), cum_paid=cum(paid),
                unbilled=round(sum(work.values()) - sum(billed.values()), 2), unpaid=round(sum(v for m, v in billed.items()) - sum(v for m, v in paid.items() if m <= M), 2))


def _is_pronto_accrual_line(r):
    """A finance accrual journal on Work in Progress (see pronto_accruals)."""
    return r.get("class") == "journal" and ("work in progress" in (r.get("account_desc") or "").lower() or "ACCRUAL" in (r.get("reference") or "").upper()) \
        and bool(WIP_RE.search(f"{r.get('description') or ''} {r.get('reference') or ''}"))


# ---- the master list: every accrual from every source in one table, to filter by employee or company ----------------------
SOURCES = {
    "estimate": dict(label="Your estimate", risk="Highest risk: no document behind it. Adjust or reverse it when the invoice lands.", tone="warn"),
    "approval": dict(label="Awaiting approval", risk="Invoice or claim received, not yet approved and entered in Pronto. Reverses itself when it lands.", tone=""),
    "claim": dict(label="Subcontract claim", risk="From a received claim and its approval. Reverses itself when its invoice lands.", tone=""),
    "finance": dict(label="Finance journal (Pronto)", risk="Work in Progress journal in Pronto. Read only: change it in Pronto.", tone="navy"),
    "timesheet": dict(label="Unposted timesheet", risk="Hours listed but not yet costed at a rate. Reverses when the timesheet posts.", tone=""),
}


def _clean(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def estimate_hints(con, pid, rows):
    """For estimates (accruals with no document behind them): an invoice that has landed in Pronto on the same line and PO or supplier
    since the work month. Estimates never match by themselves, so this is a nudge: adjust or reverse the estimate."""
    inv = gl_invoices(con, pid)
    out = {}
    for a in rows:
        if _kind(a) != "work" or a.get("status") not in ("open", "partial"):
            continue
        po, sup = _clean(a.get("po_no")), _clean(a.get("supplier_name"))
        if not (po or sup):
            continue
        hit = [i for i in inv if a["node_id"] in i["nodes"] and (i["month"] or "") >= a["month"]
               and ((po and _clean(i["po"]) == po) or (sup and sup in _clean(i["supplier_name"])))]
        if hit:
            i = hit[0]
            out[a["id"]] = f"Invoice {i['ref']} ({i['amount']:,.2f}) landed in Pronto in {i['month']} on this line: adjust or reverse this estimate."
    return out


def timesheet_people(con, pid, category, month):
    """The people behind a payroll accrual: Pronto's labour rows for the cost category and work month (finance's timesheet accrual
    journal names no one). Hours, posted cost, and the cost of what is still unposted."""
    if not category or not month:
        return []
    return db.rows(con, f"SELECT l.resource_code, MAX(l.name) person, MIN(l.date_worked) d0, MAX(l.date_worked) d1, SUM(l.hours) hours, "
                        f"SUM(CASE WHEN l.posted=1 THEN COALESCE(l.total_cost,0) ELSE 0 END) posted_cost, "
                        f"SUM(CASE WHEN l.posted=0 THEN l.hours ELSE 0 END) unposted_hours, SUM(CASE WHEN l.posted=0 THEN {UNPOSTED_COST} ELSE 0 END) unposted_cost "
                        f"FROM pronto_labour l WHERE l.project_id=? AND l.month=? AND (l.category=? OR l.node_id IN "
                        f"(SELECT id FROM cbs_node WHERE project_id=? AND (code=? OR code LIKE ?))) GROUP BY l.resource_code ORDER BY person",
                   (pid, month, category, pid, category, category + ".%"))


def master(con, pid):
    """Every accrual in one list: {rows, parties}. Source: estimate | approval | claim | finance | timesheet. party_type company or
    employee. 'counts' is what PMT counts in ACC now (after finance's own accrual covers it)."""
    from . import subcontracts
    nodes = {r["id"]: r for r in db.rows(con, "SELECT id, code, name FROM cbs_node WHERE project_id=?", (pid,))}
    names = {r["id"]: (r["name"] or r["code"]) for r in db.rows(con, "SELECT id, code, name FROM resource WHERE project_id=?", (pid,))}
    rkind = {r["code"]: r["kind"] for r in db.rows(con, "SELECT code, kind FROM resource WHERE project_id=?", (pid,))}   # employee or supplier (a subcontractor's timesheets are a company's)
    cover = pronto_cover(con, pid)
    manual = db.rows(con, "SELECT * FROM accrual WHERE project_id=? AND status!='cancelled' ORDER BY month DESC, id DESC", (pid,))
    hints = estimate_hints(con, pid, manual)
    out = []

    def row(**k):
        n = nodes.get(k.get("node_id")) or {}
        base = dict(code=n.get("code", ""), line=n.get("name", ""), po="", quote="", invoice="", detail="", hint="", editable=False, people=[], link=None)
        base.update(k)
        out.append(base)

    for a in manual:
        kind = _kind(a)
        left = a["amount"] or 0
        if a["status"] == "open":
            left = (a["amount"] or 0) - cover.get(a["id"], 0.0)
        elif a["status"] == "partial":
            left = max(0.0, (a["amount"] or 0) - (a["matched_amount"] or 0))
        elif a["status"] in ("matched", "investigate"):
            left = 0.0 if a["status"] == "matched" else (a["amount"] or 0)
        if kind == "hours" and not a.get("inv_ref"):
            who = names.get(a.get("resource_id")) or "(person not named)"
            row(key=f"a{a['id']}", source="timesheet", party=who, party_type="employee", node_id=a["node_id"], month=a["month"], amount=a["amount"] or 0, counts=left,
                status=a["status"], detail=f"{(a.get('hours') or 0):g} h on {a.get('day') or a['month']}, accrued by you at the person's rate", editable=False,
                link=dict(type="calendar"))
            continue
        src = "approval" if kind == "invoice" else "estimate"
        row(key=f"a{a['id']}", source=src, party=a.get("supplier_name") or "(no company named)", party_type="company", node_id=a["node_id"], month=a["month"],
            amount=a["amount"] or 0, counts=left, status=a["status"], po=a.get("po_no") or "", quote=a.get("quote_ref") or "", invoice=a.get("inv_ref") or "",
            detail=a.get("note") or "", hint=hints.get(a["id"], ""), editable=True, link=dict(type="accrual", id=a["id"], node_id=a["node_id"]))
    for c in subcontracts.claim_accruals(con, pid, landed_refs(con, pid)):
        sub = db.one(con, "SELECT * FROM subcontract WHERE id=?", (c["sub_id"],)) or {}
        cl = db.one(con, "SELECT * FROM sub_claim WHERE id=?", (c["claim_id"],)) or {}
        t = subcontracts.claim_totals(con, cl, sub) if cl and sub else {}
        det = f"Claim {c['claim_no']}: {c['basis']}" + (f" (claimed {t['claimed']:,.2f}, approved {t['approved']:,.2f})" if t and t.get("approved_lines") else "")
        row(key=f"c{c['claim_id']}", source="claim", party=sub.get("supplier_name") or sub.get("supplier_code") or c["subcontract"], party_type="company", node_id=c["node_id"],
            month=c["month"], amount=c["amount"], counts=c["amount"], status="open", po=sub.get("po_no") or "", invoice=c.get("inv_ref") or "", detail=det,
            link=dict(type="claim", sub_id=c["sub_id"]))
    for p in pronto_accruals(con, pid):
        ts = p["kind"] == "timesheet"
        people = [x["person"] or x["resource_code"] for x in timesheet_people(con, pid, p["category"], p["month"])] if ts else []
        row(key=f"f{p['node_id']}|{p['reference']}|{p['month']}", source="finance", party=p["supplier"], party_type="employee" if ts else "company", node_id=p["node_id"],
            month=p["month"], amount=p["accrued"], counts=max(0.0, p["open"]), status="open" if p["open"] > 0.5 else "reversed", po=p.get("po") or "",
            detail=(p["reference"] or "") + (f" · reversed {abs(p['reversed']):,.2f}" if p["reversed"] else ""), people=people,
            link=dict(type="people", category=p["category"], month=p["month"], amount=p["accrued"]) if ts else dict(type="finance"))
    for u in unposted(con, pid)[0]:
        who = u["person"] or u["resource_code"]
        row(key=f"u{u['resource_code']}|{u['month']}|{u['node_id']}", source="timesheet", party=who, party_type="company" if rkind.get(u["resource_code"]) == "supplier" else "employee", node_id=u["node_id"], month=u["month"],
            amount=u["amount"] or 0, counts=u["auto"] or 0, status=u["state"], detail=f"{u['hours']:g} h" + ("" if u["amount"] else ", no rate yet"),
            link=dict(type="people", category=(nodes.get(u["node_id"]) or {}).get("code", "")[:4], month=u["month"], resource_code=u["resource_code"]))
    parties, shown = {}, {}
    for r in out:
        t = "company" if r["party_type"] == "company" else "employee"
        for nm in ([r["party"]] if t == "company" or not r["people"] else r["people"]):
            if nm:
                # the same name in another case or punctuation is one party; the first spelling seen is the one shown
                k = (_clean(nm), t)
                shown.setdefault(k, nm)
                p = parties.setdefault(k, dict(name=shown[k], type=t, n=0))
                p["n"] += 1
        if t == "company":
            r["party"] = shown[(_clean(r["party"]), t)]
        r["party_type"] = t
        r["people"] = [shown[(_clean(n), "employee")] for n in r["people"] if n]
    out.sort(key=lambda r: (r["counts"] == 0, r["month"] or ""), reverse=False)
    return dict(rows=out, parties=sorted(parties.values(), key=lambda p: (p["type"], p["name"].lower())), sources=SOURCES)
