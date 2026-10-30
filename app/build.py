"""Which release of the program files is in use: a fingerprint of the code and page files (name, size, date).

The server keeps the fingerprint it started with. When the files on disk change while it runs (a new release copied
over the SharePoint folder), the two differ: the page shows a "restart PMT" banner and the launcher replaces the old
server instead of reconnecting to it (an old server with new pages gives "Not Found" errors)."""
import hashlib
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = "2026-10-31.121"  # the bundle version in HANDOFF.md; shown at the bottom of the left menu
_cache = {"at": 0.0, "fp": None}


def _files():
    return sorted([*ROOT.glob("app/*.py"), *ROOT.glob("app/*.sql"), *ROOT.glob("static/**/*.js"), *ROOT.glob("static/**/*.css"),
                   ROOT / "static" / "index.html", ROOT / "requirements.txt"])


def on_disk(max_age=0.0):
    if max_age and _cache["fp"] and time.time() - _cache["at"] < max_age:
        return _cache["fp"]
    h = hashlib.sha1()
    for f in _files():
        try:
            st = f.stat()
        except OSError:
            continue
        h.update(f"{f.relative_to(ROOT).as_posix()}|{st.st_size}|{int(st.st_mtime)}\n".encode())
    _cache.update(at=time.time(), fp=h.hexdigest()[:12])
    return _cache["fp"]


STARTED = on_disk()
SERVER = None  # the running uvicorn server, set by app.launch so /api/shutdown can stop it cleanly
