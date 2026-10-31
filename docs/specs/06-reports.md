# PMT spec S6: Reports (DRAFT)

Status: Draft, not yet verified by Vincent (Zoe, 31/10/2026)

Commercial in Confidence. Amounts AUD excluding GST. Backlog B-24. Decision IDs P1 to P6, all proposed.

## 1. Purpose and scope

The EOM report is in the first rollout and goes to Finance, who check it against Pronto (M9, M12). The PMR (internal board) and the PSR (client) come later. S6 must respect M14 visibility. Carried from S0, open item 3 (not re-asked here): the EOM shows the whole project, including margin, so Finance sees the full project through it.

## 2. EOM report today [repo]

**Blocks** (eom_report.py:1-6, 193-224):
- Revenue by stage: claimed, approved, invoiced and paid; base and variations; previous month, this month, to date, remaining, contract value.
- Gross margin: original, revised, to date, at completion.
- Approved variations.
- Claims, PMT against Pronto.
- Cashflow.
- Cost table by CBS: revised value, ordered, outstanding commitment, actuals, accruals, CTC, EAC (eom_report.py:231-236).
- An internal check that the table's EAC and CTD equal the engine totals.

**Outputs:** JSON, Excel and PDF (routers/pmo.py:315-333).

**Revision:** numbered by counting month-end snapshots (eom_report.py:211-213), but always rebuilt from live data (see S3, E3).

**Cashflow:** earned basis, before payment terms (eom_report.py:153-164). B-14 proposes cash on payment terms.

**Margin basis:** the at-completion cost uses EAC without the risk bucket (eom_report.py:204). The Reconcile page uses EAC plus risk (reports.py:27-28); see S1 note A.

**Format points:**
- The "prepared" date prints as DD-Mon-YY (eom_report.py:218), not DD/MM/YYYY.
- The title string contains an em dash (eom_report.py:217).

## 3. PMR and PSR today [repo]

- **PMR:** placeholder page with a proposed layout, the live commercial block and the complexity history (static/js/views/pmr.js:8-25).
- **PSR:** placeholder. It never shows internal cost, margin or contingency (static/js/views/psr.js:4-8).
- Samples of both are still awaited from Vincent (docs/threads.md, thread 28; backlog note).

## 4. Proposed decisions

- P1: The EOM report sent to Finance is the version frozen at close (S3 E3), with a revision number and the date in DD/MM/YYYY.
- P2: One margin basis across the EOM, Reconcile and PMR (follows S1 C5).
- P3: The EOM cashflow stays on an earned basis for the first rollout and is labelled as such. B-14 comes later. [Vincent to confirm]
- P4: The PMR layout follows Vincent's sample. Until then the commercial block is the only built part. Sections: [placeholder].
- P5: The PSR layout follows the contract or the client's template. It never includes cost, margin, contingency or risk. Sections: [placeholder].
- P6: Who receives each report and in which format (PDF, Excel) is recorded per project: [placeholder distribution list].

## 5. Acceptance tests

1. On a synthetic project, the EOM cost table's EAC and CTD equal the engine totals to the cent (the check block reads zero).
2. The EOM margin at completion equals the Reconcile forecast GP under the basis chosen in P2.
3. After closing, the stored EOM for that month does not change when data changes (P1).
4. All dates on the EOM read DD/MM/YYYY, and the report contains no em dash.
5. A synthetic PSR contains no cost, margin, contingency or risk figure.
6. Finance confirms, for [placeholder] months, that the EOM ties to Pronto (M12).

## 6. Open items and interview questions

- PMR and PSR samples (Vincent).
- Whether a parent project carries its own EOM report (B-15).

1. Can you share a PMR and a PSR sample (anonymised)?
2. Should the EOM cashflow stay on an earned basis for the first rollout (P3)?
3. Who receives the EOM, and in which format (PDF, Excel or both)?
4. Does the PSR follow the client's template or an EPEC standard?
5. Should a parent project carry its own EOM report (B-15)?
