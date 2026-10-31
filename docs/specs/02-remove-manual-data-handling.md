# PMT spec S2: Remove manual data handling (DRAFT)

Status: Draft, not yet verified by Vincent (Zoe, 31/10/2026)

Commercial in Confidence. Amounts AUD excluding GST. Backlog B-20. Decision IDs H1 to H4, all proposed.
Labels: [repo] seen in code; [company context] EPEC internal knowledge; [assumption] Vincent to confirm.

## 1. Purpose and scope

S2 lists the manual steps in today's monthly cycle around Pronto, CMT, the PM workbook and the EOM report. For each step it says how PMT removes it. This answers M5 (Excel constraints, manual handling) and is the list that acceptance test M11(a) is judged against. S2 does not change Pronto, which stays the system of record (M8).

## 2. Manual steps today and how PMT removes them

Where the repo does not show a step, the row is a placeholder for Vincent.

| # | Manual step today | How PMT removes it | Evidence | Status |
|---|---|---|---|---|
| 1 | Export Pronto reports (transactions, timesheets, POs, claims, variations, CTD overview) | Not removed: still exported by hand. PMT reads the files | pronto.py:1-7; import kinds schema.sql:148 | Residual [repo] |
| 2 | Work out which export each sheet is and map its columns | Sheets detected and columns matched by synonym | pronto.py:181-237 | Removed [repo] |
| 3 | Code each Pronto cost row to a CBS line | Automatic resolution, with suggestions for leftovers | pronto.py:551, 628 | Removed, except leftovers [repo] |
| 4 | Tie CTD to Pronto by category (the workbook's Match sheet) | Reconcile page and diagnostics | reports.py:280-311; diagnostics.py:67 | Removed [repo] |
| 5 | Keep the accruals register, apply the MAX rule against Finance WIP accruals | Accrual register; Finance WIP journals read from the GL | accruals.py:1-18, 243 | Removed [repo] |
| 6 | Reverse accruals when invoices or timesheets land | Automatic match and reversal | accruals.py:61; D10, D17 | Removed [repo] |
| 7 | Accrue unposted timesheets | Automatic until the PM accrues | accruals.py:363; D18 | Removed [repo] |
| 8 | Accrue subcontract claims not yet invoiced | Automatic from approved claims | subcontracts.py:12-15, 178 | Removed [repo] |
| 9 | Re-key forecasts from the PM workbook into CMT | CMT comparison and write-back during parity (S1) | cmt_import.py:296-418 | Interim; ends when CMT retires (S1 C1) [repo] |
| 10 | Build the EOM report by hand (the workbook's EOM sheet) | Generated from the engine as Excel and PDF | eom_report.py:1-6, 241, 464 | Removed [repo] |
| 11 | Price variations in the workbook's Variation Engine | Variation register with the same formulas | variations.py:13-16; D22 | Removed [repo] |
| 12 | Prepare progress claims and check them against Pronto | Claim schedule, claim PDF and Excel, Pronto claims check | revenue.py:412; eom_report.py:136 | Removed [repo] |
| 13 | Load an existing project's workbook | One-off loader | pmt_workbook.py:1-19 | Migration only [repo] |
| 14 | Finance checks the EOM against Pronto | Stays a human check (M12); PMT shows its own tie-outs | M12; reports.py:306-311 | Residual by design |
| 15 | [Vincent: further manual steps, for example PMR assembly, cashflow, timesheet checks] | placeholder | | Unknown |

## 3. Proposed decisions

- H1: Section 2 is the M11(a) list. A step counts as removed when the PM no longer types, copies or reconciles it by hand during a close.
- H2: Pronto exports stay manual for the first rollout. A direct Pronto feed needs IT and is out of S2.
- H3: The PM workbook loader and the CMT write-back are migration tools, not part of the steady state.
- H4: Each removed step has a test or a demonstrated flow before M11(a) is claimed.

## 4. Acceptance tests

1. Every row in section 2 marked Removed has a passing automated test or a recorded walkthrough on a synthetic project.
2. On a synthetic month, a close runs from the Pronto load to the EOM report with no figure typed outside PMT, apart from forecast and accrual judgements.
3. The residual steps (rows 1 and 14, plus any Vincent adds) are listed with an owner.

## 5. Open items and interview questions

1. What manual steps does the close involve today that are not in section 2?
2. Which of those steps take the most time?
3. Should the Pronto exports stay manual for the first rollout (H2)?
4. Is a direct Pronto feed wanted later (yes or no)?
5. After migration, is the PM workbook loader still needed (H3)?
