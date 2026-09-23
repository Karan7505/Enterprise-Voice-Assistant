"""Server-side policy gate for outbound business actions (WhatsApp / Email).

The LLM may *propose* an action, but the decisions that actually matter for
security — *is this user allowed to send at all*, *to whom*, *how often*, and
*does it require an explicit confirmation* — are made here in code, independent
of the model. This is the control that stops a low-privilege account (or a
prompt-injected instruction) from driving real outbound sends under operator
credentials.

Every attempt is written to the ``action_audit`` table so an operator can later
reconstruct who sent what to whom and with what outcome.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time

from app.core.config import settings
from app.core.database import get_connection
from app.core.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)

# Short, explicit words that confirm or cancel a pending action. Anything that is
# not clearly one of these is treated as a *new* request (which discards the
# pending action) — a fail-safe, so an accidental phrase never triggers a send.
_CONFIRM_WORDS = {
    "yes", "y", "yep", "yeah", "ya", "yup", "ok", "okay", "confirm", "confirmed",
    "send it", "send", "go ahead", "proceed", "do it", "haan", "sahi hai", "bhejo",
}
_DENY_WORDS = {
    "no", "n", "nope", "nah", "cancel", "canceled", "cancelled", "stop", "abort",
    "don't", "dont", "no thanks", "na",
}


def allowed_business_users() -> set[str]:
    """The set of usernames (lower-cased) permitted to trigger outbound sends."""
    raw = (settings.BUSINESS_ACTION_ALLOWED_USERS or "").strip()
    if not raw:
        return set()
    return {u.strip().lower() for u in raw.split(",") if u.strip()}


def is_enabled_for(username: str | None) -> tuple[bool, str]:
    """Whether ``username`` may trigger outbound business actions, and why not."""
    if not settings.BUSINESS_ACTIONS_ENABLED:
        return False, (
            "Outbound sending isn't enabled on this deployment. "
            "Ask your administrator to enable it."
        )
    if not username or not username.strip():
        return False, "You must be signed in to send messages."
    if username.strip().lower() not in allowed_business_users():
        return False, (
            "Sending messages isn't enabled for your account. "
            "Ask your administrator if you need it."
        )
    return True, ""


def hourly_cap_ok(user_id: int | None) -> tuple[bool, int]:
    """Per-user cap on outbound actions per rolling hour. Consumes one unit."""
    limit = settings.BUSINESS_ACTION_MAX_PER_HOUR
    if limit <= 0 or user_id is None:
        return True, 0
    return check_rate_limit("business_action", f"user:{user_id}", limit, 3600)


def classify_confirmation(text: str) -> str | None:
    """Map a short user reply to ``'yes'`` / ``'no'`` / ``None`` (not a decision)."""
    normalized = " ".join((text or "").lower().split())
    if not normalized:
        return None
    if normalized in _DENY_WORDS or normalized.startswith(("no", "cancel", "stop", "abort")):
        return "no"
    if normalized in _CONFIRM_WORDS or normalized.startswith(
        ("yes", "yep", "confirm", "send it", "go ahead", "proceed", "haan")
    ):
        return "yes"
    return None


def record_action(
    user_id: int | None,
    username: str | None,
    channel: str | None,
    recipient: str | None,
    subject: str | None,
    message: str | None,
    outcome: str,
    detail: str = "",
) -> None:
    """Append an audit row for a business-action attempt. Message text is stored
    only as a SHA-1 digest so the audit trail doesn't over-retain PII."""
    try:
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO action_audit
                    (user_id, username, channel, recipient, subject,
                     message_sha1, outcome, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    channel,
                    recipient,
                    subject,
                    hashlib.sha1((message or "").encode("utf-8")).hexdigest()
                    if message
                    else None,
                    outcome,
                    (detail or "")[:300],
                ),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info(
            "business_action user_id=%s username=%s channel=%s recipient=%s outcome=%s",
            user_id, username, channel, recipient, outcome,
        )
    except Exception:
        logger.exception("Failed to record business-action audit row")


# --- pending-action store (the explicit confirmation step) -------------------


def store_pending_action(session_id: str, action_data: dict) -> None:
    try:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO pending_actions "
                "(session_id, action_json, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT (session_id) DO UPDATE SET "
                "action_json = excluded.action_json, "
                "created_at = excluded.created_at",
                (session_id, json.dumps(action_data), time.time()),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to store pending business action")


def get_pending_action(session_id: str) -> dict | None:
    try:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT action_json, created_at FROM pending_actions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        # A confirmation must not be able to fire long after it was staged.
        age = time.time() - float(row["created_at"] or 0)
        if age > settings.BUSINESS_ACTION_CONFIRM_TTL_SECONDS:
            clear_pending_action(session_id)
            return None
        return json.loads(row["action_json"])
    except Exception:
        logger.exception("Failed to load pending business action")
        return None


def clear_pending_action(session_id: str) -> None:
    try:
        conn = get_connection()
        try:
            conn.execute(
                "DELETE FROM pending_actions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to clear pending business action")
