"""COST > Actuals > Invoices by supplier: every supplier invoice in the Pronto GL export, per supplier.

An invoice is what Pronto posted against a supplier: a purchase-order receipt (document type PO, the supplier invoice
matched to the order) or a direct creditor invoice (CV, no order), plus journals that re-code a supplier's cost (GJ/GV).
One invoice can post on several GL lines (categories / CBS lines); they are grouped back into one invoice by supplier,
document, suffix, reference and date. Labour timesheets (TS) are not invoices and stay on the labour calendar.
Each supplier shows its purchase orders (committed, received) and, for a subcontractor, its subcontract in PMT with the
claims approved to date, so "approved but not yet invoiced" is visible.
"""
import io
import re
from collections import defaultdict

from . import db, subcontracts, suppliers

KINDS = {"PO": "PO receipt", "CV": "Direct invoice", "GJ": "Journal", "GV": "Journal reversal"}
GROUPS = {"PS": "Subcontractors", "PM": "Materials and equipment", "PE": "Expenses", "PL": "Labour"}


def _n(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def listing(con, pid):
    p = db.one(con, "SELECT status_date FROM project WHERE id=?", (pid,)) or {}
    M = (p.get("status_date") or "")[:7]
    codes = {r["id"]: r["code"] for r in con.execute("SELECT id, code FROM cbs_node WHERE project_id=?", (pid,))}
    known = suppliers.known(con, pid)
    rows = db.rows(con, "SELECT * FROM pronto_tx WHERE project_id=? AND class IN ('actual','journal') AND doc_type IN ('PO','CV','GJ','GV') "
                        "AND COALESCE(resource_code,'')!='' ORDER BY tx_date, id", (pid,))
    # subcontract claims with an invoice reference: link the invoice to its claim
    subs = db.rows(con, "SELECT * FROM subcontract WHERE project_id=?", (pid,))
    claim_by_ref = {}
    for s in subs:
        for c in subcontracts.claims_of(con, s["id"]):
            if c.get("inv_ref"):
                claim_by_ref[_n(c["inv_ref"])] = dict(sub_id=s["id"], claim_id=c["id"], claim_no=c.get("claim_no"), month=c.get("month"))

    inv = {}
    for r in rows:
        key = (r["resource_code"], r["doc_type"], r["doc_no"], r["doc_suffix"], r["reference"], r["tx_date"])
        i = inv.get(key)
        if i is None:
            ref = r["reference"] or f"{r['doc_no'] or ''}{r['doc_suffix'] or ''}"
            i = inv[key] = dict(supplier=r["resource_code"], date=r["tx_date"], month=r["month"], ref=ref, kind=KINDS.get(r["doc_type"], r["doc_type"]),
                                doc_type=r["doc_type"], po=r["po_no"], description=r["description"] or "", amount=0.0, lines=0, categories=set(), cbs=set(),
                                claim=claim_by_ref.get(_n(ref)) or claim_by_ref.get(_n(r["reference"])))
        i["amount"] += r["cost"] or 0
        i["lines"] += 1
        if r["category"]:
            i["categories"].add(r["category"])
        if r["node_id"] in codes:
            i["cbs"].add(codes[r["node_id"]])
        if not i["po"] and r["po_no"]:
            i["po"] = r["po_no"]
    invoices = []
    for i in inv.values():
        i["amount"] = round(i["amount"], 2)
        i["categories"], i["cbs"] = sorted(i["categories"]), sorted(i["cbs"])
        invoices.append(i)
    invoices.sort(key=lambda i: (i["date"] or "", i["ref"] or ""), reverse=True)

    names = {}
    for r in rows:
        names.setdefault(r["resource_code"], r["account_desc"])
    sub_of = {}
    summ = {s["id"]: s for s in subcontracts.summary(con, pid)}
    for s in subs:
        if s.get("supplier_code"):
            sub_of.setdefault(s["supplier_code"], []).append(summ.get(s["id"], s))
    by = defaultdict(list)
    for i in invoices:
        by[i["supplier"]].append(i)
    out = []
    for code, lst in by.items():
        k = known.get(code) or {}
        cats = defaultdict(float)
        months = defaultdict(float)
        for i in lst:
            for c in i["categories"] or [""]:
                cats[c[:2]] += i["amount"] / max(1, len(i["categories"]) or 1)
            months[i["month"]] += i["amount"]
        group = max(cats, key=lambda g: abs(cats[g])) if cats else ""
        total = sum(i["amount"] for i in lst)
        pos = list((k.get("pos") or {}).values())
        sc = sub_of.get(code, [])
        approved = sum(s.get("claimed_gross") or 0 for s in sc)
        out.append(dict(
            code=code, name=(k.get("name") if k.get("name") and k.get("name") != code else None) or names.get(code) or code,
            group=group, group_name=GROUPS.get(group, "Other"), invoices=len(lst), total=round(total, 2), this_month=round(months.get(M, 0.0), 2),
            first=min(i["date"] for i in lst), last=max(i["date"] for i in lst), last_amount=lst[0]["amount"],
            months={m: round(v, 2) for m, v in sorted(months.items())},
            pos=sorted(pos, key=lambda x: x["order_no"]), po_committed=round(sum(x["committed"] for x in pos), 2), po_received=round(sum(x["received"] for x in pos), 2),
            subcontracts=[dict(id=s["id"], name=s["name"], contract_value=s.get("contract_value"), approved=round(s.get("claimed_gross") or 0, 2)) for s in sc],
            approved_not_invoiced=round(approved - total, 2) if sc else None))
    out.sort(key=lambda s: -abs(s["total"]))
    return dict(status_month=M, suppliers=out, invoices=invoices, total=round(sum(s["total"] for s in out), 2), groups=GROUPS)


def xlsx(con, pid):
    """The same, for Excel: suppliers, then every invoice."""
    import xlsxwriter
    d = listing(con, pid)
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    hd = wb.add_format({"bold": True, "font_color": "white", "bg_color": "#102361", "border": 1})
    money = wb.add_format({"num_format": "#,##0.00;[Red]-#,##0.00"})
    date = wb.add_format({"num_format": "dd/mm/yyyy"})
    names = {s["code"]: s["name"] for s in d["suppliers"]}
    ws = wb.add_worksheet("Suppliers")
    cols = ["Supplier code", "Supplier", "Group", "Invoices", "Invoiced to date", f"Invoiced {d['status_month']}", "First invoice", "Last invoice",
            "PO committed", "PO received", "Subcontract", "Claims approved", "Approved not invoiced"]
    ws.write_row(0, 0, cols, hd)
    for r, s in enumerate(d["suppliers"], 1):
        ws.write_row(r, 0, [s["code"], s["name"], s["group_name"], s["invoices"]])
        ws.write_number(r, 4, s["total"], money)
        ws.write_number(r, 5, s["this_month"], money)
        ws.write(r, 6, s["first"]), ws.write(r, 7, s["last"])
        ws.write_number(r, 8, s["po_committed"], money)
        ws.write_number(r, 9, s["po_received"], money)
        ws.write(r, 10, ", ".join(x["name"] for x in s["subcontracts"]))
        if s["subcontracts"]:
            ws.write_number(r, 11, sum(x["approved"] for x in s["subcontracts"]), money)
            ws.write_number(r, 12, s["approved_not_invoiced"], money)
    ws.set_column(0, 0, 13), ws.set_column(1, 1, 36), ws.set_column(2, 2, 22), ws.set_column(3, 12, 15)
    ws.autofilter(0, 0, len(d["suppliers"]), len(cols) - 1), ws.freeze_panes(1, 2)
    wi = wb.add_worksheet("Invoices")
    cols = ["Date", "Month", "Supplier code", "Supplier", "Invoice / reference", "Type", "PO", "Description", "Categories", "CBS lines", "Amount", "Subcontract claim"]
    wi.write_row(0, 0, cols, hd)
    from datetime import date as _d
    for r, i in enumerate(d["invoices"], 1):
        try:
            wi.write_datetime(r, 0, _d.fromisoformat(i["date"]), date)
        except (TypeError, ValueError):
            wi.write(r, 0, i["date"])
        wi.write_row(r, 1, [i["month"], i["supplier"], names.get(i["supplier"], ""), i["ref"], i["kind"], i["po"] or "", i["description"],
                            ", ".join(i["categories"]), ", ".join(i["cbs"])])
        wi.write_number(r, 10, i["amount"], money)
        wi.write(r, 11, f"Claim {i['claim']['claim_no'] or ''} ({i['claim']['month']})" if i["claim"] else "")
    wi.set_column(0, 1, 11), wi.set_column(2, 2, 13), wi.set_column(3, 3, 30), wi.set_column(4, 6, 15), wi.set_column(7, 7, 44), wi.set_column(8, 9, 16), wi.set_column(10, 11, 16)
    wi.autofilter(0, 0, len(d["invoices"]), len(cols) - 1), wi.freeze_panes(1, 0)
    wb.close()
    return buf.getvalue()
