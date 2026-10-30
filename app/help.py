"""The help assistant behind the chat button: answers questions about using PMT from its own guide.

It runs on this PC with no internet and no AI service: questions are matched to the guide's topics (the README's
"What it does" table, its other sections, and the questions people ask below), with common abbreviations understood.
The same guide downloads as one document (/api/help/guide.md) to give to a Microsoft Copilot Studio agent as its
knowledge, for a Copilot that answers in the chat panel instead (Settings > Your defaults > Copilot web chat address).
"""
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# route -> page name (for "Open ..." buttons and "what is this page")
PAGES = {
    "dashboard": "Dashboard", "portfolio": "Portfolio", "library": "Archive", "pmolibrary": "Project library", "lifecycle": "Project lifecycle", "meetings": "Meetings", "gates": "Project gate", "phases": "Project phase", "commatrix": "Communication matrix", "projstakeholders": "Project stakeholders", "setup": "Project setup", "cbs": "CBS and allowances", "programme": "Project schedule",
    "costcontrol": "Cost control", "risk": "Allowances", "pronto": "Pronto data", "actuals": "Actuals",
    "commitments": "Commitments", "accruals": "Accruals", "subcontracts": "Subcontracts", "forecast": "Forecast lines",
    "fhistory": "Forecast history", "calendar": "Labour calendar", "review": "Month-end review", "revenue": "Contract and claims",
    "variations": "Variations", "diagnostics": "Diagnostics", "reconcile": "Reconcile", "reports": "Reports and history",
    "activity": "Activity and history", "resources": "Resources and rates", "settings": "Settings",
}

