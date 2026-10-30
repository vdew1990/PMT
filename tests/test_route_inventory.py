"""The live route set must equal the committed snapshot (docs/route_inventory_before.txt).

Catches a dropped, duplicated, renamed or re-configured route when `app/main.py` is split into routers. Registration order
is checked where it can matter: for every pair of routes that share an HTTP method and whose paths could match the same
URL (for example `/variations/from-schedule` and `/variations/{vid}`), the one registered first must stay first.
Routes that cannot match the same URL may move relative to each other.

When a route is added or changed on purpose, regenerate the snapshot:
    .venv/bin/python tools/route_inventory.py > docs/route_inventory_before.txt
"""
import importlib.util
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "docs" / "route_inventory_before.txt"


def _tool():
    spec = importlib.util.spec_from_file_location("route_inventory", ROOT / "tools" / "route_inventory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _lines():
    from app.main import app
    tool = _tool()
    return tool, tool.inventory(app), SNAPSHOT.read_text(encoding="utf-8").splitlines()


def test_route_set_matches_snapshot():
    _tool_mod, live, snap = _lines()
    a, b = Counter(live), Counter(snap)
    missing, extra = sorted((b - a).elements()), sorted((a - b).elements())
    assert not missing and not extra, "routes missing from the app:\n" + "\n".join(missing) + "\nroutes not in the snapshot:\n" + "\n".join(extra)
    assert len(live) == len(snap)


def test_no_duplicate_method_and_path():
    tool, live, _snap = _lines()
    seen = Counter((tool.parse(l)["methods"], tool.parse(l)["path"]) for l in live)
    assert not [k for k, n in seen.items() if n > 1 and k[1] != "/"]   # "/" and docs routes may share GET,HEAD


def test_order_of_overlapping_routes_is_kept():
    tool, live, snap = _lines()
    assert tool.order_signature(live) == tool.order_signature(snap)
