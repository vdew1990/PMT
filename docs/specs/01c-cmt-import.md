# S1c: CMT import for mid-project moves

Commercial in Confidence. Amounts are AUD excluding GST; dates are DD/MM/YYYY.

**Status:** DRAFT. Decision S1-17 verified by Vincent in interview, 31/10/2026 (AEST). The existing-capability evidence is Zoe's reading of `main`; the open items and acceptance tests are proposals, unverified. Parent spec: [`01-pronto-tie-out.md`](01-pronto-tie-out.md) (S1). Related: [`01b-cmt-format-export.md`](01b-cmt-format-export.md) (S1b).

## 1. Decision (verified)

| ID | Decision |
|---|---|
| S1-17 | Keep and maintain a CMT import so a PM can move from the CMT to PMT mid-project. Vincent: an import function for the CMT is very useful for PMs who want to move mid-project. |

## 2. Existing capability (Zoe, from main)

- `app/cmt_import.py` reads the sheets "Project Summary" and "Forecast Costs & Revenue", and "Financial Summary" for the period only.
- It writes a gap analysis. Per line the user chooses Use CMT, Use app or Keep gap.
- Use CMT sets the line to MANUAL and loads the CMT months. It can post category budget adjustments, create new CBS lines and undo.
- Use app writes forecast cells back into the uploaded CMT (`app/cmt_import.py:296` and `:388`).
- It matches only on exact resource code or PO number; other matches are weak and need review.
- Not handled: actuals, accruals, commitments (read, not compared), revenue (reported only), and lines with several CMT rows (these cannot be written back).
- Routes are in `app/routers/platform.py` (`/cmt/analyse`, report, apply, updated, undo); the UI is `static/js/views/_cmt.js`; manual CMT entry is in `app/routers/pmo.py`.
- Release-log note: fuzzy matching can map a CMT person to the wrong resource.

## 3. Open items (not decided)

1. What a mid-project move must carry: forecast per line, PM accruals, claim schedules, variations and history, given that actuals, commitments and posted accruals come from Pronto anyway.
2. How the CMT's hard-coded plugs and anomalies are handled on import (see S1b).
3. Whether the existing Excel write-back to the CMT still matters once the export exists (S1b).
4. Testing against the CMT layout; only LibreOffice was checked for the write-back.
5. Mapping when CBS codes differ between the CMT and the project in PMT.
6. Acceptance tests, to be proposed and then verified by Vincent (none are proposed yet).