# questions people ask, answered in the app's own words: (title, page, keywords, answer)
FAQ = [
    ("What do the numbers in a labour calendar cell mean?", "calendar", "cell number p t 11 p11 grey orange hint unposted timesheet auto accrue accrued meaning mark",
     "A past day can show up to three things. A plain number is hours that landed: pink is a posted Pronto timesheet (actual), "
     "light blue is your own accrual. A small \"P 11\" under the number means Pronto has 11 h entered for that person and day but "
     "not posted yet; \"T 11\" is a subcontractor's timesheet you uploaded. When there is a P or T mark and you have not accrued the "
     "day yourself, the number above it is shown in a lighter colour: PMT accrues those hours automatically (at the person's cost rate) until the "
     "timesheet is posted. Click the cell to change it: the boxes open filled with those hours split into normal time and overtime "
     "(above the normal hours a day set in Settings is overtime). Change them and leave the cell, or press Enter on OT to accrue them "
     "as they are. Purple means a timesheet and your accrual differ; click it to adjust your accrual."),
    ("How do I change an accrual on the labour calendar?", "calendar", "change revise edit accrual nt ot normal time overtime split hours day calendar",
     "Click the day. NT and OT boxes open with your current accrual (or the Pronto hours not yet posted, split at the normal hours a "
     "day). Type the new hours and leave the cell: it saves a moment later and replaces the accrual for that day, it does not add a "
     "second one. Clear both boxes (or type 0) to remove your accrual."),
    ("What is EAC and how is it calculated?", "costcontrol", "eac estimate at completion formula calculated ctd ctc acc accruals",
     "EAC (estimate at completion) = cost to date (CTD, from Pronto) + accruals (ACC, cost incurred but not yet in Pronto) + cost to "
     "complete (CTC, the forecast). Unlike the CMT, PMT includes accruals in EAC; the CMT-style figure is on the Reconcile page."),
    ("What is the difference between budget, allowance, current and total allowance?", "cbs", "budget allowance current total risk view difference company pm",
     "The budget is what the estimate gave each CBS line. Risk is held in a separate bucket by the company. Current allowance is the "
     "budget plus movements (transfers, approved variations) plus any risk the company has released to the project. Total allowance "
     "adds the whole risk bucket. Switch between them with View at the top of the page."),
    ("What is contingency?", "costcontrol", "contingency headroom overrun underrun allowance less eac",
     "Contingency on a line is its allowance less its EAC: positive is headroom, negative is a forecast overrun. On Risk and "
     "contingency you can set some aside as cover for a risk."),
    ("How do I update PMT without losing my data?", None, "update upgrade new release version lose data install zip copy",
     "Your data is not in the program folder: it lives in %LOCALAPPDATA%\\PMT (and the shared folder when sharing). Close PMT (its "
     "window, or end Python in Task Manager), copy the new release over the program folder, and open PMT.exe again. The release "
     "number shows at the bottom of the left menu. If a yellow bar says PMT was updated while running, close and reopen it."),
    ("Why do I get \"Not Found\" errors?", None, "not found error page broken old server restart",
     "An older PMT is still running behind the new pages. Close PMT (or end Python in Task Manager) and open PMT.exe again."),
    ("How do I open a page or table in another window?", None, "window screen monitor popout new window separate second",
     "\"New window\" in the top bar opens the page you are on in a window of its own, without the side menu, so you can move it to "
     "another screen. Every table also has \"New window\" above it. The labour calendar and its unassigned pools each open on their own."),
    ("How do I sort or filter a table?", None, "sort filter column order original reset search table",
     "Click the small arrow in a column heading to sort (ascending, descending, off). \"Filter\" above the table adds a box under each "
     "heading: type text to match, or >1000, <0, =0 for numbers, and !text to exclude. \"Original order\" puts it back in CBS order."),
    ("How do I set how pages open (my defaults)?", "settings", "default defaults settings preference month grid level open start page weeks",
     "Settings > Your defaults: the page PMT opens on, cost control's level, monthly grid and empty lines, the labour calendar's weeks "
     "and whole-project view, and more. They apply to you on this PC, for every project."),
    ("Where does a dashboard tile take me?", "dashboard", "tile click dashboard chart open source drill",
     "Click any tile or chart to open the data behind it: Accruals opens the accruals, Cost to date the actuals, Cost to complete the "
     "forecast lines, and so on. Bars on the allowance chart drill into the next CBS level."),
    ("How do I add an accrual?", "accruals", "add accrual new manual invoice not yet received estimate approval po quote",
     "Accruals > + Add accrual. Choose what it is: an estimate of work done (the least certain: it stays until you reverse it) or an "
     "invoice awaiting approval (give the supplier and its PO, invoice and / or quote number: it matches the invoice by itself when it "
     "lands in Pronto). Hours go on the labour calendar. PMT refuses an invoice already in Pronto, and warns when finance has already "
     "accrued that PO or supplier on the line."),
    ("What happens when the invoice of an accrual lands in Pronto?", "accruals", "accrual invoice lands reverse reversal matched month work performed timing",
     "PMT matches it by invoice number, quote number or PO. The invoice amount then counts in the month you accrued (when the work was "
     "done), and the accrual reverses in the month the invoice landed, so that month nets to zero. If the invoice is for a different "
     "amount it is flagged: accept the invoice amount, or keep the rest open if part of the work is still to be invoiced."),
    ("How do I bring my PMT Excel workbook into the app?", "cbs", "excel workbook xlsm import load allowance ledger accrual register cost control migrate",
     "CBS and allowances > Load PMT workbook...: choose the .xlsm. The preview shows how its lines match the Pronto lines and what "
     "will be created. Apply sets every line's allowance to the workbook's Cost Control (the Ledger is replayed as transfers), makes "
     "each line MANUAL with the workbook's forecast grid from the status month, and loads the accrual register. A tie-out per "
     "category follows. Set the status date first so the months line up."),
    ("How do I see the raw Pronto rows? Is a totals row skewing the data?", "pronto", "raw pronto rows inspect totals row future date wrong year keying error duplicate check",
     "Pronto data > Inspect rows on each report shows the rows exactly as loaded: search every column, sort, export to Excel. "
     "Checks on the loaded rows lists rows dated after the status date (often a year keyed wrong in Pronto), rows that look like "
     "a report's totals or a blank line, very large cost entries reversed soon after (keying errors), and identical rows. "
     "Click a check to see its rows. The card's \"to\" date ignores future-dated rows and counts them apart."),
    ("Has finance already accrued this in Pronto?", "accruals", "finance accrual pronto work in progress wip journal double accrue twice",
     "Accruals > Accrued by finance in Pronto: the month-end accrual journals on the Work in Progress account and their reversals. "
     "Open ones are already in cost to date: do not accrue them again. An accrual of yours on the same line and PO or supplier counts "
     "only above finance's."),
    ("What do I do with unposted timesheets?", "accruals", "unposted timesheets hours no cost approval journal another project move dispute",
     "Accruals > Unposted timesheets: hours entered in Pronto, not yet approved. PMT accrues them at the person's cost rate until they "
     "are posted; Accrue makes it your own accrual. If the hours do not belong to this project, use Not ours: move... to record a "
     "journal request (and copy the email text for payroll): the hours stop accruing here, and the request closes once Pronto moves them."),
    ("Work performed, billed and paid: what is the difference?", "accruals", "timeline work performed billing cash paid finance pm reporting cashflow",
     "Accruals > Work, billing and cash. Work performed: when the work was done (what the PM reports). Billed: when it reached Pronto. "
     "Paid: when the money leaves (invoice date plus the supplier terms in Settings). The gaps are the accrued position and what is "
     "payable to suppliers."),
    ("How do I load the Pronto exports?", "pronto", "pronto upload load export gl transactions labour po claims import",
     "Pronto data: drop each export on its placeholder (GL transactions, labour, purchase orders, claims, CTD overview). Re-uploading a "
     "newer export replaces the old one; your tags and accruals stay."),
    ("How do I forecast a line?", "forecast", "forecast method ctc ground up calendar roster milestone at budget",
     "Forecast lines: open a line and pick its method. At budget holds the remaining allowance; ground-up builds it from items: a "
     "resource calendar, a roster, milestone payments, quantity x rate, or typed months. The preview shows it by month."),
    ("How do I price a variation?", "variations", "variation price markup risk spread cost revenue client proposal",
     "Variations: open one, Pricing tab. Add price items and the cost lines that build them (each on a CBS line), with risk and markup. "
     "Spread cost over other price items if needed, choose how much detail the client sees, and print the proposal. On approval, "
     "top up the CBS lines or copy them to track the variation separately."),
    ("What does Diagnostics show?", "diagnostics", "diagnostics differences pronto mismatch tie match supplier po",
     "Every place PMT and Pronto disagree, worst first: costs that do not tie, suppliers and POs entered ahead of Pronto (with a "
     "one-click match), accruals that landed for a different amount, unposted timesheets and claim differences."),
    ("How does sharing with the team work?", None, "share sharing team sharepoint onedrive sync colleagues journal",
     "Everyone runs PMT on their own PC from a SharePoint folder synced with OneDrive. Changes travel through the shared folder and "
     "merge every few seconds, with who made each change. See \"Sharing a project through SharePoint\" in the guide."),
    ("How do I change many rows at once, reorder rows or widen a column?", "revenue", "fill handle bulk edit drag rows reorder column width autofit resize",
     "Payment Milestones is edited in the table itself: change a cell and it saves. Click a cell, then drag the small orange "
     "square at its corner down or up over other rows: they all take that value (not the item number). Drag a row by its "
     "body to move it within its group (also on the CBS and project schedule milestones). Drag a column header border to resize it, "
     "or double-click the border to fit the content; widths are remembered for that page."),
    ("How do I link projects into a parent project, and see a portfolio or program together?", "linked", "link parent child project portfolio program director combined cbs rollup drill down",
     "SETUP > Linked projects: tick the projects, name the parent and its project director, then Link. The parent project "
     "adds its children's CBS together line by line (the same CBS code is one line) and cannot be edited: each PM keeps working "
     "in their own project. Click any line or amount for each project's share, then Open in project to land on that project's own "
     "line. For a PM's portfolio or a director's program: OVERVIEW > Portfolio, choose the person, then Combined CBS."),
    ("Where are the over and underruns, and every budget movement?", "risk", "contingency overrun underrun ledger movements transfer reason date",
     "COST > Allowances (four tiles: Allowance, Risk register, Ledger, Contingency). Contingency: every CBS line forecast above (overrun) or below (underrun) its allowance, grouped "
     "by CBS with subtotals; click a line to open it in cost control. Ledger: every movement of budget, risk and contingency per "
     "CBS line (original estimate, transfers, risk releases, variations, adjustments) with its date, reference, reason and who made it."),
    ("How do I pick a client or person, or add a new one?", "setup", "client project manager director dropdown database add new name lookup",
     "Fields that ask for a client, project manager, director or resource list the company database as you type. Pick a name, keep "
     "typing a new one, or click + Add to put it in the database. OVERVIEW > Stakeholders holds them all."),
    ("How do I go back to the previous page?", "dashboard", "back previous page escape esc keyboard close dialog",
     "Press Esc. It first closes an open dialog, drawer or the help panel, then leaves the field you are typing in, and "
     "otherwise goes back to the previous page you opened in PMT (never out of PMT)."),
    ("What is the difference between the payment milestones template and the claim schedule template?", "revenue", "template payment milestones claim schedule claimed approved month grid download import",
     "Both list the contract's milestones (item, description, stage, kind, status, in the original contract or not, dates, "
     "value). The payment milestones template (Contract value tab) stops there. The claim schedule template (Claim schedule "
     "tab) adds a month grid with a Claimed and an Approved column per month. Importing it sets each item's monthly claim "
     "profile from Claimed and records past months as progress claims, with Approved as the certified amount."),
    ("I uploaded the wrong data into one part of the setup. How do I clear just that part?", "setup", "erase clear wrong data section payment milestones cbs project schedule details",
     "Project setup: each step (Project, Contract value, CBS and allowances, Project schedule) has \"Erase this section\". It clears only "
     "that part; anything carrying real data (claims, Pronto cost, accruals, forecast) is kept and listed. \"Undo: erase ...\" at the "
     "top of Project setup puts it back."),
    ("I loaded the wrong Excel file into a project. How do I undo it?", "setup", "undo revert wrong excel load template reinitialise re-initialise restore name",
     "Project setup > Undo last Excel load puts the project back as it was before that load: its details and name, CBS items and "
     "allowances, payment milestones, resources, rate card and project schedule; lines the load created are removed. Load from Excel "
     "always shows what it would change first (and warns when the file is another project's); nothing is written until you Save. "
     "Choose the loading mode as for Pronto: Update and add keeps everything the file does not list; Replace makes the file the "
     "setup and removes CBS items, allowances and payment milestones it does not list, except those that carry data."),
    ("How do I archive or delete a project?", "settings", "archive archived delete remove old finished project list restore hide",
     "Archive finished projects: Settings > Archive > Archive this project. It moves from the running projects to the "
     "Archive (PMO > Archive) for everyone sharing it, with its contract value, final cost and margin as "
     "they stood. Nothing is deleted. In the library, search by name, client, location, project manager or director, the period "
     "it ran and its contract value; open a project to look through it, or restore it. To delete a project for good (it cannot "
     "be undone, and it goes for everyone sharing it): Settings > Delete a project, choose it from the list, click Delete..., "
     "then OK on the confirmation."),
    ("What does the Portfolio show?", "portfolio", "portfolio program schedule director manager my projects analytics all projects compare",
     "OVERVIEW > Portfolio puts the running projects side by side: the projects you manage, the program you direct (as named on "
     "Project setup: EPEC project manager, EPEC project director), anyone else's, or all of them. Tiles total contract value, "
     "final cost, margin, erosion and claims; the charts compare margin at tender and now, contract value against final cost, "
     "cost and revenue by month and cumulative, time elapsed against cost spent, and contingency per project. A director also "
     "gets a table by project manager. Click a project to open it."),
    ("How is a PM's workload worked out?", "portfolio", "workload team capacity pm level overloaded percentage director complexity travel spread",
     "Portfolio > Team workload. Each running project asks for a share of a full-time PM Level 2 at the peak of delivery, by its "
     "complexity (1 = 15% to 5 = 85%). A difficult or high-risk client adds to it; the phase changes it (mobilising 35%, delivery 100%, "
     "commissioning 75%, close-out 40%); a site far from the PM's base adds travel (up to +25%), and sites spread far apart add up "
     "to +20% on everything. Capacity follows the PM level in EPEC-PM-FW-0002 (Level 1 = 0.6, 2 = 1.0, 3 = 1.25, 4 = 1.5) times the "
     "time they have. Workload % = demand / capacity: under 70% room for more, above 105% overloaded. A project more complex than the "
     "PM's level is flagged as a stretch. Set PM levels, time and home base with \"+ Add a person\" or by clicking a PM."),
    ("Where do I record a client's risk and contacts?", "portfolio", "client crm contacts risk profile difficult complexity sector relationship",
     "Portfolio > Clients: a card per client with sector, head office, key contacts, risk profile (Low, Medium, High), how difficult "
     "they are to work with (1 easy to 5 difficult), payment terms and the relationship, plus their running and finished projects "
     "with margins. Clients come from the projects (Project setup: Client); the card adds the detail. A difficult or high-risk client "
     "adds to the PM's workload."),
    ("How do I put a project on the map?", "setup", "map location site latitude longitude world map type mw mwh voltage asset",
     "Project setup > Asset and site: choose the type (solar farm, wind farm, BESS, hybrid, mining, transmission, substation), capacity in MW, storage in MWh, "
     "the voltage levels (e.g. 33/330) and the complexity, then find the town (needs internet) or click the site on the map. The "
     "Portfolio map then shows it, coloured by type and sized by contract value."),
    ("Can I open PMT from SharePoint in the browser?", None, "sharepoint browser click exe download open run onedrive synced shortcut",
     "Yes, once PMT has run from the synced library on your PC. A browser only downloads PMT.exe; the downloaded copy then "
     "finds the PMT folder that OneDrive syncs and starts PMT from there. If it cannot find one, it explains how to sync the "
     "library (SharePoint > Sync, then File Explorer > your organisation > PMT > PMT.exe). You can delete the downloaded copies."),
    ("Where do I see the invoices of a supplier or subcontractor?", "actuals", "invoices invoice supplier subcontractor actuals po receipt paid billed vendor creditor",
     "COST > Actuals > Invoices by supplier: every invoice Pronto has posted to the project (purchase-order receipts, direct "
     "invoices and supplier journals), per supplier. Click a supplier for its invoices, its invoicing by month, its purchase "
     "orders and, for a subcontractor, its claims approved in PMT against what has been invoiced. Search by invoice number, PO "
     "or description; Export to Excel lists suppliers and every invoice. The invoices come from the Pronto GL transactions export."),
    ("How do I ask Microsoft Copilot instead?", "settings", "copilot microsoft ai chat assistant studio agent",
     "In the chat panel, Copilot tab: \"Open Copilot Chat\" copies your question with what you are looking at and opens Microsoft 365 "
     "Copilot Chat; paste it there. For a Copilot that knows PMT, IT can make a Copilot Studio agent with the PMT guide as its "
     "knowledge (Download the guide below) and publish it to a website; put its web chat address in Settings > Your defaults and it "
     "answers inside this panel."),
    ("How do I fill in the claim schedule and claim this month?", "revenue", "claim schedule grid month type percent dollar percentage drag move forecast revenue submit pdf excel progress claim status month cap price 100",
     "Open Contract and claims > Claim schedule. Click a month on a line and type a dollar amount or a percentage of the line's price "
     "(25%, 12000, or rest for whatever is left). A line can never be scheduled for more than its price in total, claims already issued "
     "included. What you type in the status month is this month's claim: use \"Create the claim\" in the bar above the grid, then open the "
     "claim and export it as a PDF or Excel for the client, and mark it as submitted. Months after the status month are your forecast "
     "revenue. Drag the grip that appears on a value onto a later month of the same line to move it. Months already claimed are locked. "
     "If a line is scheduled for more than its price (an old even spread, for example), \"Trim the excess\" takes it off the latest months. "
     "To load a whole claim schedule that already has past months, this month and the forecast, use Import claim schedule and choose Overwrite: past months become claims already made, the status month the draft claim, later months the forecast."),
    ("How do I record the project's gate and download the gate paper?", "setup", "gate gates 1 2 3 4 5 6 7 handover approval proceed proposal deliver completion early works epc paper form download",
     "Project setup > Project > Project gate: choose the gate the project has reached (1 to 7), what it applies to (whole project, Early Works or EPC), "
     "the date and a note, then Record gate. Every change is kept and the latest is where the project stands, so a project can go back from Gate 5 to Gate 3 "
     "for an EPC award after Early Works. Choosing a gate shows a link to download that gate's paper (Word) for Gates 1 to 7. Portfolio shows each project's gate."),
    ("How do I rate how challenging a client is?", "portfolio", "client challenge knowledge difficulty grid clueless expert client pm complexity assessment director programme",
     "Stakeholders > Clients > open a client: click the square on the grid (across: how much they know, clueless to expert; up: how difficult they are). "
     "Each month, the EPEC PM records on Project setup (or the client card, Assess) how hard the client's project manager is and how complex the project is. "
     "The challenge score is half the grid position and half the mean of those assessments across the client's projects. Portfolio shows it to project directors."),
    ("What reminds me what to check when the project moves to a new phase?", "setup", "phase design procure construct commission close out readiness review checklist site start up reminder download",
     "Project setup > Project > Delivery phase: choose the phase the project has moved to (Design, Procure, Construct, Commission or Close Out) and Move to this phase. "
     "PMT lists what to look for and offers EPEC's papers: the Site Start Up Planning Meeting and Construction Readiness Review (Phase 2) for Construct, the Commissioning "
     "Readiness Review (Phase 3) for Commission. Papers EPEC has not supplied (design review, Ready to Close Out review) are named without a download."),
    ("How do I show who the owner, developer, builder and NSP are and how they communicate?", "orgchart", "org chart organisation chart owner developer builder principal contractor contractor nsp transgrid powerlink reporting line communication contract parties",
     "SETUP > Project org chart: EPEC is always on the chart, as the Principal Contractor or the Contractor (choose at the top). Start from a template or add parties "
     "(owner, developer, builder, principal contractor, contractor, NSP such as Transgrid or Powerlink, subcontractor, consultant). Drag a box to move it, click it to change its role, "
     "name or note. Draw a line, then click two boxes, to join them as a contract, a reporting line (the arrow points to who is reported to) or communication; click a line to label it, "
     "swap its direction or delete it. It saves as you go, and Download image gives you an SVG for a presentation."),
]

