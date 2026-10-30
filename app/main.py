"""HTTP API and static front end: app assembly (middleware, error handlers, start-up, static files) and router inclusion."""
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import linking, changelog, db, sync, pronto, services
from .routers._shared import J, UPLOADS
from .routers import platform, setup, pmo, revenue as revenue_routes, cost   # app.revenue (the calculations) is a different module
from .routers.revenue import claim_create, sub_save  # noqa: F401  (tests call these endpoint functions directly)

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    try:                                  # running projects get their CTC (Unallocated) lines too (idempotent)
        _c = db.connect()
        for _r in db.rows(_c, "SELECT id FROM project WHERE initialised=1"):
            if services.ensure_ctc_lines(_c, _r["id"]):
                pronto.resolve_all(_c, _r["id"])      # cost parked on a pot moves to the new WIP line
        _c.commit(); _c.close()
    except Exception as _e:
        print("CTC lines:", _e)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    sync.start(background=os.environ.get("PMT_SYNC_THREAD", "1") != "0")
    yield
    sync.stop()


app = FastAPI(title="Project Management Tool", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
app.router.default_response_class = J


@app.exception_handler(services.Problem)
async def _problem(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(ValueError)
async def _valerr(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.middleware("http")
async def _one_action(request, call_next):
    changelog.new_txn()  # every change made by this request is grouped as one user action (copied into worker threads)
    # a parent project is read-only: its figures are its children's, changed in the child projects
    parts = request.url.path.split("/")
    if request.method not in ("GET", "HEAD", "OPTIONS") and len(parts) > 3 and parts[1:3] == ["api", "p"] and parts[3].isdigit():
        con = db.connect(logging=False)
        try:
            parent = linking.is_parent(con, int(parts[3]))
        finally:
            con.close()
        if parent:
            return JSONResponse({"detail": "This is a parent project: its figures come from its child projects. Open a child project to change them."}, status_code=400)
    resp = await call_next(request)
    # the pages and scripts are revalidated on every load (a 304 when unchanged), so a new release is never shown with the old scripts from the browser's cache
    if request.method in ("GET", "HEAD") and (request.url.path == "/" or request.url.path.startswith("/static/")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


# Routers, one module per area (see docs/areas.md). Registration order matters only where two paths could match the same
# URL; those routes live in the same router in their original order (tests/test_route_inventory.py checks it).
app.include_router(platform.router)
app.include_router(setup.router)
app.include_router(pmo.router)
app.include_router(revenue_routes.router)
app.include_router(cost.router)


# ---------------------------------------------------------------------------
# Static front end
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
