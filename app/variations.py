"""Variation register, cost build-up and approval flow.

A variation moves through two independent negotiations (the client's view of the price and EPEC's own position).
When the client has Approved and EPEC has Agreed, the variation is recognised: its value becomes contract revenue
and its cost build-up posts to the allowance ledger, so cost control sees the extra allowance straight away.
"""
from . import db, services


DETAIL = ["items", "scope", "contributions", "full"]  # what the client sees: see proposal()


def line_calc(l):
    """One cost line, as the workbook's Variation Engine: quantity = count x (hrs/day x days/wk x weeks + extra), or
    count x quantity when no time is given; cost = qty x rate; risk and markup are both a % of cost; the price is
    cost + risk + profit unless a contract (sell) rate or a fixed price is given."""
    num = lambda k: float(l.get(k) or 0)
    time = [float(l[k]) for k in ("hrs_day", "days_wk", "wks") if l.get(k) not in (None, "", 0)]
    count = float(l.get("item_count") or 1) if l.get("item_count") not in (None, "") else 1.0
    if time:
        p = 1.0
        for t in time:
            p *= t
        qty = count * (p + num("extra_qty"))
    else:
        qty = count * num("qty")
    cost = qty * num("rate")
    risk = cost * num("risk_pct")
    allowance = cost + risk
    if l.get("contract_rate") not in (None, ""):
        price = float(l["contract_rate"]) * qty
    elif l.get("price_override") not in (None, ""):
        price = float(l["price_override"])
    else:
        price = allowance + cost * num("markup_pct")
    return dict(qty=qty, cost=cost, risk=risk, allowance=allowance, profit=price - allowance, price=price,
                sell_rate=(price / qty) if qty else price)


def build(v, items, lines):
    """Price items with their cost lines, the spread, totals and the cost / risk / revenue per CBS node.
    An option counts in the value only when selected (Yes); provisional sums (PS) are listed apart, as in the workbook.
    A spread item's price is shared over the carrier items (uniformly, or in proportion to their price), only over
    items in its own section when its scope says so; its cost and risk stay on its own CBS lines."""
    by_item = {it["id"]: dict(it, lines=[]) for it in items}
    loose = []
    for l in lines:
        c = dict(l, **line_calc(l))
        (by_item[l["price_id"]]["lines"] if l.get("price_id") in by_item else loose).append(c)
    out = sorted(by_item.values(), key=lambda i: (i.get("seq") or 0, i["id"]))
    for it in out:
        it["base"] = sum(c["price"] for c in it["lines"])
        it["cost"] = sum(c["cost"] for c in it["lines"])
        it["risk"] = sum(c["risk"] for c in it["lines"])
        it["counted"] = (not it.get("optional")) or it.get("selected") == "Yes"
        it["received"] = 0.0
        it["spread_out"] = False
    warnings = []
    for sp in [i for i in out if (i.get("spread") or "none") != "none"]:
        rec = [i for i in out if i is not sp and (i.get("spread") or "none") == "none" and i.get("carries", 1) and i["counted"]
               and (sp.get("spread_scope") != "section" or (i.get("section") or "") == (sp.get("section") or ""))]
        if not rec:
            warnings.append(f"'{sp.get('name')}' has nothing to spread over: tick 'carries spread' on at least one price item.")
            continue
        if sp["spread"] == "proportional":
            den = sum(i["base"] for i in rec)
            if abs(den) < 0.005:
                warnings.append(f"'{sp.get('name')}': the carrier items have no price to spread in proportion to; use a uniform spread.")
                continue
            for i in rec:
                i["received"] += sp["base"] * i["base"] / den
        else:
            for i in rec:
                i["received"] += sp["base"] / len(rec)
        sp["spread_out"] = True
    for it in out:
        it["price"] = 0.0 if it["spread_out"] else it["base"] + it["received"]
        for c in it["lines"]:  # each line's share of what its item received, for the client's contributions view
            c["shown_price"] = 0.0 if it["spread_out"] else c["price"] + (it["received"] * c["price"] / it["base"] if abs(it["base"]) > 0.005 else it["received"] / max(1, len(it["lines"])))
    counted = [i for i in out if i["counted"]]
    T = lambda k, xs: sum(i[k] for i in xs)
    total = dict(cost=T("cost", counted), risk=T("risk", counted), price=sum(i["base"] for i in counted))
    total["allowance"] = total["cost"] + total["risk"]
    total["profit"] = total["price"] - total["allowance"]
    total["margin"] = (total["profit"] / total["price"]) if total["price"] else None
    total["base"] = sum(i["price"] for i in counted if i.get("pricing_type") != "PS")
    total["provisional"] = sum(i["price"] for i in counted if i.get("pricing_type") == "PS")
    total["optional"] = sum(i["base"] + i["received"] for i in out if i.get("optional") and i.get("selected") != "Yes")
    by_node = {}
    for it in counted:
        for c in it["lines"]:
            k = c.get("node_id") or ("cat:" + (c.get("category") or "")) if (c.get("node_id") or c.get("category")) else None
            d = by_node.setdefault(k, dict(node_id=c.get("node_id"), category=c.get("category"), cost=0.0, risk=0.0, revenue=0.0))
            d["cost"] += c["cost"]
            d["risk"] += c["risk"]
            d["revenue"] += c["shown_price"]
    if loose:
        warnings.append(f"{len(loose)} cost line(s) are not in a price item.")
    return dict(items=out, loose=loose, total=total, by_node=list(by_node.values()), warnings=warnings)


