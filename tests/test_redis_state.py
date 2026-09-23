"""Phase 2 verification: Redis-backed sessions, rate limiting, and failure modes.

Covers the blueprint's required checks:

* rate-limit atomicity under concurrency (exactly N admitted for a limit of N),
* session state surviving an application restart,
* multi-instance consistency (two independent clients share one token store),
* global rate limiting across instances,
* fail-closed 503 on authenticated paths when Redis is down,
* fail-open in-process fallback for the rate limiter when Redis is down,
* conversation-context cache rebuildability (cache loss never loses data).
"""

import os
import threading
import unittest

import redis as redis_lib

from pg_test_support import TestDatabase
from app.core import database, redis_client, redis_sessions
from app.core.rate_limiter import _LUA_FIXED_WINDOW, check_rate_limit
from app.services import auth_service
from app.services import database_chat_history, session_service

DEAD_REDIS_URL = "redis://127.0.0.1:6390/0"  # nothing listens here


def _bucket(window_seconds: int) -> int:
    import time

    return (int(time.time()) // window_seconds) * window_seconds


def _instance_client() -> redis_lib.Redis:
    """A fresh, independent client simulating a second application instance."""
    return redis_lib.Redis.from_url(
        redis_client.redis_url(),
        decode_responses=True,
        protocol=2,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


class RedisStateTests(unittest.TestCase):
    def setUp(self):
        self._db = TestDatabase()
        self._db.start()

    def tearDown(self):
        self._db.stop()

    # --- rate-limit atomicity ---------------------------------------------
    def test_rate_limit_is_atomic_under_concurrency(self):
        limit = 10
        window = 60
        threads = 40
        results = []
        results_lock = threading.Lock()
        barrier = threading.Barrier(threads)

        def worker():
            barrier.wait()
            allowed, _ = check_rate_limit("burst", "worker", limit, window)
            with results_lock:
                results.append(allowed)

        pool = [threading.Thread(target=worker) for _ in range(threads)]
        for t in pool:
            t.start()
        for t in pool:
            t.join()

        self.assertEqual(sum(results), limit, "exactly `limit` requests may pass")

        # Every attempt must have been counted in the shared store (the counter
        # includes denied attempts), proving all 40 increments landed atomically.
        counter = int(redis_client.get_redis().get(f"ratelimit:burst:worker:{_bucket(window)}"))
        self.assertEqual(counter, threads)

    def test_rate_limit_is_global_across_instances(self):
        limit = 5
        window = 60
        scope, identifier = "chat", "user:424242"

        # Instance 1 (the module client) consumes its full budget.
        for _ in range(limit):
            allowed, _ = check_rate_limit(scope, identifier, limit, window)
            self.assertTrue(allowed)

        # Instance 2 is an independent client on the same server. It must see
        # instance 1's counter, not a fresh one.
        instance2 = _instance_client()
        try:
            count = instance2.eval(_LUA_FIXED_WINDOW, 1, f"ratelimit:{scope}:{identifier}:{_bucket(window)}", window)
            self.assertEqual(count, limit + 1)  # over budget -> would be denied
            denied_call = check_rate_limit(scope, identifier, limit, window)
            self.assertFalse(denied_call[0], "instance 1 must be denied after instance 2's increment")
        finally:
            instance2.close()

    # --- multi-instance session sharing ------------------------------------
    def test_two_instances_share_one_token_store(self):
        auth_service.register_user("carol", "password123")
        token = auth_service.authenticate("carol", "password123")
        self.assertIsNotNone(token)

        instance2 = _instance_client()
        try:
            # Instance 2 can read the session instance 1 issued.
            key = redis_sessions._key(token)
            self.assertTrue(instance2.exists(key))
            user_id = str(auth_service.resolve_user(token)["user_id"])
            self.assertEqual(instance2.hget(key, "user_id"), user_id)

            # Revoking from instance 2 kills the token for instance 1 too.
            instance2.delete(redis_sessions._key(token))
            self.assertIsNone(auth_service.resolve_user(token))
        finally:
            instance2.close()

    def test_session_survives_application_restart(self):
        user = auth_service.register_user("dave", "password123")
        token = auth_service.authenticate("dave", "password123")
        self.assertIsNotNone(token)

        # Simulate a process restart: drop the Redis client and the DB pool.
        redis_client.close_redis()
        database.close_pool()

        # Fresh lazy clients (rebuilt from the same env) resolve the same token.
        resolved = auth_service.resolve_user(token)
        self.assertEqual(resolved["user_id"], user["id"])
        self.assertEqual(resolved["username"], "dave")

        # Revocation after restart propagates as expected.
        auth_service.revoke_token(token)
        self.assertIsNone(auth_service.resolve_user(token))

    # --- failure modes -------------------------------------------------------
    def test_redis_down_fails_closed_over_http(self):
        from fastapi.testclient import TestClient

        from app.main import app

        user = auth_service.register_user("erin", "password123")
        token = auth_service.authenticate("erin", "password123")
        self.assertIsNotNone(token)

        os.environ["REDIS_URL"] = DEAD_REDIS_URL
        redis_client.close_redis()
        try:
            with TestClient(app, base_url="https://testserver") as client:
                # A session issued before the outage cannot be verified -> 503.
                resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
                self.assertEqual(resp.status_code, 503)

                # New logins fail closed: refused, and no orphan row is left behind.
                def session_rows():
                    conn = database.get_connection()
                    try:
                        return conn.execute("SELECT count(*) AS n FROM auth_sessions").fetchone()["n"]
                    finally:
                        conn.close()

                before = session_rows()
                resp = client.post(
                    "/auth/login",
                    json={"username": "erin", "password": "password123"},
                )
                self.assertEqual(resp.status_code, 503)
                self.assertEqual(session_rows(), before)

                # An unauthenticated request needs no Redis -> plain 401.
                resp = client.get("/auth/me")
                self.assertEqual(resp.status_code, 401)
        finally:
            os.environ.pop("REDIS_URL", None)
            redis_client.close_redis()

    def test_rate_limiter_fails_open_when_redis_down(self):
        os.environ["REDIS_URL"] = DEAD_REDIS_URL
        redis_client.close_redis()
        try:
            # Align to a bucket start: a 60 s fixed window rolls over every
            # minute, and the 4 calls must land inside a single bucket.
            import time as _t

            to_next = 60 - (_t.time() % 60)
            if to_next < 2:
                _t.sleep(to_next + 0.05)

            # In-process fallback: bounded, still enforcing, never crashing.
            for i in range(3):
                allowed, _ = check_rate_limit("down", f"unique-{id(self)}", 3, 60)
                self.assertTrue(allowed, f"attempt {i + 1} should pass the local budget")
            allowed, retry = check_rate_limit("down", f"unique-{id(self)}", 3, 60)
            self.assertFalse(allowed)
            self.assertGreaterEqual(retry, 1)
        finally:
            os.environ.pop("REDIS_URL", None)
            redis_client.close_redis()

    # --- conversation context cache -----------------------------------------
    def test_context_cache_loss_rebuilds_from_database(self):
        sid = "user:777"
        database_chat_history.add_message("user", "remember the blue key", sid)

        ctx = session_service.get_session("follow up on the blue key", sid)
        self.assertEqual(len(ctx.chat_history), 1)

        # The context was cached in Redis.
        self.assertTrue(redis_client.get_redis().exists(session_service._ctx_key(sid)))

        # Simulate Redis data loss (or a fresh instance): drop the cache key.
        redis_client.get_redis().delete(session_service._ctx_key(sid))

        # Rebuild from the database: history is identical, nothing was lost.
        rebuilt = session_service.get_session("and the blue key again", sid)
        self.assertEqual(len(rebuilt.chat_history), 1)
        self.assertEqual(rebuilt.chat_history[0]["content"], "remember the blue key")

    def test_context_cache_ttl_is_applied(self):
        sid = "user:888"
        session_service.get_session("hello", sid)
        ttl = redis_client.get_redis().ttl(session_service._ctx_key(sid))
        self.assertGreater(ttl, 0)
        self.assertLessEqual(ttl, 86400)


if __name__ == "__main__":
    unittest.main()
