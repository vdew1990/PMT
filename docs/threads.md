# Threads 1 to 32 (moved from HANDOFF.md unchanged, 2026-10-31)

Historical status of each build thread. New work is tracked in `docs/backlog.md`; add a line here only when a thread's status changes.

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