def _adopt_legacy(con, vid):
    """Earlier variations had cost lines grouped only by a section: give each section a price item."""
    orphan = db.rows(con, "SELECT * FROM variation_line WHERE variation_id=? AND price_id IS NULL ORDER BY sort_order, id", (vid,))
    if not orphan:
        return
    made = {}
    for l in orphan:
        sec = l["section"] or "Works"
        if sec not in made:
            made[sec] = db.insert(con, "variation_price", dict(variation_id=vid, seq=len(made) + 1, section=sec, name=sec,
                                                               optional=1 if l["optional"] else 0, selected="No" if l["optional"] else "Pending"))
        con.execute("UPDATE variation_line SET price_id=? WHERE id=?", (made[sec], l["id"]))


def get(con, pid, vid):
    v = db.one(con, "SELECT * FROM variation WHERE id=? AND project_id=?", (vid, pid))
    if not v:
        return None
    _adopt_legacy(con, vid)
    v["revs"] = db.rows(con, "SELECT * FROM variation_rev WHERE variation_id=? ORDER BY rev", (vid,))
    v["items"] = db.rows(con, "SELECT * FROM variation_price WHERE variation_id=? ORDER BY seq, id", (vid,))
    v["lines"] = db.rows(con, "SELECT l.*, n.code AS node_code, n.name AS node_name FROM variation_line l "
                              "LEFT JOIN cbs_node n ON n.id=l.node_id WHERE l.variation_id=? ORDER BY l.sort_order, l.id", (vid,))
    for l in v["lines"]:
        l.update(line_calc(l))
    v["build"] = build(v, v["items"], v["lines"])
    v["events"] = db.rows(con, "SELECT * FROM variation_event WHERE variation_id=? ORDER BY date, id", (vid,))
    cur = next((r for r in v["revs"] if r["is_current"]), v["revs"][-1] if v["revs"] else None)
    v["current_rev"] = cur
    v["value"] = cur["value"] if cur else 0
    t = v["build"]["total"]
    v["calc"] = dict(cost=t["cost"], risk=t["risk"], allowance=t["allowance"], profit=t["profit"], price=t["price"], margin=t["margin"])
    v["recognised"] = v["client_status"] == "Approved" and v["epec_status"] == "Agreed"
    v["official"] = v["recognised"] and (v["contract_change"] == "No" or v["contract_status"] == "Executed")
    v["state"] = "Closed" if v["closed"] else "Open"
    v["copies"] = db.rows(con, "SELECT id, code, name, kind, copied_from FROM cbs_node WHERE project_id=? AND variation_id=? ORDER BY code", (pid, vid))
    return v


def listing(con, pid):
    out = []
    for r in db.rows(con, "SELECT id FROM variation WHERE project_id=? ORDER BY ref", (pid,)):
        v = get(con, pid, r["id"])
        v.pop("lines"), v.pop("events"), v.pop("build"), v.pop("items")
        out.append(v)
    return out


