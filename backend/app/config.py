"""Runtime configuration. Reads backend/.env (never logged). Secrets are never printed."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


APP_ENV = _env("APP_ENV", "dev")
VERSION = "0.1.0"
DB_NAME = _env("VERITY_DB_NAME", "verity")
DATABASE_URL = _env("DATABASE_URL")  # blank -> bundled PostgreSQL under PGDATA
PGDATA = Path(_env("PGDATA", str(ROOT_DIR / ".pgdata")))
STORAGE = Path(_env("VERITY_STORAGE", str(BACKEND_DIR / "storage")))
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
FIXTURES_DIR = ROOT_DIR / "fixtures"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# Delegation of authority (INR, upper bounds inclusive)
DELEGATION = [(50_000, "adjuster"), (200_000, "senior_adjuster")]
DELEGATION_TOP = "committee"
