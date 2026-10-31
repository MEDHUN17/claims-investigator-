"""Database bootstrap. Bundled PostgreSQL 16 (pixeltable_pgserver) unless DATABASE_URL is set."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

import psycopg
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from . import config

_lock = threading.Lock()
_server = None
_engine: Optional[Engine] = None
_Session: Optional[sessionmaker] = None
_url: Optional[str] = None


def _sa_url(base_uri: str, dbname: str) -> str:
    # base_uri like postgresql://postgres:@127.0.0.1:62488/postgres
    head = base_uri.rsplit("/", 1)[0]
    return head.replace("postgresql://", "postgresql+psycopg://", 1) + "/" + dbname


def _ensure_database(admin_uri: str, dbname: str) -> None:
    with psycopg.connect(admin_uri, autocommit=True) as c:
        row = c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone()
        if not row:
            c.execute(f'CREATE DATABASE "{dbname}"')


def init_db(pgdata: Optional[Path] = None, url: Optional[str] = None, dbname: Optional[str] = None,
            cleanup_mode: str = "stop", migrate: bool = True) -> Engine:
    """Start (or attach to) the database, create the dedicated database, build the engine, run migrations."""
    global _server, _engine, _Session, _url
    with _lock:
        if _engine is not None:
            return _engine
        url = url or config.DATABASE_URL or None
        dbname = dbname or config.DB_NAME
        if url:
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        else:
            import pixeltable_pgserver

            pg = Path(pgdata or config.PGDATA)
            pg.mkdir(parents=True, exist_ok=True)
            _server = pixeltable_pgserver.get_server(pg, cleanup_mode=cleanup_mode)
            admin = _server.get_uri()
            _ensure_database(admin, dbname)
            url = _sa_url(admin, dbname)
        _url = url
        _engine = create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=10,
                                connect_args={"options": "-c timezone=UTC"})
        _Session = sessionmaker(_engine, expire_on_commit=False)
    if migrate:
        run_migrations()
    return _engine


def get_url() -> str:
    if _url is None:
        raise RuntimeError("database not initialised: call db.init_db() first")
    return _url


def engine() -> Engine:
    if _engine is None:
        raise RuntimeError("database not initialised: call db.init_db() first")
    return _engine


def session() -> Session:
    if _Session is None:
        raise RuntimeError("database not initialised: call db.init_db() first")
    return _Session()


def is_ready() -> bool:
    return _engine is not None


def version() -> str:
    with engine().connect() as c:
        v = c.execute(text("SHOW server_version")).scalar()
    return f"postgresql {v}"


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(config.BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(config.BACKEND_DIR / "alembic"))
    with engine().begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def shutdown(stop_server: bool = True) -> None:
    """Dispose the engine; optionally stop the bundled server (data stays on disk)."""
    global _server, _engine, _Session, _url
    with _lock:
        if _engine is not None:
            _engine.dispose()
        srv = _server
        _engine = _Session = _url = None
        _server = None
    if srv is not None and stop_server:
        srv.cleanup()