def sync(con, pid, vid):
    """Make revenue and allowance reflect the variation's current status."""
    v = get(con, pid, vid)
    con.execute("DELETE FROM allowance_ledger WHERE project_id=? AND variation_id=?", (pid, vid))
    con.execute("DELETE FROM contract_item WHERE project_id=? AND variation_id=?", (pid, vid))
    bound = db.one(con, "SELECT id FROM contract_item WHERE id=? AND project_id=?", (v.get("schedule_item_id"), pid)) if v.get("schedule_item_id") else None
    if bound:
        # the variation came from the uploaded contract: its revenue stays on that item (and its claims, plan and dates), which follows the register
        st = "approved" if v["recognised"] else ("declined" if v["client_status"] in ("Denied", "Withdrawn") else "pending")
        upd = {"optional_status": st}
        if v["value"]:
            upd["value"] = v["value"]
        db.update(con, "contract_item", bound["id"], upd)
    if v["recognised"] and not bound:
        proj = db.one(con, "SELECT project_end, status_date FROM project WHERE id=?", (pid,))
        start = db.iso(v["client_status_date"]) or proj["status_date"]
        end = max(proj["project_end"] or start, start)
        # revenue is planned from approval to the end of the project until the PM re-phases it
        db.insert(con, "contract_item", dict(project_id=pid, ref=v["ref"], description=v["title"] or v["ref"],
                                             stage=v["stage"], kind="variation", value=v["value"], variation_id=vid,
                                             start_date=start, end_date=end, method="even"))
        by_node = {}
        for d in v["build"]["by_node"]:
            nid = d["node_id"]
            if not nid and d["category"]:
                n = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND category=?", (pid, d["category"]))
                nid = n["id"] if n else None
            if nid and (d["cost"] or d["risk"]):
                nid = target_node(con, pid, vid, nid, v.get("funding"))
                b, r = by_node.get(nid, (0, 0))
                by_node[nid] = (b + d["cost"], r + d["risk"])
        for nid, (b, r) in by_node.items():
            db.insert(con, "allowance_ledger", dict(project_id=pid, node_id=nid, date=db.iso(v["client_status_date"]),
                                                    kind="variation", budget=b, risk=r, ref=v["ref"],
                                                    note=v["title"], variation_id=vid))
    db.bump(con, pid)
    return v["recognised"]


def next_ref(con, pid, stage_prefix="VAR"):
    n = db.scalar(con, "SELECT COUNT(*) FROM variation WHERE project_id=?", (pid,)) + 1
    while db.one(con, "SELECT 1 x FROM variation WHERE project_id=? AND ref=?", (pid, f"{stage_prefix}-{n:03d}")):
        n += 1
    return f"{stage_prefix}-{n:03d}"


# ---- funding an approved variation: top up the CBS lines, or track it on its own copy of the CBS ----------------------
def target_node(con, pid, vid, nid, funding="topup"):
    """Where a cost line's allowance goes: its own CBS node (top up), or the variation's copy of it (separate)."""
    if funding != "separate":
        return nid
    c = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND variation_id=? AND copied_from=?", (pid, vid, nid))
    return c["id"] if c else nid


def duplicate_cbs(con, pid, vid, node_ids=None, only_used=False):
    """Copy CBS for this variation: same categories and resources, so Pronto cost coded to the variation lands on the
    copy. The copies sit next to the originals; returns {original: copy}.
      * node_ids: copy these groups or lines with everything under them (a complete copy of that structure);
      * only_used: copy just the CBS lines (or groups) the variation's cost lines point to, nothing else."""
    v = db.one(con, "SELECT * FROM variation WHERE id=? AND project_id=?", (vid, pid))
    if not v:
        raise ValueError("Variation not found")
    made = {}
    digits = "".join(ch for ch in v["ref"] if ch.isdigit())[-3:]
    tag = "V" + (digits or str(vid))

    def copy(n, parent_id, top, deep=True):
        have = db.one(con, "SELECT id FROM cbs_node WHERE project_id=? AND variation_id=? AND copied_from=?", (pid, vid, n["id"]))
        if have:
            made[n["id"]] = have["id"]
            return have["id"]
        parent = db.one(con, "SELECT * FROM cbs_node WHERE id=?", (parent_id,))
        name = f"{n['name']} ({v['ref']})" if top else n["name"]
        # the copy's code mirrors the original: PS04 -> PS04-V001, PS04.002 -> PS04-V001.002
        code = f"{n['code']}-{tag}" if top else f"{parent['code']}.{n['code'].split('.')[-1]}"
        base, k = code, 2
        while db.one(con, "SELECT 1 x FROM cbs_node WHERE project_id=? AND code=?", (pid, code)):
            code = f"{base}{chr(96 + k)}"  # PS04-V001b if the copy is made twice
            k += 1
        nid = db.insert(con, "cbs_node", dict(
            project_id=pid, parent_id=parent_id, code=code, name=name, kind=n["kind"], gp=n["gp"],
            category=n.get("category"), resource_id=n.get("resource_id"), function=n.get("function"), scope=n.get("scope"),
            method=n.get("method"), start_date=n.get("start_date"), end_date=n.get("end_date"), po_no=n.get("po_no"),
            sort_order=(n.get("sort_order") or 0), origin="variation", notes=f"Copy of {n['code']} for {v['ref']}",
            variation_id=vid, copied_from=n["id"]))
        made[n["id"]] = nid
        if deep:
            for k in db.rows(con, "SELECT * FROM cbs_node WHERE parent_id=? AND project_id=? AND variation_id IS NULL ORDER BY sort_order, id", (n["id"], pid)):
                copy(k, nid, False)
        return nid
    if only_used:
        used = [r["node_id"] for r in db.rows(con, "SELECT DISTINCT node_id FROM variation_line WHERE variation_id=? AND node_id IS NOT NULL", (vid,))]
        if not used:
            raise ValueError("No cost line of this variation has a CBS yet: choose them on the build-up first")
        for x in used:
            n = db.one(con, "SELECT * FROM cbs_node WHERE id=? AND project_id=?", (x, pid))
            if n and n["parent_id"] and not n.get("variation_id"):
                copy(n, n["parent_id"], True, deep=False)
        node_ids = []
    for x in node_ids or []:
        n = db.one(con, "SELECT * FROM cbs_node WHERE id=? AND project_id=?", (int(x), pid))
        if not n:
            continue
        if not n["parent_id"]:
            raise ValueError(f"{n['code']} is a top-level code; choose a group or line under it")
        if n.get("variation_id"):
            raise ValueError(f"{n['code']} is already a variation copy")
        copy(n, n["parent_id"], True)
    db.update(con, "variation", vid, {"funding": "separate"})
    db.bump(con, pid)
    sync(con, pid, vid)
    return made


