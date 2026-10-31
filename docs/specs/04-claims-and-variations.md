# PMT spec S4: Claims and variations (DRAFT)

Status: Draft, not yet verified by Vincent (Zoe, 31/10/2026)

Commercial in Confidence. Amounts AUD excluding GST. Backlog B-22. Decision IDs V1 to V5, all proposed.
Statutory content (BIF Act statement, review periods) is UNVERIFIED: Legal owns it. Revenue recognition belongs to Finance.

## 1. Purpose and scope

S4 covers the revenue side: contract value, the client claim schedule and progress claims, variations, and subcontract claims as cost (D19 to D27). It does not decide contract entitlement, notice validity or accounting treatment.

## 2. What PMT does today [repo]

**Contract value** (revenue.py:124-183):
- Base, optional prices (offered, confirmed, cancelled) and variations.
- "Recognised" = base + optional taken + approved variations (revenue.py:152).
- "Official" is a separate figure (revenue.py:153).
- A bridge from original to revised value (revenue.py:155-160).
- "Recognised" here is a contract value measure, not accounting revenue [Finance to confirm wording].

**Claim schedule (D26, D27):**
- Typed as $ or %, capped at each line's price (revenue.py:412, 451).
- The status month is the claim; later months are forecast.
- Can be loaded from a file (claim_template.py:1-10).
- A certified line counts at its certified amount (revenue.py:27-29).
- Claims carry retention (schema.sql:262).

**Claim output and checks:**
- Claim PDF and Excel (routers/revenue.py:640-651).
- Claims are checked against Pronto in diagnostics and on the EOM report (diagnostics.py:100; eom_report.py:136).

**Statutory [unverified, Legal]:**
- A Queensland BIF Act statement is shown when the site is in Queensland and the governing law is Queensland or not stated, with a manual override (exporters.py:210-223). The section reference s 61(4) in the code is unconfirmed.
- The client review deadline is counted in business days (excluding weekends and project holidays) or in calendar days (revenue.py:554-569).

**Variations:**
- Two negotiations: client status and EPEC position. A variation is recognised when the client has Approved and EPEC has Agreed. Revenue then becomes contract value and the cost build-up posts to the allowance ledger (variations.py:1-5, 150-186).
- Markup is a % of cost (D22; variations.py:13-16).
- Spread is uniform or proportional (D23; variations.py:43-68).
- Client detail level (D24; variations.py:10).
- Funding tops up the CBS line or goes to a copy of it (D25; variations.py:197-205).
- Register placeholders are created from the uploaded contract (decisions 26/10; variations.py:288).

**Subcontract claims (D19):**
- Payment portions, progress through price items, and subcontractor plans.
- Approved but not invoiced claims accrue and reverse on invoice (subcontracts.py:1-15, 178).

## 3. Proposed decisions

- V1: S4 adopts D19 to D27 unchanged.
- V2: Legal verifies the BIF Act statement rule, the s 61(4) reference and the review period logic before the claim PDF is used on a live project. Until then the PDF carries [placeholder wording: "statutory content not yet verified"].
- V3: Finance confirms the names "recognised" and "official" for contract value, or gives replacements, so they are not read as accounting revenue.
- V4: Whether an unapproved variation goes into forecast revenue or cost is set by the commercial manager and project director, with Finance on revenue. PMT shows pending variations separately until then.
- V5: B-08 (variation engine overview and exports) and B-10 (claim grid usability) are in S4 scope. [Vincent to confirm]

## 4. Acceptance tests

1. On a synthetic contract, claimed to date never exceeds any line's price, including claims already issued.
2. Approving a synthetic variation, with client Approved and EPEC Agreed, adds its value to recognised contract value and its cost and risk to the allowance ledger. Withdrawing it removes both.
3. A certified claim counts at the certified amount in the revenue curve and the EOM report.
4. Claims in PMT tie to Pronto claims within [placeholder tolerance] on a synthetic month.
5. The review deadline for a synthetic claim, submitted on 23/12/2026 with a 10 business day period, skips weekends and the listed public holidays (calendar arithmetic only; the period itself is for Legal).
6. Legal sign-off on V2 is recorded before live use.

## 5. Open items and interview questions

1. Who in Legal verifies the BIF Act statement and the review period logic (V2)?
2. Until Legal confirms, should the claim PDF carry a "not yet verified" note?
3. Who in Finance confirms the names "recognised" and "official" (V3)?
4. Do pending variations go into forecast revenue, forecast cost, both or neither (V4)?
5. Are B-08 and B-10 in S4 scope (V5)?
6. Should PMT track retention and its release, or is retention Pronto only?
7. Can you share a real subcontract template and timesheet (anonymised)?
