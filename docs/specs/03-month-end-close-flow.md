# PMT spec S3: Month-end close flow (DRAFT)

Status: Draft, not yet verified by Vincent (Zoe, 31/10/2026)

Commercial in Confidence. Amounts AUD excluding GST. Backlog B-21. Decision IDs E1 to E5, all proposed.

## 1. Purpose and scope

The three slowest steps today (M6) are the Pronto load and check, the reforecast and accruals. S3 defines how a complete close runs in PMT with no side spreadsheet (M11 c) and how long it takes. Accounting cut-off and accrual policy belong to Finance.

## 2. The flow in PMT today [repo]

The Month-end page (static/js/views/monthend.js; steps in checklists.py:55-108) lists seven steps in order:

1. **Load this month's Pronto reports.** Shows Done once transactions and timesheets reach the status month (checklists.py:61-71). POs, CTD and variation reports carry no date and are not judged (checklists.py:60).
2. **Check accruals.** Counts open accruals and those marked "investigate" (checklists.py:72-76). Detail is on the Accruals page (accruals.py).
3. **Review each line.** For each line, what was forecast for the month at the last close is set against what landed (actual plus accrued). The PM records a decision: as planned, accrued, slipped and reforecast, partial, not needed, or noted (review.py:1-17, 40). This is the reforecast step.
4. **Complexity and client assessment** (checklists.py:84-90).
5. **Confirm the team** (checklists.py:91-99).
6. **Close the month.** Stores a month-end snapshot. Closing again replaces it (checklists.py:100-104; monthend.js close()).
7. **Send the reports.** EOM to Finance, PMR to the board, PSR to the client (checklists.py:105-106).

Supporting checks:
- Diagnostics lists every place PMT and Pronto disagree: Pronto data, suppliers and POs, cost, accruals, timesheets, revenue (diagnostics.py:1-13, 67-106).
- Health checks: CTD tie, old accruals, accruals to investigate (reports.py:230-248).

Gaps seen in the repo:
- Closing does not freeze the month. The snapshot can be replaced, and the EOM report is rebuilt live (eom_report.py:193; routers/pmo.py:315-333).
- The time a close takes is not measured. Timestamps exist that could measure it: import_batch.uploaded_at (schema.sql:152) and snapshot.created_at (schema.sql:401).
- Open question 2 and B-09 (whether forecast starts the month after a month-end status date) affect the reforecast.

## 3. Proposed decisions

- E1: Close time is measured from the first Pronto import of the month to the month-end snapshot, from timestamps PMT already stores.
- E2: Targets are set for each step and in total, for a project of a stated size: [placeholder: hours per project; placeholder: calendar days after the month end].
- E3: A closed month is frozen. The EOM report Finance receives is the version stored at close. Re-closing creates a new revision instead of overwriting.
- E4: A close counts as complete only when steps 1, 2, 3 and 6 are Done and diagnostics show no error level item. Remaining items are either accepted with a note or block the close: [Vincent to choose].
- E5: Assessment and team steps (4, 5) are part of the close but not of the M11(c) cost close. [Vincent to confirm]

## 4. Acceptance tests

1. On a synthetic project, all steps show Done after loading synthetic Pronto files, resolving accruals, deciding every differing line and closing.
2. PMT reports the elapsed close time per project and month (E1).
3. After closing, a change to cost data does not change the stored EOM report for that month (E3).
4. Re-closing creates revision 02 and keeps revision 01.
5. The close time on the rollout projects meets [placeholder target] for [placeholder] consecutive months.
6. No side spreadsheet is used; the PM confirms this in writing for each closed month (M11 c).

## 5. Open items and interview questions

1. Roughly how many hours does one project's close take today?
2. What is your target close time per project, in hours?
3. By which business day after month end must the EOM go to Finance?
4. Should a closed month freeze, with re-closing creating a new revision (E3)?
5. Must diagnostics errors block the close, or only be noted (E4)?
6. Are the complexity and team steps part of the cost close (E5)?
7. Should forecast start the month after the status month when the status date is the last day of the month (B-09)?
