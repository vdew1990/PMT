"""Drill-through for cost control: the records behind any amount, for a CBS node (or its unallocated pot), optionally for one month."""
from collections import defaultdict

from . import accruals, activity, db, engine, forecast, risk, services, subcontracts

TX_COLS = [("date", "Date", "date"), ("code", "CBS", "text"), ("doc", "Doc", "text"), ("doc_no", "Doc no", "text"), ("ref", "Reference", "text"), ("who", "Supplier / account", "text"),
           ("desc", "Description", "wrap"), ("qty", "Qty", "num"), ("amount", "Cost", "money")]


def _ids(con, pid, node):
    node = str(node)
    if node.startswith("p"):
        return [int(node[1:])], True
    return services.subtree_ids(con, pid, int(node)), False


def _section(title, cols, rows, total_key=None, note=None):
    total = sum((r.get(total_key) or 0) for r in rows) if total_key else None
    return dict(title=title, columns=[dict(key=k, label=l, type=t) for k, l, t in cols], rows=rows, total=total, total_label=dict((k, l) for k, l, t in cols).get(total_key), note=note)


def drill(con, pid, node, metric, month=None):
    res = engine.compute(con, pid)
    ids, is_pot = _ids(con, pid, node)
    q = ",".join("?" * len(ids))
    by_row = {str(r["id"]): r for r in res["rows"]}
    row = by_row.get(str(node))
    if not row:
        raise ValueError("Row not found")
    leaves = engine.scope_leaves(res, node)
    code_of = {r["id"]: r["code"] for r in res["rows"] if isinstance(r["id"], int)}
    M = res["status_month"]
    grid = res["grid"]
    out = dict(title=f"{row['code']} {row['name']}", metric=metric, month=month, sections=[], summary=None, status_month=M, method=row.get("method"))
    mfilter = " AND t.month=?" if month else ""
    margs = [month] if month else []

    if metric in ("ctd", "actual"):
        rows = db.rows(con, f"SELECT t.*, n.code ncode FROM pronto_tx t LEFT JOIN cbs_node n ON n.id=t.node_id WHERE t.project_id=? AND t.class IN ('actual','journal') AND t.node_id IN ({q}){mfilter} "
                            f"ORDER BY t.tx_date, t.id", [pid, *ids, *margs])
        det = [dict(date=r["tx_date"], code=r["ncode"], doc=r["doc_type"], doc_no=r["doc_no"], ref=r["reference"], who=r["account_desc"] or r["account_code"], desc=r["description"], qty=r["qty"], amount=r["cost"], journal=r["class"] == "journal") for r in rows]
        grp = defaultdict(lambda: [0, 0.0])
        for r in rows:
            k = (r["resource_code"] or r["account_code"] or "unknown", r["account_desc"] or r["account_code"] or "")
            grp[k][0] += 1
            grp[k][1] += r["cost"] or 0
        out["sections"].append(_section("By supplier or resource", [("code", "Code", "text"), ("who", "Name", "text"), ("n", "Transactions", "num"), ("amount", "Cost", "money")],
                                        [dict(code=k[0], who=k[1], n=v[0], amount=v[1]) for k, v in sorted(grp.items(), key=lambda kv: -abs(kv[1][1]))], "amount"))
        out["sections"].append(_section("Transactions in Pronto" + (f" for {month}" if month else ""), TX_COLS, det, "amount",
                                        note="Includes journalled accruals and their reversals; they net out once the invoice posts." if any(d["journal"] for d in det) else None))

    elif metric in ("po", "outstanding"):
        only_out = metric == "outstanding"
        lines = db.rows(con, f"SELECT p.*, n.code ncode FROM pronto_po p LEFT JOIN cbs_node n ON n.id=p.node_id WHERE p.project_id=? AND p.node_id IN ({q}) ORDER BY p.order_no, p.id", [pid, *ids])
        pos = {}
        for l in lines:
            o = pos.setdefault(l["order_no"], dict(order_no=l["order_no"], who=l["supplier_name"], supplier_code=l["supplier_code"], status=l["status"], type=l["order_type"], date=l["ordered"], due=l["due"], code=l["ncode"], lines=0, ordered=0.0, received=0.0, outstanding=0.0, counts=0.0, is_open=l["is_open"]))
            o["lines"] += 1
            o["ordered"] += l["committed"] or 0
            o["received"] += l["received"] or 0
            if l["is_open"]:
                o["outstanding"] += max(0.0, (l["committed"] or 0) - (l["received"] or 0))
            o["counts"] += (l["committed"] or 0) if l["is_open"] else (l["received"] or 0)
        plist = [o for o in pos.values() if (o["outstanding"] > 0.005 if only_out else True)]
        keep = {o["order_no"] for o in plist}
        cols = [("order_no", "PO", "text"), ("who", "Supplier", "text"), ("code", "CBS", "text"), ("type", "Type", "text"), ("status", "Status", "text"), ("date", "Ordered", "date"), ("lines", "Lines", "num"),
                ("ordered", "Ordered value", "money"), ("received", "Received", "money"), ("outstanding", "Outstanding", "money"), ("counts", "Counts as commitment", "money")]
        out["sections"].append(_section("Purchase orders" + (" with an open balance" if only_out else ""), cols, sorted(plist, key=lambda o: o["order_no"]), "outstanding" if only_out else "ordered",
                                        note="A closed PO commits only what was received; an open PO commits its full ordered value."))
        det = [dict(order_no=l["order_no"], who=l["supplier_name"], code=l["ncode"], cat=l["category_desc"] or l["category"], status=l["status"], ordered=l["committed"], received=l["received"],
                    outstanding=max(0.0, (l["committed"] or 0) - (l["received"] or 0)) if l["is_open"] else 0.0) for l in lines if l["order_no"] in keep]
        out["sections"].append(_section("Order lines (the sub amounts that make up each PO)", [("order_no", "PO", "text"), ("who", "Supplier", "text"), ("code", "CBS", "text"), ("cat", "Category", "text"), ("status", "Status", "text"),
                                                                                              ("ordered", "Ordered value", "money"), ("received", "Received", "money"), ("outstanding", "Outstanding", "money")], det, "ordered"))

    elif metric in ("acc", "accrual"):
        mf = " AND month=?" if month else ""
        manual = db.rows(con, f"SELECT a.*, n.code ncode FROM accrual a JOIN cbs_node n ON n.id=a.node_id WHERE a.project_id=? AND a.node_id IN ({q}) AND a.status IN ('open','partial'){mf.replace('month', 'a.month')} ORDER BY a.month", [pid, *ids, *margs])
        cover = accruals.pronto_cover(con, pid)
        for a in manual:
            a["cover"] = cover.get(a["id"], 0.0) if a["status"] == "open" else 0.0
            if a["status"] == "partial":  # only the part not yet landed (timesheet or invoice) still counts
                a["amount"] = max(0.0, (a["amount"] or 0) - (a["matched_amount"] or 0))
        st = activity.stamps(con, "accrual", [a["id"] for a in manual])
        sec = _section("Your accruals (open): click one for its history", [("month", "Month", "month"), ("code", "CBS", "text"), ("kind", "Kind", "text"), ("hours", "Hours", "num"), ("inv", "Invoice ref", "text"), ("po", "PO", "text"), ("note", "Note", "wrap"),
                                                       ("by", "Raised by", "text"), ("accrued", "Accrued", "money"), ("cover", "Already accrued by finance", "money"), ("amount", "Counts", "money")],
                       [dict(id=a["id"], month=a["month"], code=a["ncode"], kind=accruals.KINDS.get(accruals._kind(a), ""), hours=a.get("hours"), inv=a["inv_ref"], po=a["po_no"], note=a["note"] or a["reason"],
                             by=st.get(a["id"], {}).get("created_by"), accrued=a["amount"], cover=a["cover"] or None, amount=a["amount"] - a["cover"]) for a in manual], "amount")
        sec["tbl"] = "accrual"  # rows open their change history
        out["sections"].append(sec)
        # invoices that landed after the month the work was done: counted in the work month, reversed in the landing month
        idset = set(ids)
        moved = [x for x in accruals.counted(con, pid) if x[3] == "Matched" and x[0] in idset and (not month or x[1] == month)]
        if moved:
            out["sections"].append(_section("Invoices counted in the month the work was done (reversed in the month they landed in Pronto)",
                                            [("month", "Month", "month"), ("code", "CBS", "text"), ("what", "", "text"), ("amount", "Amount", "money")],
                                            [dict(month=m, code=code_of.get(nid), what="work month: the invoice amount" if amt > 0 else "landing month: reversal", amount=amt) for nid, m, amt, _ in moved], "amount"))
        ts = db.rows(con, f"SELECT l.*, {accruals.UNPOSTED_COST} AS total_cost, n.code ncode FROM pronto_labour l LEFT JOIN cbs_node n ON n.id=l.node_id WHERE l.project_id=? AND l.posted=0 "
                          f"AND {accruals.UNPOSTED_NOT_ACCRUED} AND l.node_id IN ({q}){mfilter.replace('t.month', 'l.month')} ORDER BY l.date_worked", [pid, *ids, *margs])
        out["sections"].append(_section("Timesheets not yet posted in Pronto (accrued automatically where you have not accrued the day yourself)", [("date", "Worked", "date"), ("code", "CBS", "text"), ("who", "Person", "text"), ("rc", "Code", "text"), ("hours", "Hours", "num"), ("status", "Pronto status", "text"), ("amount", "Cost", "money")],
                                        [dict(date=l["date_worked"], code=l["ncode"], who=l["name"], rc=l["resource_code"], hours=l["hours"], status=l["status"], amount=l["total_cost"]) for l in ts], "amount"))
        cl = [c for c in subcontracts.claim_accruals(con, pid, accruals.landed_refs(con, pid)) if c["node_id"] in set(ids) and (not month or c["month"] == month)]
        out["sections"].append(_section("Subcontractor claims received, invoice not yet in Pronto", [("month", "Month", "month"), ("code", "CBS", "text"), ("sub", "Subcontract", "text"), ("claim", "Claim", "text"), ("basis", "Basis", "text"), ("inv", "Invoice ref", "text"), ("amount", "Accrued (net of retention)", "money")],
                                        [dict(month=c["month"], code=code_of.get(c["node_id"]), sub=c["subcontract"], claim=c["claim_no"], basis=c["basis"], inv=c["inv_ref"], amount=c["amount"]) for c in cl], "amount"))

    elif metric in ("budget", "allowance"):
        led = db.rows(con, f"SELECT l.*, n.code ncode, n.name nname FROM allowance_ledger l JOIN cbs_node n ON n.id=l.node_id WHERE l.project_id=? AND l.node_id IN ({q}) ORDER BY l.id", [pid, *ids])
        out["sections"].append(_section("Allowance ledger", [("date", "Date", "date"), ("kind", "Type", "text"), ("code", "CBS", "text"), ("name", "Name", "text"), ("budget", "Budget", "money"), ("risk", "Risk bucket", "money"),
                                                             ("cont", "Contingency earmark", "money"), ("cover", "Risk cover", "money"), ("ref", "Reference", "text"), ("note", "Note", "wrap")],
                                        [dict(date=l["date"] or (l["created_at"] or "")[:10], kind=l["kind"].replace("_", " "), code=l["ncode"], name=l["nname"], budget=l["budget"], risk=l["risk"], cont=l["contingency"], cover=l["risk_cover"], ref=l["ref"], note=l["note"]) for l in led], "budget",
                                        note="Budget is what the PM works to. The risk bucket is held by the company and only counts in the Company view."))

    elif metric in ("ctc", "forecast"):
        out["sections"].append(_section("Cost to complete by line", [("code", "CBS", "text"), ("name", "Name", "text"), ("method", "Method", "text"), ("how", "How it is built", "wrap"), ("amount", "CTC", "money")],
                                        [dict(code=r["code"], name=r["name"], method=r.get("method"), how=_how(r, M), amount=r["ctc"]) for r in leaves if abs(r["ctc"]) > 0.005 or r.get("note")], "amount"))
        for r in leaves[:1] if len(leaves) == 1 else []:
            out["sections"] += _method_detail(con, pid, r, res)

    elif metric == "eac":
        out["sections"].append(_section("EAC = cost to date + accruals + cost to complete", [("code", "CBS", "text"), ("name", "Name", "text"), ("ctd", "CTD", "money"), ("acc", "Accruals", "money"), ("ctc", "CTC", "money"), ("eac", "EAC", "money")],
                                        [dict(code=r["code"], name=r["name"], ctd=r["ctd"], acc=r["acc"], ctc=r["ctc"], eac=r["eac"]) for r in leaves if abs(r["eac"]) > 0.005], "eac"))

    elif metric in ("contingency", "headroom"):
        out["sections"].append(_section("Allowance less EAC", [("code", "CBS", "text"), ("name", "Name", "text"), ("allowance", "Allowance", "money"), ("eac", "EAC", "money"), ("amount", "Contingency", "money")],
                                        [dict(code=r["code"], name=r["name"], allowance=r["allowance"], eac=r["eac"], amount=r["contingency"]) for r in leaves if abs(r["allowance"]) > 0.005 or abs(r["eac"]) > 0.005], "amount",
                                        note="Negative means the forecast is over the allowance."))

    elif metric in ("risk", "risk_cost"):
        cat_of = risk.node_category(con, pid)
        tags = [t for t in risk.tagged_costs(con, pid, M) if t["node_id"] in set(ids) and (not month or t["month"] == month)]
        names = {r["id"]: f"{r['ref']} {r['title']}" for r in db.rows(con, "SELECT id, ref, title FROM risk WHERE project_id=?", (pid,))}
        out["sections"].append(_section("Costs tagged to risk events", [("month", "Month", "month"), ("kind", "Type", "text"), ("risk", "Risk", "text"), ("code", "CBS", "text"), ("what", "What", "wrap"), ("amount", "Amount", "money")],
                                        [dict(month=t["month"], kind=t["kind"], risk=names.get(t["risk_id"]), code=code_of.get(t["node_id"]), what=t.get("text"), amount=t["amount"]) for t in sorted(tags, key=lambda t: t["month"])], "amount"))
        fund = db.rows(con, f"SELECT r.*, n.code ncode FROM risk_release r JOIN cbs_node n ON n.id=r.target_node_id WHERE r.project_id=? AND r.target_node_id IN ({q}) ORDER BY r.id", [pid, *ids])
        out["sections"].append(_section("Funding of risk cost", [("date", "Date", "date"), ("kind", "Step", "text"), ("code", "CBS", "text"), ("ref", "Reference", "text"), ("by", "Approved by", "text"), ("amount", "Amount", "money")],
                                        [dict(date=f["date"], kind={"contingency": "1 contingency", "release": "2 release", "infuse": "3 infusion"}.get(f["kind"], f["kind"]), code=f["ncode"], ref=f["ref"], by=f["approved_by"], amount=f["amount"]) for f in fund], "amount"))

    elif metric == "month":
        if not month or month not in grid:
            raise ValueError("Choose a month")
        i = grid.index(month)
        d1 = drill(con, pid, node, "ctd", month)
        d2 = drill(con, pid, node, "acc", month)
        out["sections"] += d1["sections"] + d2["sections"]
        fc = [dict(code=r["code"], name=r["name"], method=r.get("method"), how=_how(r, M), amount=r["f"][i]) for r in leaves if abs(r["f"][i]) > 0.005]
        out["sections"].append(_section(f"Forecast for {month}", [("code", "CBS", "text"), ("name", "Name", "text"), ("method", "Method", "text"), ("how", "How it is built", "wrap"), ("amount", "Forecast", "money")], fc, "amount"))
        if len(leaves) == 1:
            out["sections"] += [s for s in _method_detail(con, pid, leaves[0], res, month)]
    else:
        raise ValueError("Unknown amount")
    out["total"] = sum(s["total"] or 0 for s in out["sections"][:1]) if out["sections"] else 0
    return out


