"""Helpers shared by every router and by main.py: database dependency, project lookup, JSON response class, upload folder, temp-file clean-up, xlsx response."""
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .. import db, sync


UPLOADS = db.DB_PATH.parent / "uploads"  # beside the database: on this PC, never in the synced folder


def _round(o):
    if isinstance(o, float):
        return round(o, 2)
    if isinstance(o, dict):
        return {k: _round(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_round(v) for v in o]
    return o


class J(JSONResponse):
    def render(self, content):
        return super().render(_round(content))


def get_con(request: Request):
    con = db.connect()
    try:
        yield con
        pid = request.path_params.get("pid")
        if pid and request.method != "GET":
            con.execute("UPDATE project SET version = COALESCE(version,0)+1 WHERE id=?", (pid,))
        con.commit()
        if request.method != "GET":
            sync.poke()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def need_project(con, pid):
    p = db.one(con, "SELECT * FROM project WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def _rm(path):
    """Delete a temporary upload; a file Windows still has open is left for the next clean-up rather than failing the request."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _xlsx(data, name):
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
