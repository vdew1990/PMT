# Backlog

One row per item. Seeded on 30/10/2026 from the open items in `docs/threads.md`, `docs/release-log.md`, `docs/designs.md`
and `docs/decisions.md`; nothing here is new scope. Source column says where the wording came from, so check it before building.
Stage: Idea, Spec, Design agreed, Build, Test, Review, Done. Items marked "check" had a planned release whose outcome is not stated in the handoff.

Priority is blank on purpose: Vincent sets it. Keep this table in step with the Notion board if one is used.

| ID | Item | Area | Stage | Depends on | Source |
|---|---|---|---|---|---|
| B-01 | Team and lead accountability: team tagging and home team, legal entity and owning team on the project, team chip bar on Cost control, COO Teams page | Setup and Team | Design agreed | none | designs.md, "Design agreed with Vincent (24/10/2026)" |
| B-02 | Role-based experience: what each role sees and edits (PM sees the PM view and own profile, director the director view); PMT has no sign-in today | Platform | Idea | B-12 | decisions.md (31/10/2026); release-log .119 "Open" |
| B-03 | Personal data held for people (pay band, home address, age): wait for B-02 and HR / IT agreement | Platform | Idea | B-02 | decisions.md (31/10/2026) |
| B-04 | Ledger tile: full pivot (today only per line and by date views) | Cost | Idea | none | release-log .93 "Known gaps" |
| B-05 | Allowances: drag a line allowance back to its pot | Cost | Idea | none | release-log .93 "Known gaps" |
| B-06 | Ground-Up: import the PMT workbook's Ground-Up sheet (about 240 lines) as test data; Excel import template (ISS-003 part 2); check status, planned for .114 | Forecast | Idea (check) | none | designs.md "Plan" item 3 and 4 |
| B-07 | Ground-Up: day-grid view of the register for rosters; link supplier milestones to project schedule items | Forecast | Idea | B-06 | designs.md "Plan" item 3 |
| B-08 | Variation engine overview and exports (ISS-005 part 2); check status, planned for .114 | Revenue | Idea (check) | none | designs.md "Plan" item 4 |
| B-09 | Forecast status month: should forecast start the month after the status month at a month-end status date? | Cost | Needs decision | none | open-questions.md, question 2 |
| B-10 | Claim schedule: fill-right or copy a value to several months; undo for the last grid edit; import historical issued claims with the claim schedule | Revenue | Idea | none | threads.md, thread 29 |
| B-11 | Subcontract timesheets: show NT/OT on posted Pronto timesheets (needs Pronto work rate codes for overtime); list view of uploaded subby timesheets | Cost | Idea | Pronto codes | threads.md, thread 4 |
| B-12 | Platform: journal compaction (snapshot and high-water mark); verified Entra sign-in (MSAL) if IT registers an app; test on a real SharePoint library | Platform | Idea | IT | threads.md, thread 1 |
| B-13 | Forecast: copy supplier rates and holidays when cloning a project; Excel import of supplier rates and of a Ground-Up day grid; per-role permissions (for example only the PM reverses accruals) | Forecast | Idea | B-02 for permissions | threads.md, thread 2 |
| B-14 | Reporting: cashflow on payment terms (cash in and cash out) instead of the earned basis | Reporting | Idea | none | threads.md, thread 5 |
| B-15 | Linked projects: CBS merge mapping for differently coded CBS between projects; parent carries its own EOM report | Setup and Team | Needs decision | none | threads.md, thread 27 |
| B-16 | Tables stretching to the window height (possible follow-up) | Platform | Idea | none | threads.md, thread 26 |
| B-17 | People: company org chart page, allocation across projects, support roles and contacts per project, vacancies, 21/10/2026 interim reporting lines, HR review of titles not on the allowed list | Setup and Team | Idea | HR | release-log .119 "Open" |
| B-18 | Ground-Up Excel and role leads: leads for Commissioning (Engineering) and Engineering; hours per line or dollars only; sample R01/R02 and BoP SCADA CBS | Setup and Team | Needs decision | B-01 | designs.md, "Open" under the teams design |
| B-19 | Schema version (PRAGMA user_version) and numbered migration runner; existing additive MIGRATIONS list kept as step 1; old-database test | Platform | Spec | none | team/neo.md (Guardrails); decisions.md, D3, D4 |
| B-20 | Sync gate: warn when replicas are on different schema levels (Vincent decided warn first; refusing is a later decision for Vincent if a warning proves not enough); Neo writes a design note first, including what the warning says and what is blocked, if anything; includes a check at start-up and on a timer of a version marker in the shared folder, which tells the user a newer release exists (detect and tell: wait for OneDrive to finish syncing, then restart); no self-update and no download from the internet; Neo costs it in the design note | Platform | Spec | B-19, B-21 | team/neo.md (Guardrails); decisions.md, D3, D4 |
| B-21 | Make app VERSION follow the release number (app/__init__.py says 2026.10.16 against bundle 2026-10-31.121); decide how it is set at release | Platform | Spec | none | app/__init__.py (VERSION); decisions.md, D4 |
| B-22 | Finance rulings: rounding basis for claims, invoices and certificates; retention rounding; remainder policy and who absorbs cents; basis of approved variation value; tolerances (0.005, $1, $1,000, 0.05%); month-end tolerance against Pronto and CMT. Owner for now: Vincent; routed to a finance owner once Vincent names one; statutory claim arithmetic to Legal | Cost | Needs decision | none | decisions.md, D19, D23, D26; release-log.md (assign dialog tolerance entry) |
| B-23 | Rounding and allocation policy through one money module (one rounding function in Python and JavaScript tested to agree; one remainder helper); first uses: revenue, variation and allowance spreads; touches several lanes | Platform | Idea | B-22 | decisions.md, D19, D23, D26; threads.md, thread 29 |
| B-24 | Conditional: revisit integer cents or Decimal only if a trigger fires (real month-end evidence that float causes the differences, or B-12 compaction proceeds) | Platform | Idea | B-19, B-20, B-23, B-12 | decisions.md, D3, D4, D15; threads.md, thread 1 |

Also waiting on Vincent rather than on a build (see the Next step lines in `docs/threads.md`): trying releases on real Wandoan data,
a real subcontract template and timesheet, a real Pronto GL export, a PMR and PSR sample, and the Copilot Studio agent decision (thread 13).
