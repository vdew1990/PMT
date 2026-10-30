import os
os.environ.setdefault("PMT_NO_JAVA_DOWNLOAD", "1")   # tests never fetch Java
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="pmt-test-")
os.environ["PMT_DB"] = str(Path(_tmp) / "test.db")

import pytest  # noqa: E402

from app import db  # noqa: E402


@pytest.fixture(scope="module")
def demo():
    """A fully seeded demonstration project in a fresh database."""
    from demo import build_demo
    path = Path(_tmp) / f"demo-{os.getpid()}-{id(object())}.db"
    os.environ["PMT_DB"] = str(path)
    db.DB_PATH = path
    db.init_db()
    build_demo.write_template_file(build_demo.DEMO / "demo_project_template.xlsx")
    build_demo.build_pronto_file(build_demo.DEMO / "demo_pronto_export.xlsx")
    con = db.connect()
    pid, _ = build_demo.seed(con)
    build_demo.seed_extras(con, pid)
    con.commit()
    yield con, pid
    con.close()


@pytest.fixture()
def blank():
    path = Path(tempfile.mkdtemp(prefix="pmt-blank-")) / "b.db"
    db.DB_PATH = path
    db.init_db()
    con = db.connect()
    yield con
    con.close()
