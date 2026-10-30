"""PMO > Project library: every knowledge document (checklists, procedures, forms) in one place.

EPEC's gate papers and readiness review forms that ship with the app are listed alongside what users upload. Each document can
be tagged with a delivery phase and/or a gate; Project lifecycle shows the ones tagged for the project's current phase and gate.
"""
import base64
import mimetypes
from datetime import datetime

from . import db, gates

MAX_BYTES = 15 * 1024 * 1024
TYPES = ["Checklist", "Procedure", "Form", "Template", "Guide", "Policy", "Other"]
PHASES = list(gates.PHASES)
PROJECT_TYPES = ['Solar farm', 'Wind farm', 'BESS', 'Hybrid (solar + BESS)', 'Mining', 'Transmission', 'Substation', 'Other']   # as on the project; no type means every type


def _builtin():
    out = []
    for g in gates.catalogue():
        if g["has_form"]:
            f = gates.form_file(g["gate"])
            out.append(dict(id=f"gate:{g['gate']}", title=f"{g['label']} ({g['form']})", doc_type="Form", phase=None, gate=g["gate"], description="EPEC gate paper",
                            filename=f.name, size=f.stat().st_size, builtin=True, url=f"/api/gates/{g['gate']}/form"))
    for ph in gates.phase_catalogue():
        for r in ph["reviews"]:
            f = gates.review_form(r["code"])
            if f:
                out.append(dict(id=f"form:{r['code']}", title=f"{r['name']} ({r['code']})", doc_type="Checklist", phase=ph["phase"], gate=None, description=r["when"] or "",
                                filename=f.name, size=f.stat().st_size, builtin=True, url=f"/api/forms/{r['code']}"))
    return out


def listing(con):
    own = [dict(r, id=f"kb:{r['id']}", builtin=False, url=f"/api/kb/{r['id']}/file") for r in db.rows(
        con, "SELECT id, title, doc_type, phase, gate, project_type, description, filename, size, uploaded_by, uploaded_at FROM kb_doc ORDER BY title")]
    return _builtin() + own


def _clean(title, doc_type, phase, gate, description, project_type=None):
    title = (title or "").strip()
    if not title:
        raise ValueError("Give the document a title")
    if phase and phase not in PHASES:
        raise ValueError("Phase is " + ", ".join(PHASES))
    gate = int(gate) if str(gate or "").strip() else None
    if gate is not None and gate not in gates.GATES:
        raise ValueError("Unknown gate")
    if project_type and project_type not in PROJECT_TYPES:
        raise ValueError("Unknown project type")
    return dict(title=title, doc_type=doc_type if doc_type in TYPES else "Other", phase=phase or None, gate=gate, project_type=project_type or None, description=(description or "").strip() or None)


def add(con, data, filename, title, doc_type, phase, gate, description, by, project_type=None):
    if not data:
        raise ValueError("The file is empty")
    if len(data) > MAX_BYTES:
        raise ValueError("The file is over 15 MB")
    d = _clean(title or filename.rsplit(".", 1)[0], doc_type, phase, gate, description, project_type)
    return db.insert(con, "kb_doc", dict(**d, filename=filename, mime=mimetypes.guess_type(filename)[0] or "application/octet-stream", size=len(data), data=base64.b64encode(data).decode(),
                                         uploaded_by=by, uploaded_at=datetime.now().isoformat(timespec="seconds")))


def update(con, did, body):
    d = _clean(body.get("title"), body.get("doc_type"), body.get("phase"), body.get("gate"), body.get("description"), body.get("project_type"))
    db.update(con, "kb_doc", did, d)


def file_of(con, did):
    f = db.one(con, "SELECT filename, mime, data FROM kb_doc WHERE id=?", (did,))
    return dict(f, data=base64.b64decode(f["data"] or "")) if f else None


def relevant(con, pid):
    """Documents tagged for the project's current delivery phase, and for its latest gate and the next one."""
    docs = listing(con)
    ptype = (db.one(con, "SELECT project_type FROM project WHERE id=?", (pid,)) or {}).get("project_type")
    ptype = "Substation" if ptype == "Substation / transmission" else ptype
    docs = [d for d in docs if not d.get("project_type") or d["project_type"] == ptype]
    ph = gates.phase_current(gates.phase_log(con, pid))
    g = gates.current(gates.log(con, pid))
    phase = ph["phase"] if ph else None
    want = {x for x in ((g["gate"], g["gate"] + 1) if g else (1,)) if x in gates.GATES}
    return dict(phase=phase, gate=g["gate"] if g else None, gates_wanted=sorted(want),
                docs=[d for d in docs if (phase and d["phase"] == phase) or (d["gate"] is not None and d["gate"] in want)])


def bundle(con):
    """Every library document plus the blank Project setup templates, as one zip (bytes)."""
    import io
    import zipfile
    from . import templates_io
    buf = io.BytesIO()
    used = set()

    def put(z, folder, name, data):
        base, dot, ext = name.rpartition(".")
        path, n = f"{folder}/{name}", 1
        while path in used:
            n += 1
            path = f"{folder}/{base or name} ({n}){dot}{ext}"
        used.add(path)
        z.writestr(path, data)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for g in gates.catalogue():
            f = gates.form_file(g["gate"]) if g["has_form"] else None
            if f:
                put(z, "Documents/Gate papers", f.name, f.read_bytes())
        for ph in gates.phase_catalogue():
            for r in ph["reviews"]:
                f = gates.review_form(r["code"])
                if f:
                    put(z, "Documents/Readiness reviews and checklists", f.name, f.read_bytes())
        for r in db.rows(con, "SELECT id, filename FROM kb_doc ORDER BY title"):
            f = file_of(con, r["id"])
            if f:
                put(z, "Documents/Uploaded", f["filename"] or f"document-{r['id']}", f["data"])
        put(z, "Setup templates", "project-load-template-blank.xlsx", templates_io.build_template(None, None, None))
        for step in templates_io.STEP_SHEETS:
            put(z, "Setup templates", f"project-load-template-{step}-blank.xlsx", templates_io.build_template(None, None, step))
    return buf.getvalue()
