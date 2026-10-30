"""Suppliers and purchase orders known from Pronto, and how subcontracts tie to them.

A subcontract names its supplier and PO. Either both are already in the Pronto data (the supplier code fills itself and
the PO is picked from that supplier's orders), or they are entered ahead of Pronto: a new supplier by name, or a PO
number not yet raised. Those stay "to be matched" until the Pronto data has them; the diagnostics page lists them and
suggests the Pronto supplier whose name is closest.
"""
import difflib
import re
from collections import defaultdict

from . import db


def _norm(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s or "").upper())
    s = re.sub(r"\b(PTY|LTD|LIMITED|P L|THE|AND|CO|COMPANY|GROUP|AUSTRALIA|AUST)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def known(con, pid):
    """Every supplier Pronto has given PMT (register, purchase orders, transactions): code -> {code, name, pos}."""
    out = {}
    for r in con.execute("SELECT code, name FROM resource WHERE project_id=? AND kind='supplier'", (pid,)):
        out[r["code"]] = dict(code=r["code"], name=r["name"] or r["code"], pos={})
    for r in con.execute("SELECT DISTINCT resource_code FROM pronto_tx WHERE project_id=? AND resource_code IS NOT NULL AND resource_code!=''", (pid,)):
        out.setdefault(r["resource_code"], dict(code=r["resource_code"], name=r["resource_code"], pos={}))
    pos = defaultdict(lambda: dict(committed=0.0, received=0.0, open=False, lines=0, categories=set(), nodes=set()))
    who = {}
    for r in con.execute("SELECT order_no, supplier_code, supplier_name, committed, received, is_open, category, node_id FROM pronto_po WHERE project_id=? AND order_no IS NOT NULL", (pid,)):
        code = r["supplier_code"] or ""
        if code:
            s = out.setdefault(code, dict(code=code, name=r["supplier_name"] or code, pos={}))
            if s["name"] == code and r["supplier_name"]:
                s["name"] = r["supplier_name"]
        p = pos[r["order_no"]]
        p["committed"] += r["committed"] or 0
        p["received"] += r["received"] or 0
        p["open"] = p["open"] or bool(r["is_open"])
        p["lines"] += 1
        if r["category"]:
            p["categories"].add(r["category"])
        if r["node_id"]:
            p["nodes"].add(r["node_id"])
        who[r["order_no"]] = code
    codes = {r["id"]: r["code"] for r in con.execute("SELECT id, code FROM cbs_node WHERE project_id=?", (pid,))}
    for no, p in pos.items():
        s = out.get(who.get(no))
        if s is not None:
            s["pos"][no] = dict(order_no=no, committed=round(p["committed"], 2), received=round(p["received"], 2), open=p["open"], lines=p["lines"],
                                categories=sorted(p["categories"]), cbs=sorted(codes[n] for n in p["nodes"] if n in codes))
    return out


def all_pos(con, pid):
    """order_no -> {supplier_code, committed, ...} over every Pronto purchase order."""
    return {no: dict(po, supplier_code=s["code"]) for s in known(con, pid).values() for no, po in s["pos"].items()}


def listing(con, pid):
    """For the pickers: suppliers sorted by name with their POs, and which subcontracts already use each."""
    subs = defaultdict(list)
    for r in con.execute("SELECT id, name, supplier_code FROM subcontract WHERE project_id=?", (pid,)):
        if r["supplier_code"]:
            subs[r["supplier_code"]].append(r["name"])
    out = []
    for s in known(con, pid).values():
        out.append(dict(code=s["code"], name=s["name"], pos=sorted(s["pos"].values(), key=lambda p: p["order_no"]), subcontracts=subs.get(s["code"], [])))
    return sorted(out, key=lambda s: (s["name"] or "").upper())


def suggest(con, pid, name, k=3, cutoff=0.6):
    """Pronto suppliers whose name is closest to a name typed ahead of Pronto: [(code, name, score)]."""
    n = _norm(name)
    if not n:
        return []
    res = []
    for s in known(con, pid).values():
        m = _norm(s["name"])
        if not m:
            continue
        score = difflib.SequenceMatcher(None, n, m).ratio()
        if n in m or m in n:
            score = max(score, 0.9)
        if score >= cutoff:
            res.append((s["code"], s["name"], round(score, 2)))
    return sorted(res, key=lambda x: -x[2])[:k]


def link_state(con, pid, sub, kn=None, pos=None):
    """How a subcontract ties to Pronto: supplier 'pronto' | 'pending' | 'missing', PO 'pronto' | 'pending' | 'missing',
    and what to check (a PO under another supplier, a PO value different from the contract)."""
    kn = kn if kn is not None else known(con, pid)
    pos = pos if pos is not None else all_pos(con, pid)
    code, po = sub.get("supplier_code"), (sub.get("po_no") or "").strip()
    sup = "pronto" if code and code in kn else ("pending" if (code or sub.get("supplier_name")) else "missing")
    pst = "pronto" if po and po in pos else ("pending" if po else "missing")
    notes = []
    if pst == "pronto" and code and pos[po]["supplier_code"] and pos[po]["supplier_code"] != code:
        notes.append(f"PO {po} belongs to supplier {pos[po]['supplier_code']} in Pronto, not {code}.")
    if pst == "pronto" and sub.get("contract_value") and abs(pos[po]["committed"] - sub["contract_value"]) > 1:
        notes.append(f"PO {po} is {pos[po]['committed']:,.0f} in Pronto; the subcontract value is {sub['contract_value']:,.0f}.")
    return dict(supplier=sup, po=pst, notes=notes, po_info=pos.get(po) if pst == "pronto" else None,
                supplier_name=(kn[code]["name"] if sup == "pronto" else sub.get("supplier_name") or code or ""))
