"""Pronto data > Inspect: the rows exactly as PMT loaded them from each Pronto report, and checks that point at rows that
deserve a look before trusting the numbers:

  future     dated after the status month (in Pronto itself: often a date keyed with the wrong year); still in CTD
  totals     rows that look like a report's totals or a blank line rather than a transaction (no category or date, a
             TOTAL label, or one row worth exactly the sum of all the others)
  reversed   very large entries cancelled by an opposite entry soon after (a keying error in Pronto and its correction):
             they net to nothing but swell a month's figures
  duplicates identical rows (same date, category, account, document, reference and amount)
Each check filters the row viewer to its rows.
"""
import io
import re
from collections import defaultdict
from datetime import date

from . import db

# kind -> table, date column, amount column, columns shown (column, label)
RAW = {
    "transactions": ("pronto_tx", "tx_date", "cost", [("tx_date", "Date"), ("month", "Month"), ("category", "Category"), ("cat_desc", "Category description"),
                     ("account_code", "Account"), ("account_desc", "Account description"), ("type", "Type"), ("doc_type", "Doc type"), ("doc_no", "Doc no"),
                     ("doc_suffix", "Suffix"), ("reference", "Reference"), ("description", "Description"), ("qty", "Hrs / qty"), ("cost", "Cost"),
                     ("variation_no", "Variation"), ("fin_year", "Fin year"), ("fin_period", "Period"), ("class", "PMT class"), ("node_code", "CBS line")]),
    "labour": ("pronto_labour", "date_worked", "total_cost", [("date_worked", "Worked"), ("month", "Month"), ("resource_code", "Resource"), ("name", "Name"),
               ("work_rate_code", "Rate code"), ("work_rate", "Work rate"), ("category", "Category"), ("status", "Status"), ("approved", "Approved"), ("posted", "Posted"),
               ("hours", "Hours"), ("cost_rate", "Cost rate"), ("total_cost", "Cost"), ("notes", "Notes"), ("node_code", "CBS line")]),
    "po": ("pronto_po", "ordered", "committed", [("order_no", "PO"), ("status", "Status"), ("order_type", "Type"), ("supplier_code", "Supplier"), ("supplier_name", "Supplier name"),
           ("ordered", "Ordered"), ("due", "Due"), ("received_date", "Received"), ("category", "Category"), ("committed", "Committed"), ("received", "Received $"),
           ("invoiced_inc_tax", "Invoiced inc GST"), ("is_open", "Open"), ("notes", "Notes"), ("node_code", "CBS line")]),
    "claims": ("pronto_claim", "date_submitted", "total", [("claim_no", "Claim"), ("description", "Description"), ("status", "Status"), ("status_desc", "Status description"),
               ("date_created", "Created"), ("date_submitted", "Submitted"), ("date_certified", "Certified"), ("date_paid", "Paid"), ("total", "Total"), ("certified", "Certified $"),
               ("retained", "Retained"), ("paid", "Paid $"), ("order_no", "Order")]),
    "variations": ("pronto_variation", "approved_date", "approved", [("variation_no", "Variation"), ("status", "Status"), ("description", "Description"), ("expected", "Expected"),
                   ("approved", "Approved"), ("total_cost", "Cost"), ("total_hours", "Hours"), ("approved_date", "Approved on"), ("customer_ref", "Customer ref"), ("instructed_by", "Instructed by")]),
    "ctd": ("pronto_ctd", None, "actual", [("category", "Category"), ("description", "Description"), ("cat_type", "Type"), ("actual", "Actual"), ("budget", "Budget"),
            ("hrs_actual", "Hours actual"), ("hrs_budget", "Hours budget")]),
}
BIG = 1_000_000          # entries this large that are reversed soon after are flagged
PAIR_DAYS = 62
TOTAL_RE = re.compile(r"\s*(GRAND\s+|SUB\s*-?\s*)?TOTALS?\b", re.I)


def _cutoff(con, pid):
    """The last date a Pronto row can carry: the end of the status month, or today if later. A row dated after it is in
    the future: it still counts in cost to date (it is an actual in Pronto) but it is a keying error to raise."""
    p = db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,)) or {}
    sd = p.get("status_date") or date.today().isoformat()
    return max(db.month_end(sd[:7]), date.today().isoformat())


def future_rows(con, pid):
    """GL rows dated in the future: [{tx_date, category, doc_type, doc_no, reference, account_desc, description, cost}]."""
    return db.rows(con, "SELECT tx_date, category, doc_type, doc_no, reference, account_desc, description, cost, fin_year, fin_period FROM pronto_tx "
                        "WHERE project_id=? AND tx_date>? ORDER BY tx_date, doc_no", (pid, _cutoff(con, pid)))


