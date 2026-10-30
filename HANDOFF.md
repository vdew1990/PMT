# PMT handoff (read this first)

This file is the live state of the Project Management Tool (PMT) build. It travels inside the code zip, so whichever
Claude account opens the zip next can carry on from here. It is overwritten in place as work lands, not appended
as a session log.

**Rule for every session (either account):** update the Status and Next step of a thread the moment a unit of
work lands, in the same turn. Before handing the zip back, bump the bundle version below and add one line to the
Bundle history.

## Bundle

- Bundle version: **2026-10-31.121** (CRM link path from a settings file, `crm_link.txt`; before that .120: CRM link: start a project from an MM_CRM opportunity, read-only, one way copy; before that .119: personal account: baseline visible to Project Director and above, PM level kept apart from the ECF level, leavers across projects, the org chart load with duplicate merge, the paper's sign-off block, the data objects catalogue and My profile; before that .118: the PM's competency by dimension against the baseline (director only); before that .117: the EPEC Classification Framework in the team (ECF role, level and business title on each person, levels in the team read from it); before that .116: team looking ahead, monthly team confirmation, the director's Team fit view and the Word resourcing paper; before that .115: the Project team page (team chart, each role against the band, first risk rule) and competency levels by role on the person; before that .114: project complexity (ten dimensions, bands, radar, the director's baseline and the PM's monthly assessment); before that .113: the Ground-Up register, forecast method changed only on the Cost control row, the claim schedule and by building a line ground-up, and a fix for saving forecast items; before that .112: Allowance as a setup step with multi-select, a pre-flight before Initialise, a What next card, one Month-end page, a close-out checklist; before that .111: the quiet design restyle, one extra stylesheet; before that .110: the outline for month and day grids, hidden columns take no width; before that .109: margin bridge on the dashboard tile and an accruals master list by party; .108: ledger as a CBS tree with funding and reasons, in-place redraws, Columns and Group by CBS on every table, variation placeholders from the contract, setup tidy-ups; before that .107: quarters as foldable column groups, Allowances panes in separate windows, right pane columns shrink together, one-line pane headers on Allowances, Meetings moved under Communication, clickable lifecycle and delivery phase tiles with start, end and note, month grid with frozen working columns, quarters and hidden months, claim line windows linked to the client schedule, Start End Mths on Allowances lines, Allowances tree with multi-select and return, Undo and Redo buttons, minimal Allowances design, drag to reorder, adjustable panes, separate filters on the Allowances panes, Revert button, collapsible and re-orderable Allowances workspace, three placeholders per CBS parent, Allowances hub, allowance page, workflow page, forecast typing, activity window with schedule drivers, month forecast window). Release notes per version are the "Release" sections at the end of this file; the team and accountability design (not yet built) is in "Design agreed with Vincent"
- Received from: `pmt-app_20261021_business_9.zip` (business account, 2026-10-21.36) merged with the personal account's claim schedule
  work (threads 29 and 30, built on `pmt-app_20261021_business_8.zip`); see thread 31
- How to resume: unzip, `python -m venv .venv && .venv/bin/pip install -r requirements.txt`,
  `.venv/bin/python -m pytest tests -q`, then read the threads below

## Threads

### 1. Multi-user on SharePoint, user identity, change history
- Status: built and checked in a browser with two simulated users sharing one folder. Backend: `app/identity.py`,
  `app/changelog.py` (triggers), `app/sync.py` (journal export/import/merge, first publish), `app/activity.py`,
  `app/launch.py` (port pick, shared-mode detection). UI: user chip + "You and sharing" dialog (role, people,
  sync now), CONTROL > Activity and history page, History buttons on accruals, History tab in the cost-control
  drawer, "publish existing database" on the welcome screen in shared mode, toast + refresh when colleagues'
  changes arrive. run.bat keeps the venv and pycache in %LOCALAPPDATA%\PMT. 91 tests pass.
- Next step: none required for this thread now. Backlog: journal compaction (snapshot + high-water mark) once
  journals get large; verified Entra sign-in (MSAL) if IT registers an app; test on a real SharePoint library.

### 2. Forecast module
- Status: built and checked in a browser. FORECAST group in the left panel: "Forecast lines" (`static/js/views/forecast.js`:
  list + full-page line editor with Calendar day grid, Milestones list with presets, Roster with live preview, classic
  items) and "Labour calendar" (`static/js/views/calendar.js`: timesheet / unposted / accrued / forecast hours per day,
  type to forecast or accrue). Resources > Supplier rates tab; Settings > Public holidays. Cost-control drawer links to
  the Forecast editor. Demo project seeds one roster, one milestone item, one calendar and an hours accrual.
  Hours accrual with no rate is refused with a message. Nested pools (D13) built and checked. 104 tests pass.
- Next step: Vincent to try it on the real Wandoan data and say what feels wrong. Backlog: copy supplier rates and
  holidays when cloning a project; Excel import of supplier rates and of a Ground-Up day grid; per-role permissions
  (for example only the PM reverses accruals) if wanted.

### 3. Monthly review loop (cost control and labour calendar in the workbook's colours)
- Status: built and checked in a browser (Vincent's request of 16/10).
  - Labour calendar (`static/js/views/calendar.js`): Cost Control sheet colours at hours level.
    - Forecast days are light green; click to type (autosave). The current month is doubled: darker green forecast
      line above, darker blue landed line below.
    - Past days show Pronto timesheet hours read-only: pink when posted (matching any accrual), purple when the
      timesheet differs from what was accrued, light blue for accruals or unposted timesheets.
    - Click an empty past cell to accrue hours. Click a timesheet cell for its detail.
    - `forecast.day_state` holds the rule. An hours accrual for different hours than the timesheet becomes
      'investigate'.
  - Cost control month grid: the same colours, with the current month doubled. "(F)" is the month as forecast at
    the last month-end snapshot (`review.planned`); next to it is what landed, with "+$x" still forecast.
  - Clicking CTC opens a month pane (`monthsPane`): the line by month plus a what-if of every method
    (`GET nodes/{id}/what-if`, nothing saved until "Use this"), with links to the ground-up detail, the claim sheet
    (CLAIM), the month-end review and the records.
  - New FORECAST > Month-end review (`app/review.py`, `static/js/views/review.js`): per line, planned (last
    month-end) against actual + accrued. Prefilled "accrue the difference", "slipped: reforecast" (opens the right
    place per method), a decision per line per month (`month_review` table, audited), and keyboard ↑/↓ to cycle.
- Next step: Vincent to try the review loop on real data. Open question 2 below.

### 4. Subcontractors: lump-sum claim sheet and schedule-of-rates calendar (Vincent, 16/10)
- Status: built, tested and checked in a browser.
  - Lump sum: "Claim sheet" tab in the subcontract drawer, per schedule line by month, in the workbook colours:
    - Past claims: pink when invoiced, light blue when accrued.
    - This month doubled: forecast (dark green) next to claimed/approved (dark blue).
    - Future: the PM's forecast, typed (light green). Buttons: start from the schedule, slip one month, back to
      the schedule. The CLAIM method uses the PM forecast (`sub_forecast`, `subcontracts.direct_net`). A month with a
      received claim is never forecast again, and the unclaimed remainder is never lost.
  - Schedule of rates: Labour calendar > Subcontractor timesheets: download a template, upload it
    (`site_files.timesheet_template/import_timesheets`, `sub_timesheet`; re-uploading skips rows already there).
    - Hours show as "T x" on supplier rows (per role). The PM accrues them: bulk or per cell, priced per worker
      from the supplier rates.
    - "Invoice ref..." gives a month's accruals the subby's invoice number. Accruals sharing a reference are
      matched as a group against the invoice total: pink when it agrees, purple when it does not.
  - 3-week lookahead: Labour calendar > 3-week lookahead: download a template pre-filled with the current supplier
    forecast from the Monday after the status date, people a day per supplier/role/line. Upload writes the three
    weeks (blank = nobody). A roster on the same line is first turned into a "people" calendar, so the lookahead
    replaces days; later swings are kept. New Calendar basis "people" (headcount x hours a shift).
  - NT/OT (Vincent's mid-turn request): clicking an editable calendar cell (forecast or accrual) splits it into NT
    and OT boxes. OT is priced at the OT rate as typed (`forecast_day.ot`, `accrual.ot_hours`, `split_cost`).
    Untyped days keep the automatic split (above the normal hours a day).
- Next step: Vincent to try a real subby timesheet and lookahead. Backlog: show NT/OT on posted Pronto timesheets
  (needs the Pronto work rate codes for overtime); a list view of uploaded subby timesheets.

### 5. History pages, EOM report, sums in number cells (Vincent, 16-17/10)
- Status: built, tested and checked in a browser.
  - Forecast history (FORECAST > Forecast history), Actuals (COST > Actuals) and Accruals > "By month and history":
    one page design (`static/js/views/_history.js`, `app/timeline.py`). Pick a close ("As at" dropdown, arrows or
    "Play the closes"):
    - the cost curve at that close with earlier closes faded (a perfect forecast keeps the curves on top of each other);
    - EAC (or cost to date / accrued) at each close;
    - a matrix "<metric> at each close" that answers "what did I forecast for Sep-26 back in Jul-26";
    - per line: method (with "was X" when it changed) and the change against the previous close.
    Day zero (baseline) is always the first close. Closes now store actual / accrued / forecast by month and the
    method per line (`snapshot_line.a_json/x_json/f_json/method/kind`); older closes only have the total by month
    (taken as actual before the close month, forecast from it).
    Cost control and the labour calendar stay the combined monthly views.
  - EOM report (Reports and history > EOM report; `app/eom_report.py`): the workbook's "EOM Report" sheet (sheet36)
    plus the requested cashflow graph and monthly / cumulative table. Download as PDF (reportlab, A3 landscape like
    the sheet's print setup) or Excel (native combo chart, A3, cost rows grouped by level). Revision defaults to
    the number of EOM closes; "Hide zero lines" as on the sheet. The sheet's tie-out block (not printed) is not
    reproduced: the report reads the same engine as cost control, and the page shows whether the EAC ties.
  - Sums in number cells: every number field accepts `8*5`, `=1200/3`, `(10+2)*4`, `1,500 x 3`, `$2,000 ÷ 4`.
    Done once in `ui.js`: `h()` makes number inputs calculator fields and a capture-phase listener works the sum out
    before the page's own change / Enter handlers run; a safe parser (`calc`), no eval. A sum that cannot be worked
    out is outlined red. Excel uploads already read formula results (`data_only=True`).
- Next step: Vincent to check the EOM report against the workbook for a real month. Backlog: revenue "Invoiced"
  and "Paid" are split base / variations in the approved ratio (as the workbook); cashflow is on an earned basis,
  payment terms (Settings has client and supplier terms) could shift it to cash in / cash out later.

### 6. Launcher window and icon (Vincent, 17/10)
- Status: built and compiled (Zig, no warnings; icon, manifest and version embedded). NOT yet run on Windows here
  (no Windows or Wine in the build container): Vincent to try it.
  - PMT.exe (`launcher/launcher.c`) is a window, no console: PMT tile, "Project Management Tool loading...", the
    current step with a running timer, a moving progress bar and the hourglass pointer while it starts. "More info"
    shows run.bat's output live; "Copy details" copies it. On "ready" it opens the browser and shows "running";
    closing the window or "Stop PMT" stops PMT (job object). Errors expand the details automatically.
  - Protocol: run.bat and app/launch.py print `##PMT step|ask-python|ready|already` lines when PMT_GUI=1. Missing
    Python: run.bat exits 10, the window asks Yes/No, then reruns with PMT_INSTALL_PYTHON=1. The window opens the
    browser itself (PMT_NO_BROWSER=1 for Python) so the browser is never inside the job.
  - Icon: the logo on a white rounded tile (all sizes 16-256), because the navy bars vanished on dark
    backgrounds and left only the orange ring. Original kept in git history.
- Next step: Vincent to run PMT.exe on a PC (first run with no venv, a normal start, a second start while running).

### 7. Subcontract payment terms and Excel payment schedule; update safety; tree levels (Vincent, 17/10)
- Status: built, tested (121 tests) and checked in a browser.
  - Payment terms (D19): a subcontract's price splits into portions: Milestone (% of contract, claimed when achieved),
    Progress (% claimed monthly) and Variation (value). New line type Price = a price-table item. With a price table
    the Progress portion is claimed through the items: each item is claimable at price x progress share (the Progress
    %, or 100% less the milestones), and the Progress line itself is not claimed (`subcontracts.progress_share`,
    `items(..., claimable_only)`, `terms`). Without a price table the Progress line is claimed as before, so existing
    subcontracts are unchanged. UI: "Payment terms and prices" tab (terms, price table, variations, each with a total);
    claim dialog shows "Price x 80%" and a "% complete" helper.
  - Subcontractor's planned claims: new table `sub_plan` (claimable $ per line per month). It replaces the even spread;
    a plan loaded mid-project keeps the line's full value (the part before the plan sits in the month before it).
  - Excel payment schedule (`app/subcontract_io.py`): Subcontracts > Download template / Download all / Upload payment
    schedule (preview, then apply); per subcontract "Download to Excel". One sheet per subcontract: header, table of
    lines with claimed to date / current claim / residual and approved to date / current approval / residual, and two
    month grids (claimed: claims to the status month, subcontractor's plan after; approved: approvals, then your planned
    approval = `sub_forecast`). Colours follow the status month cell. Upload at the start of a job or mid-project;
    lines missing from the sheet are kept; a blank month leaves PMT's claim as it is; a re-upload of an unchanged
    download changes nothing (tested).
  - Update safety: `app/build.py` fingerprints the program files. /api/me returns build and build_now; the page shows a
    banner when they differ; app.launch stops an older server of the same user (POST /api/shutdown, local + X-PMT
    header) and starts the new one; PMT.exe shows "##PMT fail" text if it cannot. Cause: Vincent saw "Not Found" on
    Actuals because an old server was serving the new pages.
  - CBS and allowances: total line and "Expand to Level 1-5" (as cost control). Contract value and Claim schedule:
    the same levels plus an arrow per group; the claim schedule now shows group subtotals and freezes Ref and
    Description while scrolling sideways (`table.freeze2`).
- Next step: Vincent to try the template on a real subcontract (start-of-job and mid-project).

### 8. Suppliers and POs, Diagnostics, variation register, identity fix, stale servers (Vincent, 17/10)
- Status: built, tested (126 tests) and checked in a browser.
  - Subcontract template: Claimed and Approved sit next to each other under each month (hidden row of month dates
    above the headings drives the formulas and the upload; uploads of the earlier two-grid layout still read). Month
    headings black on the status colours; the fixed columns keep navy/white. New header field "Supplier name".
  - Supplier and PO linking (`app/suppliers.py`, `static/js/views/_supplier.js`): one picker in the upload preview (per
    sheet) and the subcontract editor. A known Pronto supplier (register, POs, transactions) fills its code and lists
    its POs (value, open/closed, CBS); any other name is kept as a new supplier (`subcontract.supplier_name`), and a PO
    can be typed ahead of Pronto. Both show "to be matched" until Pronto has them.
  - Diagnostics (CONTROL > Diagnostics, `app/diagnostics.py`): every PMT vs Pronto divergence by section (Pronto data,
    subcontract suppliers/POs with one-click "Match to ..." / "Use PO ...", cost tie-out, unplaced categories, parked
    actuals, POs missing, CTC below PO, accruals investigate/partial/old, unposted timesheets not accrued, client
    claims, variations not in Pronto). Reuses reports.health / reconcile and eom_report checks.
  - Variation register in Excel (`app/variation_io.py`): Variations > Download register / Upload register (preview,
    apply). Matched by Ref; new Ref adds, blank Ref numbers itself; a changed value becomes a new revision; status
    changes go into the history; recognition (revenue + allowance) re-synced as on the page.
  - View names: "Current allowance" (budget incl. risk the company has released, D20) and "Total allowance" (+ risk the
    company still holds).
  - Identity fix (D21): OneDrive for Business "DisplayName" is the organisation (e.g. EPEC Group Pty Ltd). It is now the
    person's entity; the name comes from Office's user name, then Windows, then the email; company-like names are never
    used as a name. Profile dialog: name and entity (EPEC Projects / Group / Engineering Pty Ltd), shared like the role.
    History rows recorded under the company name show the person's name.
  - Stale servers: Vincent kept seeing "Not Found" (Actuals, Month-end review, Forecast history, Reports) because an
    old PMT process kept serving the new pages. launch.py now also ends an old server that cannot stop itself (Windows
    netstat + taskkill, only a server that answered as PMT for the same user). Release number shown at the bottom of
    the left menu (`build.RELEASE`); history pages show "Nothing to show yet" before the first close.
- Next step: Vincent to end the old PMT once (Task Manager > Python), copy this release over, open PMT.exe, check the
  release number reads 2026-10-17.12, set name/entity in the profile, then try Diagnostics on Wandoan.

### 9. Variation engine: cost and price build-up, spreads, client detail, funding (Vincent, 17/10)
- Status: built, tested (130 tests) and checked in a browser. Based on the workbook's Variation Engine / Proposal /
  Backend sheets (analysis: tbl_VariationEngine A58:AK388; levels VAR > H1 section > H2/H3 price item > LINE).
  - Model: `variation_price` (price items: section, name, pricing type, option + selected, client detail, spread,
    spread scope, carries) and cost lines (`variation_line.price_id`, extra_qty, contract_rate). Older variations'
    lines are adopted into one price item per section on first open (`variations._adopt_legacy`).
  - Formulas as the workbook (D22): qty = count x (hrs/day x days/wk x weeks + extra) or count x qty; cost = qty x rate;
    risk and markup both % of cost; a contract (sell) rate overrides the price. Options count only when selected;
    PS items are listed as provisional sums.
  - Spread (D23): a price item can be spread over the items that carry it, uniformly or in proportion to their price,
    over all sections or only its own; "carries" picks which items take a share. Price only moves; cost and risk stay
    on the spread item's CBS. (The workbook only had proportional and no carrier choice.)
  - Client detail (D24): items only / scope (line descriptions) / contributions (line prices incl. spread, no qty or
    rates) / full; set on the variation, overridable per price item. Proposal: `exporters.variation_proposal_html`,
    `?level=` to force one. Exclusions field added.
  - Funding (D25): "Top up the existing CBS lines" (as the workbook) or "Track this variation on its own CBS": copy a
    CBS group or line (and everything under it) for the variation (`variations.duplicate_cbs`; codes PS04-V001,
    PS04-V001.002; `cbs_node.variation_id / copied_from`). The variation's cost and risk then post to the copies;
    Pronto cost whose variation number matches the variation's Pronto ref or ref lands on the copies
    (`pronto.resolve_all`); copies are left out of the normal category/resource/PO matching.
  - Register: cost, risk, calculated price and margin columns on the page; a read-only "Cost and revenue" section in
    the Excel register.
  - Cost control (17/10): a CBS line and its variation copies show as ONE row (`engine.merge_variation_copies`,
    /cost-control?merge=1, cost control page only; copies stay real nodes elsewhere), marked "+n var". The drawer shows
    "Budget build-up" (`engine.budget_buildup`, /nodes/{id}/budget-buildup): original budget, movements, each
    variation (topped up here or tracked on its copy) = total budget; and "Base scope and variation scope" (allowance,
    CTD, ACC, CTC, EAC per part, Open to see a variation's copy on its own).
  - Copy modes (17/10): "Copy only the CBS lines this variation uses" (each used line/group copied alone, no
    placeholders; e.g. PS04.001-V003) or "Copy a whole CBS group..." (everything under it).
  - Vincent's answers (17/10): copies start with zero original estimate (only the variation's funds); variation-coded
    Pronto cost on a CBS that was not copied stays on the original line. Both as built.
- Next step: Vincent to rebuild one real variation (e.g. EPC-VAR-003) in the app and compare with the workbook, and
  try "track separately" on one.

### 10. Windows, sort and filter (Vincent, 17/10)
- Status: built and checked in a browser.
  - Every table (`static/js/tabletools.js`, attached automatically by a MutationObserver in app.js): sort arrows in
    the headings (ascending, descending, off), "Filter" row (contains; >, <, >=, <=, = for numbers; !text excludes),
    "Original order" back to CBS order, "New window" = a copy of the table in its own window (sortable/filterable).
    Sort/filter remembered per page+table, so redraws keep them. Opt out with class "notools"; day grids (.dg) are
    skipped; tables with rowspans (labour calendar) get only "New window".
  - Every page: "New window" in the top bar opens the page live in its own window without the side menu
    (?popout=1, body.popout).
  - Labour calendar: the unassigned pools collapse (remembered); "Own window" on the pools and "Calendar in its own
    window" open each part live on its own (#/calendar?part=pools|grid).
- Next step: Vincent to try on two screens.

### 11. Labour calendar: popout like the page, whole project by month (Vincent, 17/10)
- Status: built and checked in a browser.
  - A table can name its own page (`data-popout="#/calendar?part=grid"`): its "New window" then opens that page live
    (same layout, frozen columns, editing) instead of a static copy. Static copies drop sticky positioning so frozen
    columns no longer overlap.
  - "Whole project by month" chip: the grid spans project start to end (`/calendar` allows up to 1500 days); every
    month is one collapsed column (totals: landed for past months, forecast for future, both for the current month);
    click a month heading or cell to open its days. Only the current month is open to start with; open months are
    remembered (sessionStorage `calui.open`). The grid starts scrolled to the current month. ◀ / ▶ go back to the
    6-week window.
- Next step: Vincent to try on two screens.

### 12. Dashboard click-through (Vincent, 17/10)
- Status: built and checked in a browser.
  - Every dashboard tile opens the page holding its data (`jumpTo` in ui.js; hover shows an arrow): Budget/Allowance
    -> CBS, Cost to date -> Actuals, Accruals -> Accruals, Cost to complete -> Forecast lines (its "Open POs" figure ->
    Commitments), EAC and Contingency -> Cost control, revenue -> Contract value / Progress claims, margins -> PMR
    output, accrual effect -> Accruals. CBS scope carries over (cost control and forecast get `?node=`).
  - Charts (`chartJump` in ui.js: nearest point, hand cursor): revenue series -> claims; cost series -> Actuals for
    months up to the status month, Forecast lines after it; bills/payments -> Pronto data; net cash -> EOM report;
    monthly cost by category -> that category in cost control (past) or forecast (future); doughnut slices -> Actuals
    / Accruals / Forecast; profit chart -> PMR; line status chart -> Cost control. The "Revenue against cost" tiles
    link the same way. Allowance vs EAC bars still drill into the next CBS level.
  - Table filter boxes: typed text is black (it inherited the white heading font).
- Next step: Vincent to say if any tile should land somewhere else.

### 13. Help chat, tile links everywhere, your defaults, calendar NT/OT prefill (Vincent, 17/10)
- Status: built and checked in a browser. 137 tests.
  - Ask button (bottom right, `static/js/help.js`): panel with two tabs.
    - PMT guide: offline answers from `app/help.py` (hand-written FAQ + README "What it does" rows + README sections,
      keyword scoring with abbreviations such as CTC, EAC, NT, OT), "Open this page", related topics, page-aware
      greeting and suggestions. `/api/help/ask`, `/api/help/topic/{id}`, `/api/help/guide.md` (whole guide).
    - Microsoft Copilot: "Open Copilot Chat" copies the question plus page context to the clipboard and opens
      https://m365.cloud.microsoft/chat. If Settings > Your defaults has a Copilot Studio agent web chat address
      (https only), it is shown in an iframe in the panel. The guide .md is meant as that agent's knowledge.
    - No AI API is called from PMT; nothing leaves the PC unless the user pastes it into Copilot.
  - Tile links everywhere (`static/js/tilelinks.js`, MutationObserver like tabletools): one map per page keyed on the
    tile label (regex keys for the history pages), targets are a page hash or a scroll-to-card / table action
    (`toCard(...titles)` falls back through titles). Cost-control drawer and forecast line tiles use data-node /
    data-row. Dialog tiles (.ov) are left alone. `h()` now supports `dataset`.
  - Your defaults (Settings, first card): `PREFS` in api.js, stored per person in sync_state `prefs:<upn>` (this PC,
    not shared), GET in /api/me (`prefs`), PUT /api/me/prefs. Pages read `pref(key)` when the session has no view state;
    saving clears the session view keys (`VIEW_KEYS`). Covers start page, table filter row, cost control level /
    monthly grid / empty lines / filter, CBS and contract levels, calendar weeks / whole project / who / pools, month-end
    review filter, commitments open-only, dashboard flow tab, Copilot addresses.
  - Labour calendar: "11 / P 11" = Pronto has 11 h entered not posted; PMT auto-accrues them (lighter number) until
    the user accrues the day. Clicking now opens NT/OT prefilled (split at the project setting "Normal hours a day
    (staff)", default 8; forecast days use their typed OT). Leaving it unchanged saves nothing; Enter on OT accrues it
    as shown. An existing own accrual still opens with its own NT/OT.
- Next step: Vincent to decide whether IT sets up a Copilot Studio agent (then paste its web chat address).

### 14. Project library (archive) and Portfolio with analytics (Vincent, 17/10)
- Status: built and checked in a browser. 139 tests.
  - Archive (`app/library.py`): project.archived_at / archived_by / archive_summary (JSON figures saved on archiving:
    contract value, final cost (EAC), margin, CTD...; computed lazily for older archives). POST /api/projects/{pid}/archive.
    Archived projects leave the running list and the Portfolio; nothing is deleted; synced like any change.
  - OVERVIEW > Project library (`views/library.js`, GET /api/library): search text (name, code, client, location, PM,
    director, contract ref), client / location / PM / director filters, period it ran (overlap with start..end), contract
    value range, totals tiles, Open / Restore. Works with no project open. Project selector's last entry links to it;
    an open archived project shows an Archived badge + Restore. Settings > Archive card.
  - New project fields on Project setup: Location, EPEC project director (EPEC project manager already existed).
  - OVERVIEW > Portfolio (`app/portfolio.py`, GET /api/portfolio, `views/portfolio.js`): running projects (not archived,
    not templates). Chips: Projects managed / Program directed / All, "by" any person named as PM or director (defaults to
    you; directors (role) start on Program). Tiles; charts: margin at tender vs forecast, contract value vs EAC,
    cost/revenue by month (landed vs forecast, summed by calendar month), cumulative (separate chart, no dual axis), time
    elapsed vs cost spent (scatter with in-step diagonal), contingency per project; By project manager table (click drills
    to that PM); projects table. Clicking a project or its bar opens its dashboard. Names match case/space-insensitively.
- Next step: Vincent to fill EPEC project manager / director on each project's setup page.

### 15. Map, client CRM and PM workload (Vincent, 17/10; EPEC-PM-FW-0002 PM Technical Capability Framework)
- Status: built and checked in a browser. 142 tests.
  - Project setup > Asset and site: project_type (Solar farm, BESS, Hybrid (solar + BESS), Wind farm, Substation /
    transmission, Other), capacity_mw, storage_mwh (shown as GWh from 1,000), voltage (text, e.g. 33/330; max kV parsed),
    complexity 1..5 (blank = suggested: value bands <5m/15m/40m/100m, +1 at >=220 kV, +1 hybrid), lat/lon (click the map, or
    Find via OpenStreetMap Nominatim when online).
  - Map (`static/js/map.js`): Leaflet 1.9.4 + world-atlas countries-50m (Natural Earth) bundled in static/vendor, so it works
    offline; "Street map (online)" layer = OSM tiles. Dots coloured by type (fixed colours), sized by contract value.
  - Portfolio: tabs Overview (map, mix tiles MW / MWh / highest kV / clients / avg complexity, charts by type, client,
    voltage band), Clients (CRM, `views/_clients.js`), Team workload (`views/_team.js`).
  - Company-wide tables `client` and `person` (no project_id; sync carries them). Matched to projects by name, case and
    spaces ignored. /api/clients, /api/people (CRUD), /api/workload?director=.
  - Workload (`app/workload.py`, all weights there): demand per project = complexity load (1..5: .15/.25/.40/.60/.85 of a
    Level 2 PM) x client factor (difficulty .85..1.25, risk .97/1/1.08) x phase (mobilising .35, later start .15, delivery 1,
    last 10% .75, after end .4) x travel (1 + min(.25, km from base / 4000)); x spread (1 + min(.20, mean km from centroid /
    2500)). Capacity = level (1: .6, 2: 1, 3: 1.25, 4: 1.5) x FTE. % = demand / capacity; bands 70/90/105. Required level by
    complexity 1,2,2,3,3; below it = "stretch". Director's team = PMs on projects they direct or who report to them.
- Next step: Vincent to calibrate the weights with a director against how the team feels; fill types, sites, levels.

### 16. PMT.exe clicked in SharePoint (Vincent, 20/10)
- Status: built; tested under Wine (Windows emulator) with a fake synced library: found via the profile search (library
  4 levels down), via home.txt, via OneDrive's Tenants registry key, and the explanation window when nothing is found.
  Not yet tried on a real EPEC PC with SharePoint.
  - launcher.c: no run.bat next to the exe = a downloaded copy. find_synced(): %LOCALAPPDATA%\PMT\home.txt (written by
    every normal run), then HKCU\Software\Microsoft\OneDrive\Accounts\*\Tenants\* value names (sync roots) and each
    account's UserFolder, then %OneDriveCommercial%, %OneDrive%, %USERPROFILE%; depth 5; a PMT folder = PMT.exe + run.bat +
    app\launch.py; skips AppData, Downloads, dot folders, junctions/symlinks (cloud reparse points are searched).
    Found: ShellExecute that PMT.exe and exit. Not found: MessageBox with the three sync steps.
  - Build now needs -ladvapi32 (registry). Rebuilt PMT.exe with zig 0.x (pip ziglang).
- Next step: Vincent to click PMT.exe in SharePoint on his PC (after one normal run from File Explorer).

### 17. Actuals: invoices by supplier (Vincent, 20/10)
- Status: built and checked in a browser. 143 tests.
  - The Actuals page used to be only the close-by-close history (empty until a month is closed). Now two tabs:
    "Invoices by supplier" (default) and "By CBS line and month (at each close)" (the old page; ?node= opens it).
  - `app/invoices.py`, GET /api/p/{pid}/invoices and /invoices.xlsx: pronto_tx class actual/journal, doc_type PO (PO
    receipt), CV (direct invoice), GJ/GV (supplier journals) with a supplier code; GL lines grouped into one invoice by
    supplier + doc + suffix + reference + date. TS (timesheets) excluded. Per supplier: name, group (PS/PM/PE by
    category), invoices, total, status-month total, POs (suppliers.known: committed/received), linked subcontracts
    (supplier_code) with claims approved, "approved less invoiced". Invoices whose reference matches a sub_claim.inv_ref
    link to the claim.
  - Page: search, type chips, invoice date range, suppliers table (click one: monthly bar chart, its POs, subcontract,
    its invoices), all-invoices table otherwise, Excel export (Suppliers + Invoices sheets).
- Next step: Vincent to check it against a real Pronto GL export (document types PO/CV used by EPEC's Pronto).

### 18. Accruals reviewed against the workbook (Vincent, 20/10)
- Status: built and checked in a browser. 148 tests (tests/test_accrual_rules.py).
  - Source: workbook "Accruals" sheet (merged register: Pronto WIP harvest + PM accruals, balance per CBS x supplier =
    MAX(Pronto open, PM), automatic reversals in the landing month matched by INV Nr or PO, statuses "Pronto accrued -
    do not accrue" / "PM accrual open"), Backlog BL-163/164/165/166/170, and the real Pronto export: finance's accruals are
    JE (GJ) / RJ (GV) on account 3000B1125 "Work in Progress", "<Mon YY> Acc <supplier>", reference = PO; payroll ones
    "<MON YY> Timesheet Accrual" (reference TIMESHEET / PAYROLL ACCRUAL). Document types in the real export: PO, CV, TS,
    GJ, GV, JP (profit journals, category 999), SO (client invoices).
  - accrual.kind: work (estimate) | invoice (awaiting approval) | hours. New columns supplier_code/name, quote_ref,
    matched_via/month/refs, resolution. accruals.match(): invoice number (normalised, digits-tail), then quote number in
    the invoice text, then PO (invoice accruals only; first untaken invoice on the PO from the accrual month, same line
    first). Estimates never auto-match. Differs: status investigate, counted as trued-up until the PM accepts
    (matched) or keeps the rest open (partial).
  - Timing (accruals.counted, used by the engine's x series): matched invoice = +invoice in the work month, -invoice in
    the landing month (setting accrual_work_timing, default on). Same for subcontract claims whose invoice landed
    (claim_landings). ACC totals unchanged; months show when the work was done.
  - Finance's accruals: accruals.pronto_accruals() (per line x reference x named month: accrued, reversed, open);
    pronto_cover() reduces an open PM accrual on the same line + PO / invoice / supplier by finance's open amount (MAX rule);
    finance's timesheet accrual covers PMT's automatic unposted accrual for that category and month. Warnings on save
    (/accruals/check); saving an invoice accrual whose invoice already landed is refused; an invoice accrual needs a ref.
  - Unposted timesheets: accruals.unposted() per person-month; "Accrue" (hours accruals per day) or "Not ours: move..."
    (timesheet_request; excluded from auto-accrual via UNPOSTED_NOT_ACCRUED; closes by itself when Pronto no longer has
    the hours on the project; copyable email text).
  - Accruals page: tabs Register | Work, billing and cash (accruals.timelines: work = GL + counted accruals; billed =
    GL less finance accrual journals; paid = PO/CV invoice date + supplier terms, else GL month) | By month and history.
    ACC drill shows "counts" after finance's cover and the moved invoice amounts.
- Next step: Vincent to try it on the real project: check finance's open WIP accruals list against the workbook's
  "Accrual balance" block, and the PO matches.

### 19. Pronto raw rows and data checks; cost to date without forecast (Vincent, 20/10)
- Status: built and checked in a browser on Vincent's upload (data.zip, project 3 Wandoan South Stage II). 152 tests
  (tests/test_pronto_raw.py, tests/test_claims_flows.py).
  - app/pronto_raw.py: RAW (table, date, amount, columns per report), checks() (future | totals | reversed | duplicates
    with row ids), rows() (search all columns, check filter, sort, paging), xlsx(), as_of() (latest date not in the future
    + count later). Endpoints /pronto/checks, /pronto/raw/{kind}, /pronto/raw-xlsx/{kind}; /pronto/status adds last/future.
  - Totals check: blank category/date, a label field STARTING with TOTAL (notes skipped: timesheet notes like "LAFHA Qty 1
    Rate $24.50 Total $24.50" are real), or one row worth the sum of the others. Reversed: cost (class actual) entry
    >= 1,000,000 with an opposite cost or journal entry within 62 days; revenue accrual pairs are routine and not flagged.
  - Pronto data page: card "to" date ignores future rows (+ N in the future), Inspect rows button, Checks card;
    #/pronto?inspect=<kind>&check=<id> is the row viewer.
  - Finding on the real data: no totals row (9,314 GL rows, all with category, date, document; labour 5,968 likewise).
    The 01/12/2026 date is 8 real rows: Madeline Bristow expense claim corrections (CV 10909/10910, ref 357, -311.26,
    fin period 2026 P6) dated 1 Dec 2026 in Pronto. Keying errors: McClelland PO 2124 79,065,000 on 13/11/2025 reversed by
    GJ 4008 -79,059,729 next day (5,271 remains); Aliweld PO 2614 +/-15,734,436 on 5-6/05/2026.
  - Dashboard > Revenue against cost: "Cost incurred to date" summed every month up to the status month, so it counted
    the status month's forecast (status date 01/10 -> status month Oct, forecast already there). reports.flows() now
    returns cost_incurred / cost_forecast / revenue_actual / revenue_planned and *_to_date (incurred only); the chart
    stacks forecast as its own lighter bars ("Cost forecast", "Revenue forecast"); invoice tiles likewise.
    On the real project the remaining cost (ETC 20.26m) is spread flat over Oct-Dec 2026 (about 7m a month): that is
    the forecast lines' spread to the end date, not Pronto data.
- Next step: Vincent to ask finance whether the 1/12/2026 date is intended, and whether McClelland's residual 5,271 is
  the real PO receipt; phase the forecast lines (Forecast lines page) so the remaining cost is not lumped into 3 months.

### 20. Load from the PMT workbook (Vincent, 20/10; WDSF-PD-RP-0000_1_Project_Management_Tool_Live.xlsm)
- Status: built, tested on Vincent's workbook + data.zip copy, checked in a browser (CBS and allowances > Load PMT
  workbook...). 154 tests (tests/test_pmt_workbook.py).
  - Why: the app's EOM (EOM-report_0182_2026-10_rev01) showed EAC 44.8m against the workbook's 25.8m
    (WDSF-FI-RP-0001 rev 4): the app had the estimate on its items ("(Unallocated)") and the Pronto lines at no
    allowance, no PM accruals, and every item forecast AT-BUDGET.
  - app/pmt_workbook.py: read() Cost Control (lines by CC key cc.cat.1.nnn, Budget [src] / Risk [src], dates, month
    grid; .999 Bulk and .998 WIP rows = the category's own pot), Allowance (items cc.cat.0.nnn: curr budget, adj risk -
    risk allocated, approved variations), Ledger (383 movements), Accruals tbl_Accruals (A:N). plan() maps lines by
    category + resource code, items by name below the category (any depth), the rest to the category node.
    apply(): creates missing lines that carry allowance or forecast; replays the Ledger as transfers; posts approved
    variations on the category; trues every node up to the workbook (kind adjustment, ref "PMT workbook"); nodes the
    workbook does not have end at zero; every line MANUAL with the grid from the status month (CURRENT (F) + FUTURE);
    accruals (invoice kind when INV / PO / quote, Source "Pronto" -> source Timesheet); accruals.match(). Re-apply
    replaces an earlier import. tieout() per category. Endpoints /pmt-workbook/preview (upload) and /apply.
  - accruals.UNPOSTED_NOT_ACCRUED: a Timesheet-source accrual on the line and month stands the automatic one down.
  - accruals.pronto_accruals(): a reversal journal naming another month ("April 26 Acc LAZZARONI - Reversal" against
    "May 26 Acc Lazzaroni", PO 2765, 491,261) now offsets on the same line and reference; it had "covered" 363k of
    Vincent's Lazzaroni accruals.
  - Tie-out on the real project: budget 21,834,038 and risk 1,789,705 exact in every category; ACC 791,883 vs
    792,090; CTD +21,435 (Pronto rows after the workbook's extract, PM03/PM05 journals, future-dated rows); CTC
    1,017,223 vs CTC [src] 511,231: the workbook's CTC [src] leaves out the current month's forecast (CURRENT (F),
    505,992 on 27 lines, flagged in its own EAC delta); app EAC 26,347,689 vs workbook EAC [clc] 26,326,462.
  - CTD tie-out to 30/09 (Vincent 20/10, "ignore the Oct data"): the workbook's "Transactions - Pronto" and the app's GL
    are the same 9,314 rows (sum -490,051.69). Workbook CTD 24,517,148.48, app 24,538,582.67; the difference is
    treatment only: +10,649.00 MV Technology Aug-26 finance accrual GJ 5800 (workbook moves open Pronto accruals to ACC,
    app keeps them in CTD; EAC equal), +7,016.40 Yurika Aug-26 accrual posted twice (GJ 5800 + GJ 5890) and reversed
    once (GJ 6004) - the workbook ignores it, Pronto still carries it, +4,080.00 LMATS Aug-26 accrual GJ 5800 not
    reversed after invoice PO 3174 (workbook: ACC with the PM's -4,080), -311.26 the 8 rows dated 01/12/2026. Every
    other line difference is the same cost on another line in the same category (McClelland reversal journal, INTRO x2,
    PPI, Bushlander, Big River, Brandis...).
  - accruals.match(): a negative row (the PM reversing an accrual) is never PO-matched to an invoice; it had cancelled
    the PM's -4,080 LMATS reversal.
  - Future-dated actuals (Vincent 20/10: "anything that is an actual in Pronto should be part of CTD but it should be
    flagged if these costs are sitting in the future"): they stay in CTD; reports.health "pronto_future" (error) on the
    dashboard's Data health and in Diagnostics (rows listed, link to Pronto data > Inspect filtered to them). Future =
    after the end of the status month and after today (pronto_raw._cutoff / future_rows). "Pronto is current/older"
    now uses the latest real date, so the 01/12/2026 rows no longer hide that Pronto stops at 30/09.
  - accruals.claim_landings tolerates a GL row with no date (it crashed the engine).
  - Known flaky: tests/test_workload_crm.py::test_clients_people_and_team_endpoints (order of row["running"]), passes on rerun.
- Next step: revenue side (Contract Value sheet 28,689,411 vs app 30,503,740; Claim sheet; Variation Register) from
  the same workbook; Vincent to confirm whether October forecast belongs in CTC (Lazzaroni has both 192,763 accrued
  and 134,315 forecast for October).

### 21. Delete from a list, Payment Milestones, Excel load preview and undo (Vincent, 21/10)
- Status: built, 159 tests (tests/test_template_undo.py, test_core delete), checked in a browser.
  - Settings > Delete a project: dropdown of every project (archived / template / open now marked), Delete..., then
    "OK, delete permanently" on the confirmation. API unchanged (DELETE /api/projects/{id}?confirm=<name>); the typed
    name box in Clear project data no longer deletes.
  - Wording: "Schedule of values" is "Payment Milestones" everywhere visible (contract value card, setup step, tiles,
    clone list, Excel template sheet; the import still reads an old "Schedule of values" sheet). Vincent: Payment
    Milestones are the initial list; the Claim schedule is the same milestones phased over the month grid.
  - Project setup > Load from Excel: /load-template/preview runs the import in a SAVEPOINT and rolls it back (counts,
    project fields that change, warning when the file's name/number/code is another project's); Save =
    /load-template/apply, which first stores a restore_point (project fields + resources, rate card, cbs_node,
    estimate allowance entries, contract items, milestones). "Undo last Excel load" = /restore-points/{id}/undo:
    fields back, rows created by the load removed, changed rows put back, deleted rate card/milestones re-inserted
    with their ids; once only. The old /load-template (direct) also stores a restore point.
  - Loading mode, as for Pronto (Vincent 21/10): "Update and add" (merge, the old behaviour) or "Replace" (the file
    becomes the setup): templates_io._remove_unlisted removes CBS items (origin template/manual/custom; never standard,
    pronto, workbook or a category) the file does not list, with their subtree, unless something in it carries
    Pronto cost, timesheets, POs, accruals, forecast, subcontracts, variation lines, risk allocations/releases or
    allowance transfers (then kept and listed); estimate allowances on unlisted items (not once initialised); payment
    milestones not listed unless they or their children have claims. Restore points also keep revenue_plan (the claim
    schedule months) so Undo brings removed milestones back with their months. The dialog's mode dropdown re-runs the
    preview on the same upload (/load-template/preview/{token}?mode=).
  - The project selector now reloads after Save project and after a load / undo (it kept the old name: Vincent's
    Wandoan project showed "Fraser Coast" after a Fraser file was loaded into it and Wandoan's reloaded).
- Next step: Vincent's Wandoan project took a Fraser Coast load before restore points existed: Fraser's CBS lines and
  estimate stay in it where Wandoan's file has no matching row; check CBS and allowances (origin template) or reload
  from a backup.

### 22. Pronto exports as .ods (Vincent, 21/10)
- Status: built, 161 tests (tests/test_ods.py: the demo export written as LibreOffice would, read cell for cell like
  the .xlsx, and loaded through the API to the same rows). app/ods.py reads content.xml with the standard library
  (no new package): typed values like openpyxl (int/float, datetime, bool, str), repeated cells and rows expanded only
  up to the last value (LibreOffice pads to 1,048,576 rows), text:s / tab / line-break. pronto.sheet_iter and analyse
  use it for .ods; the upload accepts .ods. 10,000 GL rows (21 MB .ods) read in about a second.

### 23. Original vs revised contract value: variations and optional prices (Vincent, 21/10)
- Status: built, 165 tests (tests/test_schedule_import.py, 4 cases), checked in a browser.
  - contract_item.in_original (NULL = by kind: base and optional yes, variation no). The claim schedule import asks
    two questions when the schedule has those sections: variations "not in the original (added on top)" or "already in
    the original"; optional prices "in the original (one not taken is deducted from the revised value)" or "not in the
    original (added on top once taken)". Each item's edit form has "Original contract value" (as its kind / included /
    not included).
  - revenue.summary: original = sum of leaves in the original at full value (an optional price at its tender value
    whatever its status); recognised (revised) unchanged = base + options taken + variations. bridge: original - options
    in the original not taken + options taken on top + variations on top (+ other) = recognised; shown under the KPIs on
    Contract value. EOM report, margins and dashboard read summary.original, so they follow.
- Next step: set the two answers on Wandoan to match the workbook's Contract Value sheet (original 26,522,996 +
  approved variations 2,166,415 = revised 28,689,411) once its schedule is reloaded.

### 24. Contract tiles open their part in a window; erase a setup section; folding menu (Vincent, 21/10)
- Status: built, 166 tests (tests/test_template_undo.py erase + undo per section), checked in a browser.
  - Tiles renamed: "Optional prices" (was "Optional prices taken"), "Variations" (was "Approved variations").
  - Contract value tiles (on Contract and claims and on Project setup > Contract value) open a pop-out window
    (tilelinks.openContract) at #/revenue?tab=contract&only=original|optional|variation (Recognised / Official / Stages
    show all): only those payment milestones and their parents, their own total, + Add item preset to that kind (and
    "included in the original" for Original); Edit / delete as usual. The opener re-renders when the window closes.
    revenue.items_tree gives each item in_orig. The milestone form's Kind now also offers "variation".
  - Project setup: "Erase this section" on Project (all fields but name and status date), Contract value (milestones
    not linked to the register, kept when they have claims), CBS and allowances (as a Replace load with an empty
    file), Programme (milestones). templates_io.erase_section stores a restore point first; the Undo button at the top
    now reads "Undo: last Excel load" or "Undo: erase <section>". POST /api/p/{pid}/setup/erase {section}.
  - Restore points and Replace now cover every milestone not linked to the variation register (variation_id IS NULL),
    including variations listed in a claim schedule (they were left out before).
  - Left menu: each group (OVERVIEW, SETUP, COST, FORECAST, REVENUE, CONTROL) folds; closed by default except the one
    holding the open page; opened groups are remembered (localStorage navOpen). The dashboard's health badge shows on
    OVERVIEW while it is folded.

### 25. Optional prices: Offered / Confirmed / Cancelled (Vincent, 21/10)
- Status: built, 171 tests (tests/test_schedule_import.py status cases), checked in a browser.
  - Vincent's Optional prices tile showed $0: the template's "Confirmed" / "Cancelled" were not "taken". revenue.opt_status
    reads any wording as offered / confirmed / cancelled (taken, accepted, yes -> confirmed; declined, rejected, no ->
    cancelled; anything else -> offered). db.init_db rewrites stored values to the three words once; the template and
    claim schedule imports and the item save store them.
  - What counts: confirmed always; offered only when the option is in the original contract value (until cancelled);
    cancelled never. Tile = what counts now, captioned confirmed / offered / cancelled amounts. Bridge: "optional prices
    cancelled" (in the original) and "optional prices confirmed" (on top).
  - Payment Milestones table: Kind (base / optional / variation) and a new Status column are dropdowns in the row, saved
    at once; a click elsewhere on the row opens the item (as Edit does).

### 26. Grid tables: status columns, nesting colours, drag rows, column widths, fill handle, templates (Vincent, 21/10)
- Status: built, 178 tests (tests/test_schedule_import.py: variation status, template and claim-grid round trips),
  checked in a browser at 1440 and 2000 px wide.
  - Variations carry a status too: approved / pending / declined (revenue.var_status; blank = approved). A schedule
    variation counts when approved, or pending and in the original contract value; register variations use the
    register's client status. Variations tile captions approved / pending / declined; bridge adds "variations declined".
  - Stages tile lists one stage per line (no more clipping).
  - Nesting colours on every grouped table (Payment Milestones, CBS, cost control, EOM report): grandparent `gp`
    (navy tint, orange marker), parent `par` (slate tint, navy marker), deeper `par2` (light-blue marker), EPEC palette.
  - Drag rows to reorder (ui.sortableRows, `table(..., {reorder})`): Payment Milestones within the same parent, CBS
    within the same parent (not pots or level 1), programme milestones. POST /api/p/{pid}/reorder/{contract|cbs|milestones}
    reuses the group's sort_order slots.
  - Column widths on every `table.t` (tabletools.resizable): drag the header border; double-click it to autofit.
    Widths are remembered per page and header set in localStorage `pmt.colw`.
  - Payment Milestones is an editable grid: every Edit field is a cell, saved on change. Fill handle (ui.fillHandle):
    the orange knob on the focused cell drags the value over other rows, POST /contract/items/bulk (not Ref; register
    variations skipped). The Edit button stays; clicking a row no longer opens the form.
  - Templates (app/claim_template.py): Contract value tab downloads / imports the Payment Milestones template (no
    months; Shift-click = blank). Claim schedule tab downloads the claim schedule template, the same sheet plus a month
    grid of Claimed | Approved columns, coloured past / current / future like the subcontract template. Importing it
    sets the revenue plan from Claimed and creates or updates a progress claim per past month (Approved = certified).
  - Views use the full window width (removed the 1720 px cap).
  - Esc (app.js): closes the top dialog, drawer or help panel; else leaves the field being edited; else goes back one
    page. history.state.pmt counts PMT pages in the tab so Esc never steps out of PMT. Tabs inside a page are not pages.
  - Templates (21/10 later): every exported template opens on its deliverable sheet; Lists / Instructions / Read me come
    after it (app/xlsx_order.deliverable_first, called before wb.close() in claim_template, templates_io, subcontract_io,
    variation_io, site_files). The Payment Milestones template has no status month or colour legend (claim schedule
    only). Both templates nest grandparent 1 > parent 1.01 > child 1.01.02 in number order with SUBTOTAL rows (value,
    invoiced, every month column) in three EPEC tints; a level missing above a row is added (claim_template._nest).
  - Release .35: claim schedule Status month (C4) is a dropdown of the grid's months (Lists!D); past / status month /
    later colours are conditional formats against C4 (hidden helper row 5 holds each column's month; group rows,
    recognised from the numbering, keep their tint); the import uses the month picked (read_status_month). Resized
    table columns carry their content (inputs, dropdowns, grid cells fill the column; text shows what fits). Side menu:
    headings 13px bold caps, pages indented under them, 13px, on a guide line.
- Next step: Vincent to try the fill handle and widths on his data. Possible follow-up: tables stretching to the
  window height.

### 27. Linked projects: child -> parent project -> portfolio -> program (Vincent, 21/10)
- Status: built, 184 tests (tests/test_linking.py), checked in a browser (link, parent dashboard / cost control /
  linked page, drill from parent and from a program down to a child's line drawer, program nesting and combined CBS).
  - Levels (Vincent): child project (a PM runs it) -> parent project (two or more children together) -> portfolio (a
    PM's or senior PM's projects) -> program (a project director's projects for their clients, overseeing a team of PMs).
    A junior PM (Level 1) runs one project: Team workload flags more ("⚠ one project"); workload.SPAN gives each level's span.
  - Data: project.is_parent, project.parent_project_id (one level; a child has one parent; a parent is never a child).
    SETUP > Linked projects links projects (POST /api/links, new parent or {parent_id} to add), unlinks
    (POST /api/projects/{id}/unlink). Deleting a parent frees its children (their data is untouched).
  - app/linking.py: engine.compute on a parent = linking.merged: each child's own engine result (own status month),
    merged by CBS code (pots by code too), groups re-summed from the merged leaves, so the parent ties exactly to its
    children; every row has by_project (each child's share and its own row id). Cached on the children's versions.
    revenue.summary / revenue_curve and reports.health / dashboard (claims, variations, milestones) add the children.
  - A parent is read-only: the middleware refuses any non-GET under /api/p/{parent}. Its menu shows Dashboard, Portfolio,
    Library, Linked projects and Cost control; the top bar shows "Parent project · n linked", a child shows ↑ its parent.
  - Drill down from anywhere (static/js/rollup.js): any line or amount in a parent's cost control, the parent's combined
    CBS, or a portfolio / program "Combined CBS" tab (GET /api/rollup?ids=, a parent in the list stands for its
    children) opens the split by project; "Open in project" opens the child's own line drawer (app.openIn).
  - Portfolio: projects = child and stand-alone projects only (no double count), parents listed apart; a child without a
    director takes its parent's. Program view nests client > parent > child with subtotals; "The team: project managers
    in this program".
- Next step: Vincent to link real projects. Open: should the CBS merge by code also map differently coded CBS between
  projects (a mapping table)? Should a parent carry its own EOM report (today: open each child's)?

### 28. Project chart, clients and resources database, reporting, demo team, risk ledger, close-out (Vincent, 21/10)
- Status: built, 189 tests (tests/test_directory.py, test_linking.test_demo_team), checked in a browser.
  - Project chart (rollup.projectChart): Portfolio > Project chart (portfolio: PM > parent > child; program: director >
    PMs, each PM's projects in a column, child projects marked with their parent, each parent once listing its
    children; all: per director), parent and child dashboards, Linked projects. Click a box: that project's cost control.
  - Company database (app/directory.py, OVERVIEW > Stakeholders): clients (client table), resources kept
    apart: employees (person: PMs, directors and staff; employee code, function, phone) and companies (new company
    table: supplier / subcontractor / consultant, Pronto code, trade, contacts). backfill() at start-up adds the names
    projects already use (once; never overwrites). ui.lookup(kind): type to filter, pick, or "+ Add" what was typed;
    used for client, EPEC PM and director (Project setup, New project, linking), resource names; the subcontract supplier
    list also offers database companies. Saving a project adds a typed client / PM / director to the database.
  - REPORTING section: EOM report (finance, moved from Reports), PMR (internal board, placeholder with proposed sections
    plus the live commercial block), PSR (client, placeholder: never internal cost or margin). CONTROL keeps Month-end
    history (snapshots, change log); old reports?tab=eom|pmr links forward.
  - Risk and contingency: Contingency tab (over and underruns per CBS, groups with subtotals of the lines shown) and
    Ledger tab (every allowance movement incl. the original estimate, per CBS line with budget after each movement, or
    by date; who made it from the change log). Close-out for the estimator moved to its own CLOSE-OUT section.
  - Demo team (Settings > Demonstration data, or the welcome screen; demo/build_demo.seed_team): director Taylor Brooks
    over Riley Chen (junior PM, 1), Jordan Reyes and Priya Nair (PMs, 2 each), Sam Whitlock (senior PM, 3); Priya's
    Bellbird Wind Connection and Sam's Bellbird BESS are children of Bellbird Hybrid Program. Each project is the full
    demo scaled by size / allowance / revenue / cost factors so over- and underruns differ.
- Next step: Vincent to share a PMR and a PSR he uses so the placeholders become the reports.

### 29. Claim schedule grid: type a $ or %, status month = the claim, future = forecast, drag to a later month (Vincent, 21/10)
- Status: built, tested (174 tests incl. tests/test_claim_grid.py) and checked in a browser (typing, cap message, %, "rest", drag,
  refused backwards drag, trim, create / open the claim, PDF, mark as submitted, month lock).
  - Contract and claims > Claim schedule (`scheduleTab` in `static/js/views/revenue.js`, rules in `app/revenue.py`):
    - Click a month on a claim line and type a dollar amount or a percentage of the line's price (`25%`, `12000`, `rest`, sums
      work); Enter / arrows / Tab move on. "$ amounts | % of the price" switches the view. Group rows add up and are read-only.
    - Cap (D26): a line's months can never add up to more than its price, claims already issued included
      (`revenue.set_cell`; refusal says the most you can enter in that month). A month cannot be negative (credit lines: the
      reverse). A rounded % that lands within a cent of the price takes the last cent. Editing an already over-scheduled line is
      allowed only if it does not increase the total.
    - Status month = this month's claim: its column pre-fills the claim (`claim_create` now pre-fills `planned_this`, the grid
      column; `suggested`, the catch-up to date, still shows in the claim dialog). A draft claim for a month follows grid edits
      (`_sync_draft`). Months after the status month are the forecast revenue (they were already, via `revenue_curve`).
    - A month with an issued claim (submitted / certified / paid) is locked and shows the claimed (certified) amount.
    - Drag: grab the grip of a value, drop on a LATER month of the same line (`revenue.move_cell`; adds to what is there).
    - First edit on an even / lump item turns its spread into manual months (`_write_plan`), dates kept.
    - Bar above the grid: Create the claim from this column / Open the claim, PDF, Excel. Claim dialog gained PDF and
      "Mark as submitted" (status submitted, locks the month).
    - Trim (`revenue.trim_excess`, POST /contract/trim-excess): lines scheduled beyond their price once claims are counted (the
      demo's fully claimed lines still carried an even spread of future months) lose the excess from their latest months;
      claimed months are never touched. Shown as a notice with a button; the KPI reads "Scheduled beyond the price".
  - Exports: `exporters.claim_pdf` (reportlab, A4 landscape, navy header, orange title, group rows, totals) and
    `claim_xlsx` now list groups with subtotals (`revenue.claim_sheet`); GET /claims/{id}.pdf.
  - Bug fixed on the way: GET /claims/{id}.xlsx never worked over HTTP (the generic /claims/{cid} route caught "19.xlsx" and
    failed to read it as a number). The id routes are now `{cid:int}`.
- Next step: Vincent to try it on Wandoan: type the September column, create the claim, export the PDF, mark it submitted.
  Backlog: fill-right / copy a value to several months (only move is built); an undo for the last grid edit; historical issued
  claims are still not imported with the claim schedule (past months are plain scheduled amounts until claims exist).

### 30. Claim schedule upload with past months, this month's claim and the forecast; overwrite (Vincent, 21/10)
- Status: built, tested (179 tests; tests/test_schedule_overwrite.py) and checked in a browser on Vincent's real claim schedule (scratch database).
  - Import claim schedule (Contract and claims > Contract value) has a third way to load when the file has month columns:
    "Overwrite the claim schedule and claims with this file" (default for an empty project). `schedule_import.apply(mode="overwrite")`:
    - clears the schedule (items not linked to the variation register) AND every claim of the project, then loads the file;
    - months BEFORE the project's status month become claims already made (`link_claims`, `_load_claims`): with a claims register to
      the right of the months (headers Claim #, Date Submitted, Date Approved, Invoice Ref, Approved This Claim) each register claim
      is matched to the month whose total it equals (within $2) and takes its number (CLAIM002), submitted / certified dates,
      invoice (in the note) and status certified; an "opening balance" claim equal to several earlier months together becomes one
      claim per month (CLAIM001-2025-01 ...); months with no register claim become submitted claims numbered after the register's;
    - the status month becomes the DRAFT claim (and its plan rows, as the grid keeps them); later months are the forecast plan;
      no plan rows are kept for claimed months; lines with no months in a file that has month columns are left unscheduled;
    - the sheet's Period / Status date cell is read (`period`) and the dialog warns when it differs from the project's status date;
      the claimed-to-date column is cross-checked against the past months; unmatched register claims are listed.
  - Safety: a restore point is taken first, now including claims (`templates_io.make_restore_point(..., with_claims=True)`, undo puts
    the old claims and lines back), so Project setup > Undo works. Replace still refuses while claims exist; the dialog asks to confirm
    an overwrite that deletes claims. Needs the project's status date.
  - On Vincent's Wandoan file: 15 register claims matched (claim 1 = Jan, Feb, Apr 2025 opening balance), past $27,744,906, Sep-26
    claim $410,116, forecast $534,388; recognised revenue 28,689,411.
  - Grid fix: credit lines (negative prices, e.g. variation / cancellation pairs) are no longer flagged as "scheduled beyond the price".
- Next step: Vincent to overwrite Wandoan's claim schedule from his claim schedule and check the claims against Pronto (CLAIM
  numbers may need matching to Pronto's claim numbers on the Progress claims / Pronto reconciliation tabs).
- Parent / child projects: NOT in this version (project table is flat: no parent link; Portfolio groups only by PM, director and
  client). Another agent is building it; Vincent will ask for a merge of both versions. To make that merge easy, the files touched in
  threads 29 and 30 are: app/revenue.py, app/exporters.py, app/schedule_import.py, app/templates_io.py, app/help.py, app/build.py,
  app/main.py (routes: contract cell / move / trim-excess, claims {cid:int} + .pdf, schedule analyse / commit), static/js/views/revenue.js,
  static/css/app.css, README.md, HANDOFF.md, tests/test_claim_grid.py, tests/test_schedule_overwrite.py. No schema change.

### 31. Merge of the business account's .36 and the personal account's claim schedule work (Vincent, 21/10)
- Status: merged with git, 203 tests pass (base = business_8's last commit fb8bfbf; branch `personal-claim-grid` = threads 29 and 30, merged with the
  business account's threads 25 to 28). Conflicts were in HANDOFF, README, build.py (release), app.css, main.py, schedule_import.py and
  revenue.js; every other file merged on its own. Decisions made while merging (change them if Vincent wants otherwise):
  - Optional / variation statuses (thread 25 and 26 words offered / confirmed / cancelled, approved / pending / declined) replace the
    "taken / declined" words my grid code used: `revenue.item_counts(item)` is the one rule for "does this milestone count now", used by
    the grid (set_cell, trim_excess). `items_tree.counted` keeps its own copy of the same rule; keep them in step.
  - Two ways to load a claim schedule with month columns: a PMT claim schedule TEMPLATE (Claimed | Approved grid, `claim_template`) loads
    its own claims (`apply_grid`); a plain client claim schedule file (one column per month, optional claims register) uses Overwrite
    (`schedule_import.apply(mode="overwrite")`, thread 30). A template file never also gets the month-column claims
    (`claims_from_months=False`). Overwrite also works with a template file (it then clears the schedule and claims first).
  - `claim_template.apply_grid`: the claim for the STATUS month is now a draft (months before it stay "submitted"), so the claim still to
    submit stays editable in the grid and is not locked.
  - The claim schedule tab keeps my editable grid; the business account's template buttons (Claim schedule template, Blank template,
    Import) and nesting colours (`nestClass`) were added to it. The old per-cell number inputs it had are gone.
  - Release number is 2026-10-21.37.
- Next step: Vincent to try the merged build: link a child to a parent, then open a child's Claim schedule (type a month, create and
  export the claim, overwrite from a client file) and the parent's views.

### 32. Forecast lines grid (Vincent, 21/10)
- Forecast > Forecast lines is now a CBS tree (grandparent > parent > child) with subtotals per heading, collapse/expand, a totals row at the top (sticky) and bottom, and month columns (status month on, "Show past months" for actuals). A cell is actual + accrual + forecast for that line and month; one row per line, resource shown beside it. Click a row for the line editor (a group id in `?node=` or `?scope=` shows that group only).
- Method badge opens a picker with all methods; CLAIM is disabled unless `subcontracts.claim_nodes` lists the line (live subcontract linked to the node with at least one schedule line). Enforced in `services.update_node` and bulk `/methods`. `/cost-control` returns `claim_nodes`.
- Dashboard: future bars of Monthly cost by category (and future points of the cumulative cost line) go to `#/forecast?month=YYYY-MM&scope=<node>`; that column is highlighted with an actual/accrual/forecast summary. Past bars still go to cost control.
- Header user chip: role on a second line under the name.
- Not built: typing forecast values into the month cells (edit on the line page); per-resource sub-rows inside a line with several forecast items.
- Tests: tests/test_forecast_grid.py.
- Drag in the grids (21/10): the claim schedule grid now moves a value earlier or later, never before the status month (`revenue.move_cell`). The Forecast lines grid drags a forecast amount between months from the status month on, both ways (`POST /nodes/{nid}/forecast-move`): MANUAL lines move typed months; BURN-RATE, AT-BUDGET, AT-COMMIT and TOP-DOWN lines ask first and become MANUAL at their current forecast; GROUND-UP and CLAIM lines are changed on their items or claim schedule.
- Client challenge (21/10, `app/challenge.py`, `app/views/_assess.js`): `client.knowledge` (1 clueless to 5 expert, X axis) and `client.complexity` (difficulty, Y axis) from a clickable 5 x 5 grid on the client card; `assessment` table (project, month, client PM, PM difficulty, project complexity, note) entered on Project setup or the client card's Assess dialog, one per project and month; the project's complexity follows the latest. Score = half position (60% difficulty, 40% lack of knowledge), half the mean of assessments (each month half PM difficulty, half complexity); bands under 25, 45, 65. Clients tab chart is now knowledge against difficulty coloured by band. Portfolio gains Gate, client band and client PM / complexity columns and a Client challenge table (directors' program view). Weights are my choice, not EPEC's: change them in challenge.py if EPEC has a rule.
- Gates (21/10, `app/gates.py`): gates 1 to 7 from EPEC's gate forms and lifecycle overview (Gate 5 Handover to Delivery, Gate 6 Approval to Deliver Project, Gate 7 Approval of Project Completion; Delivery ends with the Ready to Close Out review). Gates 3 and 4 forms were not supplied, so they have no name or paper: add them to `GATES` and `app/gate_forms/`. `gate_log` keeps every change, latest is current, a gate can move back (Early Works then EPC). The five Word papers are in `app/gate_forms/` and download from `/api/gates/{n}/form` when a gate is chosen. The same knowledge went into the EPEC knowledge base skill (section 5, references/project_gates.md, assets/gate_forms), delivered as a .skill file the user must install.
- Delivery phases (21/10, `app/gates.py` PHASES, `phase_log`, `app/lifecycle_forms/`, `app/lifecycle_checklists.json`): the PM records Design, Procure, Construct, Commission or Close Out on Project setup; a dialog shows the phase reminder and each review's checklist items (parsed from the Word forms; regenerate the JSON if a form changes) with a download of the paper. Papers not supplied: Phase 1 design review (EPEC-PD-FR-0011), Ready to Close Out review (EPEC-PD-FR-0014), Gate 3/4/8. Open questions for Vincent: the Set Up Procedure also lists Gate 8, Approval of Financial Close (EPEC-PD-FR-0015) after the Warranty period, so the gates may be 1 to 8 (PMT has 1 to 7 until confirmed); Gate 5 approver (Handover Procedure says the PM, the form has a General Manager block); Gate 6 to 8 approvers depend on project value (over $25M MD, $10M to $25M GM Projects, under $10M Project Director). The knowledge skill carries all of this in references/project_lifecycle_procedures.md.
- Project types (21/10): Substation and Transmission are separate types (before: "Substation / transmission", which still reads as Substation via `canonType` in map.js). Symbols approved by Vincent: solar farm = PV panel with a sun raised above it, substation = transformer (tank, bushings, windings), transmission = tower on slate #335062, BESS battery, hybrid sun plus battery, wind turbine, other dot. Public holidays (Settings): year range and a button that pulls Queensland holidays from the Nager.Date API (`holidays.fetch_year`; could not be tested live from the build sandbox, the error path and year logic are tested), plus the built-in 2024 to 2035 list for offline use. Clear project data now picks the project from a dropdown instead of typing its name.
- Mining type (21/10): a project type of its own (not a market segment, Vincent's decision): the ultra-class haul truck symbol (from a Liebherr T 274 photo), colour #8c6a3f (an earth brown outside the brand palette: change TYPE_COLOUR.Mining if EPEC wants a brand colour). Types are now solar farm, wind farm, BESS, hybrid, mining, transmission, substation, other. Substation means a standalone network or load-side substation; the generator types include their own substation.
- Project org chart (21/10, `app/orgchart.py`, `static/js/views/orgchart.js`, table `project_org`, one JSON document per project): parties (Owner, Developer, Builder, Principal Contractor, Contractor, NSP, Subcontractor, Consultant, Other) with canvas positions and links (contract, reporting, communication) with labels. EPEC is always present, as Contractor or Principal Contractor (selector at the top). Templates for EPEC as Principal Contractor and as Contractor; Tidy layout; Download image (SVG). Names look up the client or company directory (NSP uses a suggestion list in `orgchart.NSPS`). Open: whether "Builder" and "Principal Contractor" should stay separate roles, and whether the chart should appear in the PSR or on the dashboard.
- Program and Team pages (21/10, `views/program.js`, `views/team.js`, both `portfolioPage` with the director's program fixed): OVERVIEW entries shown only while the profile role matches /director/i (`isDirector` in app.js; the pages also explain themselves if reached by URL as a non-director). Team gains a table of PMs with level, time, workload and the projects each manages. Not built yet (agreed order): per-assessor assessments with the director's own assessment and the PM calibration gap, then the assign-a-new-project ranking. Vincent accepts role-based hiding for now; real access control needs Entra sign-in via IT.
- Wording decision (Vincent, 21/10, agreed after a second look): **Program** = a collection of projects and portfolios under a director; **Project schedule** = the timeline of tasks (never a bare Schedule, and not Schedule and dates); **Claim schedule** / **Payment milestones** = the contract's money side. The word programme is no longer shown anywhere: menu "Schedule and dates", upload text, help, README, activity labels, messages. Internal names stay (route `#/programme`, API `/programme/`, table `programme_task`, module `programme.py`). The Excel template's sheet is now called Project schedule; the loader still accepts Schedule and Programme.
- Parent projects (21/10): menu now also shows Forecast lines, Contract and claims (totals only: no milestones, claim schedule or claims tabs), EOM, PMR, PSR and Settings. These pages show a banner linking to the child projects; the forecast table is read-only for a parent (no method picker, no drag, rows do not open). The server already refused every write under /api/p/{parent}/ (middleware `_one_action`).
- Map symbols (21/10): project dots on every map carry a white symbol per type (sun, battery, sun plus battery, turbine, pylon, dot) on the type colour; the legend shows the same symbols (`map.js` typeIcon).
- Stakeholders (21/10): the page formerly Clients and resources is now Stakeholders. Resources and rates left the CONTROL menu: Employees and Companies tabs show the project's own list (Pronto codes, work rates, CBS lines) under the company list, and Rate card and Supplier rates are tabs under RATES. The old `#/resources` address redirects. A client card opens with Current, Past and All projects and a map of their sites (sites come from Project setup; projects without one are counted in the map legend).
- Margin fix (`reports.project_margin`): forecast gross profit now subtracts EAC plus the unspent risk bucket (`cost_forecast`), the same provision the original and revised-plan margins carry. Before, a project forecast at budget with no costs showed erosion of +$3.35m because the original profit carried $1.79m of risk and the forecast did not. The tile now says when the forecast profit is above the original (positive = no erosion). Remaining difference on that project is revenue above original ($28.10m vs $26.54m).
- Programme upload accepts .mpp: `programme.read_mpp` reads it with MPXJ (Java + `mpxj` + `JPype1`, added to requirements.txt), writes MSPDI XML to a temp file and reuses `read_xml`. Tested here only with MSPDI content named .mpp (no real .mpp file was available); Windows setup must install Java for it to work, otherwise the upload gives a clear message.

## Decisions (do not re-open without Vincent)

**Multi-user (thread 1)**
- D1. No server. The program folder lives in a SharePoint library that each user syncs with OneDrive. Each user
  runs PMT.exe from their synced copy. Hosting one shared server (for example Azure App Service with Entra sign-in)
  remains the better long-term option but needs IT; it is not being built now.
- D2. The SQLite file is never shared. SQLite over OneDrive sync corrupts or forks. Each user keeps a local replica
  in `%LOCALAPPDATA%\PMT\replicas\<id>\pmt.db`; the venv and `__pycache__` also stay local so nothing churns in SharePoint.
- D3. Sharing is an append-only change journal: `shared/journal/<user>@<device>/<YYYY-MM>.jsonl`. Each writer only
  writes its own folder, so OneDrive never has two writers on one file. Every replica reads the others and merges.
- D4. Every write is captured by SQLite triggers into `change_log` (who, when, table, row, old and new values). The
  change log is both the audit trail and the sync payload. Merge is last-writer-wins per column, ordered by a
  hybrid clock; deletes are final (ids are never reused).
- D5. Row ids: each writer gets a slot (1..4095); new ids are `slot * 2^40 + n`, so writers never collide. Legacy ids
  (< 2^40) are the data published at first share. Ids stay below 2^53, safe in JavaScript.
- D6. Identity comes from Windows without IT: the OneDrive for Business account (UPN and display name) in the
  registry, then `GetUserNameExW`, then `whoami /upn`, then the Windows user name. Each user sets their role
  (PM, PC, ...) once. Verified Microsoft sign-in (MSAL + an Entra app registration) is phase 2 and needs IT.

**Forecast (thread 2)**
- D7. New left-panel group FORECAST: "Forecast lines" (full-page line editor) and "Labour calendar".
- D8. Ground-up gains three sub-methods on forecast items: Calendar (day grid of hours or $ for one resource on one
  CBS line), Milestones (vertical list: name, %, scheduled month, status) and Roster (start date, pattern such as
  10:4, swings, headcount, hours per shift, supplier and role priced from the supplier schedule of rates).
- D9. Labour can be forecast in hours (x rate) or in dollars, per item.
- D10. Accruals can be entered in hours on a day for a resource (hours x rate). An hours accrual reverses
  automatically once a Pronto timesheet for that resource and day lands, the same way invoice accruals reverse.
- D12. Sync conflicts: same unique key created by two people offline is settled the same way on every copy
  (code/ref suffixed with ~xxxx on the higher id; otherwise higher id wins). Day-grid cells have no unique key; newest wins.
- D13. Nested forecasting (Vincent, 16/10): a group's (Unallocated) line is a pool that can be forecast at supplier or
  role level (any method, incl. GROUND-UP with role-only calendars priced from the rate card). Every forecast item on a
  lower line is either taken out of the pool above (`forecast_item.from_pool = 1`: the pool's forecast is reduced by
  the same amount, same month first then the pool's earliest months, nearest pool first then further up) or in
  addition (0). New items default to "taken from the pool" when a pool above still has forecast. An allocation bigger
  than the pool counts in addition and is flagged on the line. Allowance is NOT moved automatically (open question 4).
  Every pool amount links back to where it is set (pool editor, cost control) and the labour calendar lists
  unassigned pools with "Assign hours to someone".
- D14. (Vincent 16/10) Allowance does NOT move automatically when forecast is taken out of a pool. The user
  balances allowance by hand (CBS and allowances > transfer) when reviewing cost control.
- D15. (Vincent 16/10) No restrictions by role. Instead a full audit trail: who did what, when, old and new value.
  Every accrual is clickable for its history: Accruals page rows, cost-control drawer Accruals tab, the ACC
  drill-through, and accrued hours in the labour calendar.
- D16. (Vincent 16/10) SharePoint cannot be the server: SharePoint Online does not run the app's Python code and no
  longer opens .html/.aspx files from a library by default; SharePoint Lists as the database would need an Entra app
  registration from IT, and lists block queries over 5,000 rows (Pronto exports are larger). Keep D1-D3: SharePoint
  is the shared storage, each PC runs the app.
- D17. (Vincent 16/10) Past days in the labour calendar are editable only to adjust your own accrual. Posted
  timesheet hours are never editable. Pink (posted, nothing else) and unposted-only Pronto timesheets are read-only.
  Light blue with no timesheet: type to create, change or clear the accrual. Purple (timesheet + accrual that
  differs): click to adjust the accrual in the day box.
  An hours accrual covered by fewer timesheet hours is 'partial': the covered part reverses and the rest keeps
  counting (engine and drill sum amount - matched_amount). Covered fully: 'matched' (equal) or 'investigate' (more).
- D18. (Vincent 16/10) Unposted timesheets: Pronto lists the hours but no cost until approval adds the rate. The PM
  accrues those hours: unposted cells are editable (light blue, "P x" = Pronto's unposted hours), with a bulk
  "Accrue all unposted timesheets in view". Only a POSTED timesheet reverses an hours accrual. Until the PM accrues
  a person-day, its unposted hours still accrue automatically (Pronto cost, else hours x cost rate); once the PM
  accrues it, the PM's accrual replaces the automatic one (accruals.UNPOSTED_NOT_ACCRUED), so nothing is counted twice.
- D19. (Vincent 17/10) Subcontract payment terms: portions as % of the contract (e.g. 10% order, 80% progress, 10% QA =
  100%). Progress claims on price-table items are multiplied by the progress %. The subcontractor's plan fills future
  claimed months; the PM's planned approval fills future approved months and drives cost to complete.
- D20. (Vincent 17/10) Views are "Current allowance" (what the project may spend, growing as the company releases
  risk to it) and "Total allowance" (plus the company's remaining risk bucket).
- D21. (Vincent 17/10) EPEC has three entities: EPEC Projects Pty Ltd, EPEC Group Pty Ltd, EPEC Engineering Pty Ltd.
  An entity is never a person's name.
- D22. (17/10) Variation lines use the workbook's formulas; markup is a % of cost (it was cost + risk in PMT before).
- D23. (Vincent 17/10) A spread can be uniform or proportional; the user picks which price items carry it.
- D24. (Vincent 17/10) The client sees price items only, their scope, each line's contribution, or full detail.
- D25. (Vincent 17/10) On approval the funds either top up the existing CBS or go to a copy of a CBS group/line made
  for the variation, which then also collects the Pronto cost coded to that variation.
- D26. (Vincent 21/10) Claim schedule grid: months are typed as $ or % of the line's price; a line can never exceed its price
  (cumulative, claims issued included); the status month is the claim to submit (PDF or Excel); later months are forecast revenue;
  a value can be dragged to a later month.
- D27. (Vincent 21/10) A claim schedule file with month columns can overwrite the claim schedule and its claims: past months are claims
  already made, the status month the claim to submit, later months the forecast.
- D11. Forecast days count from the day after the status date. Past forecast days with no timesheet and no accrual
  are flagged on the calendar so they get accrued.

## Open questions for Vincent

1. Try sharing on a real SharePoint library with one colleague (README, "Sharing a project through SharePoint").
   Confirm your name shows correctly (top right) and that a change shows on the other PC within about a minute.
   (Vincent 16/10: noted.)

2. The engine counts the status month as a forecast month too, so at a month-end status date (e.g. 30/09) AT-BUDGET
   and BURN-RATE still put forecast into September (shown as "+$x" next to what landed). Should forecast start the
   month after the status month when the status date is the last day of the month?


## Bundle history

- 2026-10-16.1 business account: received personal-account bundle 2026-10-16 02:28; added this handoff file.
- 2026-10-16.2 business account: multi-user sharing (identity, change log, journal sync, activity/history) and the
  forecast module (calendar, milestones, roster, supplier rates, hours accruals, labour calendar). Zip
  `pmt-app_20261016_business.zip`. Git history inside the zip (`.git`) shows each step.
- 2026-10-16.3 business account: nested pools (taken from the pool vs in addition), pool links, labour-calendar pools.
  Same zip name, rebuilt.
- 2026-10-16.4 business account: Vincent's answers recorded (D14-D16); accruals clickable for history everywhere;
  role stored per person; change clock in microseconds (bulk loads no longer push it ahead). 106 tests pass.
- 2026-10-16.5 business account: thread 3 (workbook colours in labour calendar and cost control, CTC month pane
  with method what-if, month-end review). 109 tests pass.
- 2026-10-16.6 business account: D17 (only accruals editable in the past, partial hour accruals); hours shown with
  decimals in the calendar. 109 tests pass.
- 2026-10-16.7 business account: D18 (PM accrues unposted timesheets; only posted ones reverse). 110 tests pass.
- 2026-10-16.8 business account: thread 4 (claim sheet, subby timesheets, lookahead, NT/OT split). 115 tests pass.
- 2026-10-17.9 business account: thread 5 (forecast / actuals / accruals history pages, EOM report PDF + Excel with
  cashflow, sums in number cells). New requirement: reportlab. 118 tests pass.
- 2026-10-17.10 business account: thread 6 (PMT.exe launcher window with progress and details, icon on a white tile).
- 2026-10-17.11 business account: thread 7 (subcontract payment terms + Excel payment schedule, update safety, CBS and
  contract tree levels, totals, frozen columns). 121 tests pass.
- 2026-10-17.12 business account: thread 8 (interleaved template months, supplier/PO linking, Diagnostics, variation
  register, allowance view names, identity fix, stale-server kill, release label). 126 tests pass.
- 2026-10-17.13 business account: thread 9 (variation engine: price items, cost lines, spreads, client detail levels,
  funding by top-up or CBS copy, register cost and revenue). 130 tests pass.
- 2026-10-17.14 business account: cost control shows base and variation scope as one line with a budget build-up
  (original + each variation = total) and a base / variation breakdown; lean "only the lines it uses" copies. 133 tests.
- 2026-10-17.15 business account: thread 10 (new windows for pages and tables, sort / filter / original order on every
  table, labour calendar pools collapse and separate windows).
- 2026-10-17.16 business account: thread 11 (labour calendar popout opens the live page; whole project by month with
  only the current month's days open). 133 tests pass.
- 2026-10-17.17 business account: thread 12 (dashboard tiles and charts click through to their data). 133 tests pass.
- 2026-10-17.18 business account: thread 13 (Ask chat with PMT guide and Microsoft Copilot, tile links on every page,
  Your defaults, calendar NT/OT prefill). 137 tests pass.
- 2026-10-17.19 business account: thread 14 (Project library for archived projects, Portfolio with analytics, location
  and project director fields). 139 tests pass.
- 2026-10-17.20 business account: thread 15 (portfolio map, asset fields, client CRM, PM workload by level). 142 tests pass.
- 2026-10-20.21 business account: thread 16 (PMT.exe clicked in SharePoint finds and starts the synced copy). 142 tests pass.
- 2026-10-20.22 business account: thread 17 (Actuals: invoices by supplier, Excel export). 143 tests pass.
- 2026-10-20.23 business account: thread 18 (accruals reviewed against the workbook: kinds, PO/invoice/quote matching, work-month timing, finance's WIP accruals, timesheet journal requests, work/billing/cash timelines). 148 tests pass.
- 2026-10-20.24 business account: thread 19 (Pronto raw rows and data checks: future dates, totals rows, reversed keying errors, duplicates; cost incurred to date without forecast). 152 tests pass.
- 2026-10-20.25 business account: thread 20 (load allowance per line, ledger, forecast grid and accrual register from the PMT workbook; finance reversals naming another month). 154 tests pass.
- 2026-10-20.26 business account: thread 20 CTD tie-out to 30/09; negative accruals never PO-matched. 155 tests pass.
- 2026-10-20.27 business account: thread 20 future-dated Pronto actuals stay in CTD and raise an error on the dashboard and in Diagnostics. 156 tests pass.
- 2026-10-21.28 business account: thread 21 (delete from a list + OK, Payment Milestones wording, Excel load preview / save / undo with Update-and-add or Replace, selector refresh). 159 tests pass.
- 2026-10-21.29 business account: thread 22 (Pronto exports as .ods). 161 tests pass.
- 2026-10-21.30 business account: thread 23 (claim schedule import asks whether variations and optional prices are in the original contract value). 165 tests pass.
- 2026-10-21.31 business account: thread 24 (contract tiles open their part in a window, erase a setup section, folding menu). 166 tests pass.
- 2026-10-21.32 business account: thread 25 (optional prices offered / confirmed / cancelled; kind and status editable in the row). 171 tests pass.
- 2026-10-21.33 business account: thread 26 (variation status, nesting colours, drag rows, column widths, editable grid with fill handle, payment milestones vs claim schedule templates, full-width views, Esc goes back). 178 tests pass.
- 2026-10-21.34 business account: thread 27 (linked projects: parent project merges its children's CBS, read-only, drill down to the child line; portfolio / program combined CBS; junior PM one project; templates open on the deliverable, payment milestones without status month, 1 > 1.01 > 1.01.02 nesting with subtotals). 185 tests pass.
- 2026-10-21.35 business account: thread 26 (claim schedule status month dropdown driving the grid colours, import uses it; resized columns widen their content; side menu hierarchy). 186 tests pass.
- 2026-10-21.36 business account: thread 28 (project chart, clients and resources database with lookups, REPORTING with PMR/PSR placeholders, contingency and ledger tabs, CLOSE-OUT section, demo team). 189 tests pass.
- 2026-10-21.51 personal account: forecast lines grid (thread 32), dashboard future bars jump to the forecast month, user chip role on its own line.
- 2026-10-21.37 personal account: merge of business_9 (.36: threads 25 to 28) with the claim schedule grid (thread 29) and the claim schedule overwrite (thread 30); thread 31 lists the merge decisions.

- 2026-10-24.82 personal account: Workflow page (PMO), Allowance page, forecast typing and activity window, schedule drivers; zip `pmt-app_20261024_parent_46.zip`. 262 tests pass.

- 2026-10-24.83 personal account: month forecast window from the dashboard bars; zip `pmt-app_20261024_parent_47.zip`.
- 2026-10-24.84 personal account: Cost control row hover is bold, no colour change; zip `pmt-app_20261024_parent_48.zip`.
- 2026-10-24.85 personal account: Cost control total row carries the month grid; zip `pmt-app_20261024_parent_49.zip`.

- 2026-10-24.86 personal account: Method, Start, Stop, Months in the Cost control row; zip `pmt-app_20261024_parent_50.zip`. 262 tests pass.

- 2026-10-24.87 personal account: Cost control total row stays behind the sticky CBS and Name columns; open groups and scroll position kept after an edit; zip `pmt-app_20261024_parent_51.zip`.

- 2026-10-24.88 personal account: Cost control numbers open the line on their own tab; zip `pmt-app_20261024_parent_52.zip`.

- 2026-10-24.89 personal account: Allowance cell on Cost control selects on click, opens the Allowance tab on double-click; zip `pmt-app_20261024_parent_53.zip`.

- 2026-10-24.90 personal account: spread allowance by dragging, double-click to source pages, method preview graph, keep place in tables; zip `pmt-app_20261024_parent_54.zip`.

- 2026-10-24.91 personal account: walkthrough review (PMT_UX_review_24-10-2026.md), CBS editor route and month label fixes; zip `pmt-app_20261024_parent_55.zip`.

- 2026-10-24.92 personal account: unallocated pools default to NONE, CTC (Unallocated) line per CBS parent; zip `pmt-app_20261024_parent_56.zip`.

- 2026-10-26.108 personal account: issues register ISS-001, 002, 004, 005 (part 1) and quick UX items (ledger tree with funding and reasons, in-place redraw, Columns and Group by CBS on tables, variation placeholders from the contract); built on `pmt-app_20261025_parent_62.zip`.
- 2026-10-27.109 personal account: dashboard margin tile (uplift or erosion) opens a margin bridge; Accruals gets an All accruals master list by party, the people behind payroll accruals, PO / Quote / Invoice columns, estimate hints and a reason on every edit or delete; zip sent.
- 2026-10-27.111 personal account: quiet design restyle (static/css/design.css loaded after app.css; sidebar sentence case, two button styles, hairline tiles, light dialogs and drawers, one-line page subtitle, Filters menu on Cost control and Forecast lines); zip not yet sent.
- 2026-10-27.112 personal account: UX items #3, #4, #5, #6, #7, #15 (Month-end checklist page and menu group, Allowance setup step, Initialise pre-flight, What next card, bulk allowance linking and hidden empty buckets, close-out checklist); zip not yet sent.
- 2026-10-27.113 personal account: Ground-Up register (ISS-003 part 1: H1 > H2 > H3 groups over the forecast items), method pickers retired (#20), fix: forecast items saved through the API lost most fields because the variation `ITEM_COLS` shadowed the forecast one; zip not yet sent.
- 2026-10-29.114 personal account: Project complexity (EPEC Complexity Matrix): the director's baseline, the PM's monthly ten-dimension assessment with client difficulty, radar profile, PM levels 1 to 5, band decides the PM level a project needs; zip not yet sent.
- 2026-10-29.115 personal account: Project team page, people's levels by role, the requirement table, fit and the first risk rule, people template (import not built); zip not yet sent.
- 2026-10-30.116 personal account: looking ahead six months, team confirmation at month-end, Team fit tab on the Team page, Word resourcing paper (python-docx added to requirements); zip not yet sent.
- 2026-10-30.117 personal account: EPEC Classification Framework (EPEC-HR-FW-0001_0 rev 0) as reference data, on people and in the project team; zip not yet sent.
- 2026-10-30.118 personal account: PM competency by complexity dimension against what the baseline asks (Complexity Matrix levels); director only; zip not yet sent.
- 2026-10-31.119 personal account: Project Director and above see the baseline; PM level independent of the ECF level; leaving date and serving notice on the person; org chart loaded from the skill chart; duplicates and merge; paper sign-off block; data objects catalogue; My profile; zip not yet sent.
- 2026-10-27.110 personal account: outline strip for every month and day grid (folded quarters, months, weeks take no width; rings and dots bring them back; 1 2 (3) level buttons); zip not yet sent.

## Release 2026-10-21.52
- Project setup: Back/Save/Next footer on every step with an unsaved-changes prompt (dirty tracking exists only on the Project step; other steps store edits as they are made, so Save just confirms). Per-step templates via `/template.xlsx?step=contract|cbs|programme|project` (`templates_io.STEP_SHEETS`). Schedule step has the drop zones (`scheduleDrop(onDone, layer)` in programme.js).
- `programme_task.layer` ('internal' default, 'upstream'): upload and remove take `?layer=`; only internal tasks are auto-linked, applied or copied to milestones.
- Project schedule menu item moved from Setup to Forecast.
- PMO menu group (Project Library = gate papers and review checklists to download, Project Lifecycle = gates and phase reviews, Meetings = placeholder, Archive = the old Project library page). Meetings content is still to be defined by Vincent.
- Long tables (10+ rows, with a total row) repeat the total under the heading (`tabletools.topTotal`); `.tw` now caps at 80vh so the scrollbars sit right and bottom.
- Project setup gained step 5 Pronto data (embeds the Pronto page; for projects that already have cost). Setup is for the baseline only: monthly updates (schedule actuals, later Pronto loads) happen outside Setup. NOT YET BUILT: baseline vs actual tracking on the Project schedule page (actual start/finish, % complete each month). Forecast lines grid: drag exists; delete/reinsert by $ or % in the grid does not (typed months are on the line page, $ only).
- COMMUNICATION menu group: Stakeholders (moved from OVERVIEW), Communication matrix (placeholder, columns to be defined), Project org chart (moved from SETUP). Org chart: select a box then Delete party (button or Delete key) or edit its name.
- NEXT (requested, not started): CMT upload (Cost control and Project setup) with gap analysis per item, reject or align; align sets forecast method to MANUAL and loads the CMT monthly forecast. Sample: Maryvale Live CMT MASTER (sheets: Project Summary, Financial Summary, ' Forecast Costs & Revenue' with a leading space; rows per resource, columns Category, Cat Description, Resource/Task, PO Number, Resource Code, Cost Rate, Budget, CTD, CTC, EAC, then monthly columns from col X Accruals).
- Release .53: CMT upload built (`app/cmt_import.py`, `/cmt/analyse|apply|undo`, `static/js/views/_cmt.js`, test_cmt_import.py). Checked against the Maryvale Live CMT (478 lines, forecast months sum to CTC 3,539,649.81). Not yet done: aligning budgets, revenue/claim forecast, the Financial Summary sheet. Fuzzy name matching can map a CMT person to the wrong app resource when no code matches; user reviews each item.
- Gate and Phase cards moved from Project setup to PMO (Project Gate, Project Phase pages). SETUP menu items are the steps (`setup?step=...` keys in NAV).
- Release .54: `pronto.wrong_project_warning` and `warning` in `/pronto/analyse`; both upload flows in pronto.js ask for confirmation (test in test_cmt_import.py).
- Release .55: `app/knowledge.py`, table `kb_doc` (data is base64 TEXT because the sharing triggers use json_object, which rejects BLOBs), `/api/kb`, `/api/p/{pid}/lifecycle/documents`; lifecycle.js hub; Back/Forward buttons in the top bar; review columns swapped; NAV `valid` list strips `?step=` and allows gates/phases routes.
- Release .56: drag-and-drop order of the left-pane groups (`renderSide` in app.js, localStorage `navOrder`, per PC).
- Release .57: `app/stakeholders.py`, table `project_stakeholder`, `/api/p/{pid}/stakeholders`, projstakeholders.js; NAV default order changed (a saved navOrder in a browser overrides it).
- Release .58: table `programme_file` (base64 original), `/programme/file?layer=&info=`, programme.js split into the schedule view (default) and `updatePage` (view=update). The claim-item tiles now live only on the Update page, headed as claim schedule and cost forecast dates.
- Release .59: setup drafts (`/setup/draft`, `/commit`, `/discard`; `draft`, `commitDraft`, `api.beforeWrite` in app.js; TOUCHED now includes programme_task and programme_file; draft restore points are hidden from the Undo list and deleted when resolved). `PUT /pronto/project` sets the Pronto code. Excluded from drafts (they confirm or undo themselves): load-template, cmt, restore-points, pronto, initialise, setup/erase. Not covered: the Project step (its own form Save), Pronto step.
- Release .60: CMT weak-match review (`match`, `candidates`, `targets` on apply); menu order and shortcuts in `user_setting` (`/api/me/menu`, `/api/me/shortcuts`); search.js; shortcuts.js; `/api/kb/download-all`; sentence-case names. PENDING (proposal sent, awaiting answers): scope selector for Overview (my projects / program / division / all), project division field, GM role, renaming the two stakeholder pages.
- Release .61: `views/_lifecycle.js` (LIFECYCLE text from the PMO graphic, `lifecycleStage`, `lifecycleStrip`, `deliveryStrip`). The mapping from gate/phase to lifecycle stage is my reading of the graphic: confirm with Vincent.
- Release .62: `kb_doc.project_type` (NULL = all types), filter in `knowledge.relevant`. Not built from the library suggestions: mandatory/optional flag, owner and revision date, PDF preview, versioning.
- Release .63: see README 'Release .63'. Forecast-set/restore endpoints (`/nodes/{id}/forecast-set`, `/forecast-restore`), CMT budget items (`kind=budget`, ledger kind adjustment, undone by pair_id), `/cmt/report`, remembered decisions in settings `cmt_decisions`. Gate 8 still to be found by Vincent.
- Release .64: `app/javaenv.py` (find Java, else download Temurin 17 JRE to <PMT home>/jre; `python -m app.javaenv --ensure` called by run.bat at every start; programme.read_mpp uses it, JPype started with the JRE's jvm library). UNTESTED on Windows or against a real .mpp (the sandbox has no internet and no Java): ask Vincent to try on a PC without Java and send the PMT.exe 'Copy details' output if it fails. Adoptium download is not checksum-verified (size and runs-check only).
- Release .65: cost control current-month column order swapped (monthCells, headers, legend, alt-method row); org chart panel moved above the chart.
- Release .66: renderTop rewritten (icons via `icon()`/`tbBtn()` in app.js, `.tb-*` styles at the end of app.css).
- Release .67: editable status date in the top bar (renderTop).
- Release .68: CMT three-way decisions (`decisions[id] in reject|align|cmt`, `cmt_edits`, `edit_sheet_xml`, `updated_workbook`, `/cmt/updated`, the original upload is kept for a day); tabletools: column reorder (`pmt.colorder`), generic copy handle (`.tt-fill`), `grip4` move grip on the forecast grid; `notools` removed from six small tables. Revenue/Financial Summary sheets are still not written back.
- Release .69: `static/js/tilelayout.js` (watchTileLayout), `/api/me/tiles` (user_setting key tiles), reset in resetMenu. Only grids made of .kpi tiles with unique labels inside #view qualify; tiles in dialogs and drawers are not movable.
- Release .70: pools (`engine.leaf_row(covered=)`, `_unmet`, COVERED status, method NONE, `app/pools.py`, `/pools/allocation`); claim PDF (`exporters.company`, `claim.client_claim_no`, `user_setting` upn='*' key company for shared settings). EPEC's ABN was NOT supplied and is not hard-coded: Vincent must type it in Settings. Client address uses `client.hq`.
- Release .71: `subcontracts.issue_certificate` (auto on approval), `sub_claim.cert_no/cert_date/cert_by`, `exporters.sub_certificate_pdf`, `ui.pdfNameDialog`, claim PDF layouts a/b (`company().claim_layout`). Certificate wording is minimal (no payment-terms or GST text) until Vincent supplies EPEC's standard wording.
- ABN default now 34 640 363 686 / EPEC Projects Pty Ltd, taken from Vincent's example claim (WDSF-FI-CL-0006) and tax invoice (WA2-EPE-INV-0006); both show Level 5, 52 Merivale St, South Brisbane, while Vincent gave L1/100 Melbourne Street: address default kept as Vincent's, to confirm.
- Release .72: certificate redesign (`sub_claim.cert_note`, `subcontracts.supplier_of`, notes and detail page), address abbreviation. Subcontractor ABN/address come from the `company` directory; a warning appears when issuing if either is missing.
- Release .73: claim PDF house format (`exporters.claim_act`, `BIF_STATEMENT`, `_tag`), `claim.revision/revision_date/client_cert_no`, `project.claim_act`. Vincent confirmed: no invoice generation (Pronto does it); claims and payment certificates are issued from here; client-certified amounts drive monthly revenue (already how `revenue.py` counts COALESCE(certified, amount)).
- Release .74: compact claim header (`st_id`, `both_blk`).
- Release .75: `project.contract_law`, `exporters.site_state/claim_act_info/LAWS`, `/api/p/{pid}/claim-act`. The mismatch case (Queensland site, other state's law) is deliberately not decided silently.
- Release .76: `project.review_days/review_basis`, `revenue.review_deadline`, `/api/p/{pid}/review-deadline`, `exporters._dmy`. Principle from Vincent: entities (client, subcontractor, employee, project) have cards that store all their relevant info; documents read from the cards.
- Release .77: claim dates box top right (`dbox`, `top_row`).
- Release .78: `claimsTable()` in revenue.js (inline editing, dblclick opens `open(id)`); app.js `render()` restores scroll when `location.hash` is unchanged (`lastRender`).

## Release 2026-10-24.79
PMO > Workflow (`static/js/views/flow.js`): stage by stage summary from setup to close-out, each stage with its next step and links, plus a short "aligning allowances" note. The full app guide is intended for the chat button and the Project library (not built yet).

## Release 2026-10-24.80
Allowance page (SETUP > Allowance; `app/allowance.py`, `static/js/views/allowance.js`, endpoints `/allowance/overview|preview|link`). Links a resource to an allowance bucket (a CBS group's own allowance) as a ledger transfer with ref LINK, the starting point of the ledger. Option 1: no cost yet, user sets the initial budget, capped by the bucket. Option 2: cost so far (CTD + accruals + open commitment, once the Pronto rows sit on the line) is covered, capped by what the bucket has left. Option 3: that cost as a floor plus a user amount, total capped by the bucket. Preview runs inside a SAVEPOINT that is rolled back. Tests: `tests/test_allowance.py`. Not built: re-linking a line to a different bucket; risk allowance (only budget moves).

## Design agreed with Vincent, not yet built (24/10/2026): teams, leads and accountability
Purpose: hold team leads accountable for their slice of a project's budget; later, per-user views and a resource workspace.
- Teams: Construction, Design, SCADA, Commissioning (Projects), Commissioning (Engineering), Engineering, plus PM (no team). Legal entity: EPEC Projects Pty Ltd for Construction, Design, SCADA, Commissioning (Projects); EPEC Engineering for Commissioning (Engineering) and Engineering. Legal entity is a project field (an R01/R02 child project is EPEC Engineering and its revenue goes there).
- A cost line's team is the first that applies: tag on line or group; for labour lines the person's home team (Stakeholders directory field, seeded from the org chart); the project's owning team; the category default; else PM.
- Category defaults: Construction PL04 PL06 PL08, PS04 PS06, PM05 PM06 PM07, PE01 to PE04. Design PL02, PL03 for Design staff, PS02, PS03. SCADA PL07, PS07, PM01. Commissioning (Projects) PL05, PS05. Engineering PL03 for Engineering staff. Commissioning (Engineering) PL03 for its staff when an EPC has no R01/R02, and all lines of an R01/R02 child. PM keeps PL01, PS01, PM02, PM03, PM04, PM08, PE05 to PE09. PL03 is a mix, so home team decides.
- Project owning team (project card): none for EPC; Commissioning (Engineering) for R01/R02 child projects (own CBS, not yet seen); SCADA for SCADA BoP contracts (project manager Dennis Miranda, who is accountable for the whole budget; EPC contracts have a delivery PM).
- One lead per team per project, picked from the Stakeholders directory (employees or consultants); the head is always eligible and sees all projects of the team. Design: Phil Gold (head), Alexander McDonald, Peter Hogan, Geoff Hampton. Commissioning (Projects): Tim Duff (head), Ian Jordaan, Neville Palmer. Construction: Matt O'Connor (head, also acts as CM), construction managers in-house or consultant. SCADA: Praveen Atmuri (head), Tysan Greaves, Ana Prado. Commissioning (Engineering): Paddy O'Connell (head). Engineering: Mick Flynn (head). A portfolio is the set of projects where someone is lead. Keep a history of lead changes.
- Accountability: the PM is accountable for the whole budget; on EPC projects each lead is accountable for their slice (allowance, committed, CTD, accruals, CTC, EAC, variance) and the app flags an overspending slice. Leads see cost, never revenue; subcontractor budget cost and budgeted hours per team (hours from the rate card unless estimates hold hours).
- PM04 stays in the PM budget (Design is technical owner only). Engineering charges are ordinary cost lines, no internal recharge.
- Build order: team tagging and home team; legal entity and owning team on the project; team chip bar on Cost control; COO Teams page; later per-user views and the resource workspace (business-wide programme for heads, project resource schedule for project-level roles).
- Open: leads for Commissioning (Engineering) and Engineering; hours held per line or only dollars; sample R01/R02 and BoP SCADA CBS.

## Release 2026-10-24.81: forecast typing and activity window
- Cost control, future month of a CBS line: click to type ($, or % on AT-BUDGET and AT-COMMIT lines), no confirmation. A line on any other method (GROUND-UP and CLAIM included) becomes MANUAL, keeping what it forecast, and only that month changes (`forecast-set` with convert). Double-click opens the forecast window (`monthsPane`). The same confirmation was removed from typing on Forecast > Forecast lines (moving a value by its grip still asks).
- Activity window: Start, Stop, Duration (months) editor (`windowEditor` in `costcontrol.js`, in the forecast window and the line drawer). Editing one of three filled fields clears the other two; with two filled the third is calculated (months counted inclusive). Saving sets `cbs_node.window_manual=1`.
- Schedule link: uploading or editing the internal project schedule now applies the dates of linked tasks to linked CBS lines automatically (earliest start, latest finish). Links survive a re-upload (matched by WBS and name). Lines with `window_manual=1` are skipped and shown as "Manual override" with "Return to schedule" (`/nodes/{id}/window-reset`). `programme.window_warnings` reports MANUAL typed months outside a moved window: a dialog after the update, and the cells are outlined (dashed) on Cost control. Nothing is cleared silently.
- Tests: `tests/test_activity_window.py`.
- Not built: a visible "windows changed" count on Cost control; claim-item windows still use the manual Apply button.

## Release 2026-10-24.82: schedule drivers for the activity window
- Start and Stop of a CBS line's activity window can each follow a schedule item (a task's start or finish; a milestone has one date), or be typed; Duration is typed or derived; any two determine the third. Table `window_link` (node_id, role start|stop, task_id, edge, suspended); `cbs_node.window_months` holds the typed duration while one end is anchored and the other follows from it.
- Old-style links (`programme_task.link_node_id`: a task drives a line start to finish) still work and count as Start = earliest start, Stop = latest finish (virtual anchors; `programme.window_state`).
- Typing over a driven field suspends that one link (it is kept: "Return to schedule" per field, or for the whole line). `programme.set_window`, `apply_node`, `reset_window`; endpoints `POST /nodes/{id}/window`, `POST /nodes/{id}/window-reset` (role optional), `GET|POST|DELETE /programme/links`.
- Both directions: Forecast > Project schedule has a "Drives CBS" column, and clicking a task opens what it drives, with link/unlink (whole window, start only, stop only, both, start or finish date). The activity window on Cost control (forecast window and line drawer) shows what drives Start and Stop. Setup > Project schedule has a button towards that. Linking is optional: a line can be set by hand.
- Schedule upload or edit re-applies automatically; typed MANUAL months outside a moved window are kept, listed in a dialog and outlined on Cost control.
- Tests: `tests/test_activity_window.py` (7).
- Not built: linking by group (a group's window is still inherited by its lines as before); claim items still use the manual Apply button; no "what changed" history for window moves.
- (.82) The schedule picker in the activity window has a "Whole task" button: Start follows the task's start and Stop its finish in one step (the line runs alongside the task). Example: PL04 construction manager linked to "Site establishment". Checked in a browser against the demo project; no new automated test.

## Release 2026-10-24.83: forecast landing in a month, in a window
- Dashboard > Revenue against cost (Cost incurred / Value of work tab) and the Monthly cost by category chart: clicking a cost bar from the status month on opens `static/js/monthforecast.js`: every line in the scope with a forecast in that month, with a box to type or change the amount; "All lines in scope" adds lines that have none. Typing converts the line to MANUAL (other months kept), same as on Cost control. Past bars still open the actuals / cost control. Revenue bars still open the claims. Checked in a browser against the demo project; no automated test (front end only).

## Release 2026-10-24.84: Cost control row hover
- Cost control (`table.t.cc`): the row under the mouse goes bold and no cell changes colour (the blue hover tint read as an accrued value). Other clickable tables keep the old tint. Checked in a browser: background unchanged, weight 400 to 700.

## Release 2026-10-24.85: Cost control month totals
- The total row (top and bottom) now carries the month grid: landed (actual + accrued) in past months, forecast in future months, and the current month twice (landed, then as forecast at the last close), for the lines in scope (`monthTotals` in `costcontrol.js`). Checked in a browser; front end only.

## Release 2026-10-24.86: Method, Start, Stop and Months in the Cost control row
- After Status, each CBS line row has Method (a picker), Start, Stop (month pickers) and Months, all editable in the row; the month grid follows. Fill any two of Start, Stop, Months and the third is worked out, in the same cell (you can read or type it). Inherited dates show greyed italic; a schedule-driven end has a navy underline; a typed-over end has an orange dotted underline. Edits post to `POST /nodes/{id}/window` (so schedule drivers keep working). The cost-control response now carries `windows` (which lines are schedule-driven).
- Method picker: TOP-DOWN asks for the EAC in a dialog; GROUND-UP opens the line's detail page to build items; CLAIM only for lines with a claim schedule. No Remaining months column and no EAC override column (computed or asked for instead).
- Learned from the Excel PMT (WDSF-PD-RP-0000_1, 24/10/2026): Steady-State default (BURN-RATE, AT-COMMIT, AT-BUDGET) plus Override (about 381 of 386 lines are GROUND-UP); the rule methods spread CTC evenly over Start to End (blank = all remaining months); Ground-Up is a flat register (own H1/H2/H3 sections, CBS and resource per line, modes Milestone, Daily, Direct) rolled up by CBS|resource; frmCostControl has Accrual, Setup (new line) and Move (allowance) pages; no VBA drives the forecast. Next: the Ground-Up register replacing Forecast lines, with an import of that sheet (240 lines).
- Checked in a browser against the demo project; no new automated test. Typing in a month cell needs Enter or Tab to commit.

## Ground-Up register: requirements so far (Vincent, 24/10/2026), not yet built
- A register like the variation register, replacing Forecast lines. Freestyle three nested headers (H1, H2, H3) chosen by the user, not the CBS order, for example everything for one person on site grouped together (LAHA, vehicle, labour). Each line still names its CBS line and resource, and rolls up to Cost control by CBS and resource.
- Spread modes seen in the PMT sheet: Milestone (percent of a PO value on a date or trigger), Daily (day grid, quantity times rate, pattern and frequency, start and end), Direct (total over a span). Import the PMT Ground-Up sheet (about 240 lines) as test data.
- Labour of the own team and of subcontractors on labour-hire schedule of rates: a day grid with rosters, hours typed or calculated from the roster pattern and the rates.
- Supplier milestone payments in the register, each linkable to a project schedule item or given a typed forecast month.

## Release 2026-10-24.87: Cost control total row and keeping your place
- The Project total label sits in cells that are sticky (CBS and Name columns), above the scrolling numbers, so totals no longer slide over the description columns (top and bottom total rows).
- Open groups are remembered per project in sessionStorage (`ccOpen:<pid>`) until the level chip changes, so an edit does not collapse the tree. `render()` in `app.js` also restores the window and `.tw` scroll at 450 ms and 1000 ms (stops as soon as you scroll, click or type) because big tables settle their widths late. Checked in a browser; no automated test.

## Release 2026-10-24.88: Cost control numbers open the matching tab
- On a line (or an unallocated pool) a click on Allowance or Contingency opens the line on the Allowance tab, Ordered or Open POs on POs, CTD on Actuals, ACC on Accruals, EAC on Forecast; CTC still opens the forecast window. A group's totals still list the records behind them (`drillModal`), whose "Open line" button also opens the matching tab (`TAB_OF`). Checked in a browser for Allowance, CTD, ACC and EAC; Ordered was not exercised.

## Release 2026-10-24.89 and a proposal not yet built: spreading allowance by dragging
- Built: on a line, the Allowance cell is selected by a click (outlined) and opened on the Allowance tab by a double-click.
- Proposal (waiting for Vincent): on a pot row ((Unallocated)) the Allowance cell gets a grip; drag it down over the lines beneath (or select the lines and drag), release, and a small popover offers Equal / By need (EAC less allowance) / Typed amounts, with the pot's remaining amount and a preview per line. Apply posts transfers (ref SPREAD) through the existing ledger; Undo reverses them. Dragging one line's allowance onto the pot returns it.

## Release 2026-10-24.90: spread by dragging, source pages, method preview, keeping your place
- Spread: on an unallocated pool row the Allowance cell has a grip (`.spgrip`); press it and drag over the lines of that group (up or down, only lines under the pool's group light up), release, and a dialog offers By need (EAC less allowance, scaled to the amount), Equal or Typed, with the pool's free amount (allowance less cost parked on it). Apply posts one ledger transfer per line (ref SPREAD) through `allowance.spread` (`POST /ledger/spread`, one all-or-nothing check against the pool), and a note on Cost control offers Undo (`/ledger/spread/undo`). Not built: dragging a line's allowance back to its pool. Test: `tests/test_allowance.py`.
- Double-click on CTD opens the Actuals page for the line, ACC the Accruals register filtered to its CBS code (banner with Show all), Ordered or Open POs the Commitments page searched for its code; a single click still opens the line's drawer on that tab (delayed 260 ms). Allowance: click selects, double-click opens the Allowance tab.
- Method preview: in the line drawer's Forecast tab, choosing another method redraws the Monthly profile (now directly under the method card) with that method's months and shows CTC, EAC and contingency against now, using the what-if endpoint; nothing is saved until Save method. The method dialog on Forecast lines has no graph (that page is to be replaced).
- Keeping your place: `clear()` in `ui.js` restores the scroll of tables redrawn inside the cleared block (once, unless you scroll yourself); `render()` restores the window and table scroll; the Cost control drawer reopens on the same tab and scroll after a save; Cost control remembers open groups. Writes that navigate after saving (`go(...)`) were audited: only intended ones remain (demo team, initialise, claim items, selecting GROUND-UP or CLAIM on a line).

## Release 2026-10-24.91: walkthrough review and two fixes
- `PMT_UX_review_24-10-2026.md` lists 20 findings from a set-up to close-out walkthrough. Fixed: the CBS editor and Rates routes were missing from the route list (the "Open the CBS editor" button and others landed on the Dashboard); the Close month dialog showed "Close ?" when opened directly (`statusMonth()` helper in `api.js`). Everything else in the review is a proposal for Vincent to decide.

## Release 2026-10-24.92: unallocated pools default to NONE, CTC (Unallocated) lines
- An unallocated pool (the allowance a group holds itself) is no longer forecast by default: `initialise` sets `unalloc_method` NONE and the engine falls back to NONE (was AT-BUDGET), because on a project that is already running the cost sits on the lines beneath and the pool's remaining allowance counted it twice. Existing projects keep what they have; Cost control shows a warning with one button, "Set all unallocated pools to NONE" (`POST /pools/method`).
- `services.ensure_ctc_lines`: one line per CBS parent called "CTC (Unallocated)" (code `<parent>.999`, `origin='ctc'`, method NONE, no allowance), made at initialise, when a new parent is added, and at startup for running projects (idempotent; `POST /ctc-lines`). It is the place to forecast a cost that has no forecast of its own yet and no estimate bucket: the engine does not let the pool above cover it (never COVERED), `pools.plan` never allocates allowance to it, and Cost control shows it even with Hide empty lines on. Test in `tests/test_activity_window.py`; pool tests in `tests/test_forecast.py` now set AT-BUDGET explicitly.
- Cost control has a one-line hint on the spread drag (the grip sits on (Unallocated) rows only, from release .90).

## Release 2026-10-24.93: Allowances hub and drag-and-drop workspace
- COST menu "Risk and contingency" is now **Allowances** (`#/risk`, `views/risk.js`). Four tiles: Allowance (default), Risk register (register upload, tagging), Ledger (all money movement), Contingency (over and underruns, release). `?tab=` values: allowance, register, ledger, contingency (old `buckets` maps to allowance). The old `bucketsTab` function is unused.
- Allowance tile (`views/_allowances.js`): left, every estimate pot per CBS parent (available, risk, source badges: estimate, variation, release, etc., parked cost); right, all CBS cost lines grouped by parent. Drag a pot onto a line (Assign dialog: budget and risk) or onto a group heading (Spread dialog: by need, equal, typed). Each move is one `/ledger/transfer` (ref ASSIGN) or `/ledger/spread`, so everything shows in the Ledger. The `+` button does the same by click. Approved variations and extra risk pots appear as pots with source badges. `allowance.overview` buckets now carry `risk` and `sources`.
- Known gaps: Ledger tile has per line and by date views only, no full pivot; dragging a line allowance back to its pot is not built.

## Release 2026-10-24.94: three placeholders per CBS parent, no CTC without a window
- Per CBS parent: the allowance pot (the group's own "(Unallocated)" row, no forecast method, holds the estimate's original budget and risk), **WIP (Unallocated CTD)** (`<parent>.998`, `origin='wip'`) and **CTC (Unallocated)** (`<parent>.999`, `origin='ctc'`). `services.ensure_ctc_lines` makes both lines (startup, initialise, new parent, `POST /ctc-lines`).
- `pronto.resolve_all`: cost with no resource line (including Pronto's WIP account) lands on the category's WIP line instead of the pot. The pot still covers WIP cost (it counts as an overspend claiming the pool); `pools.plan` never allocates to WIP or CTC. Startup re-resolves when WIP lines were just made.
- Engine: AT-BUDGET, AT-COMMIT, BURN-RATE and TOP-DOWN lines show no CTC until the line (or an ancestor) has a start or end, typed, from a duration or linked to the schedule. Project dates no longer act as a default window. MANUAL and GROUND-UP are unaffected. Demo seeds a window on the top-level CBS parents.
- Estimate upload: a row of Type "Allowance" or "Function" adds its budget and risk to the CBS parent's pot (several rows sum).
- Not changed: existing projects keep their line dates; lines with none will now show zero CTC until a window is set.

## Release 2026-10-24.95: Revert button, collapsible and re-orderable allowance workspace
- **Revert** (top bar, `app/revert.py`, `GET/POST /api/p/{pid}/revert`, table `revert_mark`): runs the signed-in user's last action on the project backwards from the change log (inserts removed, changed fields back to old values, deleted rows put back). Each click goes one step further back; a reverted action is marked so it is not taken twice; there is no redo. An action that deleted bulk Pronto rows (no copy kept) refuses, with a pointer to the import's own undo. Changes received from other users and changes made under via "Revert" are skipped. `api.afterWrite` refreshes the button's tooltip. Test: `tests/test_revert.py`.
- Allowances workspace: right pane groups open and close (remembered per project in sessionStorage; Open all / Close all; a search or the short-only filter opens every match); both panes use the CBS order of Cost control; up/down arrows on pots, groups and lines reorder among siblings only (`POST /nodes/{nid}/reorder`, `services.reorder_node`, which keeps the siblings' existing sort values so other parents are untouched).
- Assign dialog fix: figures are shown in whole dollars, so typing what the screen showed (for example risk 39,581 for 39,580.62) was rejected by the client check. Tolerance is now $1 and the amount is clamped down to what the pot holds; the default risk is what the line still needs after the budget, never more than the pot's risk.
- Ledger tile: **Edit** and **Delete** on every entry (`PUT /ledger/{id}`; Delete refuses estimate and variation entries). Editing one side of a two-sided move changes the other side by the opposite amount; a move with more than two sides only takes date, reference and reason changes. The estimate can be edited (warning shown). Revert (top bar) undoes either. Test in `tests/test_revert.py`.
- `PMT_Issues_Register.xlsx` (project folder root): issues register for users. Columns Menu group, Page, Tab or tile are dependent drop-downs that follow the left-hand menu and the page tiles (sheet Pages holds the map, sheet Dropdowns the lists `pg_<Group>` and `tab_<Group>_<Page>`); Location joins them; Page address takes the `#/...` from the browser; Summary counts open issues by menu group. Generated by a script outside the repo; when a page or tile is added, add rows on Pages and a matching named list on Dropdowns.

## Release 2026-10-24.96: separate filters on the Allowances panes
- Allowances > Allowance: a filter box for the pots on the left (code, name, source such as variation or release) and one for the lines on the right (code, name, resource, group name). They combine, so Commissioning pots on the left and a resource name on the right work together.

## Release 2026-10-25.97: quieter Allowances workspace
- Minimal restyle (hairlines, no grey bands, small hover-only arrows and + button).
- Drag a row **up or down** to reorder it among its siblings (same parent only; pots on the left, groups and lines on the right; `POST /reorder/cbs` with the new id order). Drag a pot **across** onto a line or group heading to assign money. The tiny arrows remain as a fallback.
- The border between the two panes is a draggable splitter (width kept in localStorage `wsLeft`, double-click resets).

## Release 2026-10-25.98: Allowances tree, multi-select, return, Undo and Redo
- Allowances > Allowance rewritten (`_allowances.js`): both panes show the CBS as grandparent, parent, child with the Cost control level colours; click to open or close (remembered per project). Drag a row up or down to reorder among same-level siblings of the same parent (grandparents, parents, children); drag a pot across onto a line or group to assign. Tick pots (left) and lines or groups (right), or click a line to select it, then **Allocate by need / equally** (one dialog, editable amounts). Several pots can be dragged to one line in one go: each pot gives in proportion to what it has free (one ledger transfer per pot and line). Single pot to single line keeps the budget and risk dialog.
- **Send money back**: the arrow on a line (or drag the line onto a pot) opens a dialog listing the pots that line was funded from (from the ledger pairs), default the full amount funded; posts a transfer with ref RETURN.
- **Undo and Redo** in the top bar replace the Revert button: icon only, tooltip "Undo" or "Redo", greyed out when there is nothing to go back or forward to. Redo (`POST /redo`, `revert.redo`) applies the last reverted action again and ends when the user makes a new change (`revert_mark.rev_id`, migration added). Test in `tests/test_revert.py`.
- Reported by the user: clicking a + opened the amount window at once. Now selecting is separate from allocating; the amount window opens from Allocate or a drag.
- Claim schedule (and any `freeze2` table with a totals row at the top): the totals row's month cells now slide under the frozen Ref and Description cells instead of over them (`table.t.freeze2 thead tr.tot-top` z-index rules in app.css).
- Allocate window: "How to spread the funds" with five methods (in proportion to shortfall, biggest first, smallest first, equal capped at shortfall, typed); the last choice is remembered (`localStorage wsMode`). Selecting is a click on a pot or line (click again to deselect) and the **Allocate** button opens the window.

## Release 2026-10-25.99: Start, End, Mths on Allowances lines; claim line windows
- Allowances > Allowance: every line has Start, End and Mths (same window as Cost control: typed, from a duration, or following the project schedule; `POST /nodes/{id}/window`). If a typed start falls after the end the duration is kept and the end moves.
- Claim schedule: each claim line has Start, End, Mths and a link button. A window spreads the price not yet claimed evenly over the window's open months (this month onwards, never a claimed month), like cost to complete (`revenue.set_item_window`, `POST /contract/items/{id}/window`, new item method `window` in `revenue.plan_series`; a window that has passed puts the rest in the status month). Typing a month turns the line into typed months (manual) as before. The link opens a task picker (`/programme/tasks`, client facing tasks first): the line follows the earliest start and latest finish of its linked tasks; `programme.apply(targets=("claims",))` now prefers client facing (upstream) tasks, falls back to internal tasks (old behaviour, method even or lump) and runs after any schedule upload or task link change. Typing a window takes the line off the schedule. Tests in `tests/test_claim_grid.py`.

## Release 2026-10-25.100: month grids that keep the working columns in view
- Cost control with the monthly grid on: the table shows CBS, Name, Method, Start, Stop, Months, EAC and Contingency, all frozen beside the grid (the other figures show when the grid is off). Past and Future each have a mode: Months, Quarters (Australian FY quarters, Q1 is July to September; click a quarter to open its months, click the arrow on an opened month to fold it back) or Hidden. A month column can also be hidden on its own with the × in its header; a narrow ‹n marker stands in for hidden months and brings them back on click. The status month always shows. Settings are kept for the session (`ccui`). Shared helper `static/js/monthplan.js` (`buildPlan`, `monthInput`).
- Claim schedule: Ref, Description, Start, End, Mths and the schedule link are frozen (`table.t.fz6`); Price, Claimed, Scheduled and Not scheduled can be switched off ("Price and balances"); the same Past, Future, quarter and hide controls (`sgui`).
- Start, Stop and End fields are now short text month fields (Sep-26; accepts Sep-26, Sep 2026, 2026-09, 9/26) on Cost control, the claim schedule and the Allowances lines.
- Not built: the spread-by-drag grip is on the Allowance column, which the month view hides; switch the grid off to use it.

## Release 2026-10-25.102: lifecycle stages and delivery sub-phases with start, end and note
- PMO > Project phase and Project lifecycle: click any lifecycle tile (Handover, Setup, Delivery, Close Out, Warranty) or delivery tile (Design, Procure, Construct, Commission). A window takes Start, End (when it is over) and a Note. Clicking the current tile edits its record; any other tile starts a new record on the date given and ends the previous one that day. The tile that is current is highlighted and every tile shows its dates ("01/02/2026 to now").
- The delivery tiles are sub-phases of the Delivery stage (`gates.phase_add`, `gates.stage_add`): recording one puts the project in Delivery from the same date, so it cannot be in Setup and Commissioning at once; moving the project to another stage ends the open sub-phase. With the project in another stage the delivery row is shown muted with no sub-phase highlighted.
- New table `lifecycle_log` (stage, start, end, note, by; endpoints `/lifecycle-log`), and `phase_log.end_date` (migration). The stage worked out from the gates and phase is used until a stage has been recorded. The earlier 'lifecycle_stage' project setting from .101 was never released and is gone. Tests in `tests/test_revert.py`.

## Release 2026-10-25.103: Meetings under Communication
- Meetings moved from the PMO group to COMMUNICATION (after Communication matrix). Route `#/meetings` is unchanged, so links and shortcuts still work. Fix in the same release: `gates.LIFECYCLE_STAGES` (a name clash with the project stage list `gates.STAGES` broke recording a gate for Early Works).

## Release packaging (from .103)
- The zip holds the program only. The working notes (open questions, requirements prompt, UX review, issues register, design preview images) live in `pmt_notes/` beside the program folder, are not zipped, and are sent only when they change. HANDOFF.md and README.md stay in the zip: HANDOFF.md is updated every release (live state), README.md is read by the in-app guide.

## Release 2026-10-25.104: Allowances pane headers
- Each pane has one header line inside its scrolling list (title and column names together, sticky), so the columns line up with the rows. The name column has a 170 px minimum, Start and End are 62 px, Mths 30 px.

## Release 2026-10-25.105: Allowances columns shrink together
- When the splitter narrows the lines pane, every column shrinks in proportion (grid fractions with minimums, container query on the list): below 640 px the resource code under the name is hidden, below 480 px the Short column is dropped; header labels clip rather than overlap.

## Release 2026-10-25.106: Allowances panes in their own windows
- "New window: Both | Pots | Lines" on the Allowances workspace opens `#/risk?tab=allowance&solo=1&pane=both|left|right` in a pop-out (page header and tiles hidden, `body.ws-solo`). Pots and Lines windows each show one pane, with only the filters that belong to it.
- Windows of the same project share the selection and refresh each other through a `BroadcastChannel` (`pmt-ws:<pid>`): tick pots in one window and lines in the other, then press Allocate in either. A drag carries its payload as `application/x-pmt-ws`, so a pot can be dropped on a line (or a line on a pot to return money) in the other window of the same browser. Reordering stays within a window. Tested here: pop-out, one-pane layout, selection sync and Allocate across two windows. Not testable here: the native drag between two real browser windows (depends on the browser).

## Release 2026-10-25.107: quarters as foldable column groups (replaces the summary columns)
- Cost control (monthly grid) and the claim schedule: a quarter is a group of month columns like Excel grouping, not a summary column. The quarter name sits above its first month in the header; click it to fold the quarter (the months disappear, a narrow stub stays to open it) or open it again. By default quarters before the status month are folded, the status month always shows. Buttons: This quarter only, Open all, and ◂ ▸ to step the open quarters through the year (the one left behind folds, the next opens). A single month can still be hidden with × (the ‹n marker brings it back). State is `ui.qcol` / `sg.qcol` (the folded quarters); helpers `defaultCollapsed`, `stepQuarters`, `buildPlan` in `static/js/monthplan.js`. The earlier Past and Future selectors and quarter total columns are gone.

## Release 2026-10-26.108: issues register ISS-001, 002, 004 and 005 (part 1), and the quick UX items
Source: `PMT_Issues_Register_20261026.xlsx` (5 issues, ISS-003 not in this release) and `PMT_UX_review_24-10-2026.md` (checked against .107 first: #2 was already fixed in .86 and .100).
- **Ledger (ISS-002)** (`views/risk.js` `ledgerTab`, `GET /ledger?all=1`): rows in CBS order (PL, PS, PM, PE), shown as grandparent > parent > line with the Cost control level colours (orange, navy, light blue), fold and unfold per heading, Open all and Close all; the top levels are open on a first visit. The endpoint now returns `ord` (CBS position), `anc` (ancestors), `counter` (the other side of a transfer) and `edits`. A new column "Funded by / to" names the pot that funded a line (or the lines a pot funded); a line's heading summarises "Funded by ...". Edit and Delete require a reason (`ledger_edit` table: who, when, old, new, reason; `GET /ledger/{id}/edits`; History button when an entry has been corrected). Delete takes `?reason=`. Contingency and Risk cover columns show only when something in view uses them. Allowances > "See every move in the Ledger" opens `#/risk?tab=ledger&node=<ids>` for the selected lines or pots (the entries of those lines and the pots that funded them, opened and scrolled to; "Show the whole ledger" returns).
- **No blank flash, stay in place (ISS-004)** (`app.js` `render`): the page is built beside the old one (staged `<main class="viewbox staging">`) and swapped in one step, so the old page stays until the new one is ready. Window and table scroll positions are put back at once, and so is the keyboard focus (found by its position in the page, with the caret), so a person can update cell by cell. If a field has been typed in but not saved, the redraw is dropped (the field's own save redraws). Dialogs opened before the redraw are removed at the swap; dialogs the page opens while building survive. A newer redraw cancels an older one. `tabletools`, `tilelinks` and `tilelayout` return their run function and run on the new page before it is painted. Body gets class `busy` (progress cursor) while loading.
- **Tables (ISS-001)** (`tabletools.js`): every table gets "Columns" (hide and show, kept per table by heading text, works with spanned heading rows) and "Fit to screen" (columns to their content, spare width shared; done automatically below 1500 px when nothing was chosen and the table overflows). Grouped tables (rows with gp, par, par2) are no longer sortable (it scrambled the groups). New "Group by CBS": a flat table with a CBS code column (PL04.002) is nested under grandparent (PL, orange) and parent (PL04, navy) headings with subtotals and fold; default on from 8 rows, remembered per table (`pmt.tt.group`). Allowances lines pane: "Columns" (Start, End, Mths, Short) and the remaining columns share the room. Audit of 50 pages: only the claim schedule grid and the Forecast lines grid opt out (they keep their own month-grid tools); the Workflow and PMR pages hold descriptive tables with no tools.
- **Variations from the contract (ISS-005 part 1)** (`variations.placeholders_from_schedule`, `variation.schedule_item_id`): on every contract upload (claim schedule import and template, Payment Milestones template) each variation in the contract gets a register entry with its value, status mapped (approved: Approved and Agreed; pending: Pending; declined: Denied), and one empty price item for the cost build-up. The contract item keeps carrying the revenue, claims and plan; `variations.sync` then updates its status and value from the register instead of deleting it. Existing projects: Variations shows a banner "n variations in the contract have no register entry" with "Create register entries" (`GET|POST /variations/from-schedule`). An entry with the same ref or title is re-attached, not duplicated. Cost column shows "Build-up to be added". Not built (part 2, .112): variation pivot by CBS, client position register, branded Word and PDF proposal, register PDF.
- **UX review items done:** #1 (dates before the contract and legal fields, which sit in a folded "Contract and legal" block), #8 (the pools banner now explains why nothing can be moved and links to Allowances), #9 (the Project schedule page says "n of m cost lines follow the schedule" and lists the rest), #10 (a schedule upload no longer starts a setup draft), #11 (Pronto: the Load button is a sticky bar and the list scrolls into view), #12 (the Excel load leaves name, code, number, status date, start and end alone unless "Also update this project's name, code, number and dates" is ticked; blanks are filled), #13 (one "+ Add item", the whole-project Excel buttons only on steps with none of their own, Get started now lists the six setup steps), #14 (no developer wording on Meetings, Communication matrix, PMR and PSR), #16 (the empty claims page says Pronto holds n claims and why they are not turned into claims: a Pronto claim has no split by claim schedule item; it points to the claim schedule Overwrite and Reconcile), #17 ("Suggested" is "Catch-up to date" with a hover explanation), #18 (Forecast > Rates opens the rate card).
- Tests: 277 in all. `tests/test_release108.py` (ledger order, ancestors, funding side, reasons; placeholders and revenue unchanged; identity). `tests/test_revert.py` now sends a reason; `tests/test_template_undo.py` previews and applies with the identity box ticked and checks the default keeps the project's name. The preview warning (another project's file) now reads the file's own name, number and code (`templates_io._file_identity`), so it still warns when the identity is not applied. The full run found that one failure; it was fixed and its test files rerun (not a second full run).
- Checked in a browser against the demo project: ledger tree, funding, deep link from the Allowances workspace, edit dialog, Columns menus, Group by CBS, variation chip, setup layout, redraw keeps scroll, table scroll and focus with no empty moment.

## Release 2026-10-27.109: margin bridge and the accruals master list
Source: Vincent's findings of 27/10/2026 (dashboard tile; accruals register), with his answers (a), (b), (c).
- **Margin tile** (`reports.margin_bridge`, `GET /margin-bridge`, `static/js/marginbridge.js`): the label follows the sign: "Margin erosion" below the day-zero profit, "Margin uplift" above (dashboard, Portfolio, EOM report row). Clicking it opens the margin bridge: original profit, plus revenue added (recognised less original), minus the allowance added for it (full allowance less original estimate), plus the net of every line's over and underrun (budget less EAC), equals forecast profit. The last step is split into overruns and underruns by CBS line (biggest first, grouped by category in the table, click a line to open it on Cost control) and a row for what no cost line carries (pots and unplaced cost), so it always reconciles (`check` is 0). Tested to the cent on the demo project.
- **Accruals: All accruals tab** (`accruals.master`, `GET /accruals/master`, `masterList` in `views/accruals.js`): every accrual from every source in one filterable list, filter by source chip, by company or employee (a party), search, "Counting now only". The Register tab keeps its separate sections (Vincent: the headings stay). Sources: Your estimate (highest risk), Awaiting approval (invoice or claim received, reverses itself), Subcontract claim (from claims and their approvals, with claimed against approved), Finance journal (Pronto, read only), Unposted timesheet (hours, no rate yet; includes your own hours accruals). Columns: Source, Party, CBS, Line, Work month, Accrued, Counts now, PO, Quote, Invoice, Status, Detail. Subcontractor timesheets are a company's, not an employee's (resource kind). The same name in another case is one party; different wording ("Redgum Concrete" in a finance journal, "REDGUM CONCRETE AND STEEL" on an accrual) stays two. Payroll journals cover several people and are shown whole when an employee is chosen.
- **People behind a payroll accrual** (`accruals.timesheet_people`, `GET /accruals/people`): on the Register, a finance payroll row opens "Whose timesheets": the people with Pronto labour rows for the same cost category and work month, with hours, posted cost and the unposted hours and worth. Finance's journal names nobody, so this is a link by category and month, NOT confirmed on real Wandoan data (tested on the demo only): Vincent to check one real row. The dialog does not claim the journal equals the people's total (hours posted since month end were accrued and reversed).
- **Register changes:** PO, Quote and Invoice are separate columns on Your accruals; PO on finance's table; estimates carry a hint when an invoice has landed on the same line and PO or supplier since the work month (`accruals.estimate_hints`: "adjust or reverse this estimate"; estimates still never auto-match). Every edit or delete of your own accrual needs a reason (`change_reason` on POST, `?reason=` on DELETE); it is stored as `via` ("Reason: ...") on the change log, so it shows in the accrual's history and in CONTROL > Activity and history. Finance's Pronto rows stay read only (Vincent: Pronto data is changed in Pronto only; no override).
- Table tools: `table(..., {cls})` adds a class; class `nogroup` stops Group by CBS being on by default (used on the master list).
- Tests: `tests/test_release109.py` (bridge reconciles; reasons logged; master sources and parties; people and hints).

## Release 2026-10-27.110: the outline for month and day grids
Source: Vincent's finding on Cost control (hidden columns still took up room), his approval of the design mock-up (names only on hover; folded quarter versus hidden months told apart), and "implement the 1-2-3 buttons on all tables with month/day grids; cost control only has months and quarters so only 1-2".
- **Design** (`static/js/outline.js`, logic in `outlinecore.js`, CSS `.ol*`): a thin strip above the table, outside it, modelled on Excel's outline bar, Google Sheets' grouping and AG Grid's column groups. A **bracket with a minus** over each open group (quarter; month and week on day grids), named on the line, with "n hidden" when months inside it are hidden. A **ring +** stands alone where a whole group is folded (no bracket left); a **small filled dot +** sits on a quarter's bracket where single months are hidden inside it. Names show only on hover. Many neighbouring rings become one. "Show all" appears only while something is hidden. A hidden column or folded group takes **no width** (the old 46 px stubs are gone). Hiding every month of a quarter one by one reads as a folded quarter. The status month always shows. The strip is built from the real header cells (`th[data-col]`), clipped to the scrolling part (sticky columns are detected from computed style), follows horizontal scroll, and is rebuilt on resize.
- **Level buttons:** month grids have **1 2** (1 = this quarter only, 2 = every month); day grids **1 2 3** (1 = this week, 2 = this month, 3 = every day). Level n folds, at each depth, every group except the one holding the current column (`levelFolds`). On a day grid a week that straddles two months shows its days in the open month only.
- **State** (`outlineState(key)`, localStorage `pmt.outline`): folded groups (`"0:2027-Q1"`, level:key; null = the default, quarters before the status month) and hidden columns, per grid on this PC. `init: {folded: []}` opens a grid with everything open.
- **Grids converted:** Cost control month grid (key `cc`; its Quarters buttons are gone; × on a month header still hides one), claim schedule (`sg`), Forecast lines grid (`fl`), Forecast history and its per-line table (`fh1`, `fh2`), EOM report cashflow table (`eomcf`), subcontract claim sheet (`sub`), the cost-by-month window on Cost control (`mp`), and the **Labour calendar** day grid (`cal-w` for a window of weeks, `cal-p` for the whole project, 2 levels). On the calendar a folded month or week keeps one **summary column** (landed hours past, forecast future, both when it holds the status date), with the ring over it: that grid's totals are worth seeing, so it does not vanish (`summary: true`). The whole-project calendar opens with only the current month unfolded. The forecast item **day grid** (months as rows, days 1 to 31 as columns) folds its month rows by quarter instead (a quarter heading row, and 1 2 above the grid, key `pmt.dgfold`).
- Not month or day grids, so left alone: every other table (they have Columns, Fit to screen and Group by CBS from .108).
- Tests: `tests/test_outline.py` runs `outlinecore.js` in node (skipped when node is missing): quarters, what shows, the current column always shows, hidden months, the levels for months and days. The drawing was checked in a browser on the demo project (strip, rings, dots, level buttons, calendar window and project modes, claim schedule, history, EOM, month window, day grid).
- Known: the dayGrid keeps its own row folding rather than the strip; the Forecast lines grid is due to be replaced by the Ground-Up register.

## Decisions recorded (Vincent, 26/10/2026)
- Table headers stay as they are: navy header rows, grandparent rows with an orange marker, parent rows with a navy marker (version A of the comparison). The restyle leaves tables alone apart from spacing and hover.
- Sidebar stays navy but quieter (sentence case, rounded selected item). The restyle is its own release.
- #20: the forecast can be changed in three places only: the Cost control row (rule methods), the claim schedule (CLAIM) and the Ground-Up register (GROUND-UP). When the Ground-Up register exists the method pickers in the line drawer, the forecast window and on Forecast lines are retired.
- Variations: when a contract is uploaded, at least the register placeholders are created for the user to add the cost breakdown to.

## Plan (agreed 26/10/2026 and 27/10/2026, order can change)
1. (Done in .111, see Release .111) Design release: the quiet look of the header bar across the app (page headers, tiles with no coloured top border, two button styles, one-line filter bars, consistent tabs, soft dialogs with fades, quieter sidebar). Tables keep the current look (version A). Before and after screenshots of the pages at 1600 and 1280 px.
2. (Done in .112, see Release .112) Larger UX items: #3 one Month-end page, #4 Allowance as a setup step, #5 and #6 initialise checklist and "what next" card, #7 multi-select and empty buckets on Setup > Allowance, #15 close-out checklist.
3. (Done in .113, see Release .113) Ground-Up register (ISS-003 part 1) and retiring the other method pickers (#20). Still open from the Ground-Up requirements: import the PMT workbook's Ground-Up sheet (about 240 lines) as test data, a day-grid view of the register for rosters, and linking supplier milestones to project schedule items.
4. .114 Ground-Up Excel import template (ISS-003 part 2) and the variation engine overview and exports (ISS-005 part 2).
Still open: folded quarters taking no width (below), team and lead accountability, full pivot on the Ledger tile.

## Next for the new session (raised by Vincent, not built)
- (Done in .110) Folded quarters take no width: see Release .110.
- Still open from before: team and lead accountability (design in "Design agreed with Vincent"), full pivot on the Ledger tile. The Ground-Up register and the remaining UX review items are in the Plan above.
- Working agreement: batch findings, confirm the plan, wait for "go", one build and one test run per batch, zip only on request.

## Release 2026-10-27.111: quiet design restyle
- `static/css/design.css` is loaded after `app.css` and only overrides; delete the link in `static/index.html` to go back. Tokens: radius 8/12/14 px, hairline #e6eaed, field border #d3dbde, soft shadows.
- Kept as agreed: table header rows navy, orange grandparent marker, navy parent marker; month and day grid workbook colours; sidebar navy but quieter (sentence-case group names, rounded selected item).
- `ui.filterMenu(label, items, count)`: one Filters button with a count badge and a popover; used for the problem chips on Cost control and the method chips on Forecast lines.
- `app.js render()`: a `.pagehead .sub` over 130 characters is clamped to one line and opens on hover.
- Dashboard margin tile subtitle shortened. Checked by screenshot at 1600 and 1280 px on the demo project (12 pages), plus a drawer, a dialog and the Filters popover. Not checked: other browsers, print views, real project data.

## Release 2026-10-27.112: set-up and routine checklists (UX items #3, #4, #5, #6, #7, #15)
- `app/checklists.py` reads the project's own data; items are `{key, title, state (done|todo|warn|info), detail, page, params, manual}`. Endpoints: `GET /preflight`, `GET /month-end`, `GET /close-out`, `POST /close-out/tick` (manual items only, kept in the project settings as `closeout_checks`), `POST /allowance/link-many`.
- #4 and #5: Project setup has seven steps; step 6 is Allowance (the Allowance page body, `allowanceBody()`, resources first, buckets after). Initialise lists the pre-flight (resources not linked, cost parked on pools, lines not on the schedule, default methods) and the button is enabled only after "I have read the items above". The Setup menu entry Allowance opens the step; the old `allowance` page still works.
- #6: after Initialise the dashboard shows a "What next" card (link resources, allocate pools, check methods, close the first month) until the first month is closed or it is dismissed (per project, in localStorage).
- #7: buckets with nothing held and nothing parked are hidden (a tick shows them); resources can be multi-selected and covered in one action (option 2, "cover cost so far"); the bucket is the one suggested from the resource's category. In bulk only options 1 and 2 are allowed, rows that cannot be linked are listed.
- #3: menu group MONTH-END (Month-end, Review lines, Snapshots and history, EOM report). The Month-end page checks Pronto (transactions and labour reach the status month), accruals, review decisions and the close, and has the Close month button. The old Month-end history page is "Snapshots and history"; Forecast no longer holds the review.
- #15: Close-out checklist: claims paid, retention recorded, subcontracts closed and retention held, variations settled, open accruals, current gate (read from PMT); defects liability period, Gate 7 paper, handover documents, lessons and archive are ticked by hand. EPEC's gates stop at 7 in PMT (no Gate 8). The estimator lessons stay below.
- A menu group that a saved menu order does not know (MONTH-END) is placed after the group before it in the standard menu.
- Not checked: real Wandoan data; the client retention figure only sums the per-claim retention field.

## Release 2026-10-27.113: Ground-Up register and one place per method (ISS-003 part 1, #20)
- `app/groundup.py`, `GET /groundup` (every forecast item with its CBS line, who, kind, window, months from the status month and a total; `live` = its line forecasts by GROUND-UP), `POST /groundup/group` (ids, h1, h2, h3), `POST /groundup/rename`. `forecast_item.h1/h2/h3` are labels only: no figure moves, the engine is unchanged. A blank H1 clears all three; H3 cannot exist without H2.
- `views/groundup.js` (menu FORECAST > Ground-Up register): a tree H1 > H2 > H3 with a Not grouped block last, month columns with the outline strip (key `gu`), tick items and put them in a group, rename a group, a By CBS line view, search, Counted only. A row opens the line editor on that item (`forecast?node=&item=`); Add an item picks a CBS line and opens the same editor.
- #20: the method is no longer picked on Forecast lines (badge is read-only; `methodDialog` removed), in the Forecast line editor (shows the method; keeps line start and end, top-down EAC and still-to-commit; a "Build this line ground-up" button for lines on another method), in the Cost control line drawer (shows the method; keeps the inputs of TOP-DOWN and AT-COMMIT) or in the month forecast window (the other methods are "compare only"). It is changed on the Cost control row, on the claim schedule (CLAIM) and by building a line ground-up. Kept on purpose: the group drawer's "set one method for every line below" and the pools NONE button on Cost control.
- Bug fixed: `main.py` had two `ITEM_COLS`; the variation one (defined later) shadowed the forecast item one, so `POST /nodes/{id}/items` and the item preview dropped fields such as quantity, rate and dates. The forecast one is now `FORECAST_ITEM_COLS`. Test: `test_saving_a_forecast_item_keeps_every_field`.
- Not built yet: the PMT workbook Ground-Up import, the Excel import template (.114), a horizontal day-grid or roster view inside the register, linking supplier milestones to schedule items from the register.

- Stale scripts: after an update the browser kept the old `static/js` files (the menu showed the new release number but not the new pages). `/` and `/static/*` now answer `Cache-Control: no-cache` (revalidated each load, 304 when unchanged). One hard refresh (Ctrl+F5) is still needed once on a PC that cached the old scripts.

## Release 2026-10-29.114: project complexity (first of four: .114 complexity, .115 team and fit, .116 team changes, risk and director view, .117 competency by dimension)
- Source: Vincent's EPEC Project Complexity Matrix workbook (sheets Scoring Tool, Complexity Matrix, Project Resourcing Requirement) and the two resourcing papers (Stratford Solar Farm, Smokey Creek). Ten dimensions scored 0 to 5; total 0 to 50; band C1 up to 15, C2 up to 25, C3 up to 35, C4 above. `app/complexity.py` holds the dimensions, bands and the rules.
- Two readings kept apart. `cx_baseline` (new table): the project director's score, every revision kept, the latest current; it sets `project.complexity` (the 1 to 5 number the workload page and client challenge still use: 1 to 10 points = 1, up to 20 = 2, 30 = 3, 40 = 4, above = 5). `assessment` gained `scores_json`, `total`, `band`: the PM's monthly score, one per month, with the client's difficulty. With no baseline the latest assessment still sets `project.complexity` (the old behaviour).
- Who sees what (a view, not a lock: PMT does not sign anyone in). `GET /complexity` returns the baseline, revisions and the comparison only when the profile role matches director, general manager, operations manager or PMO; any other role gets only the assessments. Only those roles can `PUT /complexity/baseline`. The Activity list hides `cx_baseline` rows from other roles. Not hidden: someone who changes their profile role, or opens the database file. `change_log` must keep logging `cx_baseline` because it is how PCs share changes.
- Pages: Setup > Project complexity (director: Baseline, PM's monthly assessments against the baseline with a by-dimension table, Add a monthly assessment; PM: the monthly form with last month's scores as the start, their own history), a radar "Complexity Profile" like the framework's chart (0 to 5, ten axes) beside the scorer, baseline against PM on the PM tab, and on the PMR page (the PM's own latest). Director dashboard: a Project complexity card (baseline, PM's latest, difference, client difficulty trend). Month-end checklist has the step "Assess the project's complexity and the client's difficulty". The old one-number dialog redirects to the page for the open project (it remains for other projects from the Portfolio).
- PM levels now run 1 to 5: Level 4 is senior PM / program manager, Level 5 project director (new directors default to 5; existing directors stored as 4 keep 4 until re-rated). `workload.BAND_LEVEL` = C1 L1, C2 L2, C3 L4, C4 L5 decides the level a project needs once it has a baseline (`REQUIRED_LEVEL` is the fallback). Capacity for Level 5 equals what Level 4 had.
- Source document points to settle with Vincent: Stratford's stakeholder score is missing (the other nine total 25); both papers still carry Lower Wonga template text; names are spelt several ways; the workbook's Scoring Tool holds placeholder 1s.
- Not built yet: the Project team page, people with role levels, fit and risk (.115, .116), the Word resourcing paper export, competency by dimension (.117). The Ground-Up register rebuild and the Excel template stay parked.

## Release 2026-10-29.115: project team and fit
- `app/team.py`: the Project Resourcing Requirement table (`REQ`: seven roles by band, with shared / if applicable / not required modes and the one mandatory role, the Senior / Lead PE at C3), `fit` per role, `risk`. Tables `person_role` (levels 1 to 4 by role; the PM level stays `person.pm_level`, 1 to 5) and `team_slot` (project, role, person, status Selected / Recruitment / To be confirmed, in post from / until, note). The PM and the director are the project's own fields (`epec_pm`, `project_director`), edited on Project setup.
- Endpoints: `GET /project-team`, `PUT /project-team/slots` (name a person, status, dates, their level for the role; a new name is added to the employees), `DELETE /project-team/slots/{id}`, `GET /api/people/template.xlsx` (blank people sheet; the import is a placeholder button), `role_levels` on `/api/people`.
- Levels for the six non-PM roles read like the requirement columns (1 = the C1 wording to 4 = the C4 wording), so a Senior / Lead PE is level 3. They are set on the person card (Stakeholders > Employees, Competency by role) or in the Add a team member dialog.
- Fit per role: meets, above, below, vacant, unrated, not required, or no band yet. A person counts only when status is Selected and today (the status date) is inside their in-post dates, so a leaver with an end date stops counting after it.
- Risk (first rule, Vincent 29/10/2026): Red if the PM or a mandatory role is vacant, below or unrated, or the PM's latest complexity assessment is in a higher band than the baseline; Amber for another dedicated role that is vacant, below or unrated; Green otherwise; shared and "if applicable" roles are not gaps when empty. Not rated without a baseline.
- The Project team page (Setup menu) shows the requirement band, the rating with reasons, an SVG team chart (director, PM, then the roles; a box is coloured by fit) and a role-by-role table. It is visible to every role: the band and what each role asks for are the resourcing requirement (as in the signed resourcing paper), but the director's dimension scores and notes stay hidden from the PM.
- Not yet: the forward look (a leaver creates a gap in a coming month), joiners and leavers recorded at month-end, the director's projects-against-roles view, the Word resourcing paper (all .116); competency by dimension (.117); the people import once the list exists.

## Release 2026-10-30.116: team changes, looking ahead, director view and the Word paper
- `team.ahead()`: the team's rating for the status month and the next six, each judged on the 15th (a person counts in a month when in post that day, so a leaver on the 10th is gone for that month). `first_gap` is the first month with a problem the team does not have today. Joiners and leavers are the in-post dates on a team member (Project team page); there is no separate movements table.
- `team_review` (new table) and `PUT /project-team/review`: the PM confirms the team for the month with a note; the rating at that moment is kept. Month-end checklist has the step "Confirm the team" (done once confirmed; Amber and Red show as a warning).
- `GET /api/team/fit?director=`: every running project with its band, rating, first gap and each role's fit; shown on Team > Team fit (project directors), worst first, click a project to open its team.
- `app/resourcing_paper.py` and `GET /project-team/paper.docx` (director roles only): the Project Resourcing paper in the layout of the Stratford Solar Farm and Smokey Creek papers: 1 Project Complexity Score (the director's scores and comments), 2 Complexity Profile (radar drawn with Pillow), 3 Project Resourcing Basis (the requirement table, the project's band marked), 4 Project Resourcing Requirements (selection and fit), 5 Summary (band, rating, reasons, first gap), 6 Authorisation and Approval blocks. EPEC brand: navy header band and table headers, orange title and top-level headings, gold secondary line and page number, pale grey banding with slate text, Mulish (Word substitutes if it is not installed). Needs `python-docx` (now in requirements.txt): on an existing install run `pip install python-docx`; without it the button explains that. Checked by rendering the file through LibreOffice; not opened in Word.
- Authorisation names other than the project director are left blank for signature. The summary text is generated from the data (no free text).
- Not yet: competency by dimension (.117); the people import (waiting for the list); a monthly history chart of the team rating.

## Release 2026-10-30.117: EPEC Classification Framework in the team
- Source: EPEC Classification Framework EPEC-HR-FW-0001_0 (inside the document EPEC-GR-FW-0001_0; to be corrected by HR), revision 0, published 01/10/2026, approved by the COO. Levelling table page 5, profiles pages 6 to 46, allowable titles under each family, definitions page 52 (all business titles need HR approval). Seven families in PMT: Management, Engineering, Design (the framework's Design column inside Engineering), Modelling, Project Management, Technicians, Drafting.
- `app/ecf.py` seeds table `ecf_role` (role key, family, level from / to, allowable titles, profile) at start-up and holds the rules; `GET /api/ecf`; `PUT /api/ecf/roles/{key}` lets HR revise a role's levels and titles (Classification framework page, PMO menu). The seeded `ecf_role` is in `changelog.NOT_LOGGED` (every PC seeds the same rows; logging them broke sharing, found by `test_sync`); HR's revisions are stored in `ecf_edit`, which is logged and shared like other changes. Profiles are loaded for the roles used on project teams (Project Management family, Engineering and Design roles, Construction Manager, Supervisor, Technician), copied from the framework's profile tables; the other roles show a note. Cadet Modeller has no level in the levelling table, so none is made up. The Senior Construction Manager is level 8 as Vincent said (it is in the Technicians titles with a blank profile, not in the levelling table): HR should confirm.
- `person` gained `ecf_role`, `ecf_level` (a role that spans two levels, Design Manager 6 to 7 and Project Support 4 to 5, takes the person's level) and `business_title`. A title not on the allowed list is kept and shown as such. The person card has a Classification section; Employees shows it; the people template has ECF role, level and title columns and an "ECF roles" sheet.
- In the team: a person's level for a team role is the level set on them if there is one, otherwise it is read from the classification (Vincent confirmed 28/10/2026): Project Engineer and Test & Commissioning from the Engineering family (level 3 and below = 1, 4 = 2, 5 to 6 = 3, 7 and above = 4); Design Manager from Engineering or Design (5 and below = 1, 6 = 2, 7 = 3, 8 and above = 4); Construction Manager from Technicians (Supervisor 5 to 6 = 1, Construction Manager 7 = 2, Senior Construction Manager 8 = 3); Project Controls and Coordinator from Project Support (3 = 1, 4 to 5 = 2). Nothing is guessed across families: no matching rule leaves the level "not recorded". Test & Commissioning using the Engineering rule is an assumption (Vincent confirmed the table, which did not list it). The PM level suggestion: Project Director (8) = PM Level 5, Senior Project Manager (7) = Level 4 (used when no PM level is set); a Project Manager (6) is set per person. The team table, chart and the Word paper show the classification; the table says "(from the classification)".
- Not done: classification of Controls Lead / cost controller (the framework has no such title: Project Scheduler sits under Project Support); HR items listed above; competency by dimension (.118).

## Release 2026-10-30.118: PM competency by dimension
- `complexity.MATRIX_LEVELS`: the PM level (lowest, highest) the workbook's Complexity Matrix writes for each dimension in each band (for example Cost: C1 L1-2, C2 L3, C3 L4, C4 L4-5; Contracting C3 L3-4; Scope names no level at C1 and C4). `dimension_band(score)`: a dimension's 0 to 5 score points to a band at the averages behind the total's limits (1 or less C1, 2 C2, 3 C3, 4 or 5 C4). That mapping is mine: the workbook does not define a band for one dimension, so Vincent should confirm it.
- `person_dimension` (new table): a person's level 1 to 5 per dimension, set on the person card ("Competency by dimension (for project managers)"); unset, the overall PM level (set, or from the ECF Project Director / Senior Project Manager classification) is used and shown as "(overall)".
- `team.competency(con, pid)` and `GET /p/{pid}/pm-competency`: for each dimension, the baseline's score and band, the level asked, the PM's level and source, and the fit (meets, above, below, no level, matrix names no level). The minimum is the lowest level of the range. It is returned only to director roles: it shows the director's dimension scores (the PM must not see them). It does not change the team rating (that would make the rating differ by who looks).
- The Project team page has a card for directors with the table and a radar (asked, lowest level, against the PM); Team > Team fit shows "Below in N dimensions" under the PM.
- Not done: competency by dimension for roles other than the PM (the matrix describes PM expectations only); a history of a PM's dimension levels.

## Decisions from Vincent (31/10/2026), team section and objects, not yet built
- Who sees the director's baseline and the PM's view: Project Director and above. The Senior PM or PM must make their own assessment each month without seeing the director's baseline or current assessment (already so). Fix pending: the `complexity.DIRECTOR` pattern (director, general manager, operations manager, pmo) misses Head of Delivery, Head of Project Management, Head of Project Engineering, COO and the Executive Directors, and "pmo" is not "Project Director and above".
- A Project Director is ECF level 8 (the framework also lists Project Director as a Business Unit Manager title at level 9; Vincent: treat it as 8). The mapping of ECF level to team seniority stays as confirmed; where the papers pick someone the mapping rates below, the app flags it (no softening).
- Load the people from the epec-knowledge-base skill's org chart (17/08/26 plus the 21/10/2026 changes): names, titles and reporting lines only; not the contact list's phones and emails unless Vincent asks.
- Everything is an object with properties: clients, people (client and EPEC employees, subcontractor people), companies, projects. An EPEC employee: role, ECF level, job family, competency levels, work rate, pay band level, Pronto resource code, home address, email, phone, age. Pay band, age and home address are personal data: PMT has no sign-in and the database file is readable by anyone with the shared folder, so they wait for the role-based access design (and HR / IT agreement).
- A development session is planned to define what the app shows to which role: the app experience should differ by the user's role.
- Vincent, 31/10/2026 (second reply): the PM competency level (PM Level 1 to 5, EPEC-PM-FW-0002) and the ECF classification level (which ties to the pay band) are two different levels and both are right. So the PM level is not derived from the ECF role or title: the suggestion built in .117 (Project Director = 5, Senior Project Manager = 4) is to be removed, and a PM level is set per person. The ECF level still drives the seniority of the other team roles (the mapping he confirmed on 28/10/2026). Age is not a property of an employee object (removed from the list).

## Release 2026-10-31.119: people as objects, leavers, org chart, My profile
- Baseline visibility: `complexity.DIRECTOR` (and `isDirector()` in `app.js`) = director, general manager, operations manager, head of, chief, COO, executive, chair; PMO is no longer included. The profile role list has Head of Project Management, Head of Project Engineering, Head of Delivery, General Manager Projects, Chief Operating Officer and Executive Director.
- The PM level (competency) is no longer derived from the ECF classification (removed `ecf.pm_level_suggestion`; the ECF level ties to pay band and is a different level). A PM level is set per person; a PM with none is "level not recorded" on the team page.
- `person` gained `leaving_date`, `employment_status` (active, serving notice, left), `engagement` (employee, contractor, secondment) and `aliases_json`. A leaving date ends every project role the person holds (and the PM role if they are the PM): `team.team()` takes the earlier of the slot's end date and the person's last day. A person serving notice with no last day is an Amber reason ("last day is not recorded"). `GET /api/people/{id}/impact` and `GET /api/team/leavers` list the projects affected, the rating now and the first month it gets worse; the person card shows it and Team > Team fit has a Leavers card.
- Org chart: `app/people_seed.py` holds 187 people from the epec-knowledge-base chart (17/08/26 with the 21/10/2026 changes): names, business titles, reporting lines, group, engagement, serving notice. `org_load.py`: `GET /api/people/org-chart` previews (nothing written; lists possible duplicates, titles to review with HR (59 on the first count), people with no title, ECF roles taken from a grade word, ranged roles whose level is not stated, serving notice, contractors), `POST` loads (only blank fields of an existing person are filled; no PM level, no individual ECF level, no contact details; people who have left are not loaded). The business title picks the ECF role (a Project Director title goes to the Project Director role, level 8, before Business Unit Manager). Reporting lines for Finance, Legal, IT, HSE and People & Culture are left blank (interim lines not stated); the Projects lines are the pre-restructure ones.
- Names: `org_load.similar()` (same surname within one letter or contained, first names one another's start or one letter apart: Brad / Bradley, Thomson / Thompson, Larissa / Larrissa), `GET /api/people/duplicates`, `POST /api/people/merge` (the dropped name becomes another spelling; roles, levels, team entries, project fields and reports-to move across). `directory.add` and the team's person lookup find a person by an old spelling.
- Paper sign-off: `resourcing_paper.signoff()` / `save_signoff()` per project (`settings_json.paper`), `GET/PUT /project-team/signoff`, dialog on the Project team page. Authorisers default to the project director, the project's Design Manager (or the person titled Design Manager), the person titled Operations Manager (Projects) and the Substation Commissioning Manager (else Head of Commissioning). The approver defaults to "General Manager Project" with no name and is meant to be set per project (GM Projects is vacant): not assumed.
- Data objects: `app/objects.py` (five object types, each property with where it is held, sensitivity and status), `GET /api/objects`, page Control > Data objects. Age is not a property. Pay band and home address are listed as deferred and restricted: not stored until the role-based access design exists.
- My profile: `GET/PUT /api/me/record`, page Control > My profile. The signed-in person's own employee record by profile name: what they may see (hidden: aliases, work rate, pay band, per-dimension competency; counted, not shown), what they can change (phone, home base, and home address once it is held), the rest view only. Access per property is `objects.SELF`, a first proposal for the role-based design session. It is a view, not a lock: PMT has no sign-in.
- Open: the role-based experience session (what each role sees and edits, for example a PM sees only the PM view and his own profile, a director the director view); a company org chart page; allocation across projects; support roles and contacts per project; vacancies; the 21/10/2026 interim reporting lines once known; HR to review the titles not on the allowed list.
