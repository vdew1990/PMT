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

Answer (Vincent, 31/10/2026): on 30/09 the current month (f) is September and the first forecast month that contributes
to CTC is October. When the date becomes 1/10, the current month (f) is October and the first forecast month is November.
So the status month never contributes to CTC; CTC starts the month after the month of the status date, at any status date.

### Q5

Build the Q4 rule now (engine change at `app/engine.py:284`, as fix F5 after F1 to F4)? Effect: any cost still
expected in the status month must sit in actuals or accruals, because the status month no longer carries forecast.
Merlin checks it against D11 first. Asked 31/10/2026.

### Q6

CMT export template storage. Option A (Neo recommends): commit a values-stripped copy of Finance's CMT as the export
template, built by a strip tool and proven clean by an allow-list test (only reviewed generic labels, no cached
values, no pivot records, blank document properties). Option B: no template in the repo; PMT reads the template from
a path in a local settings file (like `crm_link.txt`) and strips it at every export. Asked 31/10/2026.

### Q7

CMT export, Pronto sheets: fill the CMT's Pronto sheets (General Ledger, Commitments, PO Register, Labour, Revenue)
from the Pronto rows PMT already stores, so the CMT recomputes CTD from Pronto the way Finance does (Neo's plan)? Or
write PMT's actuals into the month columns as plain values? Asked 31/10/2026.

### Q8

CMT export, projects longer than the template's 31 month columns: show a 31 month window, or add columns?
Asked 31/10/2026.
