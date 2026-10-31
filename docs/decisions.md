# Decisions (do not re-open without Vincent)

Moved from HANDOFF.md unchanged. Every session reads this file. New decisions go at the end with the date.

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
- D15. (Vincent 16/10) No restrictions by role. Instead a full audit trail: who did what, when, old and new value. Superseded 31/10/2026 by M14 in docs/specs/00-purpose-and-decisions.md; the audit trail stays.
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


## Decisions recorded (Vincent, 26/10/2026)
- Table headers stay as they are: navy header rows, grandparent rows with an orange marker, parent rows with a navy marker (version A of the comparison). The restyle leaves tables alone apart from spacing and hover.
- Sidebar stays navy but quieter (sentence case, rounded selected item). The restyle is its own release.
- #20: the forecast can be changed in three places only: the Cost control row (rule methods), the claim schedule (CLAIM) and the Ground-Up register (GROUND-UP). When the Ground-Up register exists the method pickers in the line drawer, the forecast window and on Forecast lines are retired.
- Variations: when a contract is uploaded, at least the register placeholders are created for the user to add the cost breakdown to.


## Decisions from Vincent (31/10/2026), team section and objects, not yet built
- Who sees the director's baseline and the PM's view: Project Director and above. The Senior PM or PM must make their own assessment each month without seeing the director's baseline or current assessment (already so). Fix pending: the `complexity.DIRECTOR` pattern (director, general manager, operations manager, pmo) misses Head of Delivery, Head of Project Management, Head of Project Engineering, COO and the Executive Directors, and "pmo" is not "Project Director and above".
- A Project Director is ECF level 8 (the framework also lists Project Director as a Business Unit Manager title at level 9; Vincent: treat it as 8). The mapping of ECF level to team seniority stays as confirmed; where the papers pick someone the mapping rates below, the app flags it (no softening).
- Load the people from the epec-knowledge-base skill's org chart (17/08/26 plus the 21/10/2026 changes): names, titles and reporting lines only; not the contact list's phones and emails unless Vincent asks.
- Everything is an object with properties: clients, people (client and EPEC employees, subcontractor people), companies, projects. An EPEC employee: role, ECF level, job family, competency levels, work rate, pay band level, Pronto resource code, home address, email, phone, age. Pay band, age and home address are personal data: PMT has no sign-in and the database file is readable by anyone with the shared folder, so they wait for the role-based access design (and HR / IT agreement).
- A development session is planned to define what the app shows to which role: the app experience should differ by the user's role.
- Vincent, 31/10/2026 (second reply): the PM competency level (PM Level 1 to 5, EPEC-PM-FW-0002) and the ECF classification level (which ties to the pay band) are two different levels and both are right. So the PM level is not derived from the ECF role or title: the suggestion built in .117 (Project Director = 5, Senior Project Manager = 4) is to be removed, and a PM level is set per person. The ECF level still drives the seniority of the other team roles (the mapping he confirmed on 28/10/2026). Age is not a property of an employee object (removed from the list).
