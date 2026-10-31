# S1b: CMT-format export (interim bridge)

Commercial in Confidence. Amounts are AUD excluding GST; dates are DD/MM/YYYY.

**Status:** DRAFT. Decisions S1-15, S1-20 and S1-21 verified by Vincent in interview, 31/10/2026 (AEST). Everything under "Evidence", "Export requirements" and "Open items" is Zoe's analysis or a proposal, unverified by Vincent. Parent spec: [`01-pronto-tie-out.md`](01-pronto-tie-out.md) (S1).

## 1. Decisions (verified)

| ID | Decision |
|---|---|
| S1-15 | PMT exports its own CMT-format Excel as an interim bridge. PMT outputs the CMT Excel and the EOM report and ties out with Pronto; the CMT becomes a transient artefact that dies out. Finance used to update the CMT but has given that function back to the PM. Vincent does not want to maintain the CMT externally by manually updating the Pronto data it relies on just to prove it ties out with PMT. |
| S1-20 | Finance's CMT EAC is cost to date plus cost to complete, with accruals inside cost to date through ledger journals. This is what Finance uses today. The workbook's own fault log describes a different formula that includes accruals in a third term; that log is not what Finance uses. |
| S1-21 | The CMT-format export has live formulas and may use Excel 365 functions. |
| Model | The CMT in Vincent's possession has real but outdated data. It is the model for how the export should look and how its formulas should work. |

## 2. Evidence: Finance's CMT workbook (Zoe, structure only)

Formulas and structure only were read. No data from the workbook is recorded here.

**Sheets (about 20).**
- A hidden narrative project report.
- Project Summary: the CBS rollup. Revenue block, then a cost block with one row per CBS code. Columns: Original Budget, Approved Variations, Revised Budget, CTD, Commitments, CTC, EAC, Variance. Totals and gross margin rows. Check cells return OK or ERROR.
- Financial Summary: cashflow and % complete by month across columns.
- CLAIMS: the contract claim schedule by month. It defines Period, Total_Revenue and the current-period flag.
- PROGRAM: a pasted programme that drives dates through named ranges.
- The engine, "Forecast Costs & Revenue" (about 21,000 formulas): a revenue block, then a cost block under a header row with two flag rows marking each month ACTUAL or FORECAST. Columns A to R hold key, CBS, description, resource or task, PO, resource code, supplier, PO value, and check and calc columns. There are 31 month-end columns and a row total. Rows form a hierarchical tree of CBS group rows, total rows and indexed detail rows. The CBS list is static, typed into a column and described via VLOOKUP on a code-to-description list. Status columns have validations. There are about 41 conditional formats.
- A commissioning and labour estimating sheet.
- A static comparison sheet.
- Pivot-style outputs.
- Pasted Pronto sheets with helper formula columns: general ledger, labour, revenue, commitments, PO register and payments received.
- An accruals sheet (PO list with lookups).
- A code-to-description and status list sheet.

**Representative formulas (structure only).**
- Per line: CTD = SUMIF over the Actual-flag row; CTC = SUMIF over the Forecast-flag row; EAC = CTD + CTC.
- Project Summary reads CTC and EAC from the "Total" rows by CBS using SUMIFS, and reads CTD directly from the ledger sheet by SUMIF on the CBS column. The two routes to CTD agree only if the month flags are right.
- Actual months are SUMIFS on the ledger by resource code, CBS and month (or by PO).
- Commitments are a SUMIF on the commitments sheet by PO.
- Check cells compare routes (OK or ERROR, Match or Error).

**Accruals.** Accrual journals sit inside ledger cost (CTD), consistent with S1-20. A separate column deducts from PO commitments on some subcontract lines. The accruals sheet reconciles by PO. Whether accruals are ever double counted is unconfirmed and needs Finance.

**Missing CBS code.** A CBS code missing from the static list drops out of the Project Summary's per-code rows, and the check cells should show ERROR. There is no automated handling (see S1-12 in S1).

**Anomalies found.**
- Certain: three hard-coded plugs inside totals.
- Inference: uneven total ranges; a column computed as I-H in two blocks and H+I in another; a SUMIF sum range narrower than its criteria range; a typed date instead of the current-period name; two month columns carrying the same date.
- Which of these are errors is for Finance to rule on.

**Not workbook data.** VBA is present (a project with a user form and about 20 sheet code modules); the code could not be read. There is one external link, to a variation and EOT register workbook. There are 20 pivot parts and 2 charts. There are about 2,100 named ranges, mostly dead (#REF! or legacy); about 200 point at sheets. The live ones that matter are Period, Total_Revenue, crntPeriod and the programme date names.

## 3. Export requirements (proposed, unverified)

**Must reproduce:**
- The exact sheet names (formulas hard-reference them).
- The engine layout: header row, flag rows, column order, months in fixed columns, "Total" rows.
- The Project Summary rows.
- The pasted Pronto sheets with identical column letters.
- The code-to-description list.
- The names Period, Total_Revenue and crntPeriod, and the CLAIMS dates they point to.

**Needs care:** XLOOKUP, IFS and UNIQUE need Excel 365 (acceptable per S1-21); array formulas.

**Can drop:** macros (a plain .xlsx works), dead names, the static comparison sheet, the hidden narrative report, pivots, the external link, charts, and the PROGRAM sheet if its date names are kept.

**Surface, do not copy:** the hard-coded plugs should appear as visible adjustment lines.

## 4. Open items (not decided)

1. The macro code (unreadable) and what it does.
2. The manual placeholder routine for new CBS codes.
3. Whether accruals are double counted (Finance).
4. The meaning of the duplicate month columns.
5. The CLAIMS and PROGRAM internals.
6. Whether Finance needs the pasted Pronto sheets in the export, or only the engine and summaries with Pronto data embedded.
7. Acceptance tests for the export, to be proposed and verified: opens in Excel 365 with no repair prompt; no #REF!; check cells show OK; totals tie to the EOM report.
8. Who at Finance verifies that it opens and calculates.
9. Rulings on the anomalies (Finance).
