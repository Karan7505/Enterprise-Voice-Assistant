import asyncio
import json
import logging
import re

import redis

from app.core.config import settings
from app.core.redis_client import get_redis
from app.prompts.chat_prompt import build_prompt
from app.services import action_policy
from app.services.auth_service import username_for_user_id
from app.services.context_builder import build_context
from app.services.database_chat_history import add_message, get_messages, clear_messages
from app.services.llm_service import LLMError, generate
from app.services.memory_service import (
    extract_json,
    save_memories,
    delete_memories,
    clear_memories,
)
from app.connectors.orchestrator import (
    BusinessAction,
    execute_action,
    execute_action_async,
    run_business_action,
    run_business_action_async,
)

logger = logging.getLogger(__name__)

DEFAULT_SESSION_ID = "default"

# History is useful for a clear follow-up, but silently carrying an old
# recipient, action, topic, or safety state into a fresh request is unsafe.
# Keep the default conservative: only messages that explicitly refer back to
# an earlier turn receive prior conversational context.
# Pronouns such as "it" only count in an action-plus-reference continuation,
# not in a standalone question that happens to mention the same word.
_CONTINUATION_PATTERN = re.compile(
    r"^(?:and|also|then|continue|same|as above|follow(?: |-)?up|what about|how about)\b|"
    r"\b(?:send|message|email|call|text|reply|tell|write|forward|share|schedule|book|deliver|repeat|resend|update|check)\b"
    r"[^.?!;]*\b(?:it|that|those|them|him|her)\b|"
    r"\b(?:as above|the same)\b",
    re.IGNORECASE,
)


def should_include_history(message: str, history: list[dict[str, str]]) -> bool:
    """Use prior turns only when the new message clearly continues them."""
    if not history:
        return False
    return bool(_CONTINUATION_PATTERN.search(" ".join((message or "").split())))


class SessionContext:
    def __init__(
        self,
        session_id: str,
        crm_context: dict,
        chat_history: list[dict[str, str]] | None = None,
    ):
        self.session_id = session_id
        self.crm_context = crm_context
        # Load history from DB on first creation
        if chat_history is None:
            db_msgs = get_messages(session_id)
            chat_history = [
                {"role": msg.role, "content": msg.content}
                for msg in db_msgs
            ]
        self.chat_history = chat_history


# --- shared conversation-context cache (Redis) --------------------------------
#
# Conversation state used to live in an unbounded in-process dict. It is now a
# bounded, TTL-managed cache in the shared store so any instance can serve the
# same user. The database remains the source of truth: a cache miss simply
# rebuilds the context from `chat_history` + `memories`, so a Redis outage
# costs a rebuild, not correctness.

CTX_KEY_TEMPLATE = "ctx:{session_id}"
MAX_CACHED_HISTORY = 200  # entries; the prompt window only uses a fraction
MAX_CTX_BYTES = 128 * 1024


def _ctx_key(session_id: str) -> str:
    return CTX_KEY_TEMPLATE.format(session_id=session_id)


def _ctx_load(session_id: str) -> SessionContext | None:
    try:
        raw = get_redis().get(_ctx_key(session_id))
    except redis.RedisError:
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        return SessionContext(
            session_id=payload["session_id"],
            crm_context=payload["crm_context"],
            chat_history=payload["chat_history"],
        )
    except (ValueError, KeyError, TypeError):
        return None


def _ctx_save(session_id: str, ctx: SessionContext) -> None:
    try:
        payload = json.dumps(
            {
                "session_id": session_id,
                "crm_context": ctx.crm_context,
                "chat_history": ctx.chat_history[-MAX_CACHED_HISTORY:],
            }
        )
        if len(payload.encode("utf-8")) > MAX_CTX_BYTES:
            return  # oversized: skip caching; the DB rebuild covers it
        get_redis().set(
            _ctx_key(session_id),
            payload,
            ex=settings.CONTEXT_CACHE_TTL_SECONDS,
        )
    except (redis.RedisError, TypeError, ValueError):
        logger.debug("conversation-context cache write skipped (cache only)")


def _ctx_drop(session_id: str) -> None:
    try:
        get_redis().delete(_ctx_key(session_id))
    except redis.RedisError:
        logger.debug("conversation-context cache drop skipped (cache only)")


