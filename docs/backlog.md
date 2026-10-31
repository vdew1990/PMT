# Backlog

One row per item. Seeded on 30/10/2026 from the open items in `docs/threads.md`, `docs/release-log.md`, `docs/designs.md`
and `docs/decisions.md`; nothing here is new scope. Source column says where the wording came from, so check it before building.
Stage: Idea, Spec, Design agreed, Build, Test, Review, Done, plus three more: "Needs decision" (waiting on a decision from Vincent before work can proceed), "Idea (check)" (an Idea whose planned release has an outcome not stated in the handoff; check before building) and "Test (failed)" (the latest Onyx verdict is Fail; the item returns to Test when the owner hands over a new commit with a fresh test brief note).

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
| B-19 | S1: Pronto tie-out and CMT replacement (spec) | Cost | Spec | none | docs/specs/00-purpose-and-decisions.md |
| B-31 | S1b: CMT-format export (interim bridge) (spec) | Cost | Spec | B-19 | docs/specs/01b-cmt-format-export.md |
| B-32 | S1c: CMT import for mid-project moves (spec) | Cost | Spec | B-19 | docs/specs/01c-cmt-import.md |
| B-20 | S2 Remove manual data handling: The list of manual steps today and how PMT removes each. | Cost | Spec | none | docs/specs/00-purpose-and-decisions.md |
| B-21 | S3 Month-end close flow: Pronto load and check, reforecast, accruals, in a measurable time. | Cost | Spec | none | docs/specs/00-purpose-and-decisions.md |
| B-22 | S4 Claims and variations | Revenue | Spec | none | docs/specs/00-purpose-and-decisions.md |
| B-23 | S5 Risk and allowances | Cost | Spec | none | docs/specs/00-purpose-and-decisions.md |
| B-24 | S6 Reports: EOM, then PMR, PSR. | PMO and Reporting | Spec | none | docs/specs/00-purpose-and-decisions.md |
| B-25 | S7 Project setup: Template, CRM start, contract and CBS load. | Setup and Team | Spec | none | docs/specs/00-purpose-and-decisions.md |
| B-26 | S8 Team and resourcing | Setup and Team | Spec | none | docs/specs/00-purpose-and-decisions.md |
| B-27 | S9 Schedule ownership | Cost | Spec | none | docs/specs/00-purpose-and-decisions.md |
| B-28 | S10 Roles and the hub: What each role sees and does, and working together; implements M14. | Platform | Spec | B-29 | docs/specs/00-purpose-and-decisions.md |
| B-29 | S11 Deployment: Local sync to shared server, with IT. | Platform | Spec | B-28 | docs/specs/00-purpose-and-decisions.md |
| B-30 | S12 Gates and portfolio | PMO and Reporting | Spec | none | docs/specs/00-purpose-and-decisions.md |

Also waiting on Vincent rather than on a build (see the Next step lines in `docs/threads.md`): trying releases on real Wandoan data,
a real subcontract template and timesheet, a real Pronto GL export, a PMR and PSR sample, and the Copilot Studio agent decision (thread 13).
