# S1: CMT gaps and parity

Commercial in Confidence. Amounts are AUD excluding GST; dates are DD/MM/YYYY.

**Status:** DRAFT. Decisions S1-1 to S1-11 verified by Vincent in interview, 31/10/2026 (AEST). Acceptance tests in section 4 and the procedure in section 5 are proposed by Zoe and NOT yet verified by Vincent.

Decision IDs from the master spec ([`00-purpose-and-decisions.md`](00-purpose-and-decisions.md)) are written as M-numbers, which exist only on the open PR 8 branch `spec/00-followup` until it merges. On `main` they are still D1 to D14. Example: Finance's role (M12, D12 on main until PR 8 merges). Parity as a first-rollout acceptance test is M11(d).

## 1. Purpose and scope

PMT replaces Finance's CMT (Cost Management Tool, an Excel workbook). CMT misses functions project managers need and needs heavy manual handling. S1 defines which gaps must close and how parity is proven, so that CMT can be retired by rollout wave.

Finance wants only the EOM report, driven by actuals, commitments, accruals and forecast. The programme, claim schedules and similar matter to Finance only through their indirect effect on the EOM report (S1-11). The job PMT must take over from CMT is therefore producing a correct EOM report.

## 2. Verified decisions

| ID | Decision |
|---|---|
| S1-1 | Parity is measured on the EOM report. |
| S1-2 | PMT's accrual-inclusive EAC is the right number. Differences from a CMT-style EAC (cost to date plus cost to complete, which leaves accruals out) are explained, not removed. |
| S1-3 | Four CMT gap areas are real: forecast methods; claims and variations; resources and timesheets; history and review. |
| S1-4 | The test uses several projects, one closed month each. |
| S1-5 | PMT is the leading view and Pronto is the official view. The project manager enters claimed revenue, variations and accruals in PMT first. Revenue and variations reach Pronto only when approved, so recognised revenue in PMT differs from official revenue in Pronto until then. Accruals in PMT are the full picture; Pronto lags because Finance posts them after receiving the EOM report. Differences explained by these timing causes are allowed and should clear once approved or posted. Unexplained differences fail. |
| S1-6 | Allowed difference causes: claimed revenue and variations awaiting approval; accruals awaiting Finance posting; subcontract claims awaiting approval or payment. |
| S1-7 | Merged into S1-10. |
| S1-8 | CMT retires by rollout wave (each group of projects as its wave completes). |
| S1-9 | Tolerance: actuals agree to the dollar. Metrics known to drift (the S1-6 causes) are allowed to differ if explained. |
| S1-10 | Sign-off: project directors, in collaboration with the COO. (Replaces the earlier wording of S1-7, "directors sign off".) |
| S1-11 | Finance wants only the EOM report; other matters (programme, claim schedules and similar) count only through their indirect effect on it. |

## 3. What PMT already does (evidence)

Evidence from Zoe, read from `main`. She has not seen CMT or Pronto, so nothing below describes CMT itself.

**CMT import (`app/cmt_import.py`).**
- Reads the CMT sheets "Project Summary" and "Forecast Costs & Revenue", and "Financial Summary" for the period only.
- Writes a gap analysis. The user chooses per line Use CMT, Use app or Keep gap.
- Can post category budget adjustments, create CBS lines, undo, and write the app's forecast cells back into the uploaded CMT.
- Matches only on exact resource code or PO number. It does not handle actuals, accruals, commitments (read, not compared), revenue (reported only) or lines with several CMT rows.
- Routes are in `app/routers/platform.py` (`/cmt/analyse`, report, apply, updated, undo); the UI is `static/js/views/_cmt.js`; manual CMT entry is in `app/routers/pmo.py`.

**EAC.** The README states that CMT-style EAC is CTD + CTC and leaves accruals out, while PMT's includes them. `eac_cmt_style` (`app/reports.py`) is shown on Reconcile.

**Existing features that look like gap closers (evidenced).**
- Accruals in EAC, with a reconcile view.
- Month-end review, snapshots and forecast history.
- Seven forecast methods.
- Labour calendar.
- Unposted timesheets auto-accrued and reversed on posting.
- Diagnostics checks: variations not in Pronto, accrual states, unposted timesheets not accrued, client claims.
- EOM report revenue, variations and claims check (`app/eom_report.py`).

**Not found.**
- Any list of CMT gaps.
- Which CMT sheets or formulas Finance relies on beyond the two above.
- A parity tolerance (now S1-9).
- CMT's own documentation.
- Any record that the Excel write-back was checked in Excel (only LibreOffice).

## 4. Gap areas and proposed acceptance tests

All tests in this section are **proposed by Zoe, unverified** by Vincent. Use synthetic data only. Statements marked "inference" are not evidenced.

### 4.1 Forecast methods

- **Exists:** seven methods (ground-up, claim, burn-rate, at-budget, at-commit, top-down, manual) and a CMT-style EAC.
- **Unproven:** that each method's output is what project managers need, and what CMT's own methods are.
- **Tests:**
  1. Given a line with budget, CTD and a burn rate, when the method is burn-rate, then CTC equals the stated formula and EAC = CTD + accruals + CTC.
  2. Given a line on at-commit, when a PO is part-received, then EAC uses the commitment.
  3. Given a method change, when the month closes, then history shows the old and new method.

### 4.2 Claims and variations

- **Exists:** claim lines, certified and paid amounts, and approved variations in the EOM report.
- **Unproven:** the pending-variation workflow (inference).
- **Tests:**
  1. Given a claim certified for less than claimed, when the EOM is produced, then claimed and approved show separately.
  2. Given an approved variation not in Pronto, when Diagnostics runs, then it is listed with the PMT and Pronto values.
  3. Given a draft claim in the status month, when the EOM is produced, then it counts as claimed.

### 4.3 Resources and timesheets

- **Exists:** labour calendar; unposted timesheets auto-accrued and reversed on posting; Diagnostics timesheet checks.
- **Unproven:** crew and rate handling against how project managers plan (inference).
- **Tests:**
  1. Given an unposted timesheet, when the month is computed, then it is accrued at Pronto's cost or at hours times rate.
  2. Given that timesheet is later posted, when Pronto data is re-imported, then the accrual reverses with no double count.
  3. Given a partial posting, when Diagnostics runs, then the part-covered accrual is listed.

### 4.4 History and review

- **Exists:** month-end review, snapshots, forecast history, activity and history.
- **Unproven:** retention over a full project and reproducibility of a closed month (inference).
- **Tests:**
  1. Given a closed month, when later actuals are loaded, then re-opening that snapshot gives unchanged figures.
  2. Given a forecast changed after close, when history is viewed, then the old value and who changed it show.
  3. Given a line where plan and landed differ, when closing, then a warning appears until reviewed.

### 4.5 EOM report

Vincent named four EOM drivers: actuals, commitments, accruals and forecast. The four gap areas above are tested for their effect on these drivers (S1-11). Whether revenue and variations are also EOM drivers is open (section 9).

## 5. Parity procedure on the EOM report

Proposed by Zoe, unverified by Vincent.

1. Pick several projects, one closed month each. Vincent fixes the number; Zoe recommends two to five, including a subcontract-heavy one (S1-4).
2. Freeze the Pronto and CMT inputs for that month.
3. Produce the PMT EOM report for each project.
4. Compare with the Pronto and CMT figures line by line, by CBS and by revenue stage.
5. Show the CMT-style EAC beside PMT's accrual-inclusive EAC. The accrual gap is explained, not removed (S1-2).
6. Build the reconciliation: difference, cause (from the S1-6 list only), amount, expected clearing event and month.
7. Pass if actuals agree to the dollar (S1-9) and every other difference sits under a listed cause and is evidenced. Fail on any unexplained difference, or any cause past its clearing month. Zoe suggests flagging items still unexplained after two months; the clearing window is to be set (section 9).
8. Project directors, in collaboration with the COO, sign the reconciliation (S1-10). Finance's role stays as in the master spec: verifier of the EOM report against Pronto (M12, D12 on main until PR 8 merges).

Accounting treatment stays with Finance.

## 6. Reconciliation of allowed differences

One row per S1-6 cause, with how PMT identifies it today (evidence) or the gap. Finance's WIP and accrual definitions are unconfirmed.

| Cause | Identified today? | Evidence or gap |
|---|---|---|
| Claimed revenue awaiting approval | Partly | The EOM separates claimed from approved; `_claims_check` compares certified and paid with Pronto. There is no label "awaiting approval". |
| Variations awaiting approval | Gap (inference) | Diagnostics lists only approved variations missing from Pronto. |
| Accruals awaiting Finance posting | Partly | `pronto_accruals` reads posted Work in Progress journals and `accr_old` flags old accruals. Nothing flags "PM accrual with no Finance posting yet". |
| Subcontract claims awaiting approval or payment | Gap | `claim_accruals` in `app/subcontracts.py` accrues claims; Diagnostics checks only client claims. |

## 7. Sign-off and retirement

- **Sign-off (S1-10):** project directors, in collaboration with the COO.
- **Retirement (S1-8):** CMT retires by rollout wave, each group of projects as its wave completes. The dates and owners of the waves are open (section 9).

## 8. Out of scope

- Replacing Pronto.
- The Pronto side of accruals posting, which is Finance's act.
- CMT functions other than producing the EOM report (S1-11), unless Vincent adds some.

## 9. Open items (not decided)

1. Who supplies CMT figures and in what form. Today only a summary row (`cmt_entry`: revenue, EAC) is stored. Zoe recommends a CMT export per project and month, with a frozen copy.
2. The clearing window per cause, and who sets it.
3. How many projects, and which.
4. Whether the reconciliation lives in PMT as an output or in a document. Zoe recommends a PMT output, which would also cover the gaps in section 6.
5. Whether pending variations count as forecast or revenue (a ruling for the commercial manager and project director).
6. Rollout wave dates and owners.
7. Whether revenue and variations are EOM report drivers, or only actuals, commitments, accruals and forecast.
8. Verification by Vincent of the section 4 tests and the section 5 procedure.
9. Whether the Excel write-back to CMT matters once CMT is retired.
