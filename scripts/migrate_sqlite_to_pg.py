"""One-time migration: legacy SQLite database -> PostgreSQL.

Usage:
    python scripts/migrate_sqlite_to_pg.py [--sqlite PATH] [--force]

Behaviour:
  * Tolerates the legacy on-disk schema (tables or columns that may be
    missing before the last migration pass) and the current one.
  * Copies users, auth_sessions, messages, memories, audio_files,
    action_audit and pending_actions, preserving explicit ids so
    cross-table references stay intact.
  * Skips rate_limit_buckets on purpose: those counters are ephemeral
    fixed-window state and are not carried over (by design).
  * Idempotency: if the target already contains users, the script aborts
    unless --force is given. --force truncates the migrated tables first,
    i.e. it is a full reload, not an incremental merge.

The connection target is the usual DATABASE_URL environment variable (or the
application default).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.core import database  # noqa: E402
from app.core.config import settings  # noqa: E402  (loads the project .env)

TABLES = (
    "users",
    "auth_sessions",
    "messages",
    "memories",
    "audio_files",
    "action_audit",
    "pending_actions",
)

# Column list per table as expected in PostgreSQL (the migration writes
# explicitly into these columns; missing source columns are defaulted).
COLUMNS = {
    "users": ["id", "username", "password_hash", "salt", "created_at"],
    "auth_sessions": ["token", "user_id", "created_at", "expires_at"],
    "messages": ["session_id", "role", "content", "mode", "created_at"],
    "memories": ["session_id", "memory_key", "memory_value", "created_at", "updated_at"],
    "audio_files": ["filename", "session_id", "created_at"],
    "action_audit": [
        "user_id", "username", "channel", "recipient", "subject",
        "message_sha1", "outcome", "detail", "created_at",
    ],
    "pending_actions": ["session_id", "action_json", "created_at"],
}

DEFAULTS = {
    ("messages", "session_id"): "default",
    ("messages", "mode"): "text",
    ("memories", "updated_at"): None,
}


def sqlite_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error:
        return set()
    return {row[1] for row in rows}


def read_table(src: sqlite3.Connection, table: str) -> list[tuple]:
    cols = COLUMNS[table]
    present = sqlite_columns(src, table)
    if not present:
        # Table does not exist in this (possibly legacy) database.
        return []
    usable = [c for c in cols if c in present]
    if not usable:
        return []
    rows = src.execute(f"SELECT {', '.join(usable)} FROM {table}").fetchall()
    index = {c: i for i, c in enumerate(usable)}
    out = []
    for row in rows:
        rec = {}
        for c in cols:
            if c in index:
                rec[c] = row[index[c]]
            else:
                rec[c] = DEFAULTS.get((table, c))
        # The PostgreSQL schema is stricter about a few columns than the
        # legacy SQLite data may be; normalize NULLs to their defaults.
        if rec.get("mode") is None and table == "messages":
            rec["mode"] = "text"
        if rec.get("updated_at") is None and table == "memories":
            rec["updated_at"] = rec.get("created_at")
        out.append(tuple(rec[c] for c in cols))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default=str(REPO_ROOT / "assistant.db"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.is_file():
        print(f"No SQLite file at {sqlite_path}; nothing to migrate.")
        return 0

    dsn = __import__("os").environ.get("DATABASE_URL") or settings.DATABASE_URL

    # Ensure the schema exists on the target (idempotent Alembic upgrade).
    __import__("os").environ["DATABASE_URL"] = dsn
    database.initialize_database()
    database.close_pool()

    src = sqlite3.connect(sqlite_path)
    dst = psycopg2.connect(dsn)
    dst.autocommit = False
    try:
        with dst.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            existing = cur.fetchone()[0]
        if existing and not args.force:
            print(
                f"Target database already contains {existing} user(s). "
                "Re-run with --force for a full reload."
            )
            return 1
        if args.force and existing:
            with dst.cursor() as cur:
                for table in reversed(TABLES):
                    cur.execute(f"TRUNCATE {table} RESTART IDENTITY CASCADE")
            dst.commit()

        counts: dict[str, int] = {}
        for table in TABLES:
            rows = read_table(src, table)
            if not rows:
                counts[table] = 0
                continue
            cols = COLUMNS[table]
            placeholders = ", ".join(["%s"] * len(cols))
            with dst.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO {table} ({', '.join(cols)}) "
                    f"VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                    rows,
                )
            dst.commit()
            counts[table] = len(rows)

        # Keep identity sequences above the largest migrated explicit id.
        for table in ("users", "messages", "memories", "action_audit"):
            with dst.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', 'id'),
                        COALESCE((SELECT MAX(id) FROM {table}), 0) + 1,
                        FALSE
                    )
                    """
                )
        dst.commit()

        print("Migration complete (rows copied):")
        for table in TABLES:
            print(f"  {table:16s} {counts[table]}")
        return 0
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    raise SystemExit(main())
