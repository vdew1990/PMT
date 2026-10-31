---
name: pmt-ship-item
description: Use when a builder (Neo or Finn) finishes a unit of work on one PMT backlog ID and it needs to move to verification, records and merge. Triggers - "ship B-xx", "B-xx is built", "hand to Argus", "end of item". Runs the chain builder test brief, Argus verdict, Merlin check, Dex records, merge queue, in order.
---

# PMT ship one backlog item

One backlog ID per run. Atlas runs the chain and relays between members (subagents cannot message each other). Sources: `team/argus.md`, `team/dex.md`, `team/merlin.md`, `docs/backlog.md`.

Stages are only those in the `docs/backlog.md` header: Idea, Spec, Design agreed, Build, Test, Review, Done, Needs decision, Idea (check), Test (failed). Do not invent others.

## The chain

1. **Builder finishes** (Neo back end, Finn front end, or both). On the item branch, never `main`. Runs `.venv/bin/python -m pytest tests -q` and reports the result. Hands Atlas a test brief (template below), with all five parts.
2. **Argus verifies** from the brief, the backlog row and the decisions, not from the diff. If the brief is incomplete the verdict is "Not verifiable: brief incomplete" and it goes back to the builder. Verdict is one of:
   - **Pass**, listing what was and was not exercised (including the browser and Windows gaps).
   - **Fail**, with the evidence report (plain-English summary first, then the fields in `team/argus.md` Rule 18).
   - **Not verifiable**, with why.
3. **On Fail:** Atlas sends the evidence report to the owner (Neo, Finn, or both). Dex sets the stage to "Test (failed)" and records the verdict and commit. The owner fixes and hands over a NEW commit with a fresh test brief note; Dex sets the stage back to "Test"; return to step 2. Argus never fixes.
4. **On Not verifiable:** stage stays at Test; Dex says why. Fix the gap (brief, data, tooling) and return to step 2.
5. **On Pass: Merlin decisions check.** Merlin checks the plan and diff against `docs/decisions.md`, `docs/specs/` (M-decisions), `docs/designs.md` and `docs/open-questions.md`. On a conflict: if it goes to Vincent, Dex sets the stage to "Needs decision"; if it goes back to the builder, the new commit returns to Test with a fresh brief and Argus tests it again (step 2).
6. **Dex records.** Given the ID, the account, Argus's verdict and the commit tested:
   - sets the stage as far as the evidence supports. An item leaves Test only on an Argus Pass. Never Done unless the pull request is merged (checked with `gh api`, not inferred from the branch name);
   - appends one line to `docs/release-log.md`: DD/MM/YYYY (AEST), ID, one sentence, with the verdict and commit. Never rewrites earlier lines.
7. **Merge queue.** Dex lists open pull requests (number, head SHA, base, ID, shared files). Merlin judges the merge order (shared-file branches first, per `docs/areas.md`). Vincent merges. After the merge, Dex sets Done and, when told, bumps the bundle version in `HANDOFF.md`.

Order (confirmed by Vincent, 31/10/2026): on Pass, builder, Argus, Merlin, Dex, as in `team/argus.md`. On Fail or Not verifiable, Dex records it immediately and Merlin is not run on that commit.

## Who may write what

- Builders: the paths in the Scope sections of `team/neo.md` and `team/finn.md` (never `tests/independent/`), plus their own thread's Status and Next step lines in `docs/threads.md`. They do not edit `docs/backlog.md` or `docs/release-log.md`.
- Argus: `tests/independent/` only.
- Dex: `docs/backlog.md`, `docs/release-log.md`, and new threads in `docs/threads.md` when an item has none.
- Merlin: read-only.
- Vincent: merges, release sign-off. A Pass is evidence for him, not approval.

## Test brief template (builder fills in)

```
TEST BRIEF  B-__  <title from docs/backlog.md>
Builder: Neo / Finn          Date (AEST): DD/MM/YYYY

1. What changed
   Branch:
   Commit:
   Files or areas touched (shared files flagged):

2. STARTING STATE
   Seed data: demo/build_demo.py | tests/conftest.py fixture <name>
   Settings and setup steps (numbered):
   Project, month or status date used:

3. DESIRED OUTCOME (observable)
   For each check: screen, API call or export, and the exact result.
   Figures in AUD ex GST, with rounding rule. Dates DD/MM/YYYY.
   - Check 1: <action> -> <expected result>
   - Check 2:
   Messages or errors expected:

4. How to run it
   .venv/bin/python -m pytest tests -q
   App start or route to call:

5. Known limits
   Not built, not covered, assumptions, decisions cited (D- or M-numbers):
```

## Report back to Vincent

ID, branch and commit, builder test result, Argus verdict and what was not exercised, Merlin's finding, the stage Dex set, the release-log line, and the merge-queue position.
