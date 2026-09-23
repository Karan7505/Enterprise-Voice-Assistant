"""Shared, atomic fixed-window rate limiter (Redis-backed).

Counters live in Redis keys ``ratelimit:{scope}:{identifier}:{window_start}``
and are incremented through a single Lua script, so the INCR + EXPIRE pair is
atomic: no two instances (or two threads) can ever observe a stale count and
both admit a request that should exceed the limit. The window starts at the
floor of ``now / window_seconds``, matching the previous backend's semantics.

Policies (unchanged from the previous implementation):
  * login  — by client IP
  * register — by client IP
  * chat   — by authenticated user
  * business_action — by user (the outbound-send hourly cap)

If Redis is unreachable the limiter degrades to a conservative in-process
window (fail-open, per the blueprint's decision for rate limiting) and logs a
warning; it is never a reason to take the whole API down.
"""

from __future__ import annotations

import logging
import time

import redis

from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

# Atomic fixed-window increment: the TTL is set only on the first increment of
# a window so late requests cannot extend the bucket's lifetime.
_LUA_FIXED_WINDOW = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return count
"""

# Conservative in-process fallback used only while Redis is down. Bounded so a
# prolonged outage cannot grow it without limit.
_local_buckets: dict[str, tuple[int, int]] = {}
_LOCAL_BUCKET_CAP = 10_000


def client_ip(request) -> str:
    """Best-effort client address, honoring a reverse proxy's first hop."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(
    scope: str,
    identifier: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int]:
    """Consume one unit of rate budget for ``scope:identifier`` in the current
    fixed window. Returns ``(allowed, retry_after_seconds)``.

    ``limit <= 0`` or ``window_seconds <= 0`` disables limiting (always
    allowed), which also keeps unit tests that never initialize the store
    safe.
    """
    if limit <= 0 or window_seconds <= 0:
        return True, 0

    now = int(time.time())
    bucket = (now // window_seconds) * window_seconds
    key = f"ratelimit:{scope}:{identifier}:{bucket}"

    try:
        count = get_redis().eval(_LUA_FIXED_WINDOW, 1, key, window_seconds)
    except redis.RedisError:
        logger.warning(
            "rate limiter: Redis unavailable; using in-process fallback "
            "for scope=%s (fail-open until Redis recovers)",
            scope,
        )
        return _local_check(key, window_seconds, limit)

    if count <= limit:
        return True, 0
    return False, max(1, bucket + window_seconds - now)


def _local_check(key: str, window_seconds: int, limit: int) -> tuple[bool, int]:
    now = int(time.time())
    bucket = (now // window_seconds) * window_seconds
    start, count = _local_buckets.get(key, (bucket, 0))
    if start != bucket:
        start, count = bucket, 0
    count += 1
    _local_buckets[key] = (start, count)

    if len(_local_buckets) > _LOCAL_BUCKET_CAP:
        stale = [
            k
            for k, (s, _) in _local_buckets.items()
            if s != (now // window_seconds) * window_seconds
        ]
        for k in stale[: len(stale) - _LOCAL_BUCKET_CAP // 10]:
            _local_buckets.pop(k, None)

    if count <= limit:
        return True, 0
    return False, max(1, bucket + window_seconds - now)
