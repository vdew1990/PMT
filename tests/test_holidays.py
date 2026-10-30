import pytest

from app import db, holidays
from tests.conftest import *  # noqa: F401,F403


def _client(demo):
    from fastapi.testclient import TestClient
    from app.main import app
    con, pid = demo
    con.commit()
    return TestClient(app), pid


def test_fetch_year_keeps_national_and_queensland_only(monkeypatch):
    monkeypatch.setattr(holidays, "_get_json", lambda url, timeout=20: [
        dict(date="2027-01-01", name="New Year's Day", counties=None, **{"global": True}),
        dict(date="2027-03-08", name="Labour Day", counties=["AU-VIC"], **{"global": False}),
        dict(date="2027-05-03", name="Labour Day", counties=["AU-QLD"], **{"global": False}),
        dict(date="2027-10-04", name="King's Birthday", counties=["AU-NSW", "AU-QLD"], **{"global": False})])
    got = holidays.fetch_year(2027)
    assert ("2027-01-01", "New Year's Day") in got and ("2027-05-03", "Labour Day") in got and ("2027-10-04", "King's Birthday") in got
    assert all(d != "2027-03-08" for d, _ in got)


def test_range_endpoint_loads_the_years_asked_and_does_not_double(demo, monkeypatch):
    c, pid = _client(demo)
    seen = []
    monkeypatch.setattr(holidays, "fetch_year", lambda y, state="AU-QLD": seen.append(y) or [(f"{y}-01-01", "New Year's Day"), (f"{y}-12-25", "Christmas Day")])
    with c as t:
        r = t.post(f"/api/p/{pid}/holidays", json=dict(internet=True, from_year=2031, to_year=2033)).json()
        assert seen == [2031, 2032, 2033] and r["added"] == 6 and r["years"] == [2031, 2032, 2033] and r["errors"] == []
        assert t.post(f"/api/p/{pid}/holidays", json=dict(internet=True, from_year=2032, to_year=2034)).json()["added"] == 2    # only 2034 is new
        assert t.post(f"/api/p/{pid}/holidays", json=dict(internet=True, from_year=2040, to_year=2090)).status_code >= 400      # range too long


def test_internet_failure_is_reported_not_swallowed_and_builtin_list_honours_the_range(demo, monkeypatch):
    c, pid = _client(demo)
    def boom(y, state="AU-QLD"):
        raise OSError("no route")
    monkeypatch.setattr(holidays, "fetch_year", boom)
    with c as t:
        r = t.post(f"/api/p/{pid}/holidays", json=dict(internet=True, from_year=2028, to_year=2029))
        assert r.status_code >= 400 and "built-in list" in r.json()["detail"]
        got = t.post(f"/api/p/{pid}/holidays", json=dict(standard=True, from_year=2028, to_year=2028)).json()
        assert got["added"] > 5 and got["years"] == [2028]
        days = [x["day"] for x in t.get(f"/api/p/{pid}/holidays").json() if x["day"].startswith("2028")]
        assert len(days) == got["added"] or len(days) >= got["added"]