def _select(kind):
    tbl, dcol, acol, cols = RAW[kind]
    join = "LEFT JOIN cbs_node n ON n.id=t.node_id" if any(c == "node_code" for c, _ in cols) else ""
    fields = ", ".join(("n.code AS node_code" if c == "node_code" else f"t.{c}") for c, _ in cols)
    return f"SELECT t.id, {fields} FROM {tbl} t {join} WHERE t.project_id=?"


def checks(con, pid):
    """[{id, kind, level, title, detail, count, amount, ids}] over every loaded report."""
    out = []
    cut = _cutoff(con, pid)
    for kind, (tbl, dcol, acol, cols) in RAW.items():
        n = db.scalar(con, f"SELECT COUNT(*) FROM {tbl} WHERE project_id=?", (pid,))
        if not n:
            continue
        rows = db.rows(con, _select(kind), (pid,))
        # future-dated
        if dcol:
            fut = [r for r in rows if r.get(dcol) and str(r[dcol])[:10] > cut]
            if fut:
                last = max(str(r[dcol])[:10] for r in fut)
                yrs = sorted({str(r.get("fin_year")) + " P" + str(r.get("fin_period")) for r in fut if r.get("fin_year")})
                out.append(dict(id=f"{kind}:future", kind=kind, level="warn", count=len(fut), amount=round(sum(r.get(acol) or 0 for r in fut), 2), ids=[r["id"] for r in fut],
                                title=f"{len(fut)} row(s) dated in the future (after {_d(cut)}), up to {_d(last)}",
                                detail="Dated in the future in Pronto itself" + (f" (financial period {', '.join(yrs)})" if yrs else "") +
                                       ". An error in Pronto (often a date keyed with the wrong year): ask finance to correct it. They count in cost to date as every actual does."))
        # totals or blank lines
        amt_rows = [r for r in rows if r.get(acol) is not None]
        tot = []
        for r in rows:
            # a label field that starts with TOTAL (free-text notes are skipped: "LAFHA Qty 1 Rate $24.50 Total $24.50" is a real timesheet)
            labelled = any(TOTAL_RE.match(str(r.get(c) or "")) for c, _ in cols if c not in (acol, "notes"))
            blank_key = (kind == "transactions" and not r.get("category")) or (dcol and kind in ("transactions", "labour") and not r.get(dcol))
            if blank_key or labelled:
                tot.append(r)
        if len(amt_rows) > 2:
            s = sum(r[acol] for r in amt_rows)
            big = max(amt_rows, key=lambda r: abs(r[acol]))
            if abs(big[acol]) > 1 and abs(big[acol] - (s - big[acol])) < 0.5 and big not in tot:
                tot.append(big)
        if tot:
            out.append(dict(id=f"{kind}:totals", kind=kind, level="bad", count=len(tot), amount=round(sum(r.get(acol) or 0 for r in tot), 2), ids=[r["id"] for r in tot],
                            title=f"{len(tot)} row(s) that look like totals or blank lines",
                            detail="No category or date, a TOTAL label, or worth exactly the sum of all the other rows. A report's totals row loaded as a transaction would double the figures."))
        else:
            out.append(dict(id=f"{kind}:totals", kind=kind, level="ok", count=0, amount=0, ids=[], title="No totals or blank rows",
                            detail=f"All {n:,} rows look like real entries."))
        # large cost entries reversed soon after (finance's month-end accruals and their reversals are routine, not counted)
        if kind == "transactions":
            pairs, seen = [], set()
            big = sorted([r for r in rows if abs(r.get("cost") or 0) >= BIG and r.get("class") in ("actual", "journal")], key=lambda r: r["tx_date"] or "")
            for r in big:
                if r["id"] in seen or (r["cost"] or 0) <= 0 or r.get("class") != "actual":
                    continue
                for o in big:
                    if o["id"] in seen or o["id"] == r["id"] or (o["cost"] or 0) >= 0:
                        continue
                    if abs(r["cost"] + o["cost"]) <= max(0.01 * abs(r["cost"]), 1) and r["tx_date"] and o["tx_date"] and \
                            abs((date.fromisoformat(o["tx_date"][:10]) - date.fromisoformat(r["tx_date"][:10])).days) <= PAIR_DAYS:
                        pairs.append((r, o))
                        seen.update((r["id"], o["id"]))
                        break
            if pairs:
                out.append(dict(id="transactions:reversed", kind=kind, level="warn", count=len(pairs) * 2, amount=round(sum(a["cost"] + b["cost"] for a, b in pairs), 2),
                                ids=[x["id"] for p in pairs for x in p],
                                title=f"{len(pairs)} very large entr{'y' if len(pairs) == 1 else 'ies'} cancelled soon after (net {sum(a['cost'] + b['cost'] for a, b in pairs):,.2f})",
                                detail="; ".join(f"{a['account_desc'] or a['account_code']} {a['reference'] or a['doc_no']}: {a['cost']:,.0f} on {_d(a['tx_date'])}, "
                                                 f"{b['cost']:,.0f} on {_d(b['tx_date'])}" for a, b in pairs) +
                                       ". Keying errors corrected in Pronto: they net out, but swell those months' figures and the supplier's invoices."))
        # duplicates
        key_cols = [c for c, _ in cols if c not in ("node_code", "class")]
        groups = defaultdict(list)
        for r in rows:
            groups[tuple(r.get(c) for c in key_cols)].append(r)
        dup = [r for g in groups.values() if len(g) > 1 for r in g]
        if dup:
            out.append(dict(id=f"{kind}:duplicates", kind=kind, level="warn", count=len(dup), amount=round(sum(r.get(acol) or 0 for r in dup), 2), ids=[r["id"] for r in dup],
                            title=f"{len(dup)} identical row(s) in {sum(1 for g in groups.values() if len(g) > 1)} group(s)",
                            detail="Same date, category, account, document, reference and amount. Often genuine (two identical lines on one invoice); worth a look if a supplier's total seems high."))
    return out


