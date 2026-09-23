"""PostgreSQL persistence layer.

All access goes through :func:`get_connection`, which hands out a small proxy
around a pooled ``psycopg2`` connection. The proxy preserves the historical
call style of the service layer — ``conn.execute(sql, params)`` with ``?``
placeholders, ``row["column"]`` access, and ``commit()`` / ``close()`` — so
queries read the same as they did on the previous storage backend.

The schema is owned by Alembic (see ``alembic/``). :func:`initialize_database`
creates the pool and upgrades the schema to head, which is idempotent and safe
to call on every process start.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = "postgresql://evoa@127.0.0.1:5432/assistant"

_pool: ThreadedConnectionPool | None = None


def database_url() -> str:
    """Connection string: ``DATABASE_URL`` env wins over the settings default.

    Read at call time (not import time) so tests can point the app at a fresh
    per-test database by setting the environment variable.
    """
    return os.environ.get("DATABASE_URL") or settings.DATABASE_URL


def _translate(sql: str, params: tuple[Any, ...]) -> str:
    """Translate ``?`` placeholders to the driver's ``%s`` form.

    Fails loudly if the placeholder count and the parameter count disagree,
    so a mismatched query cannot silently bind the wrong arguments.
    """
    question_marks = sql.count("?")
    if question_marks != len(params):
        raise ValueError(
            f"placeholder/parameter mismatch: {question_marks} '?' vs {len(params)} params"
        )
    return re.sub(r"\?", "%s", sql)


class _Cursor:
    """Thin wrapper so callers keep using ``fetchone``/``fetchall``."""

    def __init__(self, cursor: psycopg2.extras.RealDictCursor) -> None:
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class _Connection:
    """Pool-backed stand-in for the old per-call connection."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> _Cursor:
        params = params or ()
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute(_translate(sql, params), params)
        except Exception:
            cursor.close()
            raise
        return _Cursor(cursor)

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        # Return the connection to the pool; a connection left in a failed
        # transaction state is discarded instead of recycled.
        if self._conn.closed:
            if _pool is not None:
                _pool.putconn(self._conn, close=True)
            return
        try:
            self._conn.rollback()
        except psycopg2.Error:
            _pool.putconn(self._conn, close=True)
            return
        _pool.putconn(self._conn)


def get_connection() -> _Connection:
    global _pool
    if _pool is None:
        initialize_database()
    return _Connection(_pool.getconn())


def initialize_database() -> None:
    """Create the pool and ensure the schema is at the latest revision."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None

    url = database_url()
    _pool = ThreadedConnectionPool(minconn=2, maxconn=20, dsn=url)

    # Idempotent schema upgrade (no-op when the DB is already at head).
    _run_migrations(url)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


def _run_migrations(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(_alembic_ini_path()))
    # alembic/env.py reads DATABASE_URL from the process environment.
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _alembic_ini_path():
    from pathlib import Path

    return Path(__file__).resolve().parents[2] / "alembic.ini"
