from app.core.database import get_connection
from app.models.chat_message import ChatMessage

DEFAULT_SESSION_ID = "default"


def add_message(
    role: str,
    content: str,
    session_id: str = DEFAULT_SESSION_ID,
    mode: str = "text",
):
    conn = get_connection()

    conn.execute(
        """
        INSERT INTO messages (session_id, role, content, mode)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, role, content, mode),
    )

    conn.commit()
    conn.close()


def get_messages(session_id: str = DEFAULT_SESSION_ID) -> list[ChatMessage]:
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT role, content, mode
        FROM messages
        WHERE session_id = ?
        ORDER BY id
        """,
        (session_id,),
    ).fetchall()

    conn.close()

    return [
        ChatMessage(
            role=row["role"],
            content=row["content"],
            mode=row["mode"] if row["mode"] is not None else "text",
        )
        for row in rows
    ]


def clear_messages(session_id: str = DEFAULT_SESSION_ID):
    conn = get_connection()
    conn.execute(
        "DELETE FROM messages WHERE session_id = ?",
        (session_id,),
    )
    conn.commit()
    conn.close()