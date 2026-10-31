---
name: pmt-spec-writer
description: Use when writing a new PMT spec (S1 to S12 or later) under docs/specs/, or adding a decision to a spec. Triggers - "write spec S3", "spec for <capability>", "add a decision", "new M-number". Keeps the S0 numbering conventions so nothing is renumbered later.
---

# PMT spec writer

Why this exists: decisions were renumbered from D to M1 to M15 and D15 was marked superseded after the fact. Numbers are permanent once written.

Read first: `docs/specs/00-purpose-and-decisions.md` (S0, the master spec), `docs/decisions.md`, `docs/backlog.md`. A spec must not contradict S0; change a decision in S0 first, with Vincent's verification.

## Who writes specs

Specs under `docs/specs/` are drafted by whoever Vincent names for that spec. In S0, only the Spec index Status column may be updated without asking; any other change to S0 needs Vincent's verification.

## Numbering rules

| Series | Meaning | Where it lives | Next number |
|---|---|---|---|
| S | Spec section (one file per capability) | Spec index in S0 | Already allocated S1 to S12; a new capability takes the next S after the highest in the index. |
| M | Master spec decision | Decisions table in S0 (and new specs) | Highest M in `docs/specs/` plus one. |
| D | Older decisions | `docs/decisions.md` | Not issued by specs. Never edit that file; propose wording. |
| B | Backlog item | `docs/backlog.md` | Highest B plus one; Dex adds the row. |

Find the next free numbers from the current files, never from memory:

```
grep -rhoE "^\| M[0-9]+" docs/specs/ | grep -oE "[0-9]+" | sort -n | tail -1   # decision table rows only
grep -oE "^\| B-[0-9]+" docs/backlog.md | sort -t- -k2 -n | tail -1
```

- Never renumber, reuse or delete an existing S, M, D or B number.
- A changed decision gets a NEW M-number. The old one stays, with a superseded note.

## Superseding a decision

Follow the D15 / M14 pattern:
- New row: `| M<next> | <decision> | Replaces M<n>. <who>, DD/MM/YYYY. |`
- Old row keeps its text; append to Notes: `Superseded DD/MM/YYYY by M<next> (<file>).`
- If the old one is a D-number in `docs/decisions.md`, do not edit it: propose to Vincent the line `Superseded DD/MM/YYYY by M<n> in docs/specs/<file>; <what stays>.`
- Sweep `team/*.md` and `docs/` for the old ID (`grep -rnw "M<n>" team docs`) and list stale references for their owners to fix.

## File and structure

- File: `docs/specs/NN-<short-name>.md`, NN = the S-number with two digits (S3 is `03-month-end-close.md`).
- Use `template.md` beside this skill. Sections, in order: title with S-number, Status line, Commercial in Confidence, Purpose, Decisions (M-table), Scope and out of scope, Requirements, Acceptance tests, Open items, Related material, Backlog items.
- Each spec lists its own acceptance tests; a capability is finished when they pass (S0, "How to use this spec").
- Open items are recorded, not resolved. Do not decide for Vincent.

## Conventions

- Australian English. No em dashes, no emoji.
- Dates DD/MM/YYYY in Australia/Brisbane time: `TZ=Australia/Brisbane date +%d/%m/%Y`.
- Amounts AUD excluding GST; say the rounding rule.
- Status values as in S0: "Not yet written", "Written", "Verified by Vincent in interview, DD/MM/YYYY (AEST)". A spec is only "Verified" when Vincent says so.
- Cite D- and M-numbers by ID; cite code paths in backticks.

## After writing

1. Update the S0 Spec index Status for that S-number (Written).
2. New M-decisions that change S0: add to the S0 table and get Vincent's verification.
3. New backlog items: give Dex the wording (ID, item, area, stage Spec, depends on, source); Dex adds the rows and the release-log line.
4. Work on a branch (`spec/NN-<short-name>`), never `main`.
