"""FastAPI entry point: uvicorn app.main:app"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, jobs
from .repo import Conflict, NotFound, StaleRun, get_repo
from .storage import UploadError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("verity")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not db.is_ready():
        db.init_db()
    log.info("database ready: %s", db.version())
    if os.environ.get("VERITY_NO_WORKER") != "1":
        jobs.start_worker()
    yield
    jobs.worker.stop()
    if os.environ.get("VERITY_KEEP_DB") != "1":
        db.shutdown()


def ai_health() -> dict:
    try:
        chain = jobs._providers()
        h = chain.health()
        return h if isinstance(h, dict) else h.model_dump()
    except Exception as e:  # health must never raise
        return {"configured": False, "providers": [], "message": f"AI health unavailable ({type(e).__name__})"}


def create_app() -> FastAPI:
    from . import api_cases, api_demo, api_evidence, api_lab, api_review

    app = FastAPI(title="Verity", version=config.VERSION, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(NotFound)
    async def _nf(_: Request, e: NotFound):
        return JSONResponse({"detail": str(e.args[0]) if e.args else "not found"}, status_code=404)

    @app.exception_handler(Conflict)
    async def _cf(_: Request, e: Conflict):
        return JSONResponse({"detail": e.message, **e.extra}, status_code=409)

    @app.exception_handler(StaleRun)
    async def _sr(_: Request, e: StaleRun):
        return JSONResponse({"detail": str(e), "code": "stale"}, status_code=409)

    @app.exception_handler(UploadError)
    async def _ue(_: Request, e: UploadError):
        return JSONResponse({"detail": e.message}, status_code=e.status)

    @app.get("/api/health")
    def health():
        try:
            dbv = db.version()
            ok = True
        except Exception as e:
            dbv, ok = f"error: {type(e).__name__}", False
        return {"ok": ok, "db": dbv, "ai": ai_health(), "version": config.VERSION}

    for r in (api_cases.router, api_evidence.router, api_review.router, api_lab.router, api_demo.router):
        app.include_router(r)

    dist = config.FRONTEND_DIST
    if dist.is_dir():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "not found"}, status_code=404)
            candidate = (dist / full_path).resolve()
            if full_path and dist.resolve() in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def root():
            return {"app": "Verity API", "note": "frontend/dist not built; run `npm run build` in frontend/ or use Vite on :5173", "docs": "/docs"}

    return app


app = create_app()
