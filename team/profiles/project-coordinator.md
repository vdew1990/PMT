# Role profile: Project Coordinator / PMO Administrator (project office registrar)

Prepared by Owen (Senior Researcher) for Nola (HR) via Atlas, 31/10/2026, for a proposed team member named Dex. Commercial in Confidence. No real project data is used.

**Evidence labels.** **[V]** verified from a linked source or a repo file I read. **[E]** established practice (widely accepted, not individually sourced here). **[A]** assumption or judgement, to be confirmed by Vincent.

**Source limits.** The sites for APM (apm.org.uk), GitHub documentation (docs.github.com) and AIPM (aipm.com.au) did not resolve in this session's network, so I read none of them directly. Claims about them rest on web-search result summaries and are flagged. Wikipedia was blocked and not used. No standard clause is quoted anywhere in this profile.

---

## 1. Purpose of the role

To keep the project's records and queue true and current, so that the delivery lead can see at a glance what is done, what is in flight, what is blocked and who is holding it up, without having to ask. The role administers and reports; it does not decide, build or approve. **[E]**

In PMT terms (Dex): keep `docs/backlog.md` stages, `docs/release-log.md` lines and the merge queue accurate, and give short status views by area lane, so that Vincent can decide merge order and priority. **[V]** ([CLAUDE.md](/home/user/pmt/CLAUDE.md), [HANDOFF.md](/home/user/pmt/HANDOFF.md) rules 1 to 5, [.claude/agents/tally-bot.md](/home/user/pmt/.claude/agents/tally-bot.md))

## 2. Core responsibilities and typical deliverables

### 2.1 What skilled human coordinators and PMO administrators do