GLOSSARY = {
    "ctd": "cost to date", "ctc": "cost to complete", "eac": "estimate at completion", "acc": "accruals accrual", "po": "purchase order",
    "pos": "purchase orders", "nt": "normal time", "ot": "overtime", "cbs": "cost breakdown structure", "pmr": "project monthly report",
    "eom": "end of month report", "cmt": "cost management tool", "sov": "payment milestones schedule of values", "var": "variation", "vo": "variation",
    "subby": "subcontractor subcontract", "subbie": "subcontractor subcontract", "gl": "general ledger transactions", "ts": "timesheet",
}
STOP = set("a an and are as at be but by can do does for from how i if in into is it its me my of on or so that the then this to "
           "up use what when where which who why will with you your there their them was were".split())


def _words(text):
    out = []
    for w in re.findall(r"[a-z0-9%]+", (text or "").lower()):
        if w in STOP:
            continue
        out.append(w)
        if w in GLOSSARY:
            out += GLOSSARY[w].split()
        if len(w) > 4 and w.endswith("s"):
            out.append(w[:-1])
    return out


def _readme():
    try:
        return (ROOT / "README.md").read_text(encoding="utf-8")
    except OSError:
        return ""


@lru_cache(maxsize=1)
def topics():
    """Every topic in the guide: {id, title, page, text, keys}."""
    out = []
    for i, (title, page, keys, text) in enumerate(FAQ):
        out.append(dict(id=f"faq{i}", title=title, page=page, text=text, keys=keys))
    md = _readme()
    # the "What it does" table: one topic per area
    for area, text in re.findall(r"^\| ([^|]+?) \| (.+?) \|\s*$", md, re.M):
        if area.strip() in ("Area", "---") or set(area.strip()) <= {"-"}:
            continue
        page = next((k for k, v in PAGES.items() if v.lower() in (area + " " + text[:80]).lower()), None)
        out.append(dict(id="area-" + re.sub(r"\W+", "-", area.lower()).strip("-"), title=area.strip(), page=page, text=_plain(text), keys=area))
    # the README's other sections
    for title, body in re.findall(r"^## (.+?)\n(.*?)(?=^## |\Z)", md, re.M | re.S):
        if title.strip() in ("What it does", "Tests", "Design notes"):
            continue
        out.append(dict(id="sec-" + re.sub(r"\W+", "-", title.lower()).strip("-"), title=title.strip(), page=None, text=_plain(body), keys=title))
    return out


def _plain(md):
    md = re.sub(r"```.*?```", "", md, flags=re.S)
    md = re.sub(r"\*\*(.+?)\*\*", r"\1", md)
    md = re.sub(r"`([^`]+)`", r"\1", md)
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def answer(question, page=None):
    """The best topics for a question: {answer: topic or None, related: [topics], page_topic}."""
    q = _words(question)
    scored = []
    for t in topics():
        title, keys, body = set(_words(t["title"])), set(_words(t["keys"])), _words(t["text"])
        bodyset = set(body)
        s = 0.0
        for w in set(q):
            s += 3 * (w in title) + 2 * (w in keys) + (1 if w in bodyset else 0)
        if page and t["page"] == page:
            s += 0.5
        if s:
            scored.append((s / (1 + len(body) / 400), t))
    scored.sort(key=lambda x: -x[0])
    best = scored[0][1] if scored and scored[0][0] >= 1.5 else None
    related = [t for _, t in scored[1:5] if best and t["id"] != best["id"]] if best else [t for _, t in scored[:4]]
    return dict(answer=best, related=[dict(id=t["id"], title=t["title"], page=t["page"]) for t in related])


def page_topic(page):
    """What the page you are on is for."""
    name = PAGES.get(page)
    if not name:
        return None
    for t in topics():
        if t["id"].startswith("area-") and (t["page"] == page or t["title"].lower() == name.lower()):
            return t
    return next((t for t in topics() if t["page"] == page), None)


