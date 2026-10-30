"""Shared helpers for tools/smoke_compare.py (GET replay) and tools/write_replay.py (POST, PUT and DELETE replay).

Both scripts can be pointed at another checkout of the code with the PMT_CODE_ROOT environment variable (default: this
repository), so the same script and the same seeded database can be run against the code before and after a refactor
and the output files compared with `diff`.
"""
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
CODE_ROOT = Path(os.environ.get("PMT_CODE_ROOT") or REPO).resolve()
BINARY = ("spreadsheet", "pdf", "wordprocessing", "octet-stream", "zip")


def bootstrap(seed_db, prefix="pmt-replay-"):
    """Copy the seeded database, point the app at the copy and return (client, sqlite connection, project id, work dir)."""
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    db_copy = tmp / "replay.db"
    shutil.copy(seed_db, db_copy)
    os.environ.update(PMT_DB=str(db_copy), PMT_SYNC_THREAD="0", PMT_NO_JAVA_DOWNLOAD="1")
    sys.path.insert(0, str(CODE_ROOT))
    import warnings
    warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from app.main import app
    con = sqlite3.connect(db_copy, timeout=30)
    con.row_factory = sqlite3.Row
    pid = con.execute("SELECT id FROM project ORDER BY id LIMIT 1").fetchone()[0]
    return TestClient(app), app, con, pid, tmp


def flat_routes(routes):
    """Every route in matching order, with included routers expanded (older FastAPI copies them in; newer keeps a lazy entry)."""
    for r in routes:
        if hasattr(r, "effective_candidates"):
            yield from flat_routes(r.effective_candidates())
        else:
            yield r


def api_routes(app):
    from fastapi.routing import APIRoute
    return [r for r in flat_routes(app.routes) if isinstance(getattr(r, "original_route", r), APIRoute)]


# ---------------------------------------------------------------------------
# Binary downloads: compare what a reader sees (cell values, page text), not the bytes
# ---------------------------------------------------------------------------
def extract_xlsx(data):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data))
    out = {}
    for ws in wb.worksheets:
        cells = [[ws.title, c.coordinate, c.value if not hasattr(c.value, "isoformat") else c.value.isoformat()]
                 for row in ws.iter_rows() for c in row if c.value is not None]
        out[ws.title] = dict(dims=ws.dimensions, merged=sorted(str(m) for m in ws.merged_cells.ranges), cells=[c[1:] for c in cells])
    return out


def extract_pdf(data):
    """Page count and the text of each page, read back with pypdf (the PDFs are written by reportlab)."""
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    return dict(pages=len(r.pages), text=[(p.extract_text() or "") for p in r.pages])


def extract_docx(data):
    import docx
    d = docx.Document(io.BytesIO(data))
    return dict(paragraphs=[p.text for p in d.paragraphs], tables=[[[c.text for c in row.cells] for row in t.rows] for t in d.tables])


def _member(name, data):
    """A zip member as a hash of what a reader sees (Office files carry creation times in their bytes)."""
    if name.endswith(".xlsx"):
        data = json.dumps(extract_xlsx(data), sort_keys=True, default=str).encode()
    elif name.endswith(".docx"):
        data = json.dumps(extract_docx(data), sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


def describe_binary(resp):
    """Status-independent description of a binary response: file name, kind and extracted content."""
    ct = resp.headers.get("content-type", "")
    disp = resp.headers.get("content-disposition", "")
    out = dict(content_type=ct, disposition=disp, size_class="empty" if not resp.content else "non-empty")
    try:
        if "spreadsheet" in ct:
            out["xlsx"] = extract_xlsx(resp.content)
        elif "pdf" in ct:
            out["pdf"] = extract_pdf(resp.content)
        elif "wordprocessing" in ct:
            out["docx"] = extract_docx(resp.content)
        elif "zip" in ct:
            import zipfile
            z = zipfile.ZipFile(io.BytesIO(resp.content))
            out["zip"] = {i.filename: _member(i.filename, z.read(i)) for i in z.infolist()}   # member names and contents, not the stored timestamps
        else:
            out["sha256"] = hashlib.sha256(resp.content).hexdigest()
    except Exception as e:  # an unreadable file is itself a result worth comparing
        out["unreadable"] = f"{type(e).__name__}: {e}"
        out["sha256"] = hashlib.sha256(resp.content).hexdigest()
    return out


MASK_KEYS = ("build", "build_now")   # the program-file fingerprint changes with any file edit, by design (app/build.py)


def norm_json(o):
    if isinstance(o, dict):
        return {k: ("<fingerprint>" if k in MASK_KEYS else norm_json(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [norm_json(v) for v in o]
    return o


def body_of(resp):
    ct = resp.headers.get("content-type", "")
    if any(b in ct for b in BINARY):
        return describe_binary(resp)
    if "json" in ct:
        try:
            return norm_json(resp.json())
        except ValueError:
            return resp.text
    return hashlib.sha256(resp.content).hexdigest()


def is_error(resp):
    """True for an HTTP error or a 200 carrying only an error message."""
    if resp.status_code >= 400:
        return True
    ct = resp.headers.get("content-type", "")
    if "json" in ct:
        try:
            b = resp.json()
        except ValueError:
            return False
        return isinstance(b, dict) and set(b) <= {"error", "detail"} and bool(b)
    return False


def is_empty(resp):
    """A non-error response that carries no data (empty list, object or null): it proves little."""
    ct = resp.headers.get("content-type", "")
    if "json" in ct:
        try:
            return resp.json() in ([], {}, None, "")
        except ValueError:
            return False
    return not resp.content


def table_names(con):
    return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
