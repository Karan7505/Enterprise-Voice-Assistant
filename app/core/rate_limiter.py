"""Dependency-free, SQLite-backed fixed-window rate limiter.

Keeps auth endpoints (throttled by client IP) and the expensive ``/chat`` route
(throttled by user) bounded without adding an external dependency. Counters live
in the ``rate_limit_buckets`` table created by ``app.core.database``.

This is deliberately a *fixed-window* counter rather than a sliding log: it is
simple, state stays in the same SQLite database the app already uses, and it is
more than sufficient to stop credential stuffing and per-user cost abuse.
"""

from __future__ import annotations

import time

from app.core.database import get_connection


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

    ``limit <= 0`` or ``window_seconds <= 0`` disables limiting (always allowed),
    which also keeps unit tests that never initialize the rate table safe.
    """
    if limit <= 0 or window_seconds <= 0:
        return True, 0

    key = f"{scope}:{identifier}"
    now = int(time.time())
    bucket = (now // window_seconds) * window_seconds

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT window_start, count FROM rate_limit_buckets WHERE key = ?",
            (key,),
        ).fetchone()

        if row is None or row["window_start"] != bucket:
            conn.execute(
                """
                INSERT INTO rate_limit_buckets (key, window_start, count)
                VALUES (?, ?, 1)
                ON CONFLICT(key) DO UPDATE SET
                    window_start = excluded.window_start,
                    count = 1
                """,
                (key, bucket),
            )
            count = 1
        else:
            count = row["count"] + 1
            conn.execute(
                "UPDATE rate_limit_buckets SET count = ? WHERE key = ?",
                (count, key),
            )
        conn.commit()
    finally:
        conn.close()

    if count <= limit:
        return True, 0
    return False, max(1, bucket + window_seconds - now)
