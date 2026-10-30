"""Project manager workload, as a percentage of what the PM can carry.

Each running project asks for a share of a PM's time. That share grows with the project's complexity (1..5), the
client's complexity and risk, and the phase the project is in (full in delivery, less while mobilising or closing out).
Sites far from the PM's base cost travel, and sites spread far from each other cost more than sites close together.
What a PM can carry follows their PM level in EPEC-PM-FW-0002 (PM Technical Capability Framework): Level 1 coordinates
under direction, Level 2 delivers a project, Level 3 delivers significant projects or programs, Level 4 leads a
portfolio. Workload % = demand / capacity. Every factor is reported, so the number can be challenged.

The weights below are a starting point to calibrate against how the team really feels; they live here in one place.
"""
import math
import re
from datetime import date

# share of one full-time Level 2 PM that a project of this complexity needs at the peak of delivery
COMPLEXITY_LOAD = {1: 0.15, 2: 0.25, 3: 0.40, 4: 0.60, 5: 0.85}
# what a PM of each level can carry, in Level 2 equivalents (times their FTE)
LEVEL_CAPACITY = {1: 0.6, 2: 1.0, 3: 1.25, 4: 1.5, 5: 1.5}   # Level 5 (project director) keeps the capacity Level 4 had when 4 was the director level
LEVEL_NAME = {1: "PM Level 1 (junior PM): runs one project under direction", 2: "PM Level 2 (PM): runs a portfolio of projects",
              3: "PM Level 3 (senior PM): runs a portfolio of significant projects", 4: "PM Level 4 (senior PM / program manager): runs large or multi-discipline projects and programs",
              5: "PM Level 5 (project director): directs a program and its team of PMs"}
# what each level looks after: a junior PM one project, a PM or senior PM a portfolio, a project director a program
SPAN = {1: "project", 2: "portfolio", 3: "portfolio", 4: "program", 5: "program"}
MAX_PROJECTS = {1: 1}
# the lowest PM level that should run a project of this complexity on their own
REQUIRED_LEVEL = {1: 1, 2: 2, 3: 2, 4: 3, 5: 3}      # by the 1 to 5 complexity, used only while a project has no director's baseline
# once the director has scored the project the band decides (complexity.py BANDS): C1 L1, C2 L2, C3 L4, C4 L5
BAND_LEVEL = {"C1": 1, "C2": 2, "C3": 4, "C4": 5}
CLIENT_FACTOR = {1: 0.85, 2: 0.93, 3: 1.0, 4: 1.12, 5: 1.25}
RISK_FACTOR = {"low": 0.97, "medium": 1.0, "high": 1.08}
TRAVEL_MAX, TRAVEL_KM = 0.25, 4000      # +25 % at 1,000 km or more from the PM's base
SPREAD_MAX, SPREAD_KM = 0.20, 2500      # +20 % when the PM's sites average 500 km or more from their middle
BANDS = [(70, "available", "Room for more"), (90, "good", "Well loaded"), (105, "full", "Full"), (999, "over", "Overloaded")]


def km(a, b):
    """Great-circle distance between two (lat, lon) points."""
    if None in (a[0], a[1], b[0], b[1]):
        return None
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def max_kv(voltage):
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(voltage or ""))]
    return max(nums) if nums else None


def suggest_complexity(contract_value, project_type=None, voltage=None):
    """A first guess when nobody has set the project's complexity: size, then high voltage and hybrid scope add one."""
    v = contract_value or 0
    c = 1 if v < 5e6 else 2 if v < 15e6 else 3 if v < 40e6 else 4 if v < 100e6 else 5
    if (max_kv(voltage) or 0) >= 220:
        c += 1
    if (project_type or "").lower().startswith("hybrid"):
        c += 1
    return min(5, c)


def phase(start, end, status_date):
    """(factor, label): how much of the peak load the project needs now."""
    try:
        sd = date.fromisoformat((status_date or date.today().isoformat())[:10])
        s = date.fromisoformat(start[:10]) if start else None
        e = date.fromisoformat(end[:10]) if end else None
    except ValueError:
        return 1.0, "Delivery"
    if s and sd < s:
        return (0.35, "Mobilising") if (s - sd).days <= 90 else (0.15, "Awarded, starts later")
    if e and sd > e:
        return 0.4, "Close-out and defects"
    if s and e and e > s and (sd - s).days / (e - s).days > 0.9:
        return 0.75, "Commissioning and handover"
    return 1.0, "Delivery"


def band(pct):
    for top, key, label in BANDS:
        if pct < top:
            return key, label
    return "over", "Overloaded"


def project_demand(p, client=None, base=None):
    """The load one project puts on its PM, with every factor."""
    c = p.get("complexity") or suggest_complexity(p.get("contract_value"), p.get("project_type"), p.get("voltage"))
    load = COMPLEXITY_LOAD[c]
    cf = CLIENT_FACTOR.get((client or {}).get("complexity") or 3, 1.0)
    rf = RISK_FACTOR.get(((client or {}).get("risk") or "medium").lower(), 1.0)
    ph, ph_label = phase(p.get("start"), p.get("end"), p.get("status_date"))
    dist = km(base, (p.get("lat"), p.get("lon"))) if base else None
    tf = 1 + min(TRAVEL_MAX, (dist or 0) / TRAVEL_KM)
    return dict(id=p["id"], name=p["name"], complexity=c, complexity_set=p.get("complexity_set", bool(p.get("complexity"))), base_load=load, client_factor=round(cf * rf, 3),
                phase=ph_label, phase_factor=ph, km_from_base=round(dist) if dist is not None else None, travel_factor=round(tf, 3),
                demand=round(load * cf * rf * ph * tf, 4), cx_band=p.get("cx_band"), required_level=BAND_LEVEL.get(p.get("cx_band")) or REQUIRED_LEVEL[c])


def pm_workload(person, projects, clients):
    """One PM: their projects' demand, the spread of their sites, their capacity and workload %."""
    base = (person.get("lat"), person.get("lon")) if person.get("lat") is not None else None
    rows = [project_demand(p, clients.get(_norm(p.get("client"))), base) for p in projects]
    sites = [(p["lat"], p["lon"]) for p in projects if p.get("lat") is not None and p.get("lon") is not None]
    spread_km = None
    if len(sites) >= 2:
        mid = (sum(s[0] for s in sites) / len(sites), sum(s[1] for s in sites) / len(sites))
        spread_km = sum(km(mid, s) for s in sites) / len(sites)
    sf = 1 + min(SPREAD_MAX, (spread_km or 0) / SPREAD_KM)
    demand = sum(r["demand"] for r in rows) * sf
    level = person.get("pm_level")
    capacity = LEVEL_CAPACITY.get(level or 2, 1.0) * (person.get("fte") if person.get("fte") not in (None, "") else 1.0)
    pct = round(100 * demand / capacity, 1) if capacity else None
    key, label = band(pct or 0)
    stretch = [r["name"] for r in rows if level and level < r["required_level"]]
    cap_n = MAX_PROJECTS.get(level)
    too_many = (f"A junior PM (Level 1) runs one project: {len(rows)} are assigned" if cap_n and len(rows) > cap_n else None)
    return dict(name=person["name"], level=level, level_set=bool(level), level_name=LEVEL_NAME.get(level or 0, "PM level not set (counted as Level 2)"),
                fte=person.get("fte") if person.get("fte") not in (None, "") else 1.0, base=person.get("base"), reports_to=person.get("reports_to"),
                projects=rows, spread_km=round(spread_km) if spread_km is not None else None, spread_factor=round(sf, 3),
                demand=round(demand, 3), capacity=round(capacity, 3), pct=pct, band=key, band_label=label, stretch=stretch,
                spare=round(capacity - demand, 3), span=SPAN.get(level or 2), too_many=too_many)


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())
