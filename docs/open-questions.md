# Open questions for Vincent

Moved from HANDOFF.md unchanged.


1. Try sharing on a real SharePoint library with one colleague (README, "Sharing a project through SharePoint").
   Confirm your name shows correctly (top right) and that a change shows on the other PC within about a minute.
   (Vincent 16/10: noted.)

2. The engine counts the status month as a forecast month too, so at a month-end status date (e.g. 30/09) AT-BUDGET
   and BURN-RATE still put forecast into September (shown as "+$x" next to what landed). Should forecast start the
   month after the status month when the status date is the last day of the month?

   Vincent, 30/10/2026 (reasoning, not a decision; related B-09, D11, D17, D18):
   - The status month shows forecast and accruals/actuals side by side so the user can judge whether this month's
     forecast was good, and so decide whether to accrue something or reforecast it because works were delayed.
   - CTC should exclude the value of the old forecast for the status month.
   - Vincent is considering copying the forecast numbers into accruals by default for the status month, with the
     user adjusting accruals where there is an issue. He is not sure of the mechanism.
   - For: if the current month's forecast is excluded from CTC and the user starts with an empty current month, EAC
     fluctuates depending on when it is viewed (mid-month versus the end of the month after accruing for works
     performed). Copying forecast to accruals by default would stabilise that, so EAC would move only when works
     are delayed.
   - Against: copying by default means less prompting to check each accrual, so mistakes are easier. Today's
     trigger is: "I have a forecast number for a CBS with no accrual; should I accrue or not, in other words did
     these works happen?"
   - Status: open.

3. Finance owner: who owns the rounding basis, remainder policy and tolerances?
   (Vincent, 30/10/2026: Vincent for now (backlog B-22); to be routed to a finance owner when he names one.)

4. Different releases: if two users run different PMT releases, what should happen: nothing, a warning, or a refusal?
   (Vincent, 30/10/2026: warn first; refusing is a later decision if a warning proves not enough (backlog B-20).)

5. Gate coverage and rollout: a gate only protects copies that already contain it. Is that acceptable, and how is a
   release rolled out to every user (including the first gate release)? Open.

6. Revisiting money storage: what evidence would justify moving money from REAL to integer cents or Decimal? Open.
   Candidate triggers are in backlog B-24: real month-end evidence that float noise, not allocation, causes
   differences against Pronto or the CMT; or journal compaction (B-12) proceeding, since representation should be
   settled before a snapshot format is fixed. (Vincent decided option A on 30/10/2026: money stays REAL for now.)
