---
name: pmt-team-change
description: Use for any hire, rename or retirement of a PMT AI team member (team/*.md) or legacy helper (for example Janus, the block-main hook). Triggers - Vincent or Atlas says hire, rename, retire, merge or onboard a member or helper. Makes the change in one pass and one commit so no file is missed.
---

# PMT team change (hire, rename, retire)

Why this exists: seven renames on 30 and 31/10/2026 (Bede to Neo, Cora to Raven, Raven to Zoe, SENTRY-BOT to Merlin, Vera to Onyx, Onyx to Argus, GATE-BOT to Janus) each needed two or three follow-up commits because files were missed.

This skill supports Nola's process in `team/nola.md`; it does not replace it. For a hire, Nola's Step 0 need check and Vincent's confirmation come first, and Owen's role profile comes before the member file. Retirements and merges are proposed first and Vincent confirms.

## Step 1. Confirm before writing anything

1. State the change type: hire, rename, retire, or onboard a legacy helper.
2. Ask for the FINAL name (and the old name for a rename). Read it back and get an explicit yes. Write nothing until then. A name changed later is a second rename.
3. For a hire: confirm the need check is answered "hire" and Vincent confirmed it. If not, stop.
4. Check the name is not already used: `grep -rniw "<NewName>" --exclude-dir=.git .`

## Step 2. Sweep before (record every hit)

Run from the repo root and keep the output:

```
grep -rn "<OldName>" --exclude-dir=.git --exclude-dir=.venv .
grep -rni "<oldname>" --exclude-dir=.git --exclude-dir=.venv .   # lower case, file names, slugs
git ls-files | grep -i "<oldname>"                                 # files named after the member
```

For a hire, sweep for the role title and any member the new one replaces or narrows (for example "Test Engineer", "TALLY-BOT").

## Step 3. Every place a name lives

Work down this list. Tick each, or write "no hit".

| Place | What to change |
|---|---|
| `team/<name>.md` | Create from `team/_template.md` (hire); `git mv` and update Identity, Name, Hired line (rename); keep the file and mark it retired, or delete if Vincent says so (retire). |
| `team/README.md` | Roster row (name, role, file, agent); legacy helpers table; "renamed from" note. |
| `.claude/agents/<name>.md` | `git mv` the stub; frontmatter `name:` (lower case) and `description:`; "You are <Name>" line; path to `team/<name>.md`. |
| `CLAUDE.md` | The AI team paragraph and the Helper agents section. CLAUDE.md is project configuration: change it only with Vincent's own approval. |
| `.claude/hooks/*.py` | Docstring and any message text naming the helper (for example "Janus: blocked."). |
| `.claude/settings.json` | Only if a hook file itself is renamed. |
| Other team files | `team/*.md` that mention the member (Does not do, Escalates to, pipeline lines), `team/nola.md` "Also does", and `team/profiles/*.md` where the profile names the member. |
| `docs/backlog.md` | Header or rows that name the member (for example "latest Argus verdict"). Dex is the writer. |
| `docs/release-log.md` | Do NOT rewrite history. Append one new dated line for the change. Dex is the writer. |
| `HANDOFF.md`, `docs/areas.md`, `docs/decisions.md` | Normally no hit. If `docs/decisions.md` names the member, propose wording for Vincent; do not edit it. |

Profiles under `team/profiles/` are Owen's research records: update a member name only where it is a forward-looking reference; leave dated history as written. This handling of `team/profiles/` is pending Vincent's confirmation.

## Step 4. Sweep after

Re-run the Step 2 commands. Every remaining hit must be one of:
- an allowed history mention ("renamed from <OldName>", a dated release-log line, a "formerly" note), or
- a dated research record left as written.

List any remaining hit with the reason it stays. Then sweep the new name to confirm it appears in each place from Step 3:

```
grep -rln "<NewName>" --exclude-dir=.git .
```

## Step 5. One commit

1. On a branch, never `main` (Janus blocks it). Suggested: `team/rename-<old>-<new>`, `team/hire-<role>`, `team/retire-<name>`.
2. Run `.venv/bin/python -m pytest tests -q` (a hook rename can break a run). Report the result.
3. `git status` and `git diff --stat`: only the files from Step 3 changed.
4. One commit covering every file: "Rename <Old> to <New> across team, agents, CLAUDE.md and docs" (or Hire / Retire). No follow-up commits for missed files; if the after-sweep finds one, amend before pushing.
5. Hand the backlog and release-log lines to Dex if he did not make them in the same pass.

## Report

Change type, final name, files changed, before and after sweep counts, any remaining hits with the reason, test result, commit hash.
