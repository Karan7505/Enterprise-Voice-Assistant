"""Shared Redis connection for session state and rate limiting.

A single lazily-created client is reused process-wide. The URL is read at
first use (not import time) so tests and deployment scripts can point the app
at a different instance via the ``REDIS_URL`` environment variable.
"""

from __future__ import annotations

import logging
import os

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def redis_url() -> str:
    return os.environ.get("REDIS_URL") or settings.REDIS_URL


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            redis_url(),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            # RESP2: the Windows community build of Redis 5 has no HELLO
            # command, which redis-py's default RESP3 handshake requires.
            protocol=2,
        )
    return _client


def ping_redis() -> bool:
    """Liveness probe used at startup and by health checks."""
    try:
        return bool(get_redis().ping())
    except redis.RedisError:
        return False


def close_redis() -> None:
    global _client
    if _client is not None:
        try:
            _client.close()
        except redis.RedisError:
            pass
        _client = None
