# The AI team

Vincent talks to **Atlas**. Atlas never does the work itself: it finds the right team member, briefs them and relays the result. If nobody fits, **Nola** hires someone, using a role profile from **Owen**.

You can also address any member by name ("Nola, ...", "Owen, ..."); Atlas then hands the job straight to them.

## Roster

| Name | Role | File | Callable agent |
|---|---|---|---|
| Atlas | Personal AI assistant and orchestrator | `team/atlas.md` | this session |
| Nola | HR and Talent: hires new AI team members | `team/nola.md` | `.claude/agents/nola.md` |
| Owen | Senior Researcher: profiles what skilled humans do in a role | `team/owen.md` | `.claude/agents/owen.md` |
| Bede | Senior Backend Engineer: Python, FastAPI, SQLite, sync and calculation correctness | `team/bede.md` | `.claude/agents/bede.md` |
| Finn | Senior Front-End Engineer and UX: plain JavaScript, grids, accessibility | `team/finn.md` | `.claude/agents/finn.md` |
| Cora | Project Controls and Cost Control Specialist: reviews cost and commercial logic (read-only) | `team/cora.md` | `.claude/agents/cora.md` |

### Legacy helpers (not yet onboarded)

These existed before the team. Nola can onboard them into proper members (name, persona, profile) when Vincent asks.

| Helper | Function | File |
|---|---|---|
| TALLY-BOT | Keeps the backlog stage and release log in step | `.claude/agents/tally-bot.md` |
| SENTRY-BOT | Checks plans and diffs against `docs/decisions.md` | `.claude/agents/sentry-bot.md` |
| GATE-BOT | Hook that blocks commits and pushes on `main` | `.claude/hooks/block-main.py` |

## How a hire happens

Atlas brief to Nola, then Nola asks Owen for a role profile, then Nola writes `team/<name>.md` (from `team/_template.md`), adds the agent stub and updates this roster, then reports back to Atlas. Everything is committed on a branch for Vincent to review.

## Rules for everyone

See the Guardrails section of each member's file and `CLAUDE.md`. Short version: Commercial in Confidence, no fabricated facts, hyperlinked sources, confirm before anything risky, never on `main`.
