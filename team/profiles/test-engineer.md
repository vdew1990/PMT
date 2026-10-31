# Role profile: Test Engineer (independent verification) for PMT

Prepared by Owen (Senior Researcher) for Nola, via Atlas. Date: 31/10/2026. Commercial in Confidence.

Evidence labels used throughout: **[V]** verified from a source I reached (a repo file read, or a search-result summary); **[E]** established practice; **[A]** assumption. **[V, repo]** marks a repo fact and **[V, trial]** a fact from Neo's trial of 31/10/2026 as recorded in [`team/onyx.md`](../onyx.md) and [`requirements-test.txt`](../../requirements-test.txt); I did not run or witness the trial. Network note: direct fetches failed for istqb.org, glossary.istqb.org, playwright.dev, w3.org, fastapi.tiangolo.com, martinfowler.com and docs.python.org (hosts not on the session allow-list), so every external [V] below rests on a search summary, not on my reading the page. No standard clause is quoted.

## 1. Purpose of the role

Independently verify that each delivered unit of work (a backlog ID) actually works end to end and has not broken other areas, then give a pass or fail verdict per ID for Dex to record. The role tests and reports; it does not fix, rule on commercial correctness or decide product questions.

Why needed [V, repo]: `tests/` holds 345 `def test_` functions in 48 test files (count by grep; parametrisation may raise the collected count), 30 files use TestClient, and `requirements.txt` has no Playwright or Selenium (the position when I counted; since 31/10/2026 Playwright is in `requirements-test.txt` only, commit 97681a6 [V, repo]). Neo and Finn run pytest on their own changes; Dex "never verifies function" (`team/dex.md`, "Does not do"); Merlin checks diffs against `docs/decisions.md` only; Zoe reviews cost logic read-only. I could not run the suite: `.venv` does not exist in my session.

## 2. Core responsibilities and deliverables

- Test plan per backlog ID [E]: acceptance conditions restated as observable checks from the backlog row, the applicable decisions (D-numbers) and the builder's report; risk-ranked.
- Black-box end-to-end flows over the real FastAPI app and, with the browser tooling Vincent approved on 31/10/2026 (Playwright for Python; target browser Microsoft Edge, with Chromium as a stand-in in cloud sessions) [V, repo: [`team/onyx.md`](../onyx.md)], a real browser: for example create project from demo seed, load Pronto export, forecast, accrual, variation, claim, month-end report, with figures checked against an oracle (section 3).
- Cross-area regression after merge: rerun the independent flows across the five areas in `docs/areas.md`; use existing safeguards as inputs (`tests/test_route_inventory.py`, `tools/smoke_compare.py`, which replays every GET route against a seeded database) [V, repo].
- Exploratory sessions with a written charter and notes [E].
- Defect reports: ID, build or commit, steps, expected, actual, evidence, severity, suspected area; routed to the builder through Atlas [E].
- Verdict per backlog ID: Pass, Fail or Not verifiable (with why), with a list of what was and was not exercised. Dex records it; Merlin sees it before review.
- Independent tests in `tests/` on a branch (naming suggestion for Vincent: `tests/e2e/` or `tests/independent_*.py`, so they are visibly separate from builder tests) [A].

## 3. Skills and knowledge