def _d(iso):
    s = str(iso or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) == 10 else s


def rows(con, pid, kind, q=None, check=None, offset=0, limit=500, sort=None, desc=True):
    tbl, dcol, acol, cols = RAW[kind]
    allrows = db.rows(con, _select(kind), (pid,))
    if check:
        c = next((x for x in checks(con, pid) if x["id"] == check), None)
        keep = set(c["ids"]) if c else set()
        allrows = [r for r in allrows if r["id"] in keep]
    if q:
        words = q.lower().split()
        allrows = [r for r in allrows if all(w in " ".join(str(v) for v in r.values() if v is not None).lower() for w in words)]
    key = sort if sort in {c for c, _ in cols} else (dcol or cols[0][0])
    allrows.sort(key=lambda r: (r.get(key) is None, r.get(key) if not isinstance(r.get(key), str) else r.get(key).lower()), reverse=desc)
    total = sum(r.get(acol) or 0 for r in allrows)
    return dict(kind=kind, columns=[dict(key=c, label=l, money=c == acol or l.endswith("$") or c in ("committed", "received", "total", "certified", "paid", "retained", "expected", "approved", "actual", "budget", "total_cost")) for c, l in cols],
                amount_col=acol, count=len(allrows), amount=round(total, 2), rows=allrows[offset:offset + limit], offset=offset)


def xlsx(con, pid, kind, q=None, check=None):
    import xlsxwriter
    d = rows(con, pid, kind, q, check, 0, 10 ** 7)
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    ws = wb.add_worksheet(kind[:31])
    hd = wb.add_format({"bold": True, "font_color": "white", "bg_color": "#102361"})
    money = wb.add_format({"num_format": "#,##0.00;[Red]-#,##0.00"})
    ws.write_row(0, 0, [c["label"] for c in d["columns"]], hd)
    for i, r in enumerate(d["rows"], 1):
        for j, c in enumerate(d["columns"]):
            v = r.get(c["key"])
            if isinstance(v, (int, float)) and c["money"]:
                ws.write_number(i, j, v, money)
            else:
                ws.write(i, j, v)
    ws.autofilter(0, 0, len(d["rows"]), len(d["columns"]) - 1)
    ws.freeze_panes(1, 0)
    wb.close()
    return buf.getvalue()


def as_of(con, pid, kind):
    """The latest date of a report that is not in the future (the card's "to ..."), and how many rows are later."""
    tbl, dcol, _, _ = RAW[kind]
    if not dcol:
        return None, 0
    cut = _cutoff(con, pid)
    extra = " AND posted=1" if kind == "labour" else ""
    last = db.scalar(con, f"SELECT MAX({dcol}) FROM {tbl} WHERE project_id=? AND {dcol}<=?{extra}", (pid, cut), None)
    later = db.scalar(con, f"SELECT COUNT(*) FROM {tbl} WHERE project_id=? AND {dcol}>?", (pid, cut))
    return last, later
