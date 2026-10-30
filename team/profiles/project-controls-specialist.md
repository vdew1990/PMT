# Role profile: Project Controls and Cost Control Specialist for EPC projects (domain expert)

Prepared by Owen (Senior Researcher) for Nola (HR) via Atlas, 30/10/2026. Commercial in Confidence. No real project figures are used.

**Evidence labels.** **[V]** verified from a linked source I could read (search result or repo file). **[E]** established practice (widely accepted, not individually sourced here). **[A]** assumption or judgement, to be confirmed. Where a source is a search-result summary rather than the primary document, I say so.

**Source limits.** The primary sites for PMI, AACE International, AIPM, the Queensland legislation site and the AASB did not resolve in this session's network, so I could not read the standards or certification pages themselves. Claims about them rest on search-result summaries and secondary commentary and are flagged. No standard clause is quoted anywhere in this profile. Wikipedia was blocked and not used.

---

## 1. Purpose of the role

To give the project manager, the project director and the client a cost, forecast and commercial position they can trust each month, by controlling the cost breakdown structure (CBS), reconciling the project to the ERP (Pronto), forecasting to completion, and managing variations, claims, contingency and risk on an EPC or EPCM contract. **[E]**

In PMT terms, the role is the domain owner for whether the app's cost logic is right, not only whether it runs. Scope of the app per the README: CBS, allowances, commitments, accruals, Pronto actuals, EAC and cost to complete (CTC), subcontract and client claims, variations, month-end close and review, risk, the EOM report, the PMR and the client report ([README.md](/home/user/pmt/README.md), "What it does").

## 2. Core responsibilities and typical deliverables

### 2.1 Monthly cycle on an EPC job **[E]**, mapped to PMT features **[V]** (README.md)

| Step | What a skilled controller does | PMT area |
|---|---|---|
| 1. Load and tie out actuals | Import GL, labour, PO and claims exports; confirm the project code, no future-dated or duplicate rows, totals tie to the ERP cost-to-date by category | Pronto upload, wrong-project guard, Checks, Diagnostics, Reconcile |
| 2. Commitments | Check open POs and subcontracts against the CBS; closed POs commit only what was received | Cost control (Ordered), Diagnostics |
| 3. Accruals | Accrue work done and not yet invoiced (estimates, invoices awaiting approval, unposted timesheets, subcontract claims); confirm last month's accruals reversed; avoid double counting with finance journals | Accruals, Labour calendar |
| 4. Forecast | Review every line's method, CTC and EAC; challenge methods that no longer fit; refresh ground-up forecasts for labour, milestone payments and rosters | Cost control, Forecast lines, Ground-Up register |
| 5. Month-end review | Compare last month's forecast with what landed; accrue the difference or record slippage with a reason | Month-end review |
| 6. Revenue and claims | Submit the client progress claim; process subcontract claims and certificates; update revenue at certified amounts | Claim schedule, Progress claims, Subcontract claims |
| 7. Variations | Maintain the register, price and build up new variations, track approval status and cost and revenue effect | Variations |
| 8. Risk and contingency | Update the register; tag costs to events; release or hold contingency; review allowance balance | Risk, Allowances |
| 9. Close and report | Close the month (snapshot), produce the EOM report, PMR inputs and client report, write the variance commentary | Month-end checklist, Snapshots, EOM report, PMR |

### 2.2 Typical deliverables **[E]**

- Monthly cost report: allowance, commitments, actuals, accruals, CTC, EAC, variance to budget, margin movement and a bridge explaining it.
- Cashflow forecast (cost out, revenue in, net, cumulative).
- Accruals register with reversals tied to invoices.
- Variation register and claim schedule; subcontract payment schedules.
- Risk and contingency register with drawdown history.
- Reconciliation pack to the ERP and to the prior close, with reconciling items explained.
- Director and client reporting packs; lessons and close-out cost data for the estimator.

## 3. Skills and knowledge

### Essential

