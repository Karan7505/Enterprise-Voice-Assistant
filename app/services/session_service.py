from app.core.config import settings
from app.prompts.chat_prompt import build_prompt
from app.services.context_builder import build_context
from app.services.database_chat_history import add_message, get_messages, clear_messages
from app.services.llm_service import generate
from app.services.memory_service import (
    extract_json,
    save_memories,
    delete_memories,
    clear_memories,
)

DEFAULT_SESSION_ID = "default"


class SessionContext:
    def __init__(
        self,
        session_id: str,
        crm_context: dict,
    ):
        self.session_id = session_id
        self.crm_context = crm_context
        # Load history from DB on session creation
        db_msgs = get_messages(session_id)
        self.chat_history = [
            {"role": msg.role, "content": msg.content}
            for msg in db_msgs
        ]


_sessions: dict[str, SessionContext] = {}


def get_session(
    user_message: str = "",
    session_id: str = DEFAULT_SESSION_ID,
) -> SessionContext:
    if session_id not in _sessions:
        crm_context = build_context(
            user_message=user_message,
            session_id=session_id,
        )

        _sessions[session_id] = SessionContext(
            session_id=session_id,
            crm_context=crm_context,
        )

    return _sessions[session_id]


def update_memories(
    session: SessionContext,
    memories: dict,
):
    if not memories:
        return

    session.crm_context.update(memories)

    save_memories(
        memories,
        session.session_id,
    )


def process_message(
    message: str,
    session_id: str = DEFAULT_SESSION_ID,
):
    session = get_session(
        user_message=message,
        session_id=session_id,
    )

    # Task 3: Send only the most recent N messages for conversation context
    max_history = settings.MAX_HISTORY_MESSAGES
    recent_history = (
        session.chat_history[-max_history:]
        if max_history > 0
        else session.chat_history
    )

    history_text = "\n".join(
        f'{item["role"]}: {item["content"]}'
        for item in recent_history
    )

    prompt = build_prompt(
        memories=session.crm_context,
        history=history_text,
        message=message,
    )

    raw_response = generate(prompt)

    data = extract_json(raw_response)

    reply = data.get("reply", "")
    new_memories = data.get("memories", {})
    delete_keys = data.get("delete_memories", [])

    # Process explicit deletions if requested by user
    if delete_keys and isinstance(delete_keys, list):
        delete_memories(delete_keys, session.session_id)
        for k in delete_keys:
            session.crm_context.pop(k, None)

    session.chat_history.append(
        {
            "role": "user",
            "content": message,
        }
    )

    session.chat_history.append(
        {
            "role": "assistant",
            "content": reply,
        }
    )

    add_message(
        "user",
        message,
        session.session_id,
    )

    add_message(
        "assistant",
        reply,
        session.session_id,
    )

    update_memories(
        session,
        new_memories,
    )

    return reply


def clear_chat_history(
    session_id: str = DEFAULT_SESSION_ID,
):
    """Clears ONLY conversation messages, preserving extracted long-term memories."""
    clear_messages(session_id)
    if session_id in _sessions:
        _sessions[session_id].chat_history = []


def clear_memory_data(
    session_id: str = DEFAULT_SESSION_ID,
):
    """Clears ONLY extracted long-term memories, preserving conversation messages."""
    clear_memories(session_id)
    if session_id in _sessions:
        _sessions[session_id].crm_context = {}


def clear_session(
    session_id: str = DEFAULT_SESSION_ID,
):
    """Clears both conversation messages and extracted memories."""
    _sessions.pop(
        session_id,
        None,
    )
    clear_memories(session_id)
    clear_messages(session_id)