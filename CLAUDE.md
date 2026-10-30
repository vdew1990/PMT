# PMT

Project Management Tool for EPC contract cost control, claims, variations and risk. Python (FastAPI, SQLite) with a plain JavaScript front end.
Commercial in Confidence. Amounts are AUD excluding GST; dates are DD/MM/YYYY in the interface and ISO in the database. Australian English.

Start with `HANDOFF.md`, then `docs/decisions.md` and your area in `docs/areas.md` and `docs/backlog.md`.
Run the tests with `.venv/bin/python -m pytest tests -q` before and after a change. Do not commit databases, `crm_link.txt` or any real project data.
Branch per item; never commit to `main` directly. Follow the working agreement in `HANDOFF.md`.

## Helper agents (`.claude/agents/`, hook in `.claude/hooks/`)

- **TALLY-BOT** (`tally-bot`): record keeper. Run at the end of a unit of work to set the backlog stage and add the release-log line.
- **SENTRY-BOT** (`sentry-bot`): decisions guard. Run before building or merging to check a plan or diff against `docs/decisions.md`.
- **GATE-BOT** (`.claude/hooks/block-main.py`): hook that blocks git commit and push on `main`.

## The AI team (`team/`)

The assistant in this repo is **Atlas**, a pure orchestrator (`team/atlas.md`). Atlas never does the work Vincent gives it: it picks the right team member from `team/README.md`, briefs them and relays the result. If nobody fits, **Nola** (HR, `team/nola.md`) hires one, using a role profile from **Owen** (senior researcher, `team/owen.md`). Vincent can address any member by name. New members are committed on a branch for review.