def _how(r, M):
    m = r.get("method")
    if r["kind"] == "group":
        return ""
    return {"AT-BUDGET": "Remaining budget: allowance less CTD and accruals, spread over the remaining months",
            "BURN-RATE": "Average monthly spend to date (current month excluded) times the remaining months",
            "AT-COMMIT": f"Open PO commitments ({r['outstanding']:,.0f}) plus {r.get('uncommitted') or 0:,.0f} not yet committed",
            "TOP-DOWN": "Typed EAC less CTD and accruals", "GROUND-UP": "Forecast items below", "CLAIM": "Unclaimed subcontract schedule, net of retention", "MANUAL": "Typed monthly amounts"}.get(m, m or "")


def _method_detail(con, pid, r, res, month=None):
    """For a single line: the building blocks behind its forecast."""
    secs = []
    nid = r["node_id"]
    M = res["status_month"]
    grid = res["grid"]
    if r["kind"] == "pot":
        if (r.get("pool_drawn") or 0) > 0.5:
            ids = services.subtree_ids(con, pid, nid)
            q = ",".join("?" * len(ids))
            rows = db.rows(con, f"SELECT n.code, n.name, i.scope, i.spread FROM forecast_item i JOIN cbs_node n ON n.id=i.node_id "
                                f"WHERE i.project_id=? AND i.from_pool=1 AND i.node_id IN ({q}) ORDER BY n.code", [pid, *ids])
            secs.append(_section(f"Allocated out of this pool to the lines below ({r['pool_drawn']:,.0f} taken)", [("code", "CBS", "text"), ("name", "Line", "text"),
                                 ("spread", "Kind", "text"), ("scope", "Scope", "text")], rows, None,
                                 note="Their forecasts are counted on their own lines; this pool's cost to complete is reduced by the same amount."))
        return secs
    if r.get("method") == "GROUND-UP":
        manual = defaultdict(lambda: defaultdict(float))
        for m in db.rows(con, "SELECT item_id, month, amount FROM forecast_manual WHERE node_id=?", (nid,)):
            manual[m["item_id"]][m["month"]] += m["amount"]
        rows = []
        fctx = forecast.load_ctx(con, pid)
        for it in db.rows(con, "SELECT * FROM forecast_item WHERE node_id=? ORDER BY id", (nid,)):
            it = dict(it)
            it["start_date"] = it["start_date"] or ((r.get("start") or M) + "-01")
            it["end_date"] = it["end_date"] or (db.month_end(r.get("end") or M) if it.get("spread") != "Roster" or not it.get("swings") else None)
            ser = engine.item_series(it, manual.get(it["id"]), fctx)
            amt = ser.get(month, 0.0) if month else sum(v for m, v in ser.items() if m >= M)
            rows.append(dict(scope=it["scope"], spread=it["spread"], qty=it["qty"], rate=it["rate"], start=it["start_date"], end=it["end_date"], amount=amt))
        secs.append(_section("Forecast items" + (f" in {month}" if month else " (months from the status month)"), [("scope", "Scope", "text"), ("spread", "Spread", "text"), ("qty", "Qty", "num"), ("rate", "Rate", "money"), ("start", "Start", "date"), ("end", "End", "date"), ("amount", "Amount", "money")], rows, "amount"))
    elif r.get("method") == "CLAIM":
        sch = subcontracts.node_schedule(con, pid, M).get(nid)
        if sch and sch.get("direct"):
            rows = [dict(month=m, amount=v) for m, v in sorted(sch["direct"].items()) if m >= M]
            secs.append(_section("The PM's forecast on the claim sheet (net of retention)", [("month", "Month", "month"), ("amount", "Forecast net", "money")], rows, "amount",
                                 note="Typed per schedule line on the subcontract's claim sheet; lines without a typed forecast follow their unclaimed schedule."))
        if sch and sch["net_total"]:
            rows = [dict(month=m, amount=v) for m, v in sorted(sch["net_by_month"].items())]
            secs.append(_section("Subcontract schedule (net of retention)", [("month", "Month", "month"), ("amount", "Scheduled net", "money")], rows, "amount",
                                 note=f"Scheduled {sch['net_total']:,.0f}, claimed so far {sch['net_claimed']:,.0f}: the difference is the cost to complete."))
    elif r.get("method") == "BURN-RATE":
        rows = [dict(month=m, amount=r["a"][i] + r["x"][i]) for i, m in enumerate(grid) if m < M and (r["a"][i] or r["x"][i])]
        secs.append(_section("Monthly spend the burn rate averages", [("month", "Month", "month"), ("amount", "Actual + accrued", "money")], rows, "amount"))
    elif r.get("method") == "AT-COMMIT":
        d = drill(con, pid, str(nid), "outstanding")
        secs += d["sections"][:1]
    return secs
