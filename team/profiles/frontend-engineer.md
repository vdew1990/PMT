# Role profile: Senior Front-End Engineer and UX for data-heavy business tools (plain JavaScript, no framework)

Prepared by Owen (Senior Researcher) for Nola, via Atlas. Date: 30/10/2026. Commercial in Confidence.

Evidence labels used throughout: **[V]** verified from a source I reached (search results, linked); **[E]** established practice (widely accepted, not individually sourced); **[A]** assumption or inference. Direct fetches of w3.org, playwright.dev and accessibility.org.au failed in this session (host not on the network allow-list), so [V] items rest on search-result summaries of those sites, not on my reading the pages. Wikipedia was blocked as advised and not used.

## 1. Purpose of the role

Keep PMT's front end fast, consistent and usable for project managers and directors who live in dense, finance-style grids all day, and grow it without a framework or build step. The role owns how the interface behaves (keyboard, focus, re-rendering, performance, accessibility), not what the commercial numbers mean.

Grounding in the repository (read, not changed): plain JavaScript modules, `static/js/app.js` (menu `NAV`, role-aware menu via `isDirector`), `ui.js` (about 400 lines of shared helpers: `h()` element builder, `table`, `modal`, `drawer`, `sortableRows`, `fillHandle`, `lookup`, `calc`), `outlinecore.js` (pure, import-free outline logic, written so it can be tested alone), 62 view files under `static/js/views` (8,500 lines in total, largest about 720), Chart.js and Leaflet vendored, brand tokens in `static/css/design.css`. `docs/areas.md` names `app.js`, `ui.js` and `api.js` as shared files that every area touches, merged early in short branches. `docs/decisions.md` D15 (no role restrictions, audit trail instead) and a later note (app experience to differ by role) set the role-based-view brief. Tests today are Python (`tests/`); I found no browser test tooling in the repository.

## 2. Core responsibilities and deliverables

- Own `ui.js` and shared components; keep view files thin and consistent (one table, one modal, one number field, one fill handle).
- Build and tune the outline tables (grandparent, parent, line), month and day grids with colour-coded status cells, fold levels and column hiding.
- Excel-style behaviour: arrow and Tab navigation, edit mode versus navigate mode, calculator fields, fill handle, paste from Excel, undo, drag and drop with a non-drag alternative.
- Windows and popouts, drawers, focus management and restore.
- Role-based views: what each role sees and defaults to (a view, not a lock, per D15).
- Tests for his own components (isolated logic modules in the style of `outlinecore.js`, and component-level checks), accessibility design and a known-issues list. End-to-end browser flows, cross-area regression and the pass or fail verdict belong to the Test Engineer (Onyx); Finn does not add test tooling to `requirements.txt`. [V, repo: [`team/finn.md`](../finn.md), [`team/onyx.md`](../onyx.md)]
- Deliverables: components with documented behaviour, a UI conventions page (a design-system document), performance budgets, component test specs and a test brief for Onyx at the end of each unit of work, accessibility statement and known-issues list, short PRs following `HANDOFF.md`.

## 3. Skills and knowledge

**Essential**
- Modern JavaScript (ES modules, closures, events, delegation, async), DOM and CSS (grid, sticky positioning, `contain`, custom properties). [E]
- Rendering large tables without a framework: event delegation, batched DOM writes, `DocumentFragment`, avoiding layout thrash, `requestAnimationFrame` scheduling, row or column virtualisation when counts justify it. [E]
- Keyboard interaction and focus management for grids; screen reader semantics for tables and tree grids (see section 4). [V for the pattern]
- Reading finance users: number formats, negative and rounding conventions, AUD ex GST, DD/MM/YYYY display and ISO storage (project rules in `CLAUDE.md`). [V, repo]
- Git discipline per `HANDOFF.md` (branch per item, small shared-file changes).

