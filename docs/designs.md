# Designs and plans agreed, not yet built

Moved from HANDOFF.md unchanged. When one is built, record the release in `docs/release-log.md` and set the backlog item to Done.

## Design agreed with Vincent, not yet built (24/10/2026): teams, leads and accountability
Purpose: hold team leads accountable for their slice of a project's budget; later, per-user views and a resource workspace.
- Teams: Construction, Design, SCADA, Commissioning (Projects), Commissioning (Engineering), Engineering, plus PM (no team). Legal entity: EPEC Projects Pty Ltd for Construction, Design, SCADA, Commissioning (Projects); EPEC Engineering for Commissioning (Engineering) and Engineering. Legal entity is a project field (an R01/R02 child project is EPEC Engineering and its revenue goes there).
- A cost line's team is the first that applies: tag on line or group; for labour lines the person's home team (Stakeholders directory field, seeded from the org chart); the project's owning team; the category default; else PM.
- Category defaults: Construction PL04 PL06 PL08, PS04 PS06, PM05 PM06 PM07, PE01 to PE04. Design PL02, PL03 for Design staff, PS02, PS03. SCADA PL07, PS07, PM01. Commissioning (Projects) PL05, PS05. Engineering PL03 for Engineering staff. Commissioning (Engineering) PL03 for its staff when an EPC has no R01/R02, and all lines of an R01/R02 child. PM keeps PL01, PS01, PM02, PM03, PM04, PM08, PE05 to PE09. PL03 is a mix, so home team decides.
- Project owning team (project card): none for EPC; Commissioning (Engineering) for R01/R02 child projects (own CBS, not yet seen); SCADA for SCADA BoP contracts (project manager Dennis Miranda, who is accountable for the whole budget; EPC contracts have a delivery PM).
- One lead per team per project, picked from the Stakeholders directory (employees or consultants); the head is always eligible and sees all projects of the team. Design: Phil Gold (head), Alexander McDonald, Peter Hogan, Geoff Hampton. Commissioning (Projects): Tim Duff (head), Ian Jordaan, Neville Palmer. Construction: Matt O'Connor (head, also acts as CM), construction managers in-house or consultant. SCADA: Praveen Atmuri (head), Tysan Greaves, Ana Prado. Commissioning (Engineering): Paddy O'Connell (head). Engineering: Mick Flynn (head). A portfolio is the set of projects where someone is lead. Keep a history of lead changes.
- Accountability: the PM is accountable for the whole budget; on EPC projects each lead is accountable for their slice (allowance, committed, CTD, accruals, CTC, EAC, variance) and the app flags an overspending slice. Leads see cost, never revenue; subcontractor budget cost and budgeted hours per team (hours from the rate card unless estimates hold hours).
- PM04 stays in the PM budget (Design is technical owner only). Engineering charges are ordinary cost lines, no internal recharge.
- Build order: team tagging and home team; legal entity and owning team on the project; team chip bar on Cost control; COO Teams page; later per-user views and the resource workspace (business-wide programme for heads, project resource schedule for project-level roles).
- Open: leads for Commissioning (Engineering) and Engineering; hours held per line or only dollars; sample R01/R02 and BoP SCADA CBS.


## Ground-Up register: requirements so far (Vincent, 24/10/2026), not yet built
- A register like the variation register, replacing Forecast lines. Freestyle three nested headers (H1, H2, H3) chosen by the user, not the CBS order, for example everything for one person on site grouped together (LAHA, vehicle, labour). Each line still names its CBS line and resource, and rolls up to Cost control by CBS and resource.
- Spread modes seen in the PMT sheet: Milestone (percent of a PO value on a date or trigger), Daily (day grid, quantity times rate, pattern and frequency, start and end), Direct (total over a span). Import the PMT Ground-Up sheet (about 240 lines) as test data.
- Labour of the own team and of subcontractors on labour-hire schedule of rates: a day grid with rosters, hours typed or calculated from the roster pattern and the rates.
- Supplier milestone payments in the register, each linkable to a project schedule item or given a typed forecast month.


## Plan (agreed 26/10/2026 and 27/10/2026, order can change)
1. (Done in .111, see Release .111) Design release: the quiet look of the header bar across the app (page headers, tiles with no coloured top border, two button styles, one-line filter bars, consistent tabs, soft dialogs with fades, quieter sidebar). Tables keep the current look (version A). Before and after screenshots of the pages at 1600 and 1280 px.
2. (Done in .112, see Release .112) Larger UX items: #3 one Month-end page, #4 Allowance as a setup step, #5 and #6 initialise checklist and "what next" card, #7 multi-select and empty buckets on Setup > Allowance, #15 close-out checklist.
3. (Done in .113, see Release .113) Ground-Up register (ISS-003 part 1) and retiring the other method pickers (#20). Still open from the Ground-Up requirements: import the PMT workbook's Ground-Up sheet (about 240 lines) as test data, a day-grid view of the register for rosters, and linking supplier milestones to project schedule items.
4. .114 Ground-Up Excel import template (ISS-003 part 2) and the variation engine overview and exports (ISS-005 part 2).
Still open: folded quarters taking no width (below), team and lead accountability, full pivot on the Ledger tile.


## Next for the new session (raised by Vincent, not built)
- (Done in .110) Folded quarters take no width: see Release .110.
- Still open from before: team and lead accountability (design in "Design agreed with Vincent"), full pivot on the Ledger tile. The Ground-Up register and the remaining UX review items are in the Plan above.
- Working agreement: batch findings, confirm the plan, wait for "go", one build and one test run per batch, zip only on request.
