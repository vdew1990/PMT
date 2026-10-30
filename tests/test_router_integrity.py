"""Guards for the router split: a lazy reference (a function-local import or a name used only inside a function) fails
at call time, not at import time, so the import-time checks never see it. Found by the write replay: duplicate-cbs
returned 500 because a function-local `from . import pronto` resolved to app.routers.pronto."""
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted((ROOT / "app" / "routers").glob("*.py")) + [ROOT / "app" / "main.py"]


def test_duplicate_cbs_works_on_a_seeded_project(demo):
    from app.main import app
    con, pid = demo
    c = TestClient(app)
    line = con.execute("SELECT id FROM cbs_node WHERE project_id=? AND code=?", (pid, "PL01.005")).fetchone()
    assert line, "seeded demo project should carry PL01.005"
    r = c.post(f"/api/p/{pid}/variations", json=dict(title="Dup test", stage="EPC", prepared_by="Test",
                                                    submission_date="20/10/2026", value=1000, funding="separate"))
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    r = c.post(f"/api/p/{pid}/variations/{vid}/duplicate-cbs", json=dict(node_ids=[line["id"]]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] >= 1
    n = con.execute("SELECT COUNT(*) n FROM cbs_node WHERE project_id=? AND variation_id=? AND copied_from=?",
                    (pid, vid, line["id"])).fetchone()["n"]
    assert n == 1


def test_routers_have_no_undefined_names():
    from pyflakes import api, reporter
    import io
    out, err = io.StringIO(), io.StringIO()
    rep = reporter.Reporter(out, err)
    for f in FILES:
        api.check(f.read_text(encoding="utf-8"), str(f), rep)
    bad = [ln for ln in (out.getvalue() + err.getvalue()).splitlines()
           if "undefined name" in ln or "syntax" in ln.lower() or "unable to detect undefined names" in ln]
    assert not bad, "\n".join(bad)


def test_local_relative_imports_resolve():
    """Every function-local `from . import x` / `from .. import x` in the routers names a module that exists."""
    import ast
    import importlib
    for f in FILES:
        pkg = "app.routers" if f.parent.name == "routers" else "app"
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level:
                base = importlib.util.resolve_name("." * node.level + (node.module or ""), pkg)
                mod = importlib.import_module(base)
                for a in node.names:
                    assert hasattr(mod, a.name) or importlib.util.find_spec(f"{base}.{a.name}"), f"{f.name}:{node.lineno} {a.name}"
