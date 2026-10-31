# PMT spec S5: Risk and allowances (DRAFT)

Status: Draft, not yet verified by Vincent (Zoe, 31/10/2026)

Commercial in Confidence. Amounts AUD excluding GST. Backlog B-23. Decision IDs R1 to R5, all proposed.
Contingency policy, risk release and delegations belong to the commercial manager and project director.

## 1. Purpose and scope

S5 covers how allowance is held, moved and released: budget and risk from the estimate, pools (D13, D14), contingency, the company risk bucket, releases and infusions, the allowance ledger, and PE09.

## 2. What PMT does today [repo]

**Allowance ledger:**
- Every movement is a ledger row: estimate, transfer, variation, risk release, adjustment, contingency (schema.sql:75-81).
- Views are Current and Total allowance (D20).

**Buckets and linking:**
- A bucket is a CBS group with its own (Unallocated) pool.
- Linking a resource moves allowance from the bucket to its line, with three options by cost already incurred (allowance.py:1-11, 74, 130).
- Spread and undo (allowance.py:151, 178).

**Pools (D13, D14):**
- Forecast taken from a pool reduces the pool's forecast (engine).
- Allowance does not move automatically.
- The user can run "allocate", which transfers allowance from pools to the lines they cover (pools.py:1-6, 47; routers/cost.py:1200). This is a user action, consistent with D14.

**Risk model** (risk.py:1-18):
- The estimate gives each item a budget and a risk amount. The risk amount is a bucket the company holds.
- The PM separates contingency inside the budget (risk.py:221).
- The PM moves contingency to risk cover at any time (risk.py:238).
- Company release from the bucket (risk.py:264) and infusion (risk.py:299) are allowed only once the risk cost has landed in Pronto, unless forced (risk.py:208-219).
- Releases can be reversed (risk.py:317).
- Close-out compares occurred risk cost with the estimate's risk, for estimator feedback (risk.py:327; routers/cost.py:1159-1167).
- The register can be imported (risk.py:398, 446).

**PE09 Contingency:**
- Exists in the taxonomy (taxonomy.py:29). The CMT import excludes it from budget alignment (cmt_import.py:163).
- No other special handling found.
- How PE09 relates to the PM's contingency earmark and to the company risk bucket is not defined.

**Terminology clash:** the engine's row field "contingency" is allowance minus EAC, which is headroom (engine.py:401, 598). It is not the PM's contingency earmark in risk.py.

## 3. Proposed decisions

- R1: S5 adopts D13, D14 and D20 unchanged.
- R2: Define PE09: whether it is (a) the company risk bucket, (b) the PM's contingency, or (c) a separate CBS category. [Vincent and the commercial manager to choose]
- R3: Rename the engine's "contingency" field in the interface to "headroom" (or another term Vincent prefers) so it is not confused with the contingency earmark.
- R4: The `approved_by` field on releases and infusions records a named person with delegation. Delegation limits are [placeholder: commercial manager to set]. PMT records them; it does not decide them.
- R5: The "invoice landed" rule for company funds stays. A forced release needs a note and is listed in the EOM or PMR. [Vincent to confirm]

## 4. Acceptance tests

1. On a synthetic project, the total allowance equals the sum of ledger rows, and every movement shows who made it, when, and the old and new values.
2. Taking forecast from a pool does not change any allowance (D14) until "allocate" is run.
3. A release larger than the landed, uncovered risk cost is refused unless forced. A forced release is flagged.
4. Contingency plus risk cover cannot exceed an item's budget (risk.py:229-230).
5. After R2, PE09 is treated the same way in cost control, the EOM report and the CMT parity report.

## 5. Open items and interview questions

- B-05 (drag allowance back to its pot) is an idea in this scope.
- Whether margin carries the risk bucket (S1 note A) affects how S5 figures appear in reports.

1. Is PE09 the company risk bucket, the PM's contingency, or a separate category (R2)?
2. Should the engine's "contingency" (allowance minus EAC) be renamed, for example to "headroom" (R3)?
3. Who sets the delegation limits for releases and infusions (R4)?
4. Must forced releases be listed in the EOM or the PMR (R5)?