def funding_plan(con, pid, vid):
    """Per CBS node the variation costs: cost, risk and where the allowance goes under the chosen funding."""
    v = get(con, pid, vid)
    rows = []
    for d in v["build"]["by_node"]:
        n = db.one(con, "SELECT id, code, name FROM cbs_node WHERE id=?", (d["node_id"],)) if d["node_id"] else None
        t = target_node(con, pid, vid, n["id"], v.get("funding")) if n else None
        tn = db.one(con, "SELECT code, name FROM cbs_node WHERE id=?", (t,)) if t else None
        rows.append(dict(node_id=d["node_id"], code=n["code"] if n else (d["category"] or ""), name=n["name"] if n else "(no CBS chosen)",
                         cost=d["cost"], risk=d["risk"], revenue=d["revenue"], target_code=tn["code"] if tn else "", target_name=tn["name"] if tn else "",
                         copied=bool(n and t and t != n["id"])))
    return dict(funding=v.get("funding") or "topup", recognised=v["recognised"], rows=rows, copies=v["copies"])


# ---- placeholders: a register entry for every variation in the uploaded contract ----------------------------------------
def schedule_variations(con, pid):
    """Leaf variation items of the contract (claim schedule) that no register entry stands for yet."""
    items = db.rows(con, "SELECT * FROM contract_item WHERE project_id=? AND kind='variation' AND variation_id IS NULL ORDER BY sort_order, id", (pid,))
    parents = {i["parent_id"] for i in items if i["parent_id"]}
    bound = {r["schedule_item_id"] for r in con.execute("SELECT schedule_item_id FROM variation WHERE project_id=? AND schedule_item_id IS NOT NULL", (pid,))}
    return [i for i in items if i["id"] not in parents and i["id"] not in bound]


def placeholders_from_schedule(con, pid):
    """Create (or re-attach) a register entry for each variation in the uploaded contract, with its client value and status and an empty
    cost build-up (one price item, no cost lines) for the user to fill in. Revenue is not touched: it stays on the contract item,
    which then follows the register's status. An entry that already exists with the same reference or title is re-attached, not duplicated."""
    made = []
    for it in schedule_variations(con, pid):
        st = (it.get("optional_status") or "approved").lower()
        client, epec = ("Approved", "Agreed") if st == "approved" else ("Denied", "Drafting") if st == "declined" else ("Pending", "Drafting")
        title = it["description"] or it["ref"] or "Variation"
        prior = db.one(con, "SELECT id FROM variation WHERE project_id=? AND (ref=? OR title=?) AND (schedule_item_id IS NULL OR schedule_item_id NOT IN (SELECT id FROM contract_item))",
                       (pid, it["ref"] or "\0", title))
        if prior:
            vid = prior["id"]
            db.update(con, "variation", vid, {"schedule_item_id": it["id"]})
        else:
            ref = it["ref"] if it["ref"] and not db.one(con, "SELECT 1 x FROM variation WHERE project_id=? AND ref=?", (pid, it["ref"])) else next_ref(con, pid, "EPC-VAR" if (it["stage"] or "").upper() == "EPC" else "VAR")
            vid = db.insert(con, "variation", dict(project_id=pid, ref=ref, stage=it["stage"], title=title, client_status=client, epec_status=epec,
                                                   schedule_item_id=it["id"], description=None))
            db.insert(con, "variation_rev", dict(variation_id=vid, rev=0, value=float(it["value"] or 0), is_current=1))
            db.insert(con, "variation_price", dict(variation_id=vid, seq=1, section="Works", name=title, selected="Pending"))
            db.insert(con, "variation_event", dict(variation_id=vid, kind="note", text="Created from the contract: the cost build-up is still to be added"))
        made.append(vid)
    return made
