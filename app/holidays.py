"""Queensland public holidays 2024-2035, from the PMT workbook Holidays sheet. Load them into a project from Settings."""

QLD_HOLIDAYS = [
    ('2024-01-01', "New Year's Day"), ('2024-01-26', 'Australia Day'), ('2024-03-29', 'Good Friday'),
    ('2024-03-30', 'Day after Good Friday'), ('2024-03-31', 'Easter Sunday'), ('2024-04-01', 'Easter Monday'),
    ('2024-04-25', 'Anzac Day'), ('2024-05-06', 'Labour Day'), ('2024-08-14', 'Royal QLD EKKA Show'),
    ('2024-10-07', "King's Bday"), ('2024-12-24', 'Christmas Eve'), ('2024-12-25', 'Christmas Day'),
    ('2024-12-26', 'Boxing Day'), ('2025-01-01', "New Year's Day"), ('2025-01-26', 'Australia Day'),
    ('2025-01-27', 'Australia Day (extra)'), ('2025-04-18', 'Good Friday'), ('2025-04-19', 'Day after Good Friday'),
    ('2025-04-20', 'Easter Sunday'), ('2025-04-21', 'Easter Monday'), ('2025-04-25', 'Anzac Day'),
    ('2025-05-05', 'Labour Day'), ('2025-08-13', 'Royal QLD EKKA Show'), ('2025-10-06', "King's Bday"),
    ('2025-12-24', 'Christmas Eve'), ('2025-12-25', 'Christmas Day'), ('2025-12-26', 'Boxing Day'),
    ('2026-01-01', "New Year's Day"), ('2026-01-26', 'Australia Day'), ('2026-04-03', 'Good Friday'),
    ('2026-04-04', 'Day after Good Friday'), ('2026-04-05', 'Easter Sunday'), ('2026-04-06', 'Easter Monday'),
    ('2026-04-25', 'Anzac Day'), ('2026-05-04', 'Labour Day'), ('2026-08-12', 'Royal QLD EKKA Show'),
    ('2026-10-05', "King's Bday"), ('2026-12-24', 'Christmas Eve'), ('2026-12-25', 'Christmas Day'),
    ('2026-12-26', 'Boxing Day'), ('2026-12-28', 'Boxing Day (Extra)'), ('2027-01-01', "New Year's Day"),
    ('2027-01-26', 'Australia Day'), ('2027-03-26', 'Good Friday'), ('2027-03-27', 'Day after Good Friday'),
    ('2027-03-28', 'Easter Sunday'), ('2027-03-29', 'Easter Monday'), ('2027-04-25', 'Anzac Day'),
    ('2027-05-03', 'Labour Day'), ('2027-08-11', 'Royal QLD EKKA Show'), ('2027-10-04', "King's Bday"),
    ('2027-12-24', 'Christmas Eve'), ('2027-12-25', 'Christmas Day'), ('2027-12-28', 'Boxing Day'),
    ('2028-01-01', "New Year's Day"), ('2028-01-26', 'Australia Day'), ('2028-04-14', 'Good Friday'),
    ('2028-04-15', 'Day after Good Friday'), ('2028-04-16', 'Easter Sunday'), ('2028-04-17', 'Easter Monday'),
    ('2028-04-25', 'Anzac Day'), ('2028-05-01', 'Labour Day'), ('2028-08-16', 'Royal QLD EKKA Show'),
    ('2028-10-02', "King's Bday"), ('2028-12-24', 'Christmas Eve'), ('2028-12-25', 'Christmas Day'),
    ('2028-12-26', 'Boxing Day'), ('2029-01-01', "New Year's Day"), ('2029-01-26', 'Australia Day'),
    ('2029-03-30', 'Good Friday'), ('2029-03-31', 'Day after Good Friday'), ('2029-04-01', 'Easter Sunday'),
    ('2029-04-02', 'Easter Monday'), ('2029-04-25', 'Anzac Day'), ('2029-05-07', 'Labour Day'),
    ('2029-08-15', 'Royal QLD EKKA Show'), ('2029-10-01', "King's Bday"), ('2029-12-24', 'Christmas Eve'),
    ('2029-12-25', 'Christmas Day'), ('2029-12-26', 'Boxing Day'), ('2030-01-01', "New Year's Day"),
    ('2030-01-27', 'Australia Day'), ('2030-04-19', 'Good Friday'), ('2030-04-20', 'Day after Good Friday'),
    ('2030-04-21', 'Easter Sunday'), ('2030-04-22', 'Easter Monday'), ('2030-04-25', 'Anzac Day'),
    ('2030-05-06', 'Labour Day'), ('2030-08-14', 'Royal QLD EKKA Show'), ('2030-10-07', "King's Bday"),
    ('2030-12-24', 'Christmas Eve'), ('2030-12-25', 'Christmas Day'), ('2030-12-26', 'Boxing Day'),
    ('2031-01-01', "New Year's Day"), ('2031-01-26', 'Australia Day'), ('2031-04-11', 'Good Friday'),
    ('2031-04-12', 'Day after Good Friday'), ('2031-04-13', 'Easter Sunday'), ('2031-04-14', 'Easter Monday'),
    ('2031-04-25', 'Anzac Day'), ('2031-05-05', 'Labour Day'), ('2031-08-13', 'Royal QLD EKKA Show'),
    ('2031-10-06', "King's Bday"), ('2031-12-24', 'Christmas Eve'), ('2031-12-25', 'Christmas Day'),
    ('2031-12-26', 'Boxing Day'), ('2032-01-01', "New Year's Day"), ('2032-01-26', 'Australia Day'),
    ('2032-03-26', 'Good Friday'), ('2032-03-27', 'Day after Good Friday'), ('2032-03-28', 'Easter Sunday'),
    ('2032-03-29', 'Easter Monday'), ('2032-04-25', 'Anzac Day'), ('2032-05-03', 'Labour Day'),
    ('2032-08-11', 'Royal QLD EKKA Show'), ('2032-10-04', "King's Bday"), ('2032-12-24', 'Christmas Eve'),
    ('2032-12-25', 'Christmas Day'), ('2032-12-26', 'Boxing Day'), ('2033-01-01', "New Year's Day"),
    ('2033-01-26', 'Australia Day'), ('2033-04-15', 'Good Friday'), ('2033-04-16', 'Day after Good Friday'),
    ('2033-04-17', 'Easter Sunday'), ('2033-04-18', 'Easter Monday'), ('2033-04-25', 'Anzac Day'),
    ('2033-05-02', 'Labour Day'), ('2033-10-03', "King's Bday"), ('2033-12-24', 'Christmas Eve'),
    ('2033-12-25', 'Christmas Day'), ('2033-12-26', 'Boxing Day'), ('2034-01-01', "New Year's Day"),
    ('2034-01-26', 'Australia Day'), ('2034-04-07', 'Good Friday'), ('2034-04-08', 'Day after Good Friday'),
    ('2034-04-09', 'Easter Sunday'), ('2034-04-10', 'Easter Monday'), ('2034-04-25', 'Anzac Day'),
    ('2034-05-01', 'Labour Day'), ('2034-10-02', "King's Bday"), ('2034-12-24', 'Christmas Eve'),
    ('2034-12-25', 'Christmas Day'), ('2034-12-26', 'Boxing Day'), ('2035-01-01', "New Year's Day"),
    ('2035-01-26', 'Australia Day'), ('2035-03-23', 'Good Friday'), ('2035-03-24', 'Day after Good Friday'),
    ('2035-03-25', 'Easter Sunday'), ('2035-03-26', 'Easter Monday'), ('2035-04-25', 'Anzac Day'),
    ('2035-05-07', 'Labour Day'), ('2035-10-01', "King's Bday"), ('2035-12-24', 'Christmas Eve'),
    ('2035-12-25', 'Christmas Day'), ('2035-12-26', 'Boxing Day'),
]


# ---- public holidays from the internet, for a range of years ---------------------------------------------------------
# Nager.Date (https://date.nager.at) is a free public-holiday API that needs no key. For Australia it lists every holiday with the states it
# applies to ("counties", e.g. "AU-QLD") or none when it is national. The PC needs internet; the built-in list above is the offline fallback.
import json
import urllib.request

NAGER = "https://date.nager.at/api/v3/PublicHolidays/{year}/AU"
STATE = "AU-QLD"


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "PMT public holiday loader", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf8"))


def fetch_year(year, state=STATE):
    """[(date, name)] for one year in this state: national holidays plus those listed for the state."""
    rows = _get_json(NAGER.format(year=int(year)))
    out = []
    for h in rows:
        counties = h.get("counties") or []
        if h.get("global") or not counties or state in counties:
            out.append((h["date"][:10], (h.get("name") or h.get("localName") or "Public holiday").strip()))
    return sorted(set(out))


def check_range(y0, y1):
    y0, y1 = int(y0), int(y1)
    if y0 > y1:
        y0, y1 = y1, y0
    if y0 < 2000 or y1 > 2100 or y1 - y0 > 30:
        raise ValueError("Choose a range of up to 31 years between 2000 and 2100")
    return y0, y1


def bundled(y0, y1):
    return [(d, n) for d, n in QLD_HOLIDAYS if y0 <= int(d[:4]) <= y1]
