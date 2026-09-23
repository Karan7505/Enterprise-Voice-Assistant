"""Redis-backed auth session state (blueprint Decision A).

Each login token maps to a Redis hash ``session:{token}`` holding
``{user_id, created_at, expires_at, last_activity}`` with a TTL equal to the
token lifetime. Redis is the authoritative live-session store:

  * a lookup miss is an auth failure (401);
  * Redis being unreachable is a *fail-closed* condition — the caller turns
    it into a 5xx instead of falling back to stale state.

The ``auth_sessions`` table in PostgreSQL remains the durable record (created
at login, deleted at logout / expiry); Redis holds the hot, revocable,
TTL-managed copy that lets any instance in a multi-instance deployment
resolve the same token.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis

from app.core.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

KEY_TEMPLATE = "session:{token}"


def _ttl_seconds() -> int:
    return settings.TOKEN_TTL_MINUTES * 60


def _key(token: str) -> str:
    return KEY_TEMPLATE.format(token=token)


def create_session(token: str, user_id: int, created_at: datetime, expires_at: datetime) -> None:
    """Register a freshly issued token. Raises on Redis failure (fail-closed)."""
    data = {
        "user_id": str(user_id),
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "last_activity": created_at.isoformat(),
    }
    r = get_redis()
    r.hset(_key(token), mapping=data)
    r.expire(_key(token), _ttl_seconds())


def get_session(token: str) -> dict | None:
    """Resolve a token to its session data, or ``None`` when the session does
    not exist (miss) or has expired (defensively re-checked here; the Redis
    TTL is the primary expiry mechanism). Raises on Redis failure."""
    r = get_redis()
    data = r.hgetall(_key(token))
    if not data:
        return None

    try:
        expiry = datetime.fromisoformat(data["expires_at"])
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expiry:
            r.delete(_key(token))
            return None
    except (KeyError, ValueError):
        # Malformed stored expiry: treat the session as dead (fail-closed).
        r.delete(_key(token))
        return None

    # Refresh the activity marker (TTL stays absolute — see module docstring).
    r.hset(_key(token), "last_activity", datetime.now(timezone.utc).isoformat())
    return data


def delete_session(token: str) -> None:
    """Revoke a session (logout). Best-effort: a failure here is logged, not
    raised — the durable DB row is removed by the caller and the key dies by
    TTL at the latest."""
    try:
        get_redis().delete(_key(token))
    except redis.RedisError as exc:
        logger.warning("Could not delete Redis session key: %s", exc)
