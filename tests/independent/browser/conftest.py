"""Argus browser settings: cloud Chromium (no `playwright install`), --no-sandbox, and a PMT server on loopback with a
fresh synthetic database per test. The builders' tests/conftest.py is not touched.

Pending decision (Vincent, via Neo): the guard for machines without Playwright. Until it exists, Playwright is imported
inside the fixture, so a machine without it reports an error for these tests only, not a collection failure."""
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
CHROMIUM = "/opt/pw-browsers/chromium"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def pmt_server():
    """A PMT server on 127.0.0.1 with its own empty database (synthetic data is added by the test over HTTP)."""
    tmp = Path(tempfile.mkdtemp(prefix="argus-browser-"))
    env = dict(os.environ, PMT_DB=str(tmp / "b.db"), PMT_NO_JAVA_DOWNLOAD="1")
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
    yield base
    proc.terminate()
    proc.wait(10)
    log.close()


@pytest.fixture()
def browser_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"], headless=True)
        ctx = b.new_context(viewport={"width": 1500, "height": 950})
        page = ctx.new_page()
        page.js_errors = []
        page.on("pageerror", lambda e: page.js_errors.append(str(e)))
        yield page
        ctx.close()
        b.close()