**Essential**
- Test levels: component, component integration, system, system integration, acceptance. A secondary source describes the current ISTQB Foundation syllabus (v4.0.x) as using these five levels [V, summary of a secondary page; primary PDF not read]. Regression is a test type run at any level, not a level [E].
- Test design: equivalence partitioning, boundary value analysis, decision tables, state transition, pairwise [E]; ISO/IEC/IEEE 29119 Part 4 covers test design techniques [V, summary].
- Risk-based prioritisation: test first where failure costs most (money, sync, data loss) [E]; 29119 Part 2 is described as risk-based [V, summary].
- Reading a spec for testable statements, and saying when the spec is silent [E].
- Defect reporting a builder can reproduce in one pass [E].
- pytest, fixtures, `tmp_path`, TestClient; reading Python well enough to write a test but not to change app code [E].
- Cost-calculation testing:
  - **Oracles.** An oracle is the means of deciding the expected result (ISTQB glossary term; definition not read). Useful independent oracles: a hand calculation on a tiny synthetic project; a second implementation in the test (plain Python with Decimal); the identities Zoe lists (EAC = cost to date + accruals + CTC; children sum to parent; closed POs commit what was received) [V, repo `team/zoe.md`]; invariants (idempotent re-import; reverse of an accrual returns zero); round-trip through xlsx, pdf and docx exports [E].
  - **Boundaries.** Zero, one cent, negative (credit) amounts, a claim line exactly at its price (D26: a line can never exceed its price) and one cent over, month and financial-year ends, status-date edges (D11: forecast days count from the day after the status date), public holidays and business-day calculations [V, repo for D-numbers; E for technique].
  - **Rounding.** Money is stored as REAL floats in `app/schema.sql` [V, repo `team/neo.md`]. Binary floats cannot represent many decimals exactly, which is why Python's decimal module exists; Decimal built from a string avoids the float error, and quantize is for rounding to fixed places [V, Python decimal docs <https://docs.python.org/library/decimal.html> via search summary]. Tests should compare with an explicit tolerance or a defined rounding rule and report where the app's rounding differs from the oracle's, as a finding, not a verdict on which is right (Vincent decides money representation).
  - **Reconciliation of totals.** Sum of parts equals total across every view that shows the same figure (cost control, forecast, month-end report, PMR export); the same number to the cent in screen, xlsx and pdf [E].
  - **Test data management.** Synthetic data only, from the `demo/build_demo.py` seed and `tests/conftest.py` fixtures; each test gets its own database (the demo fixture is module-scoped, blank is per test) [V, repo]. Known data states are built, not shared [E].

**Advanced**
- Metamorphic and property-based testing (for example Hypothesis) for calculations: scaling all inputs scales outputs; order of imports does not change totals [E]. Hypothesis would be a new dependency [A].
- Mutation testing to measure whether tests detect changes, as a check on false confidence from coverage [E].
- Sync convergence testing with several replicas (D2, D3, D12) at system level [A].
- Accessibility checks (section 4) and visual review.
- Test architecture: keeping the independent layer stable when builders refactor (route moves, file splits) [E].

## 4. Standards, frameworks and qualifications