def suggestions(page):
    """A few questions worth asking on this page."""
    on = [t["title"] for t in topics() if t["id"].startswith("faq") and t["page"] == page]
    general = ["What is EAC and how is it calculated?", "How do I open a page or table in another window?", "How do I set how pages open (my defaults)?"]
    return (on + [g for g in general if g not in on])[:4]


def guide_md():
    """The whole guide as one Markdown document (for a Copilot Studio agent's knowledge, or to read)."""
    from . import build
    lines = [f"# PMT (Project Management Tool) user guide", "", f"Release {build.RELEASE}. EPEC's project cost control tool: "
             "CBS, Pronto data, accruals, forecasts, subcontracts, claims, variations, risk and reports.", ""]
    lines += ["## Pages", ""] + [f"- {v} (menu)" for v in PAGES.values()] + [""]
    lines += ["## Questions and answers", ""]
    for t in topics():
        if t["id"].startswith("faq"):
            lines += [f"### {t['title']}", "", t["text"], ""]
    lines += ["## What each part of PMT does", ""]
    for t in topics():
        if t["id"].startswith("area-"):
            lines += [f"### {t['title']}", "", t["text"], ""]
    for t in topics():
        if t["id"].startswith("sec-"):
            lines += [f"## {t['title']}", "", t["text"], ""]
    lines += ["## Abbreviations", ""] + [f"- {k.upper()}: {v}" for k, v in sorted(GLOSSARY.items())] + [""]
    return "\n".join(lines)
