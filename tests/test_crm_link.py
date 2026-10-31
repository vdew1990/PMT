"""The read-only CRM link: mapping, the one-way copy, drift, and that the CRM file is never written to."""
import hashlib
import sqlite3

import pytest

from app import crm_link, db

CRM_SCHEMA = """
CREATE TABLE opportunities (primary_key INTEGER PRIMARY KEY, opportunity_id INTEGER, record_id INTEGER, record_status TEXT, hidden INTEGER DEFAULT 0,
  opportunity_name TEXT, opportunity_status TEXT, pipeline_stage TEXT, assigned_to TEXT, estimated_value NUMERIC, contract_model TEXT,
  expected_gross_margin NUMERIC, location_state TEXT, opportunity_lat NUMERIC, opportunity_lon NUMERIC, expected_commencement_date TEXT,
  expected_completion_date TEXT, expected_award_date TEXT, url TEXT, business_unit TEXT, project_owner TEXT, opportunity_services TEXT,
  modified_datetime TEXT, account_id INTEGER, contact_id INTEGER, project_id INTEGER);
CREATE TABLE accounts (primary_key INTEGER PRIMARY KEY, account_id INTEGER, record_status TEXT, hidden INTEGER DEFAULT 0, account_name TEXT, account_abn TEXT);
CREATE TABLE contacts (primary_key INTEGER PRIMARY KEY, contact_id INTEGER, record_status TEXT, hidden INTEGER DEFAULT 0, contact_name TEXT);
CREATE TABLE projects (primary_key INTEGER PRIMARY KEY, project_id INTEGER, record_status TEXT, hidden INTEGER DEFAULT 0, voltage_kv REAL,
  voltage_secondary_kv REAL, capacity_mw_primary REAL, capacity_mw_secondary REAL, capacity_mwh REAL, generation_model TEXT, transformer_type TEXT);
"""


@pytest.fixture()
def crm(tmp_path, monkeypatch):
    path = tmp_path / "crm.db"
    c = sqlite3.connect(path)
    c.executescript(CRM_SCHEMA)
    c.executescript("""
    INSERT INTO accounts VALUES (1, 7, 'A', 0, 'Acme Energy', '11 222 333 444'), (2, 7, 'S', 0, 'Acme Old Name', NULL);
    INSERT INTO contacts VALUES (1, 9, 'A', 0, 'Jo Client');
    INSERT INTO projects VALUES (1, 5, 'A', 0, 330, 33, 150, NULL, 300, NULL, NULL);
    -- version 1 (superseded) and version 2 (current) of opportunity 60; opportunity 61 is deleted
    INSERT INTO opportunities (opportunity_id, record_id, record_status, hidden, opportunity_name, opportunity_status, expected_commencement_date,
      expected_completion_date, location_state, account_id, contact_id, project_id, estimated_value, modified_datetime)
      VALUES (60, 1, 'S', 0, 'Old name', '2. Tendering', NULL, NULL, 'NSW', 7, 9, 5, 1, '01/01/2026 10:00');
    INSERT INTO opportunities (opportunity_id, record_id, record_status, hidden, opportunity_name, opportunity_status, expected_commencement_date,
      expected_completion_date, location_state, account_id, contact_id, project_id, estimated_value, contract_model, opportunity_lat, opportunity_lon, modified_datetime)
      VALUES (60, 2, 'A', 0, 'Mokoan Solar Farm and BESS', '9. Won', '05/03/2027', '2028-06-30', 'Victoria', 7, 9, 5, 15000000, 'Lump Sum', -36.5, 146.1, '22/03/2026 11:59');
    INSERT INTO opportunities (opportunity_id, record_id, record_status, hidden, opportunity_name, opportunity_status, account_id)
      VALUES (61, 1, 'D', 1, 'Deleted one', '9. Won', 7);
    """)
    c.commit(); c.close()
    monkeypatch.setenv(crm_link.ENV, str(path))
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_unset_and_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "APP_ROOT", tmp_path)              # ignore a developer's local crm_link.txt in the app root
    monkeypatch.delenv(crm_link.ENV, raising=False)
    assert crm_link.status()["configured"] is False
    monkeypatch.setenv(crm_link.ENV, str(tmp_path / "nope.db"))
    assert crm_link.status()["ok"] is False
    with pytest.raises(crm_link.CrmUnavailable):
        crm_link.list_opportunities()


def test_only_current_versions_listed(crm):
    rows = crm_link.list_opportunities()
    assert [r["id"] for r in rows] == [60]
    assert rows[0]["client"] == "Acme Energy"          # the current account version, not the superseded one
    assert crm_link.list_opportunities(status_contains="Won")[0]["id"] == 60
    assert crm_link.list_opportunities(search="zzz") == []


def test_mapping(crm):
    m = crm_link.map_to_project(crm_link.get_opportunity(60))
    f = m["fields"]
    assert f["name"] == "Mokoan Solar Farm and BESS" and f["client_name"] == "Acme Energy" and f["client_pm"] == "Jo Client"
    assert f["project_start"] == "2027-03-05" and f["project_end"] == "2028-06-30"      # DD/MM/YYYY and ISO both read
    assert f["voltage"] == "33/330" and f["capacity_mw"] == 150 and f["storage_mwh"] == 300
    assert f["project_type"] == "Hybrid (solar + BESS)" and "project_type" in m["inferred"]
    assert f["location"] == "Victoria" and f["lat"] == -36.5
    assert m["reference"]["Estimated value (AUD)"] == 15000000 and "15,000,000" in m["notes"]


def test_attach_drift_resolve_and_crm_never_written(crm):
    before = sha(crm)
    db.init_db()
    con = db.connect()
    pid = db.insert(con, "project", {"name": "From CRM", "client_name": "Acme Energy"})
    crm_link.attach(con, pid, 60)
    assert crm_link.linked_projects(con, 60) == ["From CRM"]
    assert crm_link.drift(con, pid)["changed"] == []

    c = sqlite3.connect(crm)                                  # the CRM team edits the opportunity
    c.execute("UPDATE opportunities SET expected_completion_date='2029-01-31', location_state='Queensland' WHERE opportunity_id=60 AND record_status='A'")
    c.commit(); c.close()
    after_edit = sha(crm)
    d = crm_link.drift(con, pid)
    assert {x["field"] for x in d["changed"]} == {"project_end", "location"}
    assert next(x for x in d["changed"] if x["field"] == "project_end")["was"] == "2028-06-30"

    crm_link.resolve(con, pid, accept=["project_end"], ignore=["location"])
    p = db.one(con, "SELECT project_end, location FROM project WHERE id=?", (pid,))
    assert p["project_end"] == "2029-01-31" and p["location"] is None     # accepted copied; ignored left alone
    assert crm_link.drift(con, pid)["changed"] == []
    assert sha(crm) == after_edit and before != after_edit              # PMT left the CRM file byte for byte as the CRM team had it
    con.close()


def test_opportunity_gone(crm):
    db.init_db()
    con = db.connect()
    pid = db.insert(con, "project", {"name": "X"})
    crm_link.attach(con, pid, 60)
    c = sqlite3.connect(crm); c.execute("UPDATE opportunities SET hidden=1 WHERE opportunity_id=60"); c.commit(); c.close()
    assert crm_link.drift(con, pid)["gone"] is True
    con.close()


def test_connection_is_read_only(crm):
    con = crm_link._connect()
    with pytest.raises(sqlite3.OperationalError):
        con.execute("UPDATE opportunities SET opportunity_name='x'")
    con.close()


def test_settings_file_and_precedence(crm, tmp_path, monkeypatch):
    other = tmp_path / "other.db"
    other.write_bytes(crm.read_bytes())
    app_root = tmp_path / "pmt"; app_root.mkdir()
    monkeypatch.setattr(db, "APP_ROOT", app_root)
    monkeypatch.delenv(crm_link.ENV, raising=False)
    assert crm_link.status()["configured"] is False and "crm_link.txt" in crm_link.status()["message"]
    (app_root / "crm_link.txt").write_text(f"# comment\n\n  \"{other}\"  \n", encoding="utf-8-sig")   # quotes, blank lines, BOM and comments are fine
    s = crm_link.status()
    assert s["ok"] is True and s["file"] == "other.db" and s["source"] == "crm_link.txt"
    monkeypatch.setenv(crm_link.ENV, str(crm))                   # the environment variable wins when both are set
    assert crm_link.status()["file"] == "crm.db" and "environment" in crm_link.status()["source"]
    monkeypatch.delenv(crm_link.ENV)
    (app_root / "crm_link.txt").write_text(str(tmp_path / "missing.db"))
    assert "not found" in crm_link.status()["message"] and "crm_link.txt" in crm_link.status()["message"]