def get_session(
    user_message: str = "",
    session_id: str = DEFAULT_SESSION_ID,
) -> SessionContext:
    ctx = _ctx_load(session_id)
    if ctx is None:
        ctx = SessionContext(
            session_id=session_id,
            crm_context=build_context(
                user_message=user_message,
                session_id=session_id,
            ),
        )
        _ctx_save(session_id, ctx)
    return ctx


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
    _ctx_save(session.session_id, session)


def _user_id_from_session(session_id: str) -> int | None:
    """Extract the numeric user id from a ``user:<id>`` session scope."""
    if not session_id or not session_id.startswith("user:"):
        return None
    try:
        return int(session_id.split(":", 1)[1])
    except ValueError:
        return None


def _confirmation_prompt(action: BusinessAction) -> str:
    verb = "an email to" if action.action == "email" else "a WhatsApp message to"
    preview = (action.message or "").strip()
    if len(preview) > 90:
        preview = preview[:87] + "..."
    line = f"Before I send {verb} {action.recipient}"
    if action.subject:
        line += f' with subject "{action.subject}"'
    if preview:
        line += f' saying "{preview}"'
    return line + " - shall I? Say yes to send, or no to cancel."


async def _run_and_audit(
    user_id: int | None,
    username: str | None,
    action: BusinessAction,
    ack: str = "",
) -> str:
    """Execute a policy-cleared action and record it in the audit trail."""
    result = await execute_action_async(action)
    await asyncio.to_thread(
        action_policy.record_action,
        user_id,
        username,
        action.action,
        action.recipient,
        action.subject,
        action.message,
        result.code.value,
        "" if result.success else result.message,
    )
    ack_stripped = (ack or "").strip()
    return f"{ack_stripped} {result.message}".strip() if ack_stripped else result.message


