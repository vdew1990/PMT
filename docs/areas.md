# Areas: one session per area

Each Claude session owns one area and the files in it. Two sessions should not run in parallel on the same area.
Menu groups are those in `NAV` in `static/js/app.js`. Thread numbers refer to `docs/threads.md`. Files are the main ones, not a complete list.

| Area | Menu groups | Main files | Threads |
|---|---|---|---|
| Cost and Forecast | COST, FORECAST, MONTH-END | `static/js/views/costcontrol.js`, `forecast.js`, `groundup.js`, `accruals.js`, `calendar.js`, `review.js`, `risk.js`, `_allowances.js`; `app/engine.py`, `forecast.py`, `groundup.py`, `accruals.py`, `allowance.py`, `review.py`, `timeline.py` | 2, 3, 4, 5, 8, 17, 18, 19 |
| Revenue and Subcontracts | REVENUE, subcontracts | `views/revenue.js`, `variations.js`, `subcontracts.js`; `app/revenue.py`, `variations.py`, `variation_io.py`, `subcontracts.py`, `subcontract_io.py`, `claim_template.py` | 4, 7, 9, 23, 25, 29, 30 |
| Setup and Team | SETUP, COMMUNICATION | `views/setup.js`, `complexity.js`, `projectteam.js`, `team.js`, `teamfit.js`, `orgchart.js`, `objects.js`; `app/complexity.py`, `team.py`, `ecf.py`, `org_load.py`, `people_seed.py`, `directory.py`, `orgchart.py` | 15, 20, 21, 27, 28 |
| PMO and Reporting | PMO, REPORTING, CLOSE-OUT, OVERVIEW | `views/lifecycle.js`, `pmr.js`, `psr.js`, `closeout.js`, `portfolio.js`, `program.js`, `dashboard.js`; `app/portfolio.py`, `reports.py`, `eom_report.py`, `checklists.py` | 12, 14, 28 |
| Platform | CONTROL, launcher, data load | `app/main.py` plumbing, `db.py`, `schema.sql`, `sync.py`, `identity.py`, `changelog.py`, `launch.py`, `build.py`, `diagnostics.py`; `launcher/`; `static/js/app.js`, `ui.js` | 1, 6, 10, 13, 16, 22, 26, 31, 32 |

Shared files that every area touches, so changes to them go in a short branch that merges first:
`app/main.py`, `app/schema.sql`, `static/js/app.js` (the `NAV` list), `static/js/ui.js`, `static/js/api.js`.

The thread numbers above are a first mapping from the thread titles; correct them as you find a thread belongs elsewhere.
