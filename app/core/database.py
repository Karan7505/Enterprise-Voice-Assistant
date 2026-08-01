import sqlite3
from pathlib import Path

DB_PATH = Path("assistant.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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

    conn.commit()
    conn.close()