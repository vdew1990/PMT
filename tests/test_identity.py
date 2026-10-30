"""Who is using PMT: OneDrive for Business reports the organisation, never use it as the person's name."""
from app import identity


def _setup(monkeypatch, office=None, windows=None):
    monkeypatch.delenv("PMT_USER_UPN", raising=False)
    monkeypatch.delenv("PMT_USER_NAME", raising=False)
    monkeypatch.setattr(identity, "_onedrive_business", lambda: dict(upn="vincent.dewulf@epecgroup.com.au", name=None, org="EPEC Group Pty Ltd", source="OneDrive for Business"))
    monkeypatch.setattr(identity, "_office_name", lambda: office)
    monkeypatch.setattr(identity, "_windows_api", lambda: dict(upn="x@y", name=windows, source="Windows sign-in") if windows else None)
    identity.reset()


def test_organisation_is_the_entity_not_the_name(monkeypatch):
    _setup(monkeypatch, office="Vincent De Wulf")
    u = identity.current()
    assert u["name"] == "Vincent De Wulf" and u["org"] == "EPEC Group Pty Ltd"
    identity.reset()


def test_company_names_are_skipped_down_to_the_email(monkeypatch):
    _setup(monkeypatch, office="EPEC Projects Pty Ltd", windows="EPEC Engineering Pty Ltd")
    assert identity.current()["name"] == "Vincent Dewulf"  # from vincent.dewulf@...
    identity.apply_profile(name="Vincent De Wulf", entity="EPEC Projects Pty Ltd")
    u = identity.current()
    assert u["name"] == "Vincent De Wulf" and u["org"] == "EPEC Projects Pty Ltd"
    identity.reset()
