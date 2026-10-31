# PMT spec S1: CMT gaps and parity (DRAFT)

Status: Draft, not yet verified by Vincent (Zoe, 31/10/2026)

Commercial in Confidence. Amounts are AUD excluding GST. Decision IDs are C1 to C8, all proposed. Labels: [repo] means seen in the code; [company context] means EPEC internal knowledge given in the brief; [assumption] means Vincent to confirm.

## 1. Purpose and scope

S1 does three things:
- defines what Finance's CMT does;
- lists what project managers need that CMT lacks (M5, M11 b);
- defines the parity test (M11 d) that lets CMT retire under "replace, then retire" (M7).

S1 also sets the scope of the existing CMT import (S0, Related material). Finance's role stays as M12: Finance verifies, it is not a day-to-day user. S1 does not change accounting treatment. Accrual policy and EAC definition belong to Finance.

## 2. What CMT does today

| # | CMT function | Source |
|---|---|---|
| 1 | Finance-owned Excel workbook, one per project | [company context] |
| 2 | "Project Summary" sheet: project name, period ending, revenue row (original, variations, revised, claimed, to claim, total) and one row per category (PL, PS, PM, PE) with revised budget, CTD, commitment, CTC and EAC | [repo] cmt_import.py:46-56 |
| 3 | "Forecast Costs & Revenue" sheet: under each category total row, one row per resource, task, supplier or PO. Columns include Resource/Task, PO Number, Resource Code, Cost Rate, Subbie/Supplier, Budget, Budget Movement, New Budget, PO Order Value, Other, Total, Check, Diff, PO, CTD, CTC, EAC, then month columns flagged "Forecast" or "Actual" | [repo] cmt_import.py:58-69; tests/test_cmt_import.py:15-23 |
| 4 | "Financial Summary" sheet exists. Its content is unknown | [repo] docstring only, cmt_import.py:3 |
| 5 | The PM types forecast costs against the CBS; CMT calculates EAC and forecast margin | [company context] |
| 6 | Takes actuals, POs and invoices from Pronto. How they get in (paste or link) is not known | [company context]; method [assumption] |
| 7 | Feeds the PMR (the monthly report to the SLT, plus PM commentary) | [company context] |
| 8 | EAC = CTD + CTC, with accruals left out. This is a known defect (Wandoan review, July 2026). PMs and Finance treat accruals inconsistently | [company context]; also noted at engine.py:6-7 and reports.py:322-323 |
| 9 | Anything else (cashflow, claims, variations, risk, contingency) | [assumption, Vincent to confirm] |

## 3. What PMT already covers, for each CMT function

| CMT function | PMT equivalent | Status |
|---|---|---|
| Budget by category and line | Allowance ledger, rolled up by the engine (engine.py:184, 396) | Covered |
| Commitments | Pronto PO commitments; a closed PO commits only what was received (engine.py:211-220) | Covered |
| CTD from Pronto | Engine CTD, tied to the Pronto CTD overview by category (reports.py:236-248, 306-311) | Covered |
| Accruals | Four kinds plus Pronto WIP journals, with the MAX rule (accruals.py:1-18, 243) | Covered (CMT does not do this) |
| CTC and forecast by month | Forecast methods and Ground-Up (forecast.py; engine.py:382) | Covered |
| EAC | `eac = ctd + acc + ctc` (engine.py:383); `eac_cmt_style = ctd + ctc` (engine.py:401) | Covered, on a different basis by design |
| Forecast margin | `project_margin` (reports.py:16-36); EOM margin table (eom_report.py:203-207) | Partial: see note A |
| Revenue (original, variations, claimed) | `revenue.summary`; claim schedule (D26, D27) | Partial: the measures are not like for like (note B) |
| Monthly report | EOM report (eom_report.py). PMR comes later (M9) | Partial |
| Financial Summary sheet | None | Unknown |

Note A: the two PMT margin figures do not use the same cost. Reconcile uses EAC plus the unspent risk bucket (reports.py:27-28). The EOM at-completion cost uses EAC only (eom_report.py:204). Parity needs one stated basis.

Note B: the import compares CMT's revised contract with PMT's recognised revenue (cmt_import.py:189). These are different measures.

## 4. What PMs need that CMT lacks (M5, M11 b)

PMT features with no CMT equivalent known so far (repo evidence; Vincent to confirm each is a real need):
1. Accruals in EAC, with history and automatic reversal when cost lands (D10, D15, D17, D18).
2. Nested pools and allowances (D13, D14).
3. Ground-Up register with rosters, day grids and milestones (D8, designs.md).
4. Subcontract payment terms and claims, which drive CTC (D19).
5. Claim schedule and forecast revenue (D26, D27).
6. Variations that top up the CBS (D22-D25).
7. Line-level commitments and outstanding POs (engine.py:211-220).
8. Diagnostics and the CTD tie-out (reports.py:236-248).
9. Audit trail on every change (D4).
10. [Vincent's list: placeholder]
11. [Finance's list, if any: placeholder]

## 5. Scope of the CMT import

Today the import compares and aligns in both directions:
- **What it reads (parse, cmt_import.py:40-86).** From Project Summary: project name and period, the revenue row, and category totals. From the forecast sheet: each line's task, PO, resource code, supplier, New Budget, CTD, CTC, EAC, and the months flagged "Forecast".
- **What it ignores.** The Financial Summary sheet, despite the docstring. The "Actual" month columns. Cost Rate, Budget, Budget Movement, PO Order Value, Other, Total, Check, Diff and PO. Lines with no months, no CTC and no EAC (line 82).
- **What it compares (compare, lines 111-191).**
  - Months from the status month on, line by line. A match is exact only on a one-to-one resource code or PO; anything else is weak.
  - Category budgets. PE09 is excluded from budget alignment (line 163).
  - App-only forecast.
  - A category table of budget, CTD, CTC and EAC.
  - The CMT commitment column is parsed (line 56) but not compared.
  - Line-level CTD, CTC and EAC are parsed but not compared.
- **What it changes.**
  - In PMT: CMT months go in as MANUAL forecast, budget differences are posted as ledger adjustments, and new lines are created. All of this can be undone (lines 194-270).
  - In CMT: the app's months can be written back into a copy of the CMT (lines 296-418).

Proposed scope after parity (C1): the import becomes a migration tool. It does a one-off load when a project joins PMT, and it runs the monthly comparison during the parity months. The write-back to CMT stops when CMT retires.

## 6. Parity test (M11 d)

- **Figures.** Revised budget, commitments, CTD, accruals, CTC, EAC, revenue (revised contract and claimed to date) and forecast gross margin in $ and %.
- **Level.**
  - Project total and category (grandparent) must agree within tolerance.
  - Parent level is reported, with differences explained.
  - Child level is reported only. CMT lines and PMT lines do not map one to one (cmt_import.py:111-113).
  - Cross-project child identifier: parent plus Function [company context].
- **Same month.** The CMT period equals the PMT status month, and both use the same Pronto extract date.
- **Tolerance.** [placeholder: $X or Y% per figure, set by the commercial manager and Finance].
- **Reconciling items.** Each one is defined, explained and carries a named sign-off.
  1. The accruals basis. PMT EAC minus CMT EAC should equal PMT accruals, adjusted for Finance WIP accruals already in Pronto CTD. Whether those are in CTD is an open question (accruals.py:9-12).
  2. The risk bucket in margin (note A).
  3. PE09 contingency treatment.
  4. Timing differences (unposted timesheets, D18).
- **Fictional example (not reconciled).** CTD $1,000,000, accruals $50,000, CTC $400,000. PMT EAC is $1,450,000 and the CMT-style figure is $1,400,000, leaving a reconciling item of $50,000.
- **Procedure.** Each month, close in PMT and upload the CMT. Produce the gap report (report_xlsx), with the reconciling items as their own rows. The PM explains each residual. Finance checks against Pronto (M12).
- **Duration.** [placeholder: N consecutive months] on [placeholder: N of the two to five rollout projects] (M3).
- **Sign-off.** The PM and Finance (financial controller) for each project and month. Vincent decides retirement (C6).

## 7. Acceptance tests for S1

1. The CMT import reads every sheet and column listed as in scope in section 5. A test uses a synthetic workbook.
2. The import's category comparison shows CMT EAC against PMT `eac_cmt_style`, and also against PMT EAC with the accruals reconciling item. Both tie to the cent on a synthetic case.
3. The commitment column is compared by category.
4. One margin basis is used everywhere (Reconcile and EOM agree on a synthetic case).
5. A parity report for one month lists each figure at total and category level, the tolerance, the difference, the reconciling items and the unexplained residual.
6. The residual is within tolerance for the agreed months and projects. The report carries the PM and Finance sign-off.
7. Every item in section 4 that Vincent confirms has a passing test or a demonstrated flow.

## 8. Open items and interview questions for Vincent

Decisions proposed (Vincent and Finance to rule):
- C1: import scope (section 5).
- C2: PMT keeps EAC = CTD + accruals + CTC and does not replicate the CMT defect.
- C3: parity is judged at total and category level; parent and child are explained only.
- C4: the accruals reconciling item, as defined in section 6.
- C5: one margin basis.
- C6: who decides CMT retirement.
- C7: tolerances.
- C8: the duration and number of projects.

**CMT today**
1. Do the sheet names and columns in section 2 match the current CMT template? Are there other versions in use?
2. What does the Financial Summary sheet hold, and does any figure from it go to the SLT?
3. How do Pronto actuals and POs get into CMT (paste, link, Finance keys them in)?
4. Does CMT do cashflow, claims, variations, risk or contingency? Answer yes or no for each.
5. Does CMT's CTD include Finance's WIP accrual journals?

**Gaps**
6. Which items in section 4 are real PM needs? What is missing from the list?
7. Does Finance need anything from PMT beyond the EOM report?

**Import**
8. Do you agree with C1: migration plus the parity months, with write-back stopping at retirement?
9. Should PE09 contingency be compared, or excluded as it is today?

**Parity**
10. Do you agree with C2, that PMT does not replicate the EAC defect? Who in Finance must accept it?
11. Do you agree with C3: total and category must agree, and parent and child only need explaining?
12. Which margin basis: with the risk bucket or without it?
13. What tolerance applies for each figure ($ or %), and who sets it?
14. How many consecutive months, and on which projects (count only)?
15. Who signs off each month: the PM and the financial controller?
16. Who decides that CMT retires: you, Finance, or both?

## Code findings from drafting (for the backlog, not fixed)

1. The CMT import compares PMT EAC (with accruals) to CMT EAC with no reconciling item (cmt_import.py:179-180). Owner: Neo.
2. Reconcile and EOM use different margin bases (reports.py:27-28, eom_report.py:204). Owner: Vincent to rule, Finance on treatment.
3. Revenue comparison is not like for like (cmt_import.py:189). Owner: Neo, after Vincent confirms the measure.
4. Docstring says the Financial Summary sheet is read; the code never opens it (cmt_import.py:3, 42). Owner: Neo.
5. The CMT commitment column is parsed but never compared (cmt_import.py:56, 179). Owner: Neo.
6. tests/test_cmt_import.py:237 ends in `or True`, so that check can never fail. Owner: Argus to note, Neo to fix.