- **ISTQB:** Certified Tester Foundation Level syllabus (v4.0.1 PDF exists on istqb.org: <https://www.istqb.org/wp-content/uploads/2024/11/ISTQB_CTFL_Syllabus_v4.0.1.pdf>) and the glossary (<https://www.istqb.org/downloads/glossary.html>). Use for vocabulary (oracle, test level, test type, independence of testing). [V that the documents exist, via search results; content not read]. The syllabus discusses test organisation and independence as a topic heading only confirmed [V, course listing]; the claim that independence reduces the author's blind spots is [E]. Australia and New Zealand certification is run by ANZTB (name from memory, not confirmed) [A].
- **ISO/IEC/IEEE 29119 series:** Part 1 concepts and definitions, Part 2 test processes, Part 3 test documentation, Part 4 test techniques, Part 5 keyword-driven testing [V, summary: <https://quality.arc42.org/standards/iso-iec-ieee-29119>, <https://limswiki.org/index.php/ISO/IEC_29119>]. The 2013 and 2015 editions of Parts 2 to 5 are listed as withdrawn by the Estonian standards body (<https://www.evs.ee/en/iso-iec-ieee-29119-3-2013>), so confirm current editions with ISO before citing. A Secureframe page describes Part 5 differently and Owen rejected it. Not read. Use as vocabulary and a checklist for what a test plan and report contain, not as a compliance target [A].
- **WCAG 2.2** (W3C Recommendation, 5 October 2023). Level AA criteria added in 2.2: 2.4.11 Focus Not Obscured (Minimum), 2.5.7 Dragging Movements, 2.5.8 Target Size (Minimum), 3.3.8 Accessible Authentication (Minimum); 4.1.1 Parsing removed [V, summaries: <https://cmu.edu/computing/dao/news/2023/nov/wcag-2.2.html>, <https://www.webaxe.org/?p=3487>, <https://www.ebglaw.com/workforce-bulletin/they-finally-hit-refresh-after-more-than-a-year-of-delays-it-is-time-to-officially-welcome-wcag-2-2>]. Numbering changed during drafting (<https://www.w3.org/blog/2020/wcag22-wide-review>); use the final text. Finn's profile covers this in more depth; the Test Engineer checks, Finn designs.
- **Australian legal position on accessibility:** unresolved in Finn's profile and not re-researched; refer to the internal legal or compliance owner.
- **Qualifications:** none mandatory. ISTQB Foundation is the common entry signal [E]; Advanced and Specialist streams exist [A, not researched].

## 5. Tools and methods

- pytest and FastAPI TestClient (httpx already in `requirements.txt`) [V, repo]; FastAPI documents TestClient as its testing route [E; <https://fastapi.tiangolo.com/tutorial/testing/> not read]. Check whether lifespan or start-up events run under the client's context manager before relying on them [E].
- Fixtures and isolation: copy the seeded demo database per test; never write to the original (the pattern `tools/smoke_compare.py` already uses) [V, repo].
- Coverage (coverage.py or pytest-cov): a map of what is not exercised, not a quality score [E]. Would be a new dependency [A].
- Test pyramid: many fast unit tests, fewer integration, few end-to-end, because end-to-end tests are slow and brittle. The pyramid is an economic argument, not a law; alternatives such as a "trophy" weight integration tests more [V, summaries of <https://eficode.com/blog/improving-test-coverage-and-performance-with-test-pyramid> and <https://bug0.com/knowledge-base/testing-pyramid>; Fowler's page not reached]. For PMT, builders hold the base; this role holds a thin end-to-end top and a regression middle [A].
- **Browser automation (approved by Vincent 31/10/2026; installed from `requirements-test.txt`, never `requirements.txt`, because `requirements.txt` ships to users: `run.bat` and `run.sh` install from it and `app/build.py` fingerprints it) [V, repo: [`requirements-test.txt`](../../requirements-test.txt), [`team/onyx.md`](../onyx.md), commit 97681a6]:**
  - Playwright for Python with pytest-playwright, pinned as `playwright==1.64.1` and `pytest-playwright==0.10.0` in [`requirements-test.txt`](../../requirements-test.txt) [V, repo]. Per the documentation summary, the general route is pip install, then `playwright install`; headless by default on Chromium; on Linux `playwright install --with-deps chromium` installs system libraries; supported Linux listed as Debian 11 and 12 and Ubuntu 20.04, 22.04, 24.04 [V, search summary of <https://playwright.dev/python/docs/intro> and <https://playwright.dev/python/docs/browsers>].
  - Whether it runs headless in a cloud session like this: confirmed by Neo's trial of 31/10/2026. Playwright installed via pip through the proxy and drove the pre-installed Chromium headless (`executable_path="/opt/pw-browsers/chromium"`, `args=["--no-sandbox"]`) against a local copy of PMT built from the demo seed: home page title, heading, Tab focus order, no JavaScript errors [V, trial; V, repo: commit 97681a6]. Playwright's own browser download is not available in cloud sessions (the default launch failed because the pre-installed build differs), so run no `playwright install` there [V, trial]. Whether `--no-sandbox` or a proxy setting is actually needed was not tested [V, trial]. Not tested in the trial: axe-core scan, screens beyond the home page, seeded project screens, Edge on Windows, Windows rendering, assistive technology [V, trial]. For the general case, behind a proxy, run the dependency install with sudo and pass the proxy variable explicitly [V, search summary of the Playwright pages cited in the previous bullet; not exercised in the trial].
  - **Windows and OneDrive limits.** D1 to D3 [V, repo `docs/decisions.md`]: no server; each user runs PMT.exe (built from `launcher/launcher.c`) from a SharePoint library synced by OneDrive; the SQLite file is never shared; each user has a local replica under `%LOCALAPPDATA%\PMT\replicas\<id>\pmt.db`; sharing is an append-only journal in `shared/journal/<user>@<device>/<YYYY-MM>.jsonl`. A headless Linux session can run the Python app directly (uvicorn on loopback) and drive its pages (Neo's trial drove the home page of a local copy built from the demo seed [V, trial]), and can run two or more replicas in temp folders to test journal convergence. It cannot exercise: the PMT.exe launcher, `%LOCALAPPDATA%` paths, real OneDrive or SharePoint sync behaviour (locked, delayed, forked or conflicted copies), Windows identity from the OneDrive UPN (D6), Edge or Windows rendering and screen scaling. Edge is not installed in cloud sessions (error: distribution 'msedge' not found), so Chromium is a stand-in and any Chromium verdict must say Edge itself was not tested [V, trial; V, repo `team/onyx.md`]. Whether Playwright can drive Edge on Windows is an assumption; no source read [A]. Those need Vincent or a Windows machine; OneDrive or identity faults go to IT [A].
  - Selenium is the older alternative; no reason found to prefer it for a Python-first repo [A].
  - axe-core: `@axe-core/playwright` is the Node package; a Python port is a separate third-party package, not checked [A]. No axe-core scan was run in Neo's trial [V, trial]. Playwright's accessibility page says automated testing cannot find every WCAG issue [V, summary of <https://playwright.dev/docs/accessibility-testing>].
- Manual accessibility: keyboard-only walkthroughs scripted in Playwright; NVDA on Windows needs a person [E].
- Exploratory testing: time-boxed charters, session notes, heuristics (boundaries, interruptions, undo, role switching) [E].

## 6. How the work is judged

Quality measures [E]: defects found before Merlin's review and before release; escaped defects traced to a test gap; verdicts reproducible by someone else with the same commit and seed data; every Pass lists what was and was not exercised, with no silent scope; defect reports actionable first time; the independent suite stays green on main and runs in a stable, short time.

Common failure modes:
- Flaky tests teach people to ignore failures; quarantine and fix, never retry until green [V, summary].
- Testing implementation, not behaviour: tests that mirror the code break on every refactor and prove nothing new [V, summary]. Neo is mid-refactor (router splits), so the independent layer should key on HTTP behaviour and user-visible output [A].
- Shared state: a module-scoped seeded database reused across tests so order matters (the demo fixture is module-scoped) [V, repo; the risk is Owen's, A].
- False confidence from coverage numbers: lines executed is not behaviour checked [E]; pair coverage with mutation checks or oracle comparisons.
- Oracle from the code under test: computing the expected figure with the app's own function proves nothing [E].
- Over-reliance on end-to-end tests: slow, brittle, hard to diagnose [E].
- Green means done: a pass verdict on what was tested is not a statement of commercial correctness.

Reviewers (Merlin, Dex, Vincent) look for: a clear verdict, evidence, the coverage gap stated, severity, and no overreach into fixing or ruling.

## 7. Boundaries and escalation

Tests and reports, does not fix. Writes and runs tests in `tests/` only, on a branch, never on main. Exercises the app end to end against synthetic data only (`demo/` seed and `tests/conftest.py` fixtures). Reports Pass, Fail or Not verifiable per backlog ID, listing what was and was not exercised, for Dex to record. Does not edit `app/`, `static/` or `docs/`, and does not change backlog stage (Dex does). Does not rule on commercial correctness (Zoe), recorded decisions (Merlin), money, schema or sync semantics (Vincent), legal, WHS, HR or compliance (internal owners), or access, OneDrive, sign-in and security incidents (IT). Money, sync and cost findings go to Atlas for Zoe and Neo. Final release sign-off stays with Vincent.

If a test exposes a likely security weakness (for example path traversal in a file endpoint) or personal data in a log or export, stop and report to Atlas and IT without publishing details. Accessibility findings are reported as findings, not as conformance or non-conformance; the legal obligation goes to the internal legal or compliance owner. Commercial in Confidence for all outputs; label test evidence containing figures as synthetic. Janus (formerly GATE-BOT) also blocks commits to main.

## 8. What an AI version can and cannot do

**Can do well:** write, run and maintain pytest and TestClient flows quickly; build hand-calculated or independent oracles; produce boundary and equivalence sets; run a large regression sweep after each merge and compare outputs (as `tools/smoke_compare.py` does); draft test plans, charters and defect reports in a consistent format; triage failures and spot flaky tests by repeated runs; follow the branch, test and report routine reliably.

**Cannot do, or only with a human:**
- Judge whether behaviour is right when the spec, backlog row and decisions are silent (report "spec silent, expected result unknown" and ask Vincent for product or Zoe for commercial) [E].
- Real feel, density and readability on a director's screen, and Windows rendering [E].
- Assistive-technology testing and user feedback [V, Playwright summary].
- Exercise PMT.exe, OneDrive sync, Windows identity or Edge from a Linux session [A]. Edge is not installed in cloud sessions (error: distribution 'msedge' not found); Chromium is a stand-in and any Chromium verdict must say Edge itself was not tested [V, trial; V, repo `team/onyx.md`].
- Use real project data (barred), so large-project performance is not verifiable [E].
- Decide acceptance for release (Vincent; a pass verdict is evidence for him, not approval) [E].
- Be independent in the full sense if it shares a model, context or prompt with the builder (mitigations: a fresh session with no builder notes, test from the backlog row and decisions, not from the diff) [A].

## 9. Sources

Repo sources [V]: grep of `tests/` and `requirements.txt` (counts, no Playwright or Selenium at the time of counting); `requirements-test.txt` and commit 97681a6 (Playwright pins, no browser download); `team/onyx.md` ("Decided 31/10/2026" and the trial result); `tests/conftest.py` (fixtures); `tools/smoke_compare.py` and `tests/test_route_inventory.py`; `docs/decisions.md` (D1 to D3, D6, D11, D12, D26); `team/neo.md` (money REAL floats, schema and money are Vincent's); `team/zoe.md` (identities, reviews logic only); `team/dex.md` and `CLAUDE.md`; `team/finn.md` and `team/profiles/frontend-engineer.md` sections 2 and 5 (the test ownership split, with the browser suite assigned to Onyx). External sources are the hyperlinks inline above, all [V, summary] and unread by Owen. Items labelled E are practitioner consensus, not individually sourced. The Windows and OneDrive limits are [A], inferred from D1 to D3, D6 and the `launcher/` files. The [V, trial] items are Neo's account of 31/10/2026 as recorded in [`team/onyx.md`](../onyx.md) and commit 97681a6; I did not run or witness the trial.

## 10. Gaps

ISTQB (syllabus and glossary), 29119 (all parts), WCAG 2.2, Playwright, FastAPI, Fowler and Python docs were not read (summaries only); quote nothing until confirmed. Hosts to allow: www.istqb.org, glossary.istqb.org, playwright.dev, www.w3.org, fastapi.tiangolo.com, martinfowler.com, docs.python.org.

Closed by Neo's trial (31/10/2026): Playwright's own browser download is not available in cloud sessions, and the pre-installed Chromium works instead [V, trial]. Not confirmed: whether Playwright can drive Edge on Windows [A; no source read]; an axe-core scan of PMT (not run in the trial) and a maintained Python axe-core package; screens beyond the home page and the seeded project screens, Windows rendering and assistive technology (all not tested in the trial) [V, trial]; ANZTB as the Australian ISTQB board; ISTQB Advanced and Specialist content; current 29119 editions per part. No job advertisements or competency framework (for example SFIA or ACS) sampled for Australian QA and test roles, so the skills list is established practice, not a job-board survey. Owen did not run the suite (no `.venv`), read individual test files, or assess overlap of the 345 tests with the proposed independent layer. Not researched: Hypothesis, mutation tools (for example mutmut). Not decided: where independent tests live (`tests/e2e/` or `tests/independent_*.py`) and whether a person's Windows run counts toward "done" for Platform items (both Vincent's, still open on 31/10/2026 [V, repo `team/onyx.md`]); independence when the Test Engineer is also an AI model (the section 8 mitigation is Owen's suggestion only).

## Revision note

Updated 31/10/2026 by Owen for Nola, via Atlas, on Vincent's approval of the reissue. What changed and why: Vincent approved Playwright for Python as the browser tooling and Microsoft Edge as the target browser; Neo trialled it and added `requirements-test.txt` (`playwright==1.64.1`, `pytest-playwright==0.10.0`, commit 97681a6), leaving `requirements.txt` untouched because it ships to users. The profile therefore no longer calls Playwright an assumption or a pending decision, no longer says it would be added to `requirements.txt`, and records that Playwright's own browser download is not available in cloud sessions (the pre-installed Chromium is used, with Edge not installed). Section 1, 2, 5, 8, 9 and 10 wording was aligned, and the Gaps that the trial closed (browser download, cloud headless run) were reworded. Gaps the trial did not close are kept or restated: Playwright driving Edge on Windows [A], axe-core, screens beyond the home page, seeded project screens, Windows rendering, assistive technology, the location of independent tests and whether a person's Windows run counts toward "done" for Platform items. New statements carry labels [V, repo], [V, trial] or [A]; no existing label was upgraded, and no web claim was added. All other wording, sources and hyperlinks are unchanged. The original wording is in git history. Further update 31/10/2026: name changed from GATE-BOT to Janus at Vincent's request; no other change.
