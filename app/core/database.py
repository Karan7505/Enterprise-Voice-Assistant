import sqlite3
from pathlib import Path

from app.core.config import settings

DB_PATH = Path(settings.DATABASE_PATH).resolve()


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize_database():
    conn = get_connection()

    # Messages table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Memories table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            memory_key TEXT NOT NULL,
            memory_value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, memory_key)
        )
        """
    )

    # Users table (authentication + user separation)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Server sessions (opaque bearer tokens, one per login)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )

    # Ownership of generated TTS files so /audio stays per-user.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audio_files (
            filename TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Fixed-window rate-limit counters (auth by IP, chat by user, sends by user).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rate_limit_buckets (
            key TEXT PRIMARY KEY,
            window_start INTEGER NOT NULL,
            count INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    # Audit trail for outbound business actions (who sent what to whom, outcome).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS action_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            channel TEXT,
            recipient TEXT,
            subject TEXT,
            message_sha1 TEXT,
            outcome TEXT,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # A business action staged for explicit confirm/cancel, one per session.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_actions (
            session_id TEXT PRIMARY KEY,
            action_json TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )

    # Backfill expires_at for databases created before session expiry existed.
    session_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(auth_sessions)").fetchall()
    ]
    if "expires_at" not in session_columns:
        conn.execute("ALTER TABLE auth_sessions ADD COLUMN expires_at TIMESTAMP NULL")

    # Add session_id if upgrading an existing messages table
    columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(messages)").fetchall()
    ]

    if "session_id" not in columns:
        conn.execute(
            """
            ALTER TABLE messages
            ADD COLUMN session_id TEXT DEFAULT 'default'
            """
        )

    if "mode" not in columns:
        conn.execute(
            """
            ALTER TABLE messages
            ADD COLUMN mode TEXT DEFAULT 'text'
            """
        )

    conn.commit()
    conn.close()
