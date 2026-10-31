# The AI team

Vincent talks to **Atlas**. Atlas never does the work itself: it finds the right team member, briefs them and relays the result. If nobody fits, **Nola** hires someone, using a role profile from **Owen**.

You can also address any member by name ("Nola, ...", "Owen, ..."); Atlas then hands the job straight to them.

## Roster

| Name | Role | File | Callable agent |
|---|---|---|---|
| Atlas | Personal AI assistant and orchestrator | `team/atlas.md` | this session |
| Nola | HR and Talent: hires new AI team members | `team/nola.md` | `.claude/agents/nola.md` |
| Owen | Senior Researcher: profiles what skilled humans do in a role | `team/owen.md` | `.claude/agents/owen.md` |
| Neo | Senior Backend Engineer: Python, FastAPI, SQLite, sync and calculation correctness | `team/neo.md` | `.claude/agents/neo.md` |
| Finn | Senior Front-End Engineer and UX: plain JavaScript, grids, accessibility | `team/finn.md` | `.claude/agents/finn.md` |
| Zoe | Project Controls and Cost Control Specialist: reviews cost and commercial logic (read-only) | `team/zoe.md` | `.claude/agents/zoe.md` |
| Merlin | Decision Maker (important decisions go through the `/anthropic-skills:council` skill, run by Atlas): checks plans and diffs against `docs/decisions.md`, judges merge order, recommends to Vincent (read-only; renamed from SENTRY-BOT) | `team/merlin.md` | `.claude/agents/merlin.md` |
| Dex | Project Coordinator: keeps backlog stages, release log and merge queue current; status by area lane (docs only; replaced TALLY-BOT) | `team/dex.md` | `.claude/agents/dex.md` |
| Onyx | Test Engineer: independently verifies each backlog ID end to end and across areas; tests and reports, does not fix (browser flows use Playwright for Python from `requirements-test.txt`, on cloud Chromium; Edge itself is not testable in cloud sessions) | `team/onyx.md` | `.claude/agents/onyx.md` |

### Legacy helpers (not yet onboarded)

These existed before the team. Nola can onboard them into proper members (name, persona, profile) when Vincent asks.

| Helper | Function | File |
|---|---|---|
| Janus | Hook that blocks commits and pushes on `main` (renamed from GATE-BOT; Janus is the Roman god of gates and doorways) | `.claude/hooks/block-main.py` |

## How a hire happens

It begins with a need check: Atlas asks Vincent whether a new role is needed at all (an existing member, Atlas or Merlin might handle it, or the job may be a one-off), with a recommendation. Nothing proceeds without Vincent's confirmation. Nola repeats the check in writing at the top of her report (Step 0 in `team/nola.md`) and creates nothing unless the answer is clearly "hire".

Once the need is confirmed: Atlas brief to Nola. Atlas runs Owen for a role profile and hands it to Nola (Nola cannot launch agents). Nola then writes `team/<name>.md` (from `team/_template.md`), adds the agent stub and updates this roster, then reports back to Atlas. Everything is committed on a branch for Vincent to review.

## Rules for everyone

See the Guardrails section of each member's file and `CLAUDE.md`. Short version: Commercial in Confidence, no fabricated facts, hyperlinked sources, confirm before anything risky, never on `main`.
