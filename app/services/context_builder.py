from app.services.memory_service import (
    get_all_memories,
)

DEFAULT_SESSION_ID = "default"


def build_context(
    user_message: str,
    session_id: str = DEFAULT_SESSION_ID,
) -> dict:
    """
    Builds the CRM context for the active session.

    Current implementation:
    - Loads CRM data once at session creation.
    - No additional LLM call.

    Future implementation:
    - Retrieve only relevant CRM records.
    """

    return get_all_memories(session_id)