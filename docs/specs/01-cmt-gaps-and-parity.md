# S1: CMT replacement and Pronto tie-out (formerly CMT gaps and parity)

Commercial in Confidence. Amounts are AUD excluding GST; dates are DD/MM/YYYY.

**Status:** DRAFT. Decisions S1-1 to S1-18 verified by Vincent in interview, 31/10/2026 (AEST). The acceptance tests (section 4), the revised procedure (section 5) and the open items (section 9) remain proposed and unverified.

Decision IDs from the master spec ([`00-purpose-and-decisions.md`](00-purpose-and-decisions.md)) are written as M-numbers (M1 to M15 on `main`). Example: Finance's role (M12). Parity as a first-rollout acceptance test is M11(d).

## 1. Purpose and scope

PMT replaces Finance's CMT (Cost Management Tool, an Excel workbook). CMT misses functions project managers need and needs heavy manual handling. S1 defines which gaps must close and how parity is proven, so that the CMT stops being something anyone maintains, wave by wave, as PMT's export replaces it (S1-8, S1-15).

Finance wants only the EOM report, driven by actuals, commitments, accruals and forecast. The programme, claim schedules and similar matter to Finance only through their indirect effect on the EOM report (S1-11). The job PMT must take over from CMT is therefore producing a correct EOM report that ties out with Pronto (S1-13, S1-16).

## 2. Verified decisions

| ID | Decision |
|---|---|
| S1-1 | Parity is measured on the EOM report. |
| S1-2 | PMT's accrual-inclusive EAC is the right number. Differences from a CMT-style EAC (cost to date plus cost to complete, which leaves accruals out) are explained, not removed. |
| S1-3 | Four CMT gap areas are real: forecast methods; claims and variations; resources and timesheets; history and review. |
| S1-4 | The test uses several projects, one closed month each. |
| S1-5 | PMT is the leading view and Pronto is the official view. The project manager enters claimed revenue, variations and accruals in PMT first. Revenue and variations reach Pronto only when approved, so recognised revenue in PMT differs from official revenue in Pronto until then. Accruals in PMT are the full picture; Pronto lags because Finance posts them after receiving the EOM report. Differences explained by these timing causes are allowed and should clear once approved or posted. Unexplained differences fail. |
| S1-6 | Allowed difference causes: claimed revenue and variations awaiting approval; accruals awaiting Finance posting; subcontract claims awaiting approval or payment. **Superseded by S1-14.** The PM-input layers in S1-14 correspond to this earlier cause list. |
| S1-7 | Merged into S1-10. |
| S1-8 | CMT retires by rollout wave (each group of projects as its wave completes). **Refined by S1-15:** the CMT is not retired after a proof; it stops being something anyone maintains, wave by wave, as PMT's export replaces it. |
| S1-9 | Tolerance: actuals agree to the dollar. Metrics known to drift (the S1-6 causes) are allowed to differ if explained. **Superseded by S1-14.** |
| S1-10 | Sign-off: project directors, in collaboration with the COO. (Replaces the earlier wording of S1-7, "directors sign off".) |
| S1-11 | Finance wants only the EOM report; other matters (programme, claim schedules and similar) count only through their indirect effect on it. |
| S1-12 | In theory the CMT equals Pronto, which it imports. The differences come from human error due to manual handling. Example: the CMT cost and forecast worksheet is static, so when Pronto shows new CBS entries that are not in the static CMT list, the user must create placeholders by hand to tie the numbers out. |
| S1-13 | Ultimately PMT must align perfectly with Pronto and give Finance an EOM report with cost and revenue: allowances, commitments, actuals, accruals, forecast and EAC, revenue and variations. (This resolves the earlier open item: revenue and variations are EOM report drivers.) |
| S1-14 | Parity test restated: Pronto-only figures must match exactly. PM-input layers are reported separately and explained. The PM inputs are four: subcontractor claim schedules with claimed numbers; client claims (claimed revenue not yet approved or recorded in Pronto); the variation register, including drafted variations that have not gone to the client; and accruals with numbers only the PM knows (the PM's estimated value of works done before any invoice or claim has landed). Both CMT and PMT run solely on Pronto data; the PM inputs are the only difference. Supersedes the wording of S1-9 (metrics known to drift) and S1-6 (causes). |
| S1-15 | PMT exports its own CMT-format Excel as an interim bridge. PMT outputs the CMT Excel and the EOM report and ties out with Pronto; the CMT becomes a transient artefact that dies out. Finance used to update the CMT but has given that function back to the PM. Vincent does not want to manage the CMT externally by manually updating the Pronto data it relies on just to prove it ties out with PMT. |
| S1-16 | Therefore the tie-out is PMT against Pronto, not PMT against an externally maintained CMT. |
| S1-17 | Keep (and maintain) a CMT import so a PM can move from the CMT to PMT mid-project. Vincent: an import function for the CMT is very useful for PMs who want to move mid-project. PMT already has one (`app/cmt_import.py`, section 3); S1 must define what it has to cover for a mid-project move (section 9). |
| S1-18 | Client claims are a fourth PM input: the PM's claim to the client (claimed revenue before the client approves it and Pronto records it). This amends S1-14 from three PM inputs to four. |

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

The EOM report drivers are now confirmed (S1-13): allowances, commitments, actuals, accruals, forecast and EAC, revenue and variations. The four gap areas above are tested for their effect on these drivers (S1-11).

**Proposed acceptance test, unverified by Vincent (addresses S1-12).**
1. Given a Pronto export that contains a CBS code not in the project's CBS, when it is imported, then the code appears as a placeholder or is listed as unplaced, without anyone creating it by hand.

Existing behaviour, as far as the records show: `docs/threads.md` (Diagnostics entry, `app/diagnostics.py`) lists "unplaced categories" and "parked actuals" among the PMT vs Pronto divergences. `docs/release-log.md` mentions "unplaced cost" only in the margin bridge entry, as a row for what no cost line carries. Neither record says that an import creates a placeholder for an unknown CBS code or lists it as unplaced, so that behaviour is not verified.

## 5. Tie-out procedure on the EOM report

Revised for S1-14 to S1-16. Proposed by Zoe, unverified by Vincent. The earlier steps that froze inputs and compared against an externally updated CMT are removed (S1-16).

1. Pick several projects, one closed month each. Vincent fixes the number; Zoe recommends two to five, including a subcontract-heavy one (S1-4).
2. Produce the PMT EOM report for each project, with cost and revenue drivers (S1-13).
3. Compare the PMT EOM report with Pronto only, line by line, by CBS and by revenue stage.
4. The Pronto-only layer must match exactly (S1-14). Actuals agree to the dollar.
5. List the PM-input layers separately and explain each (S1-14, S1-18): subcontractor claim schedules with claimed numbers; client claims (claimed revenue not yet approved or recorded in Pronto); the variation register, including drafted variations not yet with the client; and PM accruals (the PM's estimated value of works done before any invoice or claim has landed). Show PMT's accrual-inclusive EAC with the accrual gap explained, not removed (S1-2).
6. Check the CMT-format export (S1-15): Finance opens it, and its totals are tied out to the EOM report.
7. Fail on any unexplained difference in the Pronto-only layer, or any PM-input layer that is not listed and explained. Zoe suggests flagging items still unexplained after two months; the clearing window for the PM-input layers is to be set (section 9).
8. Project directors, in collaboration with the COO, sign the tie-out (S1-10). Finance's role stays as in the master spec: verifier of the EOM report against Pronto (M12).

Accounting treatment stays with Finance.

## 6. Reconciliation of PM-input layers

The four PM inputs (S1-14, S1-18) are the layers. Each is reported separately and explained. Evidence is how PMT identifies the layer today, or the gap. Finance's WIP and accrual definitions are unconfirmed. The earlier S1-6 cause list now maps to these inputs.

| Layer (PM input) | Identified today? | Evidence or gap |
|---|---|---|
| Subcontractor claim schedules with claimed numbers (the S1-6 subcontract-claims cause) | Gap | `claim_accruals` in `app/subcontracts.py` accrues claims; Diagnostics checks only client claims. |
| Client claims: claimed revenue not yet approved or recorded in Pronto (S1-18; the S1-6 claimed revenue awaiting approval cause) | Partly | The EOM report separates claimed from approved; `_claims_check` compares certified and paid with Pronto; there is no label "awaiting approval". |
| Variation register, including drafted variations not yet with the client (S1-6 variations cause) | Gap (inference) | Diagnostics lists only approved variations missing from Pronto. |
| PM accruals: estimated value of works done before any invoice or claim has landed (S1-6 accruals cause) | Partly | `pronto_accruals` reads posted Work in Progress journals and `accr_old` flags old accruals. Nothing flags "PM accrual with no Finance posting yet". |

## 7. Sign-off and retirement

- **Sign-off (S1-10):** project directors, in collaboration with the COO.
- **Rollout (S1-8, refined by S1-15):** the CMT is not retired after a proof; it stops being something anyone maintains, wave by wave, as PMT's export replaces it. The dates and owners of the waves are open (section 9).

## 8. Out of scope

- Replacing Pronto.
- The Pronto side of accruals posting, which is Finance's act.
- CMT functions other than producing the EOM report (S1-11), unless Vincent adds some.

## 9. Open items (not decided)

Resolved, for the record:
- Who supplies CMT figures and in what form: resolved by S1-16 (the tie-out is PMT against Pronto, not an externally maintained CMT).
- Whether revenue and variations are EOM report drivers: resolved by S1-13 (they are).

Open:
1. Excel files: Vincent supplied two Excel workbooks in the session. One is his CMT, which has real but outdated data and is the model for how the exported Excel should look and how its formulas should work. The other is his PMT workbook, the most up to date, on which the CMT was developed and with which it shares many sheets. Zoe is analysing the structure and formulas of both workbooks (structure only); her findings will define the layout of the CMT-format export, the section 4 and 5 tests and the import scope.
2. The clearing window per cause, now for the PM-input layers, and who sets it.
3. How many projects, and which.
4. Whether the reconciliation lives in PMT as an output or in a document. Zoe recommends a PMT output, which would also cover the gaps in section 6.
5. Whether pending variations count as forecast or revenue (a ruling for the commercial manager and project director).
6. Rollout wave dates and owners.
7. Verification by Vincent of the section 4 tests and the section 5 procedure.
8. How the CMT-format export should be laid out (to be settled from Zoe's workbook analysis, item 1).
9. Whether the Excel write-back to CMT still matters.
10. What the CMT import must cover for a mid-project move (S1-17), given its current limits in section 3 (no actuals, accruals, commitments or multi-row lines); to be settled from item 1.
