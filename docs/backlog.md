# Backlog

One row per item. Seeded on 31/10/2026 from the open items in `docs/threads.md`, `docs/release-log.md`, `docs/designs.md`
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

Also waiting on Vincent rather than on a build (see the Next step lines in `docs/threads.md`): trying releases on real Wandoan data,
a real subcontract template and timesheet, a real Pronto GL export, a PMR and PSR sample, and the Copilot Studio agent decision (thread 13).
