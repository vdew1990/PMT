"""Read a client claim schedule (schedule of values) from an Excel sheet whose layout is not known in advance.

Claim schedules differ from job to job, but the headers stay similar: an item number, a description, start and end
dates, a value, a claim requirement and a phase, usually followed by one column per month. The reader:

  1. finds the header row by matching header words against synonyms,
  2. decides which column is the item number and which is the stage by looking at the cell contents,
  3. skips total and section rows (anything whose item number does not start with a digit),
  4. rebuilds the hierarchy from the numbering (a row with a stage or dates is a claim item, the rest are groups),
  5. reads the month columns as each item's monthly claim profile.

Nothing is written to the database by `parse`; `apply` does that once the user has seen the preview.
"""
import re
from collections import defaultdict
from datetime import date, datetime

import openpyxl

from . import db, revenue

SYN = {
    "code": ["item", "itemno", "itemnumber", "itemref", "ref", "refno", "wbs", "no", "number", "code", "lineno", "line", "id", "sovref", "milestoneno"],
    "description": ["scopedescription", "description", "itemdescription", "scope", "activity", "milestone", "name", "workdescription", "details", "scopeofwork", "title"],
    "start": ["start", "startdate", "begin", "commence", "commencement", "from"],
    "end": ["end", "enddate", "finish", "finishdate", "completion", "completiondate", "due", "duedate", "to"],
    "value": ["value", "amount", "contractvalue", "price", "scheduledvalue", "sum", "total", "claimvalue", "audexclgst", "audexgst", "exclgst", "exgst"],
    "requirement": ["claimrequirement", "claimrequirements", "requirement", "requirements", "evidence", "claimevidence", "paymentcondition", "deliverable", "paymentmilestone", "claimbasis"],
    "phase": ["phase", "workphase", "discipline"],
    "invoiced": ["invoiced", "claimedtodate", "invoicedtodate", "claimed", "previouslyclaimed"],
    "months": ["months", "duration"],
    "stage": ["stage", "package", "stagepackage", "workpackage"],
    "kind": ["kind", "itemtype", "itemkind", "section", "scopetype"],
    "status": ["status", "optionstatus", "clientstatus", "variationstatus"],
    "inoriginal": ["inoriginal", "inoriginalcontract", "inoriginalcontractvalue", "originalcontract", "inoriginalvalue"],
}
CODE_OK = re.compile(r"^\d+([.\-][0-9A-Za-z]+)*\*?$")
MONTH_TXT = re.compile(r"^([A-Za-z]{3,9})[\s\-/.']*(\d{2}|\d{4})$")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
FIELD_LABEL = dict(code="Item number", description="Description", start="Start", end="End", value="Value", requirement="Claim requirement",
                   phase="Phase", stage="Stage / package", invoiced="Claimed to date", kind="Kind", status="Status", inoriginal="In original contract")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _txt(v):
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("$", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    try:
        x = float(s.strip("()"))
    except ValueError:
        return None
    return -x if neg else x


def _month(v):
    """YYYY-MM for a date cell or a month label such as 'Nov-24' or 'November 2024'; otherwise None."""
    if isinstance(v, (datetime, date)):
        return f"{v.year:04d}-{v.month:02d}"
    if isinstance(v, str):
        s = v.strip()
        m = re.match(r"^(\d{4})-(\d{2})(-\d{2})?$", s)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        m = MONTH_TXT.match(s)
        if m and m.group(1)[:3].lower() in MONTHS:
            y = int(m.group(2))
            y += 2000 if y < 100 else 0
            return f"{y:04d}-{MONTHS[m.group(1)[:3].lower()]:02d}"
    return None


def _match(field, key):
    if not key:
        return False
    if key in SYN[field]:
        return True
    if field == "value" and key.startswith(("aud", "value", "amount", "contractvalue")):
        return True
    if field == "requirement" and key.startswith("claimrequirement"):
        return True
    return False


def _header_candidates(row):
    """field -> [column indexes] for one row."""
    out = defaultdict(list)
    for i, c in enumerate(row):
        k = _norm(c)
        if not k:
            continue
        for f in SYN:
            if _match(f, k):
                out[f].append(i)
    return out


def _find_header(rows):
    best = (0, None)
    for hi, row in enumerate(rows[:40]):
        cand = _header_candidates(row)
        got = {f for f in cand if f != "months"}
        if "description" not in got or "value" not in got or len(got) < 3:
            continue
        score = len(got) + (1 if "start" in got else 0) + (1 if "end" in got else 0)
        if score > best[0]:
            best = (score, hi)
    return best[1]


def _pick(cands, ncols, rows, hi, kind):
    """Choose columns for each field. Where one header word could be the item number or the stage (REF, ITEM), look at the data."""
    cols = {}
    body = rows[hi + 1:hi + 400]

    def col_vals(ci):
        return [_txt(r[ci]) for r in body if ci < len(r) and _txt(r[ci])]

    code_c = cands.get("code", [])
    ratio = {}
    for ci in code_c:
        vals = col_vals(ci)
        ratio[ci] = (sum(1 for v in vals if CODE_OK.match(v)) / len(vals)) if vals else 0
    if code_c:
        best = max(code_c, key=lambda ci: ratio[ci])
        if ratio[best] >= 0.3:
            cols["code"] = best
            others = [ci for ci in code_c if ci != best]
            # a second short-text column (EW, EPC, Stage 1) is the stage / package
            for ci in others:
                vals = col_vals(ci)
                if vals and ratio[ci] < 0.3 and max(len(v) for v in vals) <= 24:
                    cols["stage"] = ci
                    break
    for f in ("description", "start", "end", "requirement", "phase", "invoiced", "months", "kind", "status", "inoriginal"):
        if cands.get(f):
            cols[f] = cands[f][0]
    if cands.get("value"):
        # prefer the first value column that holds mostly numbers
        for ci in cands["value"]:
            vals = [r[ci] for r in body if ci < len(r) and r[ci] is not None]
            if vals and sum(1 for v in vals if _num(v) is not None) / len(vals) > 0.6:
                cols["value"] = ci
                break
    if "stage" not in cols:
        for ci in cands.get("stage", []):
            cols["stage"] = ci
    return cols


def _month_columns(rows, hi, after):
    """Contiguous run of month headers: look in the header row, then the row above."""
    for r in (hi, hi - 1, hi - 2):
        if r < 0:
            continue
        row = rows[r]
        run = []
        for i in range(after + 1, len(row)):
            m = _month(row[i])
            if m:
                run.append((i, m))
            elif run:
                break
        if len(run) >= 2:
            return run, r
    return [], None


def _sheet_rows(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return [(ws.title, [tuple(r) for r in ws.iter_rows(values_only=True)]) for ws in wb.worksheets if ws.sheet_state == "visible"]
    finally:
        wb.close()                  # Windows will not delete a file that is still open


class NotRecognised(ValueError):
    pass


REG_KEYS = {
    "no": ("claim", "claimno", "claimnumber", "claimnr"),
    "submitted": ("datesubmitted", "submitteddate", "submitted"),
    "approved_date": ("dateapproved", "approveddate", "datecertified", "certifieddate"),
    "inv_ref": ("invoiceref", "invoiceno", "invoicenumber", "invoice", "invoicereference"),
    "claimed_to_date": ("claimedtodate",),
    "approved_to_date": ("approvedtodate", "certifiedtodate"),
    "note": ("note", "notes"),
}


def _register(rows, hi, after):
    """A claims register to the right of the month columns (Claim #, Date Submitted, Date Approved, Invoice Ref, Approved This Claim):
    one row per claim already made. Optional: without it past months still become claims, just without numbers and dates."""
    head = rows[hi]
    cols = {}
    for i in range(after + 1, len(head)):
        k = _norm(head[i])
        if not k:
            continue
        for f, keys in REG_KEYS.items():
            if f not in cols and k in keys:
                cols[f] = i
        if "amount" not in cols and (k.startswith(("approvedthisclaim", "certifiedthisclaim")) or k in ("approvedamount", "certifiedamount", "thisclaim")):
            cols["amount"] = i
    if "no" not in cols or "amount" not in cols:
        return []
    out = []
    for ri in range(hi + 1, len(rows)):
        r = rows[ri]
        no = r[cols["no"]] if cols["no"] < len(r) else None
        amt = _num(r[cols["amount"]]) if cols["amount"] < len(r) else None
        if no in (None, "") or amt is None:
            continue
        try:
            n = int(float(no))
        except (TypeError, ValueError):
            continue
        g = lambda f: (r[cols[f]] if f in cols and cols[f] < len(r) else None)
        out.append(dict(no=n, submitted=db.iso(g("submitted")), approved_date=db.iso(g("approved_date")), inv_ref=_txt(g("inv_ref")), amount=amt,
                        claimed_to_date=_num(g("claimed_to_date")), approved_to_date=_num(g("approved_to_date")), note=_txt(g("note")), row=ri + 1))
    return out


def _period(rows, hi):
    """The status date the sheet says it is at: a 'Period' / 'Status date' / 'As at' label with a date next to it."""
    for r in rows[:max(hi, 3) + 1]:
        for i, c in enumerate(r):
            if _norm(c) in ("period", "statusdate", "asat", "claimperiod"):
                for v in r[i + 1:i + 4]:
                    d = db.iso(v) if isinstance(v, (datetime, date)) else None
                    if d:
                        return d
    return None


def parse(path):
    sheets = _sheet_rows(path)
    last = "No sheet has a header row with a description and a value column."
    for name, rows in sheets:
        hi = _find_header(rows)
        if hi is None:
            continue
        try:
            return _parse_sheet(name, rows, hi)
        except NotRecognised as e:
            last = str(e)
    raise NotRecognised(last + " Expected headers such as ITEM, SCOPE DESCRIPTION, START, END and AUD (or Value / Amount).")


def _parse_sheet(name, rows, hi):
    cands = _header_candidates(rows[hi])
    cols = _pick(cands, len(rows[hi]), rows, hi, None)
    for need in ("code", "description", "value"):
        if need not in cols:
            raise NotRecognised(f"Sheet '{name}': could not tell which column holds the {FIELD_LABEL.get(need, need).lower()}.")
    last_fixed = max(cols.values())
    months, mrow = _month_columns(rows, hi, last_fixed)
    header = rows[hi]
    mapping = {FIELD_LABEL[f]: str(header[c]).strip() for f, c in cols.items() if f in FIELD_LABEL and c < len(header) and header[c] is not None}

    def cell(r, f):
        c = cols.get(f)
        return r[c] if c is not None and c < len(r) else None

    items, skipped, dup = [], [], defaultdict(int)
    stack = []                                # open groups: (parts, item)
    for ri in range(hi + 1, len(rows)):
        r = rows[ri]
        if not r or all(v in (None, "") for v in r[:last_fixed + 1]):
            continue
        code, desc = _txt(cell(r, "code")), _txt(cell(r, "description"))
        if not code:
            if desc and ri > hi + 1:
                skipped.append(dict(row=ri + 1, text=desc[:60], why="no item number"))
            continue
        if not CODE_OK.match(code):
            skipped.append(dict(row=ri + 1, text=(desc or code).replace("\n", " ")[:60], why="total or section row"))
            continue
        stage, start, end = _txt(cell(r, "stage")), db.iso(cell(r, "start")), db.iso(cell(r, "end"))
        value = _num(cell(r, "value"))
        monthly = {m: _num(r[ci]) for ci, m in months if ci < len(r) and _num(r[ci])}
        is_leaf = bool(stage or start or end)
        if not is_leaf and not desc and not value:
            continue                          # an empty placeholder row
        parts = len(code.split("."))
        it = dict(row=ri + 1, ref=code, description=desc or code, stage=stage, start_date=start, end_date=end, value=value or 0.0,
                  requirement=_txt(cell(r, "requirement")), phase=_txt(cell(r, "phase")), claimed=_num(cell(r, "invoiced")),
                  kind_cell=(_txt(cell(r, "kind")) or "").lower(), status_cell=_txt(cell(r, "status")) or "", inorig_cell=(_txt(cell(r, "inoriginal")) or "").lower(),
                  monthly=monthly, is_leaf=is_leaf, sheet_total=value, parent=None, children=[], depth=0)
        dup[code] += 1
        if is_leaf:
            it["parent"] = stack[-1][1] if stack else None
        else:
            while stack and stack[-1][0] >= parts:
                stack.pop()
            it["parent"] = stack[-1][1] if stack else None
            stack.append((parts, it))
        if it["parent"] is not None:
            it["parent"]["children"].append(it)
        items.append(it)
    if not items:
        raise NotRecognised(f"Sheet '{name}': the header row was found (row {hi + 1}) but no rows with an item number below it.")

    # a group with no children is really a claim item with no dates
    for it in items:
        if not it["is_leaf"] and not it["children"]:
            it["is_leaf"] = True
    # section kind from the top-level description; everything below inherits it
    for it in items:
        top = it
        while top["parent"] is not None:
            top = top["parent"]
        d = (top["description"] or "").lower()
        it["kind"] = "variation" if "variation" in d else "optional" if "optional" in d else "base"
        k = it["kind_cell"]                       # a Kind column (PMT's template) says it per row
        if k:
            it["kind"] = "variation" if k.startswith("var") else "optional" if k.startswith("opt") else "base" if k.startswith(("base", "contract", "scope")) else it["kind"]
        it["cancelled"] = any("cancel" in (a["description"] or "").lower() for a in _chain(it))
        it["depth"] = len(_chain(it)) - 1
    warnings = []
    for it in items:
        if it["is_leaf"]:
            if it["monthly"]:
                tot = sum(it["monthly"].values())
                if abs(tot - it["value"]) > 1.0:
                    warnings.append(dict(row=it["row"], ref=it["ref"], text=f"{it['description'][:40]}: monthly amounts total {tot:,.2f}, value is {it['value']:,.2f}"))
        else:
            kids = _leaves(it)
            ssum = sum(k["value"] for k in kids)
            if it["sheet_total"] is not None and abs(ssum - it["sheet_total"]) > 1.0:
                warnings.append(dict(row=it["row"], ref=it["ref"], text=f"{it['description'][:40]}: lines below add to {ssum:,.2f}, the group total in the sheet is {it['sheet_total']:,.2f}"))
    dups = sorted(c for c, n in dup.items() if n > 1)
    leaves = [i for i in items if i["is_leaf"]]
    by_kind = defaultdict(float)
    for i in leaves:
        by_kind[i["kind"]] += i["value"]
    for i, it in enumerate(items):
        it["order"] = i + 1
    register = _register(rows, hi, last_fixed) if months else []
    return dict(sheet=name, header_row=hi + 1, columns=mapping, months=[m for _, m in months], month_header_row=(mrow + 1) if mrow is not None else None,
                items=items, skipped=skipped, warnings=warnings, duplicate_refs=dups, register=register, period=_period(rows, hi),
                counts=dict(items=len(leaves), groups=len(items) - len(leaves), with_monthly=sum(1 for i in leaves if i["monthly"]),
                            with_dates=sum(1 for i in leaves if i["start_date"])),
                totals={k: round(v, 2) for k, v in by_kind.items()})


def _chain(it):
    out = []
    while it is not None:
        out.append(it)
        it = it["parent"]
    return out


def _leaves(it):
    if it["is_leaf"]:
        return [it]
    return [x for c in it["children"] for x in _leaves(c)]


def link_claims(parsed, status_month):
    """Turn the months before the status month into claims already made. With a register each claim (its number, dates, invoice,
    certified amount) is matched to the month whose total it equals; an 'opening balance' claim that equals several earlier months
    together covers them all. Months with no register claim become claims of their own, numbered after the register's."""
    totals = defaultdict(float)
    for it in parsed["items"]:
        if it["is_leaf"]:
            for m, a in it["monthly"].items():
                if m < status_month:
                    totals[m] += a
    months = sorted(m for m, t in totals.items() if abs(t) > 0.005)
    taken, claims, unmatched = {}, [], []
    for r in sorted(parsed.get("register") or [], key=lambda x: x["no"]):
        hit = next((m for m in months if m not in taken and abs(totals[m] - r["amount"]) <= 2.0), None)
        if hit:
            taken[hit] = r
            claims.append(dict(no=r["no"], months=[hit], reg=r))
        else:
            unmatched.append(r)
    for r in list(unmatched):                       # an opening balance: everything before the first matched month, in one claim
        first = min(taken) if taken else None
        early = [m for m in months if m not in taken and (first is None or m < first)]
        if early and abs(sum(totals[m] for m in early) - r["amount"]) <= 2.0 + 0.00001 * abs(r["amount"]):
            for m in early:
                taken[m] = r
            claims.append(dict(no=r["no"], months=early, reg=r))
            unmatched.remove(r)
            break
    nxt = max([c["no"] for c in claims] + [r["no"] for r in parsed.get("register") or []] + [0]) + 1
    for m in months:
        if m not in taken:
            claims.append(dict(no=nxt, months=[m], reg=None))
            nxt += 1
    claims.sort(key=lambda c: (c["months"][0], c["no"]))
    for c in claims:
        c["total"] = round(sum(totals[m] for m in c["months"]), 2)
    return dict(claims=claims, unmatched=unmatched, totals=dict(totals), months=months)


def history(parsed, status_month):
    """What a file with month columns says: claims already made (before the status month), this month's claim, the forecast."""
    if not parsed["months"] or not status_month:
        return None
    link = link_claims(parsed, status_month)
    cur = fut = 0.0
    for it in parsed["items"]:
        if it["is_leaf"]:
            for m, a in it["monthly"].items():
                if m == status_month:
                    cur += a
                elif m > status_month:
                    fut += a
    past = sum(c["total"] for c in link["claims"])
    claimed_col = sum(it["claimed"] or 0 for it in parsed["items"] if it["is_leaf"])
    return dict(status_month=status_month, claims=[dict(no=c["no"], months=c["months"], total=c["total"], approved=bool(c["reg"] and c["reg"]["approved_date"]),
                                                       submitted=c["reg"]["submitted"] if c["reg"] else None, inv_ref=c["reg"]["inv_ref"] if c["reg"] else None,
                                                       note=c["reg"]["note"] if c["reg"] else None, from_register=bool(c["reg"])) for c in link["claims"]],
                n_claims=len(link["claims"]), past_total=round(past, 2), current_total=round(cur, 2), future_total=round(fut, 2),
                unmatched=[dict(no=r["no"], amount=r["amount"]) for r in link["unmatched"]], register=len(parsed.get("register") or []),
                claimed_column=round(claimed_col, 2) if claimed_col else None, period=parsed.get("period"))


def preview(parsed, status_month=None):
    """JSON-safe summary for the screen."""
    def row(i):
        return dict(row=i["row"], ref=i["ref"], description=i["description"], stage=i["stage"], start=i["start_date"], end=i["end_date"], value=i["value"],
                    is_leaf=i["is_leaf"], depth=i["depth"], kind=i["kind"], phase=i["phase"], monthly=sum(i["monthly"].values()) if i["monthly"] else None)
    return dict(sheet=parsed["sheet"], header_row=parsed["header_row"], columns=parsed["columns"], months=parsed["months"], counts=parsed["counts"], totals=parsed["totals"],
                skipped=parsed["skipped"][:30], n_skipped=len(parsed["skipped"]), warnings=parsed["warnings"][:30], n_warnings=len(parsed["warnings"]),
                duplicate_refs=parsed["duplicate_refs"][:20], sample=[row(i) for i in parsed["items"][:60]],
                history=history(parsed, status_month), sheet_period=parsed.get("period"))


def apply(con, pid, parsed, mode="merge", variations_in_original=False, optionals_in_original=True, status_month=None, claims_from_months=True):
    """Write the parsed schedule. 'replace' clears the existing schedule first (refused if claims already refer to it);
    'merge' updates items that match on item number and description, and adds the rest.
    variations_in_original / optionals_in_original: whether the variation and optional-price sections of the schedule
    are part of the original contract value (then a declined option or a variation is not added again to the revised
    value) or come on top of it.
    'overwrite' makes the file the whole claim schedule: the schedule AND the claims are cleared first; months before the status
    month become claims already made, the status month becomes this month's draft claim, later months are the forecast."""
    if mode not in ("merge", "replace", "overwrite"):
        raise ValueError("Mode must be merge, replace or overwrite")
    overwrite = mode == "overwrite"
    if overwrite:
        if not status_month:
            raise ValueError("Set the project's status date first (Project setup): months before it are loaded as claims already made.")
        con.execute("DELETE FROM claim WHERE project_id=?", (pid,))                     # their lines go with them
        con.execute("DELETE FROM contract_item WHERE project_id=? AND variation_id IS NULL", (pid,))
    elif mode == "replace":
        n = db.scalar(con, "SELECT COUNT(*) FROM claim_line cl JOIN contract_item ci ON ci.id=cl.item_id WHERE ci.project_id=? AND ci.variation_id IS NULL", (pid,))
        if n:
            raise ValueError(f"{n} claim lines already refer to the current schedule, so it cannot be replaced. Use 'update and add' instead.")
        con.execute("DELETE FROM contract_item WHERE project_id=? AND variation_id IS NULL", (pid,))
    existing = defaultdict(list)             # rows that share an item number and description are matched one to one, in order
    for r in db.rows(con, "SELECT id, ref, description FROM contract_item WHERE project_id=? AND variation_id IS NULL ORDER BY sort_order, id", (pid,)):
        existing[(r["ref"], _norm(r["description"]))].append(r["id"])
    order0 = db.scalar(con, "SELECT COALESCE(MAX(sort_order),0) FROM contract_item WHERE project_id=?", (pid,)) or 0
    created = updated = plans = 0
    ids = {}
    for it in parsed["items"]:
        leaf = it["is_leaf"]
        status = None
        if it["kind"] == "optional" and leaf:
            status = "cancelled" if it["cancelled"] or not it["value"] else "confirmed"
        if it.get("status_cell") and leaf and it["kind"] in ("optional", "variation"):
            status = (revenue.opt_status if it["kind"] == "optional" else revenue.var_status)(it["status_cell"])
        file_months = overwrite and bool(parsed["months"])         # the file is the whole schedule: no months typed means nothing scheduled
        if leaf and (it["monthly"] or file_months):
            method = "manual"
        elif leaf and it["start_date"] and it["end_date"] and it["end_date"][:7] > it["start_date"][:7]:
            method = "even"
        else:
            method = "lump" if leaf else "even"
        in_orig = 1 if it["kind"] == "base" else int(bool(variations_in_original if it["kind"] == "variation" else optionals_in_original))
        io = it.get("inorig_cell") or ""
        if io:                                    # an "In original contract" column (PMT's template) says it per row
            in_orig = 1 if io.startswith(("y", "1", "true", "incl")) else 0 if io.startswith(("n", "0", "false", "not", "excl")) else in_orig
        data = dict(ref=it["ref"], description=it["description"], stage=it["stage"], kind=it["kind"], optional_status=status, in_original=in_orig,
                    value=it["value"] if leaf else 0, phase=it["phase"], claim_requirement=it["requirement"],
                    start_date=it["start_date"], end_date=it["end_date"], method=method)
        key = (it["ref"], _norm(it["description"]))
        if mode == "merge" and existing.get(key):
            iid = existing[key].pop(0)
            db.update(con, "contract_item", iid, data)
            updated += 1
        else:
            iid = db.insert(con, "contract_item", dict(project_id=pid, sort_order=order0 + it["order"], **data))
            created += 1
        ids[it["order"]] = iid
        it["_id"] = iid
        if leaf and (it["monthly"] or method == "manual"):
            con.execute("DELETE FROM revenue_plan WHERE item_id=?", (iid,))
            for m, a in it["monthly"].items():
                if overwrite and m < status_month:
                    continue                                    # a month already past is a claim, below, not a forecast
                db.insert(con, "revenue_plan", dict(item_id=iid, month=m, amount=round(a, 2)))
                plans += 1
    for it in parsed["items"]:
        pid_ = it["parent"]["_id"] if it["parent"] is not None else None
        db.update(con, "contract_item", it["_id"], {"parent_id": pid_})
    out = {}
    if overwrite and parsed["months"] and claims_from_months:        # not for a claim schedule template: its Claimed | Approved grid makes the claims
        out = _load_claims(con, pid, parsed, status_month)
    from . import variations as _vars
    _vars.placeholders_from_schedule(con, pid)   # a register entry for each variation in the contract, for the cost build-up
    return dict(created=created, updated=updated, plan_months=plans, groups=parsed["counts"]["groups"], items=parsed["counts"]["items"], **out,
                optional_taken=sum(1 for i in parsed["items"] if i["is_leaf"] and i["kind"] == "optional" and i["value"] and not i["cancelled"]))


def _load_claims(con, pid, parsed, status_month):
    """Claims from the month columns: each past month a claim already made (certified when the register says it was approved),
    the status month a draft claim, and a count of lines that now exceed their price."""
    leaves = [i for i in parsed["items"] if i["is_leaf"]]
    link = link_claims(parsed, status_month)
    made = []
    for c in link["claims"]:
        reg, multi = c["reg"], len(c["months"]) > 1
        for m in c["months"]:
            amts = {it["_id"]: it["monthly"][m] for it in leaves if abs(it["monthly"].get(m, 0)) > 0.005}
            total = sum(amts.values())
            certified = bool(reg and (reg["approved_date"] or reg["amount"]))
            note = "; ".join(x for x in ((f"Invoice {reg['inv_ref']}" if reg and reg["inv_ref"] else None), reg["note"] if reg else None,
                                         f"Part of claim {c['no']} (spread over {len(c['months'])} months)" if multi else None, "Loaded from the claim schedule") if x)
            cid = db.insert(con, "claim", dict(project_id=pid, claim_no=f"CLAIM{c['no']:03d}" + (f"-{m}" if multi else ""), period=m,
                                               status="certified" if certified else "submitted", submitted_date=reg["submitted"] if reg else None,
                                               certified_date=reg["approved_date"] if (reg and certified) else None,
                                               certified_amount=round(total, 2) if certified else None, note=note))
            for iid, a in amts.items():
                db.insert(con, "claim_line", dict(claim_id=cid, item_id=iid, amount=round(a, 2), certified=round(a, 2) if certified else None))
            made.append(cid)
    draft = None
    cur = {it["_id"]: it["monthly"][status_month] for it in leaves if abs(it["monthly"].get(status_month, 0)) > 0.005}
    if cur:
        nxt = max([c["no"] for c in link["claims"]] + [r["no"] for r in parsed.get("register") or []] + [0]) + 1
        draft = db.insert(con, "claim", dict(project_id=pid, claim_no=f"CLAIM{nxt:03d}", period=status_month, status="draft", note="Loaded from the claim schedule"))
        for iid, a in cur.items():
            db.insert(con, "claim_line", dict(claim_id=draft, item_id=iid, amount=round(a, 2)))
    over = 0
    for it in leaves:
        total = sum(a for m, a in it["monthly"].items())
        if it["value"] >= 0 and total > it["value"] + 1.0 or it["value"] < 0 and total < it["value"] - 1.0:
            over += 1
    past = sum(c["total"] for c in link["claims"])
    return dict(claims_created=len(made), draft_claim=draft, past_total=round(past, 2), current_total=round(sum(cur.values()), 2),
                forecast_total=round(sum(a for it in leaves for m, a in it["monthly"].items() if m > status_month), 2),
                over_scheduled=over, unmatched_register=[r["no"] for r in link["unmatched"]])