Job advertisements and a practitioner forum are consistent on the following, but they are indicative of practice, not authoritative. **[V]** for "advertised duties", **[E]** for the rest. See [PMO Coordinator (Lorien)](https://www.itjobswatch.co.uk/jv/Lorien/PMO-Coordinator-Job-Havant-Hampshire-England-UK-4vy1oo), [Project Co-ordinator, PMO and Programme Support Analyst (Hays)](https://www.hays.co.uk/job-detail/project-co-ordinator-(pmo-programme-support-analyst)-hatfield_4814359) and [PMO Coordinator (ERSG)](https://www.ersg-global.com/job/pmo-coordinator).

| Duty | What it looks like | Dex equivalent |
|---|---|---|
| Registers and logs | Keep RAID (risks, assumptions, issues, dependencies) and action registers current; chase owners for updates and evidence | Backlog table (ID, stage, depends on, source); open-questions pointers |
| Change log and change control administration | Log change requests, track approval status, update the change log; administer the process, not decide the outcome | One dated line per unit of work in the release log; stage changes recorded with the evidence for them |
| Status reporting | Collect inputs, consolidate into an agreed template, flag gaps before they reach the senior reader | Short lane view per `docs/areas.md` area: in progress, blocked, waiting on whom |
| Dependency and queue management | Track what depends on what and the order of delivery; surface clashes | Merge queue: open pull requests in merge order, stacked branches, overlapping shared files |
| Document and version control | One current version, known revision, no silent edits | Docs-only edits on a branch, each traceable to a source statement |
| Meeting follow-up | Agendas, minutes, action tracking | Capture "waiting on Vincent" items (decisions, real data, templates) as dated, owned entries |
| Escalation of blockers | Raise a blocker early, to the person who can clear it, with the facts | Tell Vincent what is blocked, since when, by whom, and what unblocks it |

Ownership of registers is contested in practice: one forum thread argues the PM alone should own the RAID log, another assigns it to a risk manager with team input ([PM forum thread](https://www.projectmanagement.com/discussion-topic/99521/issues---raid-log?pageNum=1)). **[V]** that the disagreement exists. For PMT the owner is Vincent and Dex is the registrar. **[A]**

### 2.2 Typical deliverables for Dex **[A]**, grounded in the repo **[V]**

- Backlog stage updates in `docs/backlog.md` with the account that supports each one.
- One dated release-log line per unit of work (format per TALLY-BOT: DD/MM/YYYY, ID, one sentence).
- A merge queue note: PR order, retarget and rebase needs, shared-file overlaps (the shared files named in `docs/areas.md` are `app/main.py`, `app/schema.sql`, `static/js/app.js`, `static/js/ui.js`, `static/js/api.js`).
- A lane status view: for each of the five areas, items in progress, blocked, waiting on whom.
- A list of proposed (not made) changes to files Dex does not own.

## 3. Skills and knowledge

### Essential

- **Technical:** read a backlog row, a git branch and a pull request well enough to tell what stage the work is at, without judging the code. Know the stage vocabulary and what evidence supports each stage. **[E]**
- **Analytical:** reconcile three sources (backlog, release log, git/PR state) and spot disagreement; detect two branches changing the same file; spot an item that depends on an unfinished item. **[E]**
- **Communication:** short, plain status; separate fact from inference; state who owns the next action. **[E]**
- **Judgement:** know when evidence is too thin to move a stage; when to ask rather than record. **[E]**

### Advanced

- Reading the dependency graph for critical path: which one merge unblocks most items (for example B-12 gates B-02, which gates B-03 and B-13 permissions). **[V]** for the chain in the backlog; **[E]** for the method.
- Noticing structural drift in the records themselves (section 6.3).
- Judging when a stacked branch needs retargeting rather than a rebase, and flagging the risk to the person who does the git work. **[E]**

## 4. Standards, frameworks and qualifications

Only those genuinely relevant. None is a requirement for Dex; they inform method.

- **AIPM.** The Australian Institute of Project Management offers certification in three levels: project team member or specialist (QPP), project manager (RPM) and project director or program manager (MPD) per a search-result summary; the QPP level is the nearest fit to a coordinator. I found no AIPM competency standard specific to a coordinator or PMO administrator, and could not read aipm.com.au. **[V, secondary]** Source: search summary, with a related [University of Sydney competency matrix](https://cusp.sydney.edu.au/attributes/view-attribute-set-pdf/competency_set_id/70) noting alignment to RegPM levels. **Treat as unconfirmed until checked on the AIPM site.**
- **APM (UK) role profiles** for [PMO officers and specialists](https://www.apm.org.uk/media/hh1d5iae/cf-role-profile-pmo-officers-and-specialists-final.pdf) and [PMO analysts](https://www.apm.org.uk/media/0etn3iig/cf-role-profile-pmo-analyst-final.pdf) exist and are the nearest published competence descriptors. I saw only their titles in search results; I did not read them. **[V]** that they exist, not for their content.
- **PMI and PRINCE2, P3O.** Recruiters list these (alongside AIPM) as desirable for PMO coordinators ([Chandler Macleod listing](https://www.chandlermacleod.com/job-details/integration-pmo-coordinator-in-office-support-jobs-1343134), per search summary). **[V, secondary]**
- **ISO 10007 (configuration management guidelines), adopted in Australia as AS ISO 10007:2017.** Its structure covers planning, configuration identification including baselines, change control, status accounting and audit; status accounting is formal recording and reporting of configuration information, proposed changes and the implementation status of approved changes. This is the best conceptual fit for Dex's registrar duties. **[V, secondary]** from [ISO 10007:2017 listing](https://iteh.es/catalog/standards/iso/a779c3ed-00ca-4798-9a60-8f07ee800b8f/iso-10007-2017), the [Standards Australia store entry](https://store.standards.org.au/product/as-iso-10007-2017) and a [vendor guide](https://aras.com/wp-content/uploads/2024/03/configuration-management-iso-9001-10007-quality-cmii.pdf). A listing showed both "Current" and "Superseded" tags, so confirm status with Standards Australia. The full text was not read; used for concepts only.
- **Git hosting practice for stacked branches.** Official GitHub and GitLab pages (via search summary) say: merge a stack from the bottom up; the bottom pull request targets trunk; GitLab retargets the next merge request to the default branch automatically on merge; GitHub's stacked pull request feature is in public preview and may change. Sources: [GitHub reference](https://docs.github.com/en/pull-requests/reference/stacked-pull-requests), [GitLab docs](https://docs.gitlab.com/user/project/merge_requests/reviews/stacked_merge_requests/). **[V, secondary]**. Community advice to record each PR number and head SHA before merging, and to push with `--force-with-lease`, is practitioner guidance only ([OpenReplay](https://blog.openreplay.com/stacked-pull-requests-github/)). **[E]**
- **Electrical engineering standards (AS/NZS, AEMO, NER).** Not relevant to this role. Dex records work on a software tool; none applies.

## 5. Tools and methods

- **Plain-text records:** `docs/backlog.md`, `docs/release-log.md`, read from `docs/areas.md`, `docs/decisions.md`, `docs/open-questions.md`. **[V]**
- **Git, read-only:** `git log`, `git branch`, `git diff --stat`, `git diff <a>...<b> --name-only` to find shared-file overlaps. **[E]** `gh pr list` and `gh pr view` to read PR state, base branch and review status (the `gh` CLI is preconfigured in this environment). **[V]**
- **Method:** (1) read the evidence; (2) change a record only as far as the evidence supports; (3) cite the evidence in the line written; (4) run `git diff --stat` and confirm only `docs/` changed (as TALLY-BOT does); (5) report. **[V]** for steps 4 and 5, **[A]** for the rest.
- **Queue method:** list open PRs; for each, note base branch, files changed, area, backlog ID; mark stacked ones; order by dependency and by shared-file rule ("shared-file branches merge first", `docs/areas.md`); flag clashes. **[V]** for the shared-file rule, **[A]** for the rest.

## 6. How the work is judged

### 6.1 Quality measures **[E]**, applied to PMT **[A]**

- **Accuracy:** every stage matches the evidence; every log line is true.
- **Timeliness:** recorded at the end of the unit of work, per HANDOFF rule 3 ("in the same turn"). **[V]**
- **Traceability:** each change links to a backlog ID, a PR or a statement of what was done.
- **No silent edits:** nothing changed that is not reported; earlier release-log entries never rewritten (TALLY-BOT rule). **[V]**
- **Brevity:** a status view fits one screen.

### 6.2 Common failure modes

- **Stale registers:** the backlog says Build while the PR merged a week ago, or the reverse. **[E]**
- **Marking done before merged:** TALLY-BOT already forbids Done without a stated merge. Dex should check the PR state, not only the account. **[V]** for the rule.
- **Double-counting:** the same work logged twice, for example once on the item branch and once at merge, or one change counted under two IDs. **[E]**
- **Lane confusion:** an item assigned to the wrong area lane; `docs/areas.md` itself says its thread mapping is a first mapping to be corrected. **[V]**
- **Queue errors:** a stacked branch left pointing at a merged parent; two branches changing one shared file without warning. **[E]**
- **Status without a source:** "blocked" with no owner, date or unblocker. **[E]**
- **Stating inference as fact:** guessing a PR's state from a branch name. **[E]**

### 6.3 Inconsistencies in the current records that Dex should flag, not fix **[V]**

I found these while reading; I changed nothing.

- The backlog header lists the stages as Idea, Spec, Design agreed, Build, Test, Review, Done, but rows also use "Needs decision" (B-09, B-15, B-18) and "Idea (check)" (B-06, B-08). TALLY-BOT's allowed stage list matches the header, so these would not be settable by it.
- The backlog states it was seeded on 31/10/2026 and the release-log header says 2026-10-31. These are correct in AEST (UTC+10); the machine clock is UTC and showed 30/10/2026 at the time.
- The release-log header says "one line per release", while TALLY-BOT says "one line to the end of the file" in the form date, ID, sentence. The file tail holds long multi-clause release lines, so the exact format is not uniform.
- HANDOFF rule 3 says the bundle version is bumped only on merge to `main`. `HANDOFF.md` is outside `docs/`, so whether Dex may touch it is unclear (see section 7).

## 7. Boundaries and escalation

**Must not (from the brief and CLAUDE.md):** edit code; merge; commit to `main` (GATE-BOT blocks it); change files outside the docs set it owns; touch databases, `crm_link.txt` or real project data. **[V]**

**Refer to Vincent:**
- Priority (the backlog leaves it blank on purpose), merge order when it is a trade-off, and every merge.
- Changes to `docs/decisions.md` or `docs/open-questions.md`: propose wording only. **[V]** (TALLY-BOT rule 4)
- Items "waiting on Vincent" (real Wandoan data, Pronto export, templates, Copilot Studio decision). **[V]** (backlog footer)
- Whether Dex may edit `HANDOFF.md` and `docs/threads.md` (this brief says docs only; it does not name them). **[A]**

**Refer to the internal owner:** HR-dependent items (B-03, B-17) and IT-dependent items (B-12) go to HR or IT through Vincent; Dex records the dependency and does not rule. Access, licensing or security incidents go to IT. Per EPEC organisation instructions.

**Refer to the code-owning session or SENTRY-BOT:** whether a branch conflicts with a decision is SENTRY-BOT's check, not Dex's. Git fixes (rebase, retarget, force-push) are done by the session that owns the branch or by Vincent; Dex reports the need. **[A]**

**Overlap to resolve:** TALLY-BOT already sets stages and adds release-log lines. Dex's distinct value is the merge queue and the status views. Vincent should decide whether Dex replaces TALLY-BOT, calls it, or shares its rules, to avoid two writers on one record (the double-counting failure above). **[A]**

## 8. What an AI version can and cannot do

**Can:**
- Read the backlog, release log, areas file and git/PR metadata fast and consistently.
- Cross-check them and list mismatches, shared-file overlaps and stale stages.
- Draft exact edits to docs with the evidence quoted, and give a status view on request.
- Apply the same rule every time (no Done without a merge; no rewriting history).

**Cannot, or must not, alone:**
- Merge, commit to `main`, or approve anything.
- Know what happened outside what it can read: a merge Vincent did elsewhere, a verbal decision, an agreement in a meeting. It must ask.
- Set priority, resolve a decision, or interpret HR, legal or WHS policy.
- Verify that code works; it records test results others report.
- Persist memory between sessions: the records in the repo are the only memory, which is a reason to keep them accurate. **[E]**
- Detect a silent change made by another session between its read and its write; it should re-read before writing and state the commit it read from. **[A]**

**Needs a human:** merging; priority; any conflict between records and reality that the evidence cannot settle.

## 9. Sources

Linked inline above. Summary, with strength:

| Claim | Source | Strength |
|---|---|---|
| Advertised coordinator duties (RAID, change log, status, meetings) | [Lorien](https://www.itjobswatch.co.uk/jv/Lorien/PMO-Coordinator-Job-Havant-Hampshire-England-UK-4vy1oo), [Hays](https://www.hays.co.uk/job-detail/project-co-ordinator-(pmo-programme-support-analyst)-hatfield_4814359), [ERSG](https://www.ersg-global.com/job/pmo-coordinator) | Search summary of job ads; indicative |
| RAID ownership is contested | [PM forum](https://www.projectmanagement.com/discussion-topic/99521/issues---raid-log?pageNum=1) | Search summary; indicative |
| AIPM levels, no coordinator standard found | search summary; [Univ. of Sydney](https://cusp.sydney.edu.au/attributes/view-attribute-set-pdf/competency_set_id/70) | Secondary; AIPM site unreachable |
| APM PMO role profiles exist | [officers](https://www.apm.org.uk/media/hh1d5iae/cf-role-profile-pmo-officers-and-specialists-final.pdf), [analysts](https://www.apm.org.uk/media/0etn3iig/cf-role-profile-pmo-analyst-final.pdf) | Existence only; not read |
| ISO 10007 structure, status accounting | [iTeh](https://iteh.es/catalog/standards/iso/a779c3ed-00ca-4798-9a60-8f07ee800b8f/iso-10007-2017), [Standards Australia](https://store.standards.org.au/product/as-iso-10007-2017), [Aras guide](https://aras.com/wp-content/uploads/2024/03/configuration-management-iso-9001-10007-quality-cmii.pdf) | Secondary; full text not read |
| Stacked PR merge order | [GitHub](https://docs.github.com/en/pull-requests/reference/stacked-pull-requests), [GitLab](https://docs.gitlab.com/user/project/merge_requests/reviews/stacked_merge_requests/), [OpenReplay](https://blog.openreplay.com/stacked-pull-requests-github/) | Official pages via summary; blog is practitioner |
| PMT rules, stages, lanes, boundaries | [CLAUDE.md](/home/user/pmt/CLAUDE.md), [HANDOFF.md](/home/user/pmt/HANDOFF.md), [docs/backlog.md](/home/user/pmt/docs/backlog.md), [docs/areas.md](/home/user/pmt/docs/areas.md), [.claude/agents/tally-bot.md](/home/user/pmt/.claude/agents/tally-bot.md) | Read directly |

## 10. Gaps

- AIPM, APM and GitHub documentation sites were unreachable (host not resolvable); their content is second-hand. Allow apm.org.uk, aipm.com.au and docs.github.com in the session network if a primary check is wanted.
- No AIPM or other Australian standard specific to a PMO administrator found; I could not confirm one does not exist.
- ISO 10007 and AS ISO 10007 full text not read; current status of the Australian adoption unconfirmed.
- Job ads were mainly UK, with some Australian and others; Australian EPC-specific PMO administrator practice was not separately sourced.
- Open for Vincent: Dex versus TALLY-BOT overlap; whether Dex may edit `HANDOFF.md` or `docs/threads.md`; the stage vocabulary and date inconsistencies in section 6.3; who owns git retargeting.
