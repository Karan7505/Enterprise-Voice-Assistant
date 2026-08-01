from app.core.database import get_connection

DEFAULT_SESSION_ID = "default"


def save_memory(
    key: str,
    value: str,
    session_id: str = DEFAULT_SESSION_ID,
):
    conn = get_connection()

    conn.execute(
        """
        INSERT INTO memories (
            session_id,
            memory_key,
            memory_value
        )
        VALUES (?, ?, ?)
        ON CONFLICT(session_id, memory_key)
        DO UPDATE SET
            memory_value = excluded.memory_value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (session_id, key, value),
    )

    conn.commit()
    conn.close()


def get_memory(
    key: str,
    session_id: str = DEFAULT_SESSION_ID,
):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT memory_value
        FROM memories
        WHERE session_id = ?
        AND memory_key = ?
        """,
        (session_id, key),
    ).fetchone()

    conn.close()

    return row["memory_value"] if row else None