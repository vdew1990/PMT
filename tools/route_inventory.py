"""Route inventory of the FastAPI app: one line per route, in registration order.

Usage (from the repository root):
    .venv/bin/python tools/route_inventory.py > docs/route_inventory_before.txt

The snapshot is compared with the live app by tests/test_route_inventory.py. It deliberately leaves out the module an
endpoint lives in, so moving a route between files does not change its line; everything that affects how a request
is matched, validated or answered is recorded (method, path, function name, response class, status code, response
model, dependencies, tags, operation id, schema visibility).
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ("kind", "methods", "path", "name", "response_class", "status_code", "response_model", "include_in_schema",
          "dependencies", "tags", "operation_id")


def _dep_names(dependant):
    out = []
    for d in getattr(dependant, "dependencies", []) or []:
        call = getattr(d, "call", None)
        out.append(getattr(call, "__name__", repr(call)))
    return ",".join(out)


def flat_routes(routes):
    """The routes in the order a request is matched against them, with included routers expanded in place.

    Older FastAPI copies an included router's routes into the app when it is included; newer releases (0.162 at the
    time of writing) keep one lazy `_IncludedRouter` entry that holds the router and match its routes in order. Both are
    flattened here to the same list, so the snapshot does not depend on the installed FastAPI version."""
    for r in routes:
        if hasattr(r, "effective_candidates"):
            yield from flat_routes(r.effective_candidates())
        else:
            yield r


def describe(route):
    """The recorded fields of one route, as a dict of strings."""
    kind = type(getattr(route, "original_route", route)).__name__
    methods = ",".join(sorted(getattr(route, "methods", None) or [])) or "-"
    d = dict(kind=kind, methods=methods, path=getattr(route, "path", "?"), name=getattr(route, "name", "?"))
    rc = getattr(route, "response_class", None)
    d["response_class"] = getattr(rc, "__name__", "-") if rc is not None else "-"
    d["status_code"] = str(getattr(route, "status_code", None))
    rm = getattr(route, "response_model", None)
    d["response_model"] = getattr(rm, "__name__", str(rm))
    d["include_in_schema"] = str(getattr(route, "include_in_schema", None))
    d["dependencies"] = _dep_names(getattr(route, "dependant", None)) or "-"
    d["tags"] = ",".join(str(t) for t in (getattr(route, "tags", None) or [])) or "-"
    d["operation_id"] = str(getattr(route, "unique_id", None) or getattr(route, "operation_id", None) or "-")
    return d


def inventory(app):
    """Lines in registration order: tab-separated, fields as in FIELDS."""
    return ["\t".join(describe(r)[f] for f in FIELDS) for r in flat_routes(app.routes)]


def parse(line):
    return dict(zip(FIELDS, line.rstrip("\n").split("\t")))


def _segments_overlap(a, b):
    sa, sb = a.strip("/").split("/"), b.strip("/").split("/")
    if any(":path}" in s for s in sa + sb):          # a path convertor can swallow several segments: be conservative
        return True
    if len(sa) != len(sb):
        return False
    return all(x == y or "{" in x or "{" in y for x, y in zip(sa, sb))


def overlap_pairs(lines):
    """Index pairs (i, j), i < j, of routes that share an HTTP method and whose paths could match the same URL.
    For these the registration order decides which route answers, so it must not change."""
    recs = [parse(l) for l in lines]
    pairs = []
    for i, a in enumerate(recs):
        ma = set(a["methods"].split(","))
        for j in range(i + 1, len(recs)):
            b = recs[j]
            if ma & set(b["methods"].split(",")) and _segments_overlap(a["path"], b["path"]):
                pairs.append((i, j))
    return pairs


def order_signature(lines):
    """For every overlapping pair, the two routes (as full lines) in the order they are registered."""
    pairs = overlap_pairs(lines)
    return sorted((lines[i], lines[j]) for i, j in pairs)


def load_app():
    os.environ.setdefault("PMT_NO_JAVA_DOWNLOAD", "1")
    os.environ.setdefault("PMT_DB", str(Path(tempfile.mkdtemp(prefix="pmt-inv-")) / "inv.db"))
    sys.path.insert(0, str(ROOT))
    from app.main import app
    return app


if __name__ == "__main__":
    print("\n".join(inventory(load_app())))
