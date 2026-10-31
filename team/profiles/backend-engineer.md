# Role profile: Senior Backend Engineer (Python, FastAPI, SQLite) for PMT

Prepared by Owen (Senior Researcher) for Nola, via Atlas. Date: 30/10/2026. Commercial in Confidence.

Evidence labels used throughout: **[V]** verified from a source I read; **[E]** established practice (widely accepted, not verified by me in this session); **[A]** assumption. Repo facts marked [V-repo] were read from /home/user/pmt this session.

**Source limitation.** In this session the network blocked every primary documentation host I tried (fastapi.tiangolo.com, sqlite.org, docs.python.org, docs.pytest.org, oaic.gov.au, cyber.gov.au, martinfowler.com all failed to resolve). One web search returned third-party mirrors of the SQLite ALTER TABLE page. Links below marked "not read" are the pages a reviewer should confirm; I have not quoted from them.

## 1. Purpose of the role

Own the correctness, structure and safety of PMT's Python backend: split the monolithic `app/main.py` into per-area routers without changing behaviour, keep the SQLite schema and the journal-based multi-user sync trustworthy, and make sure every dollar figure shown to a project manager is right. [A, from the brief]

## 2. Core responsibilities and deliverables

- **Router split.** Move the roughly 350 routes (349 route decorators counted [V-repo]) from `app/main.py` into `APIRouter` modules aligned to the five areas in `docs/areas.md` (Cost and Forecast, Revenue and Subcontracts, Setup and Team, PMO and Reporting, Platform). Deliverable: a sequence of small branches, each moving one router, with a before and after route inventory showing no change in method, path, status codes or response shape. `main.py` is a shared file that must merge first in short branches [V-repo, `docs/areas.md` and `HANDOFF.md` rule 4].
- **Schema and migration.** Maintain `app/schema.sql` (73 CREATE TABLE statements [V-repo]) and the additive `MIGRATIONS` list in `app/db.py` [V-repo]. Deliverable: versioned, idempotent, tested migrations, plus a rebuild procedure for changes SQLite cannot do in place.
- **Sync and conflicts.** Maintain `app/sync.py`, `changelog.py` and `identity.py`: append-only per-writer journals, last-writer-wins per column on a hybrid clock, slotted row ids, deterministic duplicate-key resolution (decisions D1 to D5, D12 [V-repo, `docs/decisions.md`]). Deliverable: tests that simulate several writers and prove every replica converges.
- **Financial correctness.** Own the calculation modules (`engine.py`, `forecast.py`, `revenue.py`, `variations.py` and others): money handling, rounding, allocation, reconciliation to Pronto data.
- **Tests and tooling.** Keep `.venv/bin/python -m pytest tests -q` green before and after every change (CLAUDE.md [V-repo]); add characterisation tests before touching code.
- **Security and data handling** for a local app holding personal data (names, UPNs, emails, phone numbers appear in the schema [V-repo]).
- **Review** of other sessions' backend changes (see section 6).

## 3. Skills and knowledge

