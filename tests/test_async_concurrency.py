"""Phase 3 verification: async provider calls keep the event loop free.

Blueprint acceptance: with a slow provider (5 s per call), 40+ concurrent
requests must run *in parallel* — total wall time stays near one provider
round-trip, not N x round-trip — because no synchronous provider I/O blocks
the loop (sync DB/Redis work is offloaded to the thread pool).

Also verifies the resilience primitives: the LLM timebox, retry-then-succeed,
and the circuit breaker trip/fail-fast behavior.
"""

import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from pg_test_support import TestDatabase
from app.core import resilience
from app.core.config import settings
from app.services import auth_service
from app.services import llm_service, session_service

CANNED = json.dumps({"reply": "ok", "memories": {}, "delete_memories": []})


class ResiliencePrimitiveTests(unittest.TestCase):
    def test_timebox_fires(self):
        async def slow():
            await asyncio.sleep(3)
            return "done"

        async def run():
            start = time.monotonic()
            with self.assertRaises(resilience.ProviderTimeoutError):
                await resilience.timebox(slow(), 0.2, "stub")
            return time.monotonic() - start

        elapsed = asyncio.run(run())
        self.assertLess(elapsed, 1.5, "timebox must cut the call short")

    def test_retries_until_success(self):
        attempts = {"n": 0}

        @resilience.async_retries(3, (ValueError,))
        async def flaky():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ValueError("transient")
            return "ok"

        self.assertEqual(asyncio.run(flaky()), "ok")
        self.assertEqual(attempts["n"], 3)

    def test_breaker_trips_and_fails_fast(self):
        breaker = resilience.CircuitBreaker("stub-test", fail_max=5, reset_timeout=60)

        async def boom():
            raise RuntimeError("provider down")

        async def run():
            for _ in range(5):
                try:
                    await resilience.call_with_breaker(breaker, boom)
                except RuntimeError:
                    pass
            self.assertEqual(breaker.state, "open")
            start = time.monotonic()
            with self.assertRaises(resilience.CircuitOpenError):
                await resilience.call_with_breaker(breaker, boom)
            return time.monotonic() - start

        elapsed = asyncio.run(run())
        self.assertLess(elapsed, 0.5, "open breaker must fail fast, not call the provider")

    def test_breaker_recovers_after_reset(self):
        breaker = resilience.CircuitBreaker("stub-recover", fail_max=1, reset_timeout=0.2)

        async def ok():
            return 42

        async def run():
            breaker.trip()
            with self.assertRaises(resilience.CircuitOpenError):
                await resilience.call_with_breaker(breaker, ok)
            await asyncio.sleep(0.25)
            self.assertEqual(breaker.state, "half-open")
            return await resilience.call_with_breaker(breaker, ok)

        self.assertEqual(asyncio.run(run()), 42)


class ConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self._db = TestDatabase()
        self._db.start()
        resilience.reset_breakers()

    def tearDown(self):
        self._db.stop()
        resilience.reset_breakers()

    def test_fifty_concurrent_slow_provider_calls_run_in_parallel(self):
        """Direct service-level check: 50 x 5 s stub LLM calls must finish in
        well under 50 x 5 s (serial) — the event loop stays free."""

        async def slow_generate(prompt):
            await asyncio.sleep(5)
            return CANNED

        users = [f"user{i}" for i in range(10)]
        sids = []
        for name in users:
            user = auth_service.register_user(name, "password123")
            sids.append(f"user:{user['id']}")

        async def run_all():
            tasks = [
                session_service.process_message("hello", sid, mode="text")
                for sid in sids
                for _ in range(5)
            ]
            return await asyncio.gather(*tasks)

        start = time.monotonic()
        with patch.object(session_service, "generate", new=slow_generate):
            replies = asyncio.run(run_all())
        elapsed = time.monotonic() - start

        self.assertEqual(len(replies), 50)
        self.assertTrue(all(r == "ok" for r in replies))
        # 50 serial calls would take >= 250 s; parallel must be far below that.
        self.assertLess(elapsed, 40, f"50 concurrent 5 s calls took {elapsed:.1f}s — the provider path looks serialized")

    def test_concurrent_http_chat_under_slow_provider(self):
        """HTTP-level check through the real app (ASGI transport): 50
        concurrent /chat requests from 5 users, each with a 5 s stub LLM,
        all succeed, and total wall time proves the loop is not blocked."""
        from app.main import app

        tokens = []
        for name in ("load1", "load2", "load3", "load4", "load5"):
            auth_service.register_user(name, "password123")
            token = auth_service.authenticate(name, "password123")
            tokens.append(token)

        async def slow_generate(prompt):
            await asyncio.sleep(5)
            return CANNED

        async def run_all():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="https://testserver", timeout=90
            ) as client:
                async def one(token, i):
                    resp = await client.post(
                        "/chat",
                        json={"message": f"hello {i}", "response_mode": "text"},
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    return resp

                # 5 users x 10 requests = 50 concurrent (per-user chat cap is 12).
                tasks = [one(token, i) for token in tokens for i in range(10)]
                return await asyncio.gather(*tasks)

        start = time.monotonic()
        with patch.object(session_service, "generate", new=slow_generate):
            responses = asyncio.run(run_all())
        elapsed = time.monotonic() - start

        self.assertEqual(len(responses), 50)
        self.assertTrue(
            all(r.status_code == 200 for r in responses),
            f"non-200 responses: {[r.status_code for r in responses if r.status_code != 200]}",
        )
        self.assertLess(elapsed, 40, f"50 concurrent HTTP chats took {elapsed:.1f}s — provider path looks serialized")


if __name__ == "__main__":
    unittest.main()
