"""Argus: browser check of the Ground-Up register date display (Neo, safe part only) on the demo seed.

Expected result from Neo's brief as relayed by Atlas (31/10/2026): the PS04.003 Lump row shows "10/12/2026 – ".
Chromium stand-in; Edge itself is not tested. Synthetic data only (demo seed built into a temporary database; the
tracked demo/ files are not rewritten)."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

_SEED = r'''
import os, sys, shutil, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from app import db
db.DB_PATH = Path(os.environ["PMT_DB"]); db.init_db()
from demo import build_demo
tmp = Path(tempfile.mkdtemp(prefix="argus-demo-files-"))
for f in build_demo.DEMO.iterdir():
    if f.is_file() and f.suffix in (".pdf", ".xml", ".xlsx"):
        shutil.copy2(f, tmp / f.name)
build_demo.DEMO = tmp
con = db.connect()
pid, _ = build_demo.seed(con)
build_demo.seed_extras(con, pid)
con.commit()
print(pid)
'''


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def demo_server():
    tmp = Path(tempfile.mkdtemp(prefix="argus-browser-demo-"))
    env = dict(os.environ, PMT_DB=str(tmp / "d.db"), PMT_NO_JAVA_DOWNLOAD="1")
    pid = int(subprocess.run([sys.executable, "-c", _SEED, str(ROOT)], cwd=str(tmp), env=env, check=True,
                             capture_output=True, text=True).stdout.strip().splitlines()[-1])
    port = _free_port()
    log = open(tmp / "server.log", "wb")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/api/projects", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("PMT server did not start; see " + str(tmp / "server.log"))
    yield base, pid
    proc.terminate()
    proc.wait(10)
    log.close()


def test_groundup_register_ps04_003_lump_shows_open_end(demo_server, browser_page, tmp_path):
    (base, pid), page = demo_server, browser_page
    page.add_init_script(f"localStorage.setItem('pmt', JSON.stringify({{pid: {pid}, scope: {{node: null, from: null, to: null}}}}))")
    page.goto(base + "/#/groundup")
    page.wait_for_load_state("networkidle")
    page.locator("h1", has_text="Ground-Up register").wait_for(timeout=10000)
    # show every item: the CBS-line grouping, in case "Your groups" hides lines not assigned to anyone
    by_cbs = page.get_by_text("By CBS line", exact=True)
    if by_cbs.count():
        by_cbs.first.click()
    row = page.locator("tr").filter(has_text="Demobilisation")
    row.first.wait_for(timeout=10000)
    page.screenshot(path=str(tmp_path / "groundup.png"), full_page=True)
    assert row.count() == 1, row.all_inner_texts()
    cells = [t for t in row.first.locator("td").all_text_contents()]
    dates = [t for t in cells if "/20" in t]
    assert dates == ["10/12/2026 – "], cells
    assert "30/11/2026" not in row.first.inner_text()
    assert page.js_errors == []