**Essential**
- Python 3 and FastAPI: `APIRouter`, `include_router` with prefix and tags, dependencies, Pydantic models, lifespan and startup. Router splitting is the documented route for bigger applications (FastAPI "Bigger Applications", [not read](https://fastapi.tiangolo.com/tutorial/bigger-applications/)) [E].
- SQLite: transactions, WAL, foreign keys (off by default and enabled per connection, as `db.connect` does [V-repo]), triggers, indexes, type affinity, `PRAGMA user_version`, `PRAGMA foreign_key_check`, `PRAGMA integrity_check`.
- pytest: fixtures and scopes, `tmp_path`, parametrisation, isolating the database per test (see `tests/conftest.py` [V-repo]).
- Reading unfamiliar code and preserving behaviour precisely, including undocumented behaviour.
- Plain-language communication with a non-developer owner (Vincent) who approves plans before builds ("confirm the plan, wait for go" [V-repo, `HANDOFF.md`]).

**Advanced**
- Distributed-systems reasoning for sync: clocks, causality, idempotent replay, convergence, tombstones, out-of-order arrival.
- Schema rebuilds in SQLite using the generalised procedure: disable foreign keys, transaction, create new table, copy, drop, rename, recreate indexes and triggers, run `foreign_key_check`. This is [V via a mirror](https://sqlite.org/draft/lang_altertable.html) (draft page returned by search; the released page at [sqlite.org/lang_altertable.html](https://www.sqlite.org/lang_altertable.html) was not reachable, so confirm step order against it). Native ALTER TABLE covers only rename table, rename column, add column and drop column [V, same source].
- Domain literacy in EPC cost control: budget, committed, accrual, EAC, forecast, variation, claim, retention, GST-exclusive amounts. [A] The engineer need not be an electrical engineer, but must be able to read `docs/threads.md` and ask the right questions.
- Windows desktop deployment (PyInstaller-style `PMT.exe`, launcher, file locking, antivirus and OneDrive behaviour). [A]

## 4. Standards, frameworks and qualifications

No Australian electrical standard (AS/NZS, AEMO, NER) governs this role; none is cited. Relevant references:

- **Privacy Act 1988 (Cth), Australian Privacy Principles**, in particular APP 11 on security of personal information: [OAIC APP guidelines](https://www.oaic.gov.au/privacy/australian-privacy-principles) (not read). Whether EPEC is an APP entity and how the Act applies to staff contact data is a legal question for the internal owner [E].
- **ACSC Essential Eight** as a baseline for endpoint hygiene: [cyber.gov.au](https://www.cyber.gov.au/resources-business-and-government/essential-cyber-security/essential-eight) (not read). Relevant to patching, application control and backups on user PCs [E].
- **OWASP Top 10 and ASVS** as a review checklist for web APIs, even for a localhost service: [owasp.org/Top10](https://owasp.org/Top10/) (not read) [E].
- **Python `decimal` module** for exact money arithmetic and explicit rounding modes: [docs.python.org/3/library/decimal.html](https://docs.python.org/3/library/decimal.html) (not read) [E].
- **SQLite documentation**, notably "How To Corrupt An SQLite Database File": [sqlite.org/howtocorrupt.html](https://www.sqlite.org/howtocorrupt.html) (not read). It is the usual authority on why copying or syncing a live database is unsafe, which is consistent with decision D2 (the database is never shared) [E; D2 is V-repo].
- **Refactoring and characterisation tests**: Fowler on refactoring as behaviour-preserving restructuring ([martinfowler.com/bliki/Refactoring.html](https://martinfowler.com/bliki/Refactoring.html), not read) and Feathers, *Working Effectively with Legacy Code* (book, not read) [E].
- Qualifications: no licence is required. Typical evidence is a degree in computer science, software or electrical engineering, or equivalent experience, plus a verifiable record of maintaining a large Python codebase. [A]

## 5. Tools and methods

- Git branch per item, never commit to `main` (CLAUDE.md, enforced by Janus hook [V-repo, `team/README.md`]).
- pytest, venv, a seeded demo project fixture [V-repo].
- **Route inventory diff**: dump `app.routes` (method, path, name, response model, dependencies) before and after each move; fetch `/openapi.json` before and after and diff. [E] Router order matters where paths overlap (for example `/x/{id}` versus `/x/export`), so the diff must preserve registration order.
- **Golden-master tests**: for each router, call every endpoint against the demo project and snapshot responses (with volatile fields such as timestamps and ids normalised) before moving code. [E]
- **Move, do not edit**: a refactor commit moves code verbatim; any fix goes in a separate commit. Watch for module-level state, circular imports, shared helpers defined in `main.py`, and `app.state` or globals.
- **Migrations**: additive columns via the `MIGRATIONS` list; anything else by table rebuild inside a transaction with `foreign_key_check` and `integrity_check`, tested on a copy of an older database and on a database that has already been migrated (idempotency). Record a schema version with `PRAGMA user_version` (none exists today: `grep` for `user_version` found nothing [V-repo]).
- **Sync tests**: N replicas in temp directories, random interleavings of edits, deletes and duplicate keys, then assert identical state (`tests/test_sync.py` is the starting point [V-repo]).
- Profiling with `cProfile` and `EXPLAIN QUERY PLAN` where routes are slow. [E]

## 6. How the work is judged

**Quality measures**
- Full test suite green before and after; no test edited to make a refactor pass unless the reason is stated.
- Route inventory and OpenAPI diff empty for a pure move.
- A migration applied twice, or to a database from any earlier release, gives the same result and no data loss.
- Two or more replicas converge after any ordering of journal files.
- Calculations reproduce known figures to the cent.
- Small, reviewable pull requests that follow the working agreement (plan, wait for "go", one build and one test run per batch [V-repo]).

**Common failure modes (what a good senior reviewer looks for)**
1. *Refactor that silently changes behaviour*: reordered routes, changed default parameters, lost decorators or dependencies, moved a global that other modules mutate, import cycles resolved by deferred imports that change startup order. [E]
2. *Refactor mixed with fixes or renames* so the diff cannot be reviewed as a move.
3. *Floating-point money.* The schema stores amounts as `REAL` (for example `amount REAL NOT NULL` [V-repo, `app/schema.sql` line 111]). Binary floats cannot represent most decimal cents exactly, and totals can differ by a cent depending on summation order (Python `decimal` docs, not read) [E]. A senior engineer would check where rounding happens (per line or per total), which rounding mode is used (Python's built-in `round` uses banker's rounding on floats), and whether the Pronto and CMT reconciliations agree. Whether to move to integer cents or `Decimal` is a design decision that touches stored data and the sync journal; it should go to Vincent through `docs/open-questions.md`, not be changed unilaterally. [A on the recommendation; V-repo on the schema type]
4. *Non-idempotent or non-transactional migrations*, or `ALTER TABLE` followed by a crash halfway; foreign keys left off after a rebuild.
5. *Sync defects*: clock skew between PCs, a delete that arrives before its create, a journal line applied twice, id slot reuse, unique-key collisions resolved differently on different replicas, a replica that re-exports imported rows (echo). Last-writer-wins per column is a deliberate decision (D4) and loses concurrent edits to the same cell by design; the review question is whether that loss is visible to the user. [V-repo for D4; E for the failure list]
6. *Triggers and the change log*: any write path that bypasses `db.connect(logging=True)` will not reach the journal and will not sync. [A, inferred from D4 and `db.connect`]
7. *Weak tests*: asserting on status code only, shared mutable fixtures across modules, tests that depend on order or on the real clock.
8. *Security slips*: SQL built by string formatting, path traversal in file endpoints (`site_files.py`, imports and exports), service bound to anything other than loopback (the launcher uses 127.0.0.1 [V-repo]), unauthenticated state-changing endpoints reachable from a browser tab on another site (CSRF or DNS rebinding against localhost) [E], secrets or personal data in logs, exports or the journal.

## 7. Boundaries and escalation

- **Vincent (product owner):** decisions in `docs/decisions.md` are not re-opened without him; money representation, schema-breaking changes, and any change to sync semantics go to `docs/open-questions.md`.
- **IT:** OneDrive and SharePoint behaviour, device security, Entra sign-in (phase 2 per D6), code signing, antivirus exclusions, any security incident.
- **Legal and the internal privacy owner:** whether and how the Privacy Act applies, retention, and disclosure of personal data in the journal and audit trail. The engineer implements controls; they do not rule on compliance.
- **HR:** anything about individuals' performance data held in the tool (team fit, complexity scoring of people) is an HR matter.
- **WHS:** not expected to arise directly; refer if a feature touches safety records.
- **Finance and the project controls lead:** the meaning of a cost rule (accrual reversal, allowance, pools, D13 to D18) is theirs; the engineer encodes it and flags ambiguity.
- **Other area sessions:** `docs/areas.md` says one session owns one area and its files; two sessions should not run in parallel on the same area.
- Never commit databases, `crm_link.txt` or real project data (CLAUDE.md [V-repo]). Use placeholders for secrets.

## 8. What an AI version can and cannot do

**Can do well**
- Read a 3,800-line module and produce a route inventory, a dependency map and a proposed router layout by area.
- Write characterisation and golden-master tests, parametrised route tests and sync simulation tests at volume.
- Perform mechanical moves verbatim, run the suite, diff OpenAPI before and after, and report the result.
- Draft migrations and rebuild scripts, and test them against copies of earlier schemas.
- Review diffs against a checklist (sections 6 and above), grep for bypasses of the change log, string-built SQL and unsafe paths.
- Keep branch, backlog and release-log hygiene as the working agreement requires.

**Cannot, or must not, do alone**
- Run PMT on real Windows PCs with OneDrive sync, observe real sync latency, file locking or antivirus effects, or reproduce a user's corrupted replica without the file being supplied (and real project data must not be committed).
- Judge whether a financial figure is commercially right; it can only show it matches the rule as written. A human who owns the cost rules signs off.
- Decide money representation, accept data loss from last-writer-wins, or re-open decisions: these are Vincent's.
- Give legal conclusions on privacy or confirm compliance; refer to the internal owner.
- Guarantee behaviour preservation. Tests show absence of observed change only; untested routes and front-end calls (`static/js/api.js`) are a residual risk and need a human or a browser-level check. [E]
- Approve its own work on `main`: merges need Vincent. It also should not handle credentials, production databases or real personal data without the confirmation the EPEC conduct rules require.

## 9. Sources

| Claim | Label | Source |
|---|---|---|
| Route, table and schema counts; money stored as REAL; no `user_version`; loopback launcher; PII fields in schema | V-repo | `/home/user/pmt/app/main.py`, `app/schema.sql` (line 111 and others), `app/db.py`, `app/launch.py` |
| Decisions D1 to D5, D12, D14 to D18; working agreement; branch rules | V-repo | `/home/user/pmt/docs/decisions.md`, `HANDOFF.md`, `CLAUDE.md`, `docs/areas.md` |
| SQLite native ALTER TABLE scope; 12-step rebuild; `foreign_key_check` | V (mirror, draft) | [sqlite.org draft lang_altertable](https://sqlite.org/draft/lang_altertable.html); official page [not reached](https://www.sqlite.org/lang_altertable.html) |
| Splitting with `APIRouter` | E | [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/) (not read) |
| Syncing a live SQLite file risks corruption | E | [SQLite: How To Corrupt](https://www.sqlite.org/howtocorrupt.html) (not read) |
| Float versus Decimal for money; rounding modes | E | [Python decimal](https://docs.python.org/3/library/decimal.html) (not read) |
| Privacy obligations for personal information | E | [OAIC APPs](https://www.oaic.gov.au/privacy/australian-privacy-principles) (not read) |
| Endpoint hardening baseline | E | [ACSC Essential Eight](https://www.cyber.gov.au/resources-business-and-government/essential-cyber-security/essential-eight) (not read) |
| Web API review checklist | E | [OWASP Top 10](https://owasp.org/Top10/) (not read) |
| Refactoring is behaviour-preserving; characterisation tests | E | [Fowler](https://martinfowler.com/bliki/Refactoring.html) (not read); Feathers, *Working Effectively with Legacy Code* (not read) |
| Fixtures, `tmp_path`, parametrisation | E | [pytest fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html) (not read) |

## 10. Gaps

- Every primary documentation host was unreachable, so only one external claim (SQLite ALTER TABLE) is verified, and that from a mirror of a draft page. All other external links are unread and should be confirmed before anyone relies on them.
- I did not find or read job descriptions or competency frameworks for this role (for example SFIA, Australian Computer Society CTPro or Engineers Australia software competencies); the role is therefore built from established practice and the repo. Salary, seniority bands and EPEC ECF level mapping are not covered.
- I did not run the test suite, read `main.py` in full, or inspect `sync.py` beyond its header, so statements about specific code paths (for example rounding in `engine.py`, route-order hazards, global state) are review prompts, not findings.
- Whether PMT's personal data triggers Privacy Act duties for EPEC is not determined (legal owner).
- No Australian standard specific to this role was identified; none is implied.
