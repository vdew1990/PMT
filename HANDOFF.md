# PMT handoff (read this first)

Short state page. The detail lives in `docs/`; this file stays under about one page.

## State

- Bundle version: **2026-10-31.121** (CRM link path from a settings file, `crm_link.txt`). Earlier releases: `docs/release-log.md`.
- Source of truth is this git repository (https://github.com/vdew1990/PMT, private). Zips are release exports only.
- How to resume: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`, then `.venv/bin/python -m pytest tests -q`.

## Where things are

| File | What it holds |
|---|---|
| `docs/backlog.md` | Every open item, with stage, area and source. Update the stage when it changes. |
| `docs/decisions.md` | Decisions not to re-open without Vincent. Read before building. |
| `docs/open-questions.md` | Questions waiting on Vincent. |
| `docs/designs.md` | Designs and plans agreed but not built. |
| `docs/areas.md` | Which session owns which menu group and files; shared files. |
| `docs/threads.md` | Threads 1 to 32: what was built and the next step of each. |
| `docs/release-log.md` | Bundle history and one section per release. |

## Rules for every session

1. Work on a branch named for the item (for example `cost/ledger-pivot`), never on `main`. Open a pull request when asked.
2. Read `docs/decisions.md` and the backlog rows for your area first. Do not read the whole of `docs/threads.md` or `docs/release-log.md`.
3. When a unit of work lands, in the same turn: set its backlog stage, add one line to `docs/release-log.md`, and bump the bundle version above only on merge to `main`.
4. Changes to `app/main.py`, `app/schema.sql`, `static/js/app.js` or `static/js/ui.js` are kept small and merged early; say so in the branch name or pull request.
5. Working agreement with Vincent: batch findings, confirm the plan, wait for "go", one build and one test run per batch, zip only on request.