- **Technical (cost):** CBS design and coding discipline; commitments versus actuals versus accruals; EAC = actual + accrued + CTC logic; retention; subcontract payment terms (milestone, progress, variation portions). **[E]**
- **Technical (commercial):** reading EPC and EPCM head contracts and subcontracts well enough to know what is claimable, when, and on what notice; change and variation mechanisms; payment claim and payment schedule timing. **[E]**
- **Analytical:** variance decomposition (price, volume, scope, timing); reconciliation and tie-out; spotting double counting and timing errors; spreadsheet and database fluency (Excel, SQL-level thinking for data tie-out). **[E]**
- **Communication:** plain, short commentary for a director; explaining a forecast movement in one sentence; writing a claim narrative that a client can accept. **[E]**
- **Judgement:** knowing when a number is wrong even though it calculates; distinguishing a timing slip from a real overrun; holding a line on unsupported revenue. **[E]**

### Advanced

- Ground-up forecasting from resource plans, rosters and milestone payments, with an independent bottom-up check on top-down results.
- Earned value and earned schedule applied honestly to engineering, procurement and construction phases (see section 4.2).
- Quantitative risk and contingency methods (expected value, ranging, Monte Carlo) and the discipline of linking each risk to a cost impact. **[V]** AACE RP 40R-08 states that quantitative methods should be risk-driven, linking risk to impacts, per the [AACE webinar and RP listing summary](https://www.pathlms.com/aace/courses/2928/documents/3825) (search-result summary; RP text not read).
- Revenue recognition awareness (AASB 15 over-time recognition, variation enforceability), enough to talk to finance, not to rule (section 4.4).
- Portfolio view: consolidating several projects' CBS and comparing forecast accuracy across closes.

## 4. Standards, frameworks and qualifications

### 4.1 Cost engineering and estimate classification

- **AACE International** is the main international body for cost engineering and project controls. **[V]** Its credentials include Certified Cost Professional (CCP), Earned Value Professional (EVP), Certified Cost Technician (CCT) and others, and they are accredited by the Council of Engineering and Scientific Specialty Boards, per the [search-result summary](https://source.aacei.org/?p=5697) of AACE material (third-party training listings; AACE's own certification page not reachable). One training provider lists the EVP as needing about eight years of experience (as one option), a closed-book 119-question exam and recertification every three years through 12 continuing education units ([IMF Academy listing](https://www.imfacademy.com/finance/earned-value-professional.php)). Check the official AACE page before anyone relies on these details.
- **AACE RP 18R-97** applies estimate classification to EPC work in the process industries. **[V]** Classification is by level of project definition, with five classes ([EPCLand commentary](https://epcland.com/cost-estimate-classification-system-for-process-industries/), third-party). Sources disagree on the revision date, and I did not confirm the current one. Whether it suits power and substation work, rather than process plant, is an **[A]**: AACE publishes other "as applied in" practices and the closest fit should be confirmed with AACE.
- **AACE contingency practices** (40R-08 general principles; 41R-08 range estimating and Monte Carlo; 44R-08 expected value; 42R-08 parametric; 118R-21 and 123R-22 for inherent risk and hybrid methods). **[V]** per the [AACE table-of-contents pages](https://web.aacei.org/docs/default-source/toc/toc_118r-21.pdf) and [listing](https://www.pathlms.com/aace/courses/2928/documents/3825) (summaries only). The same sources note that estimate ranging tends to underestimate contingency, sometimes significantly.

### 4.2 Earned value

- **PMI** publishes *The Standard for Earned Value Management*, which builds on the earlier *Practice Standard for Earned Value Management* **[V]** ([PMI EVM page via search result](https://www.pmi.org/standards/earned-value-management)). I could not confirm the current edition or year; the page itself was unreachable. I found no evidence of a "third edition" of the practice standard.
- Standard EAC forms (BAC/CPI; AC + (BAC − EV); AC + bottom-up ETC) and their assumptions are **[E]**; the search results describing them are vendor blogs and a US Department of Energy training snippet ([DOE snippet](https://www.energy.gov/sites/default/files/2015/12/f27/Snippet_5.6_with%20notes.pdf)), which also reports that earned schedule gave more reliable schedule forecasts than conventional EVM in the cases tested **[V, single secondary source]**.

### 4.3 Project management and risk

- **AIPM** (Australian Institute of Project Management) runs RegPM certification at five levels: CPPP, CPPM, CPSPM, CPPD and CPPE, open to AIPM members **[V]** ([AIPM certification brochure](https://aipm.com.au/wp-content/uploads/2026/01/AIPM-Certification-Brochure.pdf), via search-result summary; page not reachable). The UK APM "Registered Project Professional" is a different body's credential and is not the AIPM equivalent.
- **PMI** certifications relevant to controls: PMP; PMI-RMP (risk) and PMI-SP (scheduling). **[V]** PMP is not a prerequisite for PMI-RMP, and risk experience must fall within the last five years ([PMI RMP page](https://www.pmi.org/certifications/risk-management-rmp)). PMI-SP eligibility details were not found.
- **AS ISO 31000:2018** is the Australian adoption of ISO 31000, risk management guidelines; current per the store and reviewed and confirmed by ISO in 2023 **[V]** ([Standards Australia store](https://store.standards.org.au/product/as-iso-31000-2018)). It is guidance, not certifiable.
- **AIQS** (Australian Institute of Quantity Surveyors) grants the Certified Quantity Surveyor (CQS) designation to Member-grade members after an APC interview **[V]** ([AIQS](https://www.aiqs.com.au/events/expertise-experience-applying-certified-quantity-surveyor-cqs-designation)). Relevant mainly to cost planning and valuation skills; membership scope has widened to cost estimators and contract administrators.
- **Engineers Australia** chartered status (CPEng or similar) suits a controller who is also an engineer. **[E]** I did not research it in this session; treat as unconfirmed.

### 4.4 Contracts, payment law and accounting (awareness, not legal or accounting opinion)

- **AS 4902-2000** (general conditions for design and construct, part of the AS 4000 suite) is the main standard form for single-contractor D&C work; the Standards Australia store lists it as current with an "update available" flag, and I could not confirm whether a revision has been published **[V]** ([Standards Australia store](https://store.standards.org.au/product/as-4902-2000); [Norton Rose Fulbright note](https://nortonrosefulbright.com/en/knowledge/publications/b971ed19/australia-relief-provisions-in-construction-contract-suites)). EPC and EPCM head contracts for energy work are usually bespoke or heavily amended, so the contract in hand, not the standard form, governs. **[E]**
- **Security of payment.** Queensland's *Building Industry Fairness (Security of Payment) Act 2017* replaced BCIPA 2004; Chapter 3 payment provisions started on 17/12/2018; a respondent that will not pay in full must give a payment schedule within the Act's time limit **[V]** ([Corrs summary](https://www.corrs.com.au/site-uploads/images/PDFs/QBIF-building-construction-payments-act.pdf); [Piper Alderman](https://piperalderman.com.au/insight/a-new-fairer-way-in-queensland-building-industry-fairness-security-of-payment-act/)). One secondary guide gives a 10 business day default where the contract is silent; **I did not confirm the exact periods or section wording against the Act**, and Queensland case law (for example *Allencon v Palmgrove*, 2023) bears on timing and content of payment schedules ([Queensland Judgments](https://www.queenslandjudgments.com.au/caselaw/qca/2023/6)). Other states and territories have their own Acts, with different timeframes. **[E]** Legal owns interpretation.
- **AASB 15** *Revenue from Contracts with Customers* replaced AASB 111 and AASB 118 for periods from 1/1/2018; over-time recognition may use input or output measures of progress; unapproved variations need an enforceability and reversal-risk assessment **[V]** ([PKF](https://www.pkf.com.au/insights/audit-and-assurance-revenue-recognition-for-long-term-construction-contracts/); [Nexia](https://nexia.com.au/news/applying-aasb-15-building-and-construction/); accounting-firm commentary, standard text not read). Contract asset mechanics were not covered by my sources.
- **Terminology.** WIP, accrual and contract asset are used differently by project controls and finance. **[E]** Agree definitions with finance before reporting (section 8).

## 5. Tools and methods

- **Systems:** Pronto ERP (GL, labour, POs, claims, variations, CTD overview) **[V]** (README.md); the existing CMT workbook and PMR; PMT itself.
- **Methods:** CBS coding; commitment and accrual tracking; line-by-line EAC with a stated method (ground-up, claim, burn-rate, at-budget, at-commit, top-down, manual, none) **[V]** (README.md, Cost control and release .70); snapshots at each close to measure forecast accuracy **[V]** (README.md, Snapshots and Forecast history); reconciliation to the ERP and to the prior month; variance bridges; EV indicators (CPI, SPI, TCPI) as sanity checks, not as the primary forecast; cashflow modelling from payment terms **[V]** (README.md, Design notes: Pronto GL has no payment dates, so supplier payments are modelled).
- **Scheduling link:** MS Project XML or Excel schedules mapped to CBS lines and claim items (README.md, Project schedule).

## 6. How the work is judged

### Quality measures **[E]**

- Cost-to-date ties to Pronto by category, every month, with reconciling items named and aged.
- Forecast accuracy: month-end forecast versus landed (PMT's Month-end review and Forecast history support this); EAC stability and explained movement.
- No double counting between accruals, commitments, actuals and finance journals.
- Claims lodged on time and in the contractual form; payment schedules and certificates answered within the contract and statutory time.
- Variations registered promptly with notice evidence.
- Reports explain movement, not just state numbers.

### Common failure modes **[E]**

| Failure | Typical cause |
|---|---|
| EAC swings wildly early | CPI-based forecast used on a low-percent-complete job; rule of thumb of waiting for about 20% complete is vendor advice, not a standard **[V, weak source]** ([ClickUp](https://clickup.com/learn/topic/project-management/terms/estimate-at-completion/)) |
| Forecast ignores known scope change | Historic performance projected forward after a re-plan or major variation; a bottom-up ETC is then the right method |
| Accrual never reverses, or counted twice | Invoice reference not matched; finance journal and project accrual both live |
| Cost on wrong project or CBS line | Coding errors; PL or PS miscoding; wrong-project upload |
| Revenue booked ahead of entitlement | Unapproved variation, uncertified claim or disputed amount treated as certain |
| Contingency spent without record | Releases not tied to a materialised risk and a landed cost |
| Pool or allowance overspend hidden | Lower-line overruns covered silently by a group pool; flagged only if the logic shows it (see release .70 in README.md) |
| Timing confusion | Cost by work done, by invoice date and by payment date reported as one number |
| Month-end closed with unreviewed differences | Pressure to publish; no sign-off gate |

### What a reviewer looks for

A clean tie-out; a method note on each material forecast line; commentary that matches the numbers; evidence for revenue; and a trail of who changed what (PMT's change log and History tabs, decision D15 in [docs/decisions.md](/home/user/pmt/docs/decisions.md)).

## 7. Reviewing PMT's logic for correctness

A controller reviewing the app does not trust a green test run. The approach, **[E]** unless noted:

1. **Identity checks.** For every line and every roll-up, confirm EAC = cost to date + accruals + CTC (the README states this, and that the CMT excludes accruals, so the Reconcile page shows a CMT-style figure; check this is what finance expects) **[V]** (README.md, Design notes). Child lines must sum to parents; parent-project totals must equal the sum of children.
2. **Tie-outs.** Compare PMT cost-to-date by category with the Pronto source for a closed month in a copy of real data kept outside the repo; every difference must be explained.
3. **Commitment rules.** Closed PO commits what was received; open PO commits full value; partially received POs and cancelled lines; credit notes; retention. Test edge cases, not the happy path.
4. **Accrual lifecycle.** Raise, match to invoice, reverse; hours accruals versus posted and unposted timesheets (decisions D10, D17, D18 in docs/decisions.md): check no person-day is counted twice and that partial matches behave as the decisions describe.
5. **Pool and allowance logic.** Nested pools (D13, D14, release .70): test that taking a forecast out of a pool leaves the total unchanged, that an allocation larger than the pool is flagged, and that the group EAC does not double count. Question whether not moving allowance automatically (D14) leaves a state where a line shows COVERED while its own allowance is still short; that is a design decision for Vincent, not for me to reopen.
6. **Revenue and claims.** Certified amount counts as revenue where one exists, claimed otherwise (README, Client claims and release .73): check this against how finance and the contract treat uncertified claims and variations; it is a policy point (section 8).
7. **Statutory output.** The claim PDF's Queensland statement and review-deadline logic (README releases .73 to .77) depend on site state, governing law and business-day rules. The README itself notes the effect of governing law "was not confirmed in the research". Treat as unverified until legal confirms; the controller tests the arithmetic and calendar (business days, public holidays), legal owns the rule.
8. **Cashflow.** The model uses payment terms because Pronto has no payment dates; check that a change in terms moves cash, not cost.
9. **Time basis.** Status-date handling (forecast days count from the day after the status date, D11): test month-end rollover, closing a month twice and re-importing Pronto after a close.
10. **Regression and invariants.** Snapshot comparisons should be reproducible; a re-import must not change a closed month silently.
11. **Documentation.** Every formula the user sees should state its basis in plain words; every override should leave an audit trail.

Output of a review: a numbered findings list (finding, evidence, impact in dollars on a fictional or anonymised case, suggested fix, owner), not a code change.

## 8. Boundaries and escalation

| Matter | Refer to |
|---|---|
| Interpretation of contract clauses, notices, time bars, entitlement to extension or variation, security of payment compliance, whether a claim or payment schedule is valid, governing-law effects | Legal and the contract administrator |
| Revenue recognition, WIP and contract asset treatment, provisions, onerous contracts, accrual policy, GST, month-end journals in Pronto, audit queries | Finance (financial controller) |
| Margin write-back, risk bucket release or infusion, contingency policy, delegations of authority, bid versus project cost transfers | Commercial manager and project director per the company's delegations |
| Whether an unapproved variation goes in the forecast or in revenue | Commercial manager (with finance on revenue) |
| Pay rates, pay bands, personal data of staff (home address, pay band) | HR; PMT has no sign-in, so these wait for the access design (decisions of 31/10/2026) |
| Access, licensing, Entra or SharePoint sign-in, sync faults, security incidents | IT |
| WHS, compliance, HR policy | The internal owner; do not rule |
| Changes to decided behaviour in docs/decisions.md | Vincent |

Escalate early when: a reconciling item is unexplained after two months; a forecast moves by more than the agreed threshold (threshold to be set by the commercial manager, **[A]**); a client disputes a claim; a notice deadline may be near; any data would leave the repo or contain real project figures, rates, personal data or credentials (confirm first; use placeholders).

## 9. What an AI version can and cannot do

### Can do **[A]**, based on the way PMT is built

- Run the monthly tie-out checks and list differences ranked by size, with the link to the record behind each.
- Test the engine's logic against the identities in section 7 and write reproducible findings.
- Draft variance commentary, bridges and report narrative from the data, labelled as drafts.
- Flag likely double counts, stale accruals, unreversed accruals, forecasts inconsistent with commitments or schedule, and lines with a method that no longer fits.
- Compare forecast with outcome over closes and report accuracy by method.
- Summarise contract text supplied to it, quoting only what it has read, to support (not replace) the contract administrator.
- Prepare checklists, reconciliation templates and test cases; research standards and report what it could and could not confirm.

### Cannot do, or must not do alone

- Decide contract entitlement, validity of a notice, or whether a statutory claim or schedule complies; legal owns this.
- Decide accounting treatment, approve journals or sign off a month-end close.
- Approve a variation, release contingency, move allowance or commit the company; these need a named human with delegation.
- Know what is happening on site, what a subcontractor will really do next month, or what a client PM will accept; the forecast needs the PM's input.
- Verify against Pronto or contracts it has not been given; it must say so rather than infer.
- Hold personal or commercial data outside the approved workflow, or work with real project data without confirmation.
- Be the accountable owner: every material number goes out under a named human's sign-off. **[E]**

### Working rules for the AI version **[A]**

State the basis of each figure and its label (reconciled, forecast, assumption). Never fabricate a clause, a figure or a reference. Mark anything not verified. Use placeholders for secrets and keys. Write Australian English, DD/MM/YYYY, AUD excluding GST.

## 10. Sources

Repo (read in full or in part): [CLAUDE.md](/home/user/pmt/CLAUDE.md); [README.md](/home/user/pmt/README.md) ("What it does", "Design notes", release notes); [docs/decisions.md](/home/user/pmt/docs/decisions.md) (D1 to D27 and the 26/10 and 31/10/2026 records); [docs/threads.md](/home/user/pmt/docs/threads.md) (threads 1 to 7 only, first 120 lines).

Web (all via search results; primary pages not reachable unless stated):
- AACE certifications: [AACE source page](https://source.aacei.org/?p=5697); [IMF Academy EVP listing](https://www.imfacademy.com/finance/earned-value-professional.php)
- AACE RPs: [18R-97 commentary](https://epcland.com/cost-estimate-classification-system-for-process-industries/); [40R-08 listing](https://www.pathlms.com/aace/courses/2928/documents/3825); [118R-21 contents](https://web.aacei.org/docs/default-source/toc/toc_118r-21.pdf); [123R-22 contents](https://web.aacei.org/docs/default-source/toc/toc_123r-22.pdf)
- PMI: [EVM standard](https://www.pmi.org/standards/earned-value-management); [PMI-RMP](https://www.pmi.org/certifications/risk-management-rmp)
- EAC practice: [US DOE training snippet](https://www.energy.gov/sites/default/files/2015/12/f27/Snippet_5.6_with%20notes.pdf); [ClickUp](https://clickup.com/learn/topic/project-management/terms/estimate-at-completion/) (vendor blog, weak)
- AIPM: [certification brochure](https://aipm.com.au/wp-content/uploads/2026/01/AIPM-Certification-Brochure.pdf)
- AIQS: [CQS designation](https://www.aiqs.com.au/events/expertise-experience-applying-certified-quantity-surveyor-cqs-designation)
- Risk: [AS ISO 31000:2018](https://store.standards.org.au/product/as-iso-31000-2018)
- Contracts: [AS 4902-2000](https://store.standards.org.au/product/as-4902-2000); [Norton Rose Fulbright](https://nortonrosefulbright.com/en/knowledge/publications/b971ed19/australia-relief-provisions-in-construction-contract-suites)
- Security of payment: [Corrs](https://www.corrs.com.au/site-uploads/images/PDFs/QBIF-building-construction-payments-act.pdf); [Piper Alderman](https://piperalderman.com.au/insight/a-new-fairer-way-in-queensland-building-industry-fairness-security-of-payment-act/); [Queensland Judgments, 2023 QCA 6](https://www.queenslandjudgments.com.au/caselaw/qca/2023/6)
- Accounting: [PKF](https://www.pkf.com.au/insights/audit-and-assurance-revenue-recognition-for-long-term-construction-contracts/); [Nexia](https://nexia.com.au/news/applying-aasb-15-building-and-construction/)

## 11. Gaps

- Primary sources not read (hosts unreachable): AACE, PMI, AIPM, the Queensland legislation site, AASB. Every standard, Act and certification detail above is a summary-level claim and needs checking against the primary document before it is relied on.
- BIF Act: exact payment claim and payment schedule periods and section numbers not confirmed; other states' Acts (NSW, WA, Vic, SA and so on) not researched. The README's reference to s 61(4) was not independently verified.
- Current AACE RP revisions and whether a substation, transmission or renewables-specific estimate classification practice exists: not found.
- PMI EVM standard edition and year; PMI-SP eligibility; Engineers Australia credentials: not confirmed.
- AASB 15 contract asset measurement, AASB 137 (onerous contracts, provisions) and how EPEC's finance team defines WIP: not researched; ask the financial controller.
- Australian-specific project controls salary, competency or role frameworks for EPC: not found. EPEC's own classification framework (ECF) levels for a controls role were not read; HR owns that mapping.
- Benchmarks for forecast accuracy or month-end variance thresholds in Australian EPC: not found; thresholds should be set by EPEC's commercial owner.
- Only the first 120 lines of docs/threads.md were read; docs/areas.md and docs/backlog.md were not read (outside this brief's scope).
