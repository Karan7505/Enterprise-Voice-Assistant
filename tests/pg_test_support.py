"""Per-test PostgreSQL databases for the unit suite.

Each test that touches the database gets a freshly created PostgreSQL
database with the schema applied via Alembic — the same isolation the suite
previously got from per-test temporary SQLite files.

The suite requires a reachable PostgreSQL server. The admin connection
defaults to the local development/staging instance and can be overridden with
``PG_ADMIN_URL`` (CI points it at its postgres service).
"""

from __future__ import annotations

import os
import uuid

import psycopg2

from app.core import database
from app.core import redis_client

ADMIN_URL = os.environ.get(
    "PG_ADMIN_URL", "postgresql://evoa@127.0.0.1:5432/postgres"
)

# The local staging Redis is dedicated to this deployment; the suite flushes
# it per test so sessions, rate-limit buckets, and context caches start clean.
# In CI a fresh Redis service per run provides the same isolation.


def _url_for_db(url: str, dbname: str) -> str:
    idx = url.rfind("/")
    return url[: idx + 1] + dbname


class TestDatabase:
    """Context-managed fresh database for one test."""

    def __init__(self) -> None:
        self.name: str | None = None

    def start(self) -> None:
        admin = psycopg2.connect(ADMIN_URL)
        admin.autocommit = True
        try:
            self.name = "evoa_t_" + uuid.uuid4().hex[:12]
            with admin.cursor() as cur:
                cur.execute(f'CREATE DATABASE "{self.name}"')
        except Exception:
            admin.close()
            raise
        admin.close()

        os.environ["DATABASE_URL"] = _url_for_db(ADMIN_URL, self.name)
        database.initialize_database()

        redis_client.close_redis()
        redis_client.get_redis().flushdb()

    def stop(self) -> None:
        database.close_pool()
        os.environ.pop("DATABASE_URL", None)
        if not self.name:
            return
        admin = psycopg2.connect(ADMIN_URL)
        admin.autocommit = True
        try:
            with admin.cursor() as cur:
                cur.execute(f'DROP DATABASE IF EXISTS "{self.name}"')
        finally:
            admin.close()
        self.name = None
