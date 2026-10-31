# PMT master spec: purpose and decisions (S0)

Status: Verified by Vincent in interview, 31/10/2026 (AEST)

Commercial in Confidence.

Decision IDs here are M1 to M15; the older D-numbers are in docs/decisions.md.

## Purpose (M1)

PMT is the delivery team's add-on to Pronto: one place for cost control, resource management and reporting on every EPC project. Over time it becomes the hub where project directors, project managers, construction managers, cost controllers, schedulers and technical leads work together to finish projects on time and within budget.

## Decisions

| ID | Decision | Notes |
|---|---|---|
| M1 | Purpose, as stated above. | |
| M2 | Order of work: money first, then reporting, then resources, then the shared hub. | Spec order follows this and M13. |
| M3 | First rollout: a handful (two to five) of live projects. First users are project managers and project directors. | |
| M4 | Deployment: local PCs plus the synced SharePoint folder now; a shared server (for example hosted on web01) when the hub phase starts. | See S11, with IT. |
| M5 | The gap: Finance's CMT (Cost Management Tool, Excel) misses functions project managers need, and needs a lot of manual handling because the finance team has no dynamic programming skills. PMT aims to take away these Excel constraints and remove manual data handling. | See S1, S2. |
| M6 | Slowest steps of today's monthly close: Pronto load and check, reforecast, accruals. | See S3. |
| M7 | PMT replaces the PM workbook, other tools (named: Pronto reports) and Finance's CMT. CMT retires only after parity with it is proven ("replace, then retire"). | See S1. |
| M8 | Out of scope (never); see the Out of scope section. | |
| M9 | Reports: the EOM report is in the first rollout; the internal board report (PMR) and client report (PSR) come later. | See S6. |
| M10 | Schedule: PMT owns the project schedule over time. | Needs its own spec (S9); today PMT imports a schedule. |
| M11 | Success for the first rollout, four acceptance tests: (a) a listed set of today's manual handling steps no longer happens by hand; (b) the functions project managers need that CMT lacks exist in PMT; (c) a complete month-end close runs in PMT with no side spreadsheet; (d) PMT figures agree with CMT for the same month (parity), so CMT can be retired. | Targets not yet set; see Open items. |
| M12 | Finance's role in the first rollout: Finance receives the EOM report that PMT renders and checks it against Pronto. A verifier, not a day-to-day user. | |
| M13 | Specs are written in the order S1 to S12 (see the Spec index). | |
| M14 | Role-dependent visibility, enforced; see Roles and visibility. | Replaces D15 in `docs/decisions.md`. |
| M15 | During development, Vincent sets his role manually and sees how it affects the GUI, not chained to a limited view. Upon rollout to the whole team, the sign-in method must be set and role visibility enforced. | Vincent, 31/10/2026. See Roles and visibility. |

## Roles and visibility (M14)

What people see when they log in depends on their role. People genuinely cannot see what their role excludes (enforced, not only hidden). The full audit trail (who did what, when, old and new value) stays. M14 replaces D15 in `docs/decisions.md` ("No restrictions by role. Instead a full audit trail", Vincent 16/10), which now carries a superseded note.

| Role | Sees | Does not see |
|---|---|---|
| Scheduler | The programme, resource management and communication (meetings, team structure, communication matrix). | Anything else. |
| Technical lead (commissioning manager, construction manager) | The budget they directly impact and manage; the programme; resource management; cost and the claims on the subcontracts they manage. | The full project budget; client revenue; margin. |
| Project manager, project director, cost controller | The full project budget including revenue, claims and margin. | |
| Finance | The EOM report only (M12). | Everything else. |

Technical leads contribute forecasts in four forms, all of which help the project manager build the full forecast:

1. The 3-week lookahead.
2. A monthly forecast of their own slice.
3. Milestones and rosters.
4. Timesheet checks.

M15 (development and rollout): during development Vincent does not want to be chained to a limited view. He wants to set his role manually and see how it affects the GUI. Upon rollout to the whole team, the sign-in method must be set and role visibility enforced. A profile role setting that changes the menus already exists in the app. It is a view, not a lock, and stays available for development.

## Out of scope (M8)

Never:

- Replacing Pronto. Pronto stays the system of record for actuals; PMT reads its exports.
- Holding HR personal data (pay band, home address, age) until role-based access and an HR/IT agreement exist.
- Writing to the CRM. The link stays read-only and one way.

## Open items

Not decided. Recorded, not resolved.

1. Sign-in method for M14. Verified Microsoft/Entra sign-in needs IT. PMT has no sign-in today; the role is a profile setting.
2. When M14 must be in place: partly answered by M15. A sign-in method must be decided before the rollout to the whole team; the method itself remains open (item 1) and needs IT. Still open: whether it is also needed at the hub phase or before personal data.
3. The EOM report shows the whole project, so Finance seeing it means Finance sees the full project through that one report. Confirm that is intended (tension with "full budget: project manager, project director, cost controller only").
4. Whether schedulers edit the programme (M10) or only view it.
5. Construction and commissioning managers' exact slices. Links to the 24/10 teams and leads design in `docs/designs.md` and backlog B-01.
6. The other roles in M1 (construction managers and others) are not yet defined beyond M14.
7. The rollout success measures (M11) need targets, to be set in S1 to S3.
8. Does the first rollout (a handful of projects, project managers and directors) need enforced sign-in, or only the whole-team rollout?

## Related material the specs must respect

- `docs/decisions.md`
- `docs/designs.md` (teams and leads design)
- `docs/backlog.md`
- PMT already has a CMT import (`app/cmt_import.py`, with tests in `tests/test_cmt_import.py`). S1 must establish its scope.

## Spec index

| ID | Spec | Scope | Status |
|---|---|---|---|
| S0 | Purpose and decisions | This file. | Written |
| S1 | CMT gaps and parity | What CMT does today, what PMs need that it lacks, the parity test for retiring it. | Draft (`01-cmt-gaps-and-parity.md`), awaiting Vincent |
| S2 | Remove manual data handling | The list of manual steps today and how PMT removes each. | Draft (`02-remove-manual-data-handling.md`), awaiting Vincent |
| S3 | Month-end close flow | Pronto load and check, reforecast, accruals, in a measurable time. | Draft (`03-month-end-close-flow.md`), awaiting Vincent |
| S4 | Claims and variations | | Draft (`04-claims-and-variations.md`), awaiting Vincent |
| S5 | Risk and allowances | | Draft (`05-risk-and-allowances.md`), awaiting Vincent |
| S6 | Reports | EOM, then PMR, PSR. | Draft (`06-reports.md`), awaiting Vincent |
| S7 | Project setup | Template, CRM start, contract and CBS load. | Not yet written |
| S8 | Team and resourcing | | Not yet written |
| S9 | Schedule ownership | | Not yet written |
| S10 | Roles and the hub | What each role sees and does, and working together; implements M14. | Not yet written |
| S11 | Deployment | Local sync to shared server, with IT. | Not yet written |
| S12 | Gates and portfolio | | Not yet written |

The order follows M2 and M13.

## How to use this spec

Each capability gets one small spec, written in the order above. Each spec lists its own acceptance tests, so a capability is finished when its tests pass. Specs must not contradict the decisions in this file; change a decision here first, with Vincent's verification.
