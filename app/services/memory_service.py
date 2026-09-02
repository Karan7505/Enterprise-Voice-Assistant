import json

from app.core.database import get_connection

DEFAULT_SESSION_ID = "default"


def get_all_memories(
    session_id: str = DEFAULT_SESSION_ID,
) -> dict:
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT memory_key, memory_value
        FROM memories
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchall()

    conn.close()

    return {
        row["memory_key"]: row["memory_value"]
        for row in rows
    }


def get_memories_by_keys(
    keys: list[str],
    session_id: str = DEFAULT_SESSION_ID,
) -> dict:
    if not keys:
        return {}

    conn = get_connection()

    placeholders = ",".join("?" * len(keys))

    rows = conn.execute(
        f"""
        SELECT memory_key, memory_value
        FROM memories
        WHERE session_id = ?
        AND memory_key IN ({placeholders})
        """,
        [session_id] + keys,
    ).fetchall()

    conn.close()

    return {
        row["memory_key"]: row["memory_value"]
        for row in rows
    }


def save_memories(
    memories: dict,
    session_id: str = DEFAULT_SESSION_ID,
):
    if not memories:
        return

    conn = get_connection()

    for key, value in memories.items():
        conn.execute(
            """
            INSERT INTO memories
            (
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
            (
                session_id,
                key,
                value,
            ),
        )

    conn.commit()
    conn.close()


def extract_json(text: str) -> dict:
    if not isinstance(text, str):
        raise TypeError("LLM response must be text")

    text = text.strip()

    if text.startswith("```json"):
        text = text[7:]

    if text.startswith("```"):
        text = text[3:]

    if text.endswith("```"):
        text = text[:-3]

    data = json.loads(text.strip())
    if not isinstance(data, dict):
        raise ValueError("LLM response JSON must be an object")
    return data


def delete_memories(
    keys: list[str],
    session_id: str = DEFAULT_SESSION_ID,
):
    if not keys:
        return

    conn = get_connection()
    placeholders = ",".join("?" * len(keys))
    conn.execute(
        f"""
        DELETE FROM memories
        WHERE session_id = ?
        AND memory_key IN ({placeholders})
        """,
        [session_id] + keys,
    )
    conn.commit()
    conn.close()


def clear_memories(
    session_id: str = DEFAULT_SESSION_ID,
):
    conn = get_connection()
    conn.execute(
        "DELETE FROM memories WHERE session_id = ?",
        (session_id,),
    )
    conn.commit()
    conn.close()
