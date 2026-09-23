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


def _wipe_s3() -> None:
    """Reset the S3 audio store for a test (only when S3 mode is selected).

    An explicitly empty ``S3_ENDPOINT_URL`` runs the suite in local-FS mode
    (CI), where this is a no-op.
    """
    import os

    import botocore.exceptions

    from app.core.config import settings
    from app.core.s3_client import get_s3, s3_enabled

    if not s3_enabled():
        return
    s3 = get_s3()
    try:
        try:
            s3.head_bucket(Bucket=settings.S3_BUCKET)
        except botocore.exceptions.ClientError:
            s3.create_bucket(Bucket=settings.S3_BUCKET)
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.S3_BUCKET):
            objs = page.get("Contents", [])
            if objs:
                s3.delete_objects(
                    Bucket=settings.S3_BUCKET,
                    Delete={"Objects": [{"Key": o["Key"]} for o in objs]},
                )
    except botocore.exceptions.BotoCoreError as exc:
        raise RuntimeError(
            "S3 store is selected (S3_ENDPOINT_URL) but unreachable: "
            f"{exc}. Start the local staging S3 (scripts/bootstrap_s3.py "
            "targets moto/MinIO on 127.0.0.1:9000) or set S3_ENDPOINT_URL=\"\" "
            "for local-FS mode."
        ) from exc


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
        _wipe_s3()

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
