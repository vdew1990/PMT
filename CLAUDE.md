# PMT

Project Management Tool for EPC contract cost control, claims, variations and risk. Python (FastAPI, SQLite) with a plain JavaScript front end.
Commercial in Confidence. Amounts are AUD excluding GST; dates are DD/MM/YYYY in the interface and ISO in the database. Australian English.

Start with `HANDOFF.md`, then `docs/decisions.md` and your area in `docs/areas.md` and `docs/backlog.md`.
Run the tests with `.venv/bin/python -m pytest tests -q` before and after a change. Do not commit databases, `crm_link.txt` or any real project data.
Branch per item; never commit to `main` directly. Follow the working agreement in `HANDOFF.md`.
