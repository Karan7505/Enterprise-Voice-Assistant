import json

from app.core.database import get_connection
from app.prompts.chat_prompt import build_prompt
from app.services.database_chat_history import (
    add_message,
    get_messages,
)
from app.services.llm_service import generate

DEFAULT_SESSION_ID = "default"


def get_all_memories(
    session_id: str = DEFAULT_SESSION_ID,
) -> dict:
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            memory_key,
            memory_value
        FROM memories
        WHERE session_id = ?
        ORDER BY updated_at DESC
        """,
        (session_id,),
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
    text = text.strip()

    if text.startswith("```json"):
        text = text[7:]

    if text.startswith("```"):
        text = text[3:]

    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()

    return json.loads(text)


def process_message(
    message: str,
    session_id: str = DEFAULT_SESSION_ID,
):
    memories = get_all_memories(session_id)

    history = get_messages(session_id)

    history_text = "\n".join(
        f"{item.role}: {item.content}"
        for item in history
    )

    prompt = build_prompt(
        memories=memories,
        history=history_text,
        message=message,
    )

    raw_response = generate(prompt)

    data = extract_json(raw_response)

    reply = data.get("reply", "")

    new_memories = data.get(
        "memories",
        {},
    )

    add_message(
        "user",
        message,
        session_id,
    )

    add_message(
        "assistant",
        reply,
        session_id,
    )

    save_memories(
        new_memories,
        session_id,
    )

    return reply