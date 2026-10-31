# Open questions for Vincent

Moved from HANDOFF.md unchanged.


1. Try sharing on a real SharePoint library with one colleague (README, "Sharing a project through SharePoint").
   Confirm your name shows correctly (top right) and that a change shows on the other PC within about a minute.
   (Vincent 16/10: noted.)

2. The engine counts the status month as a forecast month too, so at a month-end status date (e.g. 30/09) AT-BUDGET
   and BURN-RATE still put forecast into September (shown as "+$x" next to what landed). Should forecast start the
   month after the status month when the status date is the last day of the month?

## Question register (Q numbers)

Every question put to Vincent gets a unique Q number that is never reused. Each heading is a link target
(for example `docs/open-questions.md#q1`). When a question is answered, add the answer and date under it; do not delete it.

### Q1

Goal 4 (link CBS activity windows to the project schedule): build Neo's Option 1? It extends the existing
`window_link` model so a line's start and end can each be driven by several schedule tasks (start = earliest start,
end = latest finish), adds a stable task key so links survive a re-import, and adds a task picker and a bulk
"link selected lines" action on Setup > Allowances. It needs a schema change (dropping `UNIQUE(node_id, role)` on
`window_link`), which is Vincent's decision. Merlin checks it against #20 and M10 before the build.
Alternative (Option 2): link at forecast item level instead. Asked 31/10/2026.

### Q2

When a schedule re-upload no longer contains a task that a CBS line is linked to: should the line keep its last
dates and be flagged "schedule item gone" (recommended), or fall back to typed dates? Asked 31/10/2026.

Answer (Vincent, 31/10/2026): keep the last dates, with a flag. The difference is that the link has disappeared and the values have become static.

### Q3

On schedule upload, PMT auto-suggests links by name match (`app/programme.py:261`, similarity 0.6 or more) and
creates them without asking; in Neo's test it silently linked a line. Keep auto-linking, or ask first?
Asked 31/10/2026.

Answer (Vincent, 31/10/2026): ask first. The person can check the suggestions one by one, or accept them all in one go.

### Q4

B-09, same as question 2 above: at a month-end status date (for example 30/09), should the forecast start the month
after the status month? Today `app/engine.py:284` counts the status month as a forecast month. Asked 31/10/2026.

Superseded by Q9 (answer H), 31/10/2026.

Answer (Vincent, 31/10/2026): on 30/09 the current month (f) is September and the first forecast month that contributes
to CTC is October. When the date becomes 1/10, the current month (f) is October and the first forecast month is November.
So the status month never contributes to CTC; CTC starts the month after the month of the status date, at any status date.

### Q5

Build the Q4 rule now (engine change at `app/engine.py:284`, as fix F5 after F1 to F4)? Effect: any cost still
expected in the status month must sit in actuals or accruals, because the status month no longer carries forecast.
Merlin checks it against D11 first. Asked 31/10/2026.

Status (31/10/2026): paused by Vincent before any change, to reconsider the status month against accruals. Superseded by Q9.

### Q6

CMT export template storage. Option A (Neo recommends): commit a values-stripped copy of Finance's CMT as the export
template, built by a strip tool and proven clean by an allow-list test (only reviewed generic labels, no cached
values, no pivot records, blank document properties). Option B: no template in the repo; PMT reads the template from
a path in a local settings file (like `crm_link.txt`) and strips it at every export. Asked 31/10/2026.

Answer (Vincent, 31/10/2026): Option A, including the stripping of the Majors Creek CMT as described. The template ships
inside the program files (for example `app/cmt_template/`, alongside `app/gate_forms/`), so it is in every release zip and
is replaced by each release; it is not a local setting.

### Q7

CMT export, Pronto sheets: fill the CMT's Pronto sheets (General Ledger, Commitments, PO Register, Labour, Revenue)
from the Pronto rows PMT already stores, so the CMT recomputes CTD from Pronto the way Finance does (Neo's plan)? Or
write PMT's actuals into the month columns as plain values? Asked 31/10/2026.

Answer (Vincent, 31/10/2026): Option A, fill the Pronto sheets.

### Q8

CMT export, projects longer than the template's 31 month columns: show a 31 month window, or add columns?
Asked 31/10/2026.

### Q9

How should the expected cost of the status month be treated between the status date and month-end close? Fictional
example: Sep forecast $100k, $60k invoiced on 20/09, $40k of September work invoiced in October. EAC through September:
- B (Q4 rule, CMT's own layout): status month out of CTC, accruals start from zero. EAC 100, 160, then 200 once the PM
  accrues. This is the CMT dip.
- C (default copy): the unlanded status-month forecast is proposed as a system accrual, which the PM confirms, reduces or
  deletes and pushes forward at month end. EAC stays at 200. Accruals then include forecast-based amounts with nothing
  to match when the invoice lands, so a matching rule is needed. Medium to large build.
- H (hybrid, Merlin's narrow preference): the status month stays in CTC but only its unlanded remainder counts
  (forecast minus actuals and accruals in that month). At close, every line with a remainder needs a review decision:
  accrue it, roll it to next month, or drop it. EAC stays at 200, accruals stay cost incurred, and D11 is kept. Medium build.
C and H give the same EAC and the same accruals at close. They differ only in what the unlanded amount is called during
the month (proposed accrual in C, CTC in H). Choose B, C or H. Asked 31/10/2026.

Answer (Vincent, 31/10/2026): H. This supersedes the Q4 answer; D11 stays.

### Q10

Must the month-end close be blocked until every line with an unlanded status-month remainder (or a proposed accrual)
has a review decision (S3, E4)? Yes or no. Asked 31/10/2026.

Answer (Vincent, 31/10/2026): yes, every open item needs a decision. The user must be able to cycle through them easily,
skipping lines with no forecast and lines where forecast and actuals tie out exactly.

### Q11

Under H, the "roll to next month" decision moves forecast money. Decision #20 allows forecast changes in three places
only (Cost control row, claim schedule, Ground-Up register). May the month-end review become a fourth place for this
one action, or should the review open the line's Cost control row so the PM moves it there? Asked 31/10/2026.

Answer (Vincent, 31/10/2026): no fourth place; #20 stays. A "not done, reforecast" decision at EOM takes the PM to the
line's Cost control row by default, because the PM may want to change the forecast method there. From the row the PM
goes to the right place for the method: the row itself for AT-COMMIT, BURN-RATE, AT-BUDGET and TOP-DOWN, the claim
schedule for CLAIM, or the Ground-Up register for GROUND-UP. Needs more design thought (Finn, with Neo).