**Advanced**
- A tiny state and re-render pattern: a single state object per view, a render function that is idempotent, targeted updates of changed cells, preserved scroll, selection and focus across re-render. [E]
- Designing a cell-based "grid engine" API (selection model, edit lifecycle, clipboard, fill, undo stack) so views declare columns rather than hand-wire events. [A, recommended for this codebase]
- Safe HTML handling (no unescaped `innerHTML` with data; the `h()` builder is the right habit). `ui.js` currently has one `innerHTML` use, which a reviewer should check. [V, repo]
- Performance profiling with browser DevTools (Performance panel, long tasks, layout shifts). [E]
- UX for dense data: colour never as the only signal, density controls, sticky headers and first columns, consistent empty, loading and error states. [E]
- Print and PDF output of grids if reporting needs it. [A]

## 4. Standards, frameworks and qualifications

- **WCAG 2.2** (W3C). Three new Level AA criteria matter for PMT: 2.4.11 Focus Not Obscured (Minimum), 2.5.7 Dragging Movements (single-pointer alternative to drag; relevant to `sortableRows` and `fillHandle`), 2.5.8 Target Size (Minimum, 24 by 24 CSS pixels). [V via search summary](https://www.w3.org/TR/wcag2mobile-22/) (that W3C page lists them; secondary summary: [AudioEye](https://www.audioeye.com/post/whats-new-with-wcag-2-2/)). Sources disagree on the level of 2.4.13 Focus Appearance (most say AAA, one says AA); check the Recommendation before citing it. Colour contrast (1.4.3, 1.4.11) and "use of colour" (1.4.1) bear on status-colour grids; I name them from established practice [E] and did not read the clauses in this session.
- **WAI-ARIA Authoring Practices Guide 1.2** (W3C Note, 2021): grid and treegrid patterns, including a visible focus indicator, roving focus inside the grid so the Tab sequence stays short, and a treegrid example with three navigation models (rows first, cells first, cells only). [V via search summary](https://www.w3.org/TR/2021/NOTE-wai-aria-practices-1.2-20211129/); [example](https://www.w3.org/TR/2021/NOTE-wai-aria-practices-1.2-20211129/examples/treegrid/treegrid-1.html). Older versions differ in detail (1.0 Tab entry; 1.1 navigation versus actionable mode); use the live key table when implementing. Outline tables map naturally to `role="treegrid"` with `aria-level` and `aria-expanded` [E, I did not confirm attribute lists from the page].
- **Australian context.** The Disability Discrimination Act 1992 does not name WCAG; the Australian Human Rights Commission issued digital guidelines on 2 April 2025 under s 67(1)(k), reported to point to WCAG 2.2 AA, and these are advisory. [V via secondary summaries, weak](https://www.accessibility.org.au/australia-formally-adopts-wcag-2-2-level-aa/); [overview](https://www.boia.org/blog/australia-digital-accessibility-laws-an-overview). Sources conflict on 2.0, 2.1 and 2.2 and on government-only standards (DTA, AS EN 301 549). Not legal advice; see section 7. Whether an internal tool for staff is in scope is a legal question I have not answered.
- **Playwright with axe-core** (`@axe-core/playwright`): official guidance supports scoped scans and WCAG tag selection and states automated testing cannot find every WCAG issue. [V via search summary](https://playwright.dev/docs/accessibility-testing).
- Qualifications: none are mandatory. Useful signals are IAAP WCAG-CPACC or WAS certification and a track record of shipped grid-heavy tools. [A; not researched]

## 5. Tools and methods

- Playwright (Python or Node) knowledge, used to specify the end-to-end scenarios Onyx should script and to review Onyx's browser flows: keyboard-only scripts (arrow, Tab, Enter, Esc, Ctrl+C, V, Z), fold and unfold, fill handle, drag with its alternative, popouts, role switching, screenshots of status-colour grids. Onyx owns the browser suite; whether Playwright is added to `requirements.txt` is a pending decision for Vincent, not Finn's. [V, repo: [`team/onyx.md`](../onyx.md), "Pending decisions"] If Vincent approves it, PMT is Python-first, so Playwright for Python plus the existing `.venv` keeps tooling light. [E, A for fit]
- Pure-function modules tested in isolation: `outlinecore.js` is the model (no imports, no DOM). Extend that rule to selection, fill, clipboard and number parsing (`calc`, `num`), so they can be tested with Node's built-in test runner or via Python tests that shell out. [A]
- axe-core scans on key views, run within Onyx's browser flows once browser tooling is approved [A], with a baseline of known issues (kept by Finn in the known-issues list) so new regressions fail the build. Manual checks with NVDA on Windows (users are on Windows). [E]
- Browser DevTools performance traces on a worst-case project; a performance budget (for example time to render the largest outline, input latency on cell edit). Specific numbers should be agreed with Vincent. [A]
- A written conventions page: tokens (`--navy`, orange, gold, pale grey, Mulish), spacing, density, component behaviour, naming. EPEC brand rules apply to documents and visuals; the in-app palette is already in `design.css` and `PALETTE` in `ui.js`. [V, repo]
- Lightweight visual regression with screenshot comparison, limited to a handful of grids to keep it maintainable; Onyx runs it and Finn nominates the grids and reviews the results. [E; the division of work is V, repo: [`team/finn.md`](../finn.md)]

## 6. How the work is judged

**Quality measures**
- Keyboard-only completion of the main flows with a visible focus ring never hidden behind sticky headers or popouts.
- Predictable behaviour across all 62 views (same shortcut means the same thing everywhere).
- Edit latency and scroll smoothness on the largest real project; no re-render that loses scroll, selection, open folds or focus.
- Zero critical axe findings on core views; known gaps documented.
- No regression in numbers shown: display formatting never alters stored values.

**Common failure modes**
- Each view re-implements its own grid behaviour; drift grows with file count.
- Full-table re-render on every keystroke; lost focus and scroll after save.
- Colour as the sole status signal; sub-24 px targets in dense cells; drag-only actions.
- Handlers attached per cell rather than delegated; memory leaks from popouts that never detach listeners.
- Shared files (`ui.js`, `app.js`) changed in large branches that block other areas.
- Treating a hidden menu item as access control. D15 says PMT does not restrict by role, so role views are presentation and audit, not security.

**What a good senior reviewer looks for**
1. Does it reuse the shared component, or add a one-off? If a one-off, is there a reason?
2. Can I do it with the keyboard alone, and is the focus order sane?
3. What happens to focus, scroll and selection after re-render?
4. Is data escaped before it reaches the DOM?
5. Is the change small and in the right file, with a test (pure logic in an import-free module where possible)?
6. Does it run acceptably on the biggest project, and at large-screen densities on Windows?
7. Are labels, names and states available to assistive technology, not only colour?
8. Is the commit scoped per `HANDOFF.md` and the backlog stage updated?

## 7. Boundaries and escalation

- Meaning of commercial numbers, forecasting rules, claims and variations logic: refer to the Cost, Revenue or relevant area owner and Vincent (see `docs/areas.md`, `docs/decisions.md`). Do not re-open recorded decisions.
- End-to-end browser flows, cross-area regression and the pass or fail verdict: the Test Engineer (Onyx). Test tooling in `requirements.txt` (including Playwright): Vincent's decision, proposed by Onyx; Finn does not add it. [V, repo: [`team/finn.md`](../finn.md), [`team/onyx.md`](../onyx.md)]
- Legal obligations on accessibility (DDA, contractual or client requirements): refer to the internal legal or compliance owner; do not rule.
- Identity, access, licensing, security incidents, and anything that would make role views into real access control: refer to IT.
- WHS aspects of long screen use or accessibility adjustments for staff: refer to the WHS or HR owner.
- Real project data, databases and `crm_link.txt` are not committed or pasted into tests; use synthetic data.
- Changes to shared files are kept small and merged first.

## 8. What an AI version can and cannot do

**Can do well**
- Read and refactor many view files consistently; extract repeated grid code into shared helpers.
- Write and maintain unit and component-level tests for its own components, including keyboard handler specs; specify keyboard scripts for Onyx's browser flows and review them; draft ARIA roles and keyboard handlers from the APG pattern.
- Triage axe scan output from Onyx's flows, and propose fixes; keep the conventions page current.
- Spot drift between views, unescaped HTML, missing labels, undelegated listeners.
- Follow the branch, test and release-log routine in `HANDOFF.md` reliably.

**Cannot do, or only with a human**
- Judge real feel: input latency, density comfort, whether a colour scheme reads on a director's large screen. Needs Vincent and real users. [E]
- Test with real assistive technology and users. An AI can run axe and reason about semantics, but automated tools do not catch all WCAG issues. [V, Playwright docs summary] NVDA sessions and user feedback need a person.
- Decide product trade-offs (what each role should see, which fields to hide), or settle the legal level of accessibility to target.
- Verify visual output unless a browser is available in the session; screenshots need review by a person.
- Guarantee performance on real data without access to it (real project data must not be used).
- Rule on WHS, HR or legal questions arising from accessibility.

## 9. Sources

| Claim | Label | Source |
|---|---|---|
| WCAG 2.2 adds 2.4.11, 2.5.7, 2.5.8 at AA; 2.4.13 level disputed | V (summary) | [W3C WCAG2Mobile](https://www.w3.org/TR/wcag2mobile-22/); [AudioEye](https://www.audioeye.com/post/whats-new-with-wcag-2-2/) |
| APG 1.2 grid and treegrid guidance, three navigation models, visible focus | V (summary) | [APG 1.2](https://www.w3.org/TR/2021/NOTE-wai-aria-practices-1.2-20211129/); [treegrid example](https://www.w3.org/TR/2021/NOTE-wai-aria-practices-1.2-20211129/examples/treegrid/treegrid-1.html) |
| Playwright axe-core integration; automated checks are incomplete | V (summary) | [Playwright accessibility testing](https://playwright.dev/docs/accessibility-testing) |
| DDA does not name WCAG; AHRC 2025 guidelines advisory; WCAG 2.2 AA preferred; sources conflict | V (weak, secondary) | [Centre for Accessibility Australia](https://www.accessibility.org.au/australia-formally-adopts-wcag-2-2-level-aa/); [BOIA](https://www.boia.org/blog/australia-digital-accessibility-laws-an-overview); [Deque](https://www.deque.com/accessibility-compliance/apac/australia/) |
| PMT front end structure, tests, role-view notes | V (repo) | `/home/user/pmt/CLAUDE.md`; `docs/areas.md`; `docs/decisions.md` (D15 and the role-view note); `static/js/ui.js`, `outlinecore.js`, `app.js`, `static/css/design.css` |
| Test ownership split: Finn owns tests for his own components, accessibility design and the known-issues list; Onyx owns end-to-end browser flows, cross-area regression, the verdict and the pending browser-tooling decision | V (repo) | [`team/finn.md`](../finn.md); [`team/onyx.md`](../onyx.md); [`team/profiles/test-engineer.md`](test-engineer.md) |
| Performance and re-render practices, reviewer checklist | E / A | Practitioner consensus; not individually sourced |

## 10. Gaps

- Could not fetch w3.org, playwright.dev or accessibility.org.au directly; clause wording, ARIA attribute lists and the AHRC guideline text are unconfirmed. Allow those hosts and I can verify them.
- No primary AHRC publication or DTA standard text read; the Australian legal position is unresolved and goes to the legal owner.
- No job advertisements or competency frameworks for "front end, no framework" roles were sampled; the skills list is from established practice and the repository, not a salary or job-board survey.
- Did not measure PMT performance, run the app, or audit its accessibility; observations come from reading code only. The count of keyboard and ARIA attributes in the views is low (a quick search found one `aria-label` in `ui.js` and none in `tabletools.js`, and a handful in the largest views such as `variations.js` and `revenue.js`; not a full audit), which suggests accessibility work is largely open. [A]
- No qualification or certification pathway researched beyond naming IAAP.
- Performance budgets and target browsers (assumed current Edge or Chrome on Windows) need Vincent's confirmation.

## Revision note

Reissued 31/10/2026 by Owen for Nola, via Atlas, on Vincent's approval. The test ownership split now recorded in `team/finn.md` and `team/onyx.md` gives the end-to-end browser suite, cross-area regression and the pass or fail verdict to the Test Engineer (Onyx). Finn keeps tests for his own components, accessibility design and the known-issues list, and does not add test tooling to `requirements.txt`. This profile therefore no longer gives Finn the browser suite (sections 2, 5 and 8), and the related wording in sections 2, 5, 7, 8 and 9 was aligned. All other wording, sources, labels and hyperlinks are unchanged. New statements carry labels [V, repo], [E] or [A]; no existing label was upgraded. The original wording is in git history.