async def process_message(
    message: str,
    session_id: str = DEFAULT_SESSION_ID,
    mode: str = "text",
):
    # Blocking I/O (PostgreSQL, the Redis ctx cache) runs off the event loop;
    # provider calls below are natively async.
    session = await asyncio.to_thread(
        get_session, user_message=message, session_id=session_id
    )

    user_id = _user_id_from_session(session_id)
    username = (
        await asyncio.to_thread(username_for_user_id, user_id)
        if user_id is not None
        else None
    )

    # An explicit confirm/cancel for a previously staged send takes precedence
    # over a fresh LLM turn. Anything that isn't a clear yes/no is treated as a
    # new request, which discards the staged action (fail-safe: no accidental send).
    pending = await asyncio.to_thread(action_policy.get_pending_action, session_id)
    if pending is not None:
        decision = action_policy.classify_confirmation(message)
        if decision in ("yes", "no"):
            action = BusinessAction.from_dict(pending)
            await asyncio.to_thread(action_policy.clear_pending_action, session_id)
            if decision == "yes" and action is not None and action.is_complete():
                allowed, reason = await asyncio.to_thread(
                    action_policy.is_enabled_for, username
                )
                if not allowed:
                    await asyncio.to_thread(
                        action_policy.record_action,
                        user_id, username, action.action, action.recipient,
                        action.subject, action.message, "denied_policy", reason,
                    )
                    reply = reason
                else:
                    cap_ok, _retry = await asyncio.to_thread(
                        action_policy.hourly_cap_ok, user_id
                    )
                    if not cap_ok:
                        await asyncio.to_thread(
                            action_policy.record_action,
                            user_id, username, action.action, action.recipient,
                            action.subject, action.message, "rate_limited",
                            "hourly cap reached",
                        )
                        reply = (
                            "You've reached your hourly sending limit. "
                            "Please try again later."
                        )
                    else:
                        reply = await _run_and_audit(user_id, username, action)
            else:
                reply = "Okay, I've cancelled that. Nothing was sent."
            session.chat_history.append({"role": "user", "content": message})
            session.chat_history.append({"role": "assistant", "content": reply})
            await asyncio.to_thread(
                add_message,
                "user", message, session.session_id,
                mode="voice" if mode == "voice" else "text",
            )
            await asyncio.to_thread(add_message, "assistant", reply, session.session_id)
            await asyncio.to_thread(_ctx_save, session.session_id, session)
            return reply
        # Not a yes/no: drop the stale staged action and continue with a new turn.
        await asyncio.to_thread(action_policy.clear_pending_action, session_id)

    # Task 3: Send only the most recent N messages for conversation context
    max_history = settings.MAX_HISTORY_MESSAGES
    recent_history = (
        session.chat_history[-max_history:]
        if max_history > 0
        else session.chat_history
    )
    if not should_include_history(message, recent_history):
        recent_history = []

    history_text = "\n".join(
        f'{item["role"]}: {item["content"]}'
        for item in recent_history
    )

    prompt = build_prompt(
        memories=session.crm_context,
        history=history_text,
        message=message,
    )

    raw_response = await generate(prompt)

    try:
        data = extract_json(raw_response)
        reply = data.get("reply")
        new_memories = data.get("memories", {})
        delete_keys = data.get("delete_memories", [])
        action_data = data.get("action")

        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("LLM response is missing a non-empty reply")
        if not isinstance(new_memories, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in new_memories.items()
        ):
            raise ValueError("LLM response memories must contain string keys and values")
        if not isinstance(delete_keys, list) or not all(
            isinstance(key, str) for key in delete_keys
        ):
            raise ValueError("LLM response delete_memories must be a string list")
        # action is optional; when present it must be an object or null.
        if action_data is not None and not isinstance(action_data, dict):
            raise ValueError("LLM response action must be an object or null")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.exception("LLM returned a malformed structured response")
        raise LLMError("The LLM returned an invalid response") from exc

    reply = reply.strip()

    # Business actions (WhatsApp / email): the model only *proposes* an action.
    # Whether it is allowed, whether it needs an explicit confirmation, and how
    # often it may run are decided here in code (action_policy) — the LLM is
    # never the authorizer. The orchestrator is invoked only for actions that
    # clear this gate; ambiguous/incomplete requests fall through to the
    # existing clarification path, which resolves nothing and never sends.
    if action_data is not None:
        action = BusinessAction.from_dict(action_data)
        if action is not None and action.is_complete():
            allowed, reason = await asyncio.to_thread(
                action_policy.is_enabled_for, username
            )
            if not allowed:
                await asyncio.to_thread(
                    action_policy.record_action,
                    user_id, username, action.action, action.recipient,
                    action.subject, action.message, "denied_policy", reason,
                )
                reply = f"{reply} {reason}".strip()
            elif settings.BUSINESS_ACTION_REQUIRE_CONFIRMATION:
                # Stage the action and require an explicit yes on the next turn.
                await asyncio.to_thread(
                    action_policy.store_pending_action, session_id, action_data
                )
                reply = _confirmation_prompt(action)
            else:
                cap_ok, _retry = await asyncio.to_thread(
                    action_policy.hourly_cap_ok, user_id
                )
                if not cap_ok:
                    await asyncio.to_thread(
                        action_policy.record_action,
                        user_id, username, action.action, action.recipient,
                        action.subject, action.message, "rate_limited",
                        "hourly cap reached",
                    )
                    reply = (
                        f"{reply} You've reached your hourly sending limit. "
                        "Please try again later."
                    ).strip()
                else:
                    await asyncio.to_thread(action_policy.clear_pending_action, session_id)
                    reply = await _run_and_audit(user_id, username, action, ack=reply)
        else:
            reply = await run_business_action_async(reply, action_data)

    # Process explicit deletions if requested by user
    if delete_keys:
        await asyncio.to_thread(delete_memories, delete_keys, session.session_id)
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

    await asyncio.to_thread(
        add_message,
        "user",
        message,
        session.session_id,
        mode="voice" if mode == "voice" else "text",
    )

    await asyncio.to_thread(
        add_message,
        "assistant",
        reply,
        session.session_id,
    )

    await asyncio.to_thread(
        update_memories,
        session,
        new_memories,
    )

    await asyncio.to_thread(_ctx_save, session.session_id, session)
    return reply


def clear_chat_history(
    session_id: str = DEFAULT_SESSION_ID,
):
    """Clears ONLY conversation messages, preserving extracted long-term memories."""
    clear_messages(session_id)
    _ctx_drop(session_id)


def clear_memory_data(
    session_id: str = DEFAULT_SESSION_ID,
):
    """Clears ONLY extracted long-term memories, preserving conversation messages."""
    clear_memories(session_id)
    _ctx_drop(session_id)


def clear_session(
    session_id: str = DEFAULT_SESSION_ID,
):
    """Clears both conversation messages and extracted memories."""
    _ctx_drop(session_id)
    clear_memories(session_id)
    clear_messages(session_id)
