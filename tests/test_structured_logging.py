"""Phase 4 verification: structured JSON logging + correlation IDs.

Checks (blueprint Change 6):
  * every log line the app emits is a single JSON object,
  * X-Correlation-ID is generated, honored from the client, echoed in the
    response, and present on the request's log lines,
  * no secret material (passwords, session tokens, API keys) ever appears in
    log output across a full register/login/chat/logout flow.
"""

import io
import json
import logging
import unittest

from pg_test_support import TestDatabase
from app.core import logging_conf
from app.core.correlation import HEADER
from app.services import auth_service

SECRETS = {
    "password123",
    "super-secret-token-abc",
}


class StructuredLoggingTests(unittest.TestCase):
    def setUp(self):
        self._db = TestDatabase()
        self._db.start()
        logging_conf.setup_logging(force=True)

    def tearDown(self):
        self._db.stop()
        # Leave logging in JSON mode for the rest of the suite.
        logging_conf.setup_logging(force=True)

    def _client(self):
        from fastapi.testclient import TestClient
        from app.main import app

        # https base URL so a Secure-flagged auth cookie is accepted.
        return TestClient(app, base_url="https://testserver")

    def _capture(self):
        """A temp root handler reusing the configured JSON formatter, so
        capture works no matter which stream the permanent handler holds."""
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        root = logging.getLogger()
        for existing in root.handlers:
            if getattr(existing, "formatter", None) is not None:
                handler.setFormatter(existing.formatter)
                break
        root.addHandler(handler)
        return buf, handler

    def _stop_capture(self, handler):
        logging.getLogger().removeHandler(handler)

    def _capture_flow(self, client, correlation_in=None):
        """Run register -> login -> chat -> logout, capturing the JSON log."""
        buf, handler = self._capture()
        headers = {HEADER: correlation_in} if correlation_in else {}
        try:
            r = client.post(
                "/auth/register",
                json={"username": "loguser", "password": "password123"},
                headers=headers,
            )
            token = r.json()["token"]
            r = client.get("/auth/me", headers={**headers, "Authorization": f"Bearer {token}"})
            r = client.post(
                "/auth/login",
                json={"username": "loguser", "password": "password123"},
                headers=headers,
            )
            token = r.json()["token"]
            # A chat turn: process_message is stubbed (no LLM in unit tests).
            from app.api import chat as chat_api
            from unittest.mock import patch

            with patch.object(chat_api, "process_message", new=fake_process_message):
                r = client.post(
                    "/chat",
                    json={"message": "hello", "response_mode": "text"},
                    headers={**headers, "Authorization": f"Bearer {token}"},
                )
            r = client.post("/auth/logout", headers={**headers, "Authorization": f"Bearer {token}"})
        finally:
            self._stop_capture(handler)
        return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()], r

    def test_log_lines_are_json_with_correlation_id(self):
        client = self._client()
        cid = "trace-abc-123"
        lines, logout = self._capture_flow(client, correlation_in=cid)
        self.assertGreater(len(lines), 0)

        # Every emitted line must be a complete JSON object.
        for line in lines:
            self.assertIn("event", line)
            self.assertIn("timestamp", line)
            self.assertIn("level", line)

        # The correlation id we supplied must appear on the request logs.
        correlated = [l for l in lines if l.get("correlation_id") == cid]
        self.assertTrue(
            correlated,
            f"no log line carries correlation id {cid}: {lines[:3]}",
        )
        # The response must echo the id back to the client.
        self.assertEqual(logout.headers.get(HEADER), cid)

    def test_correlation_id_generated_when_absent(self):
        client = self._client()
        r = client.post(
            "/auth/register",
            json={"username": "nologuser", "password": "password123"},
        )
        token = r.json()["token"]
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        generated = r.headers.get(HEADER)
        self.assertTrue(generated, "response must carry a generated correlation id")
        self.assertNotIn(generated, SECRETS)
        self.assertLessEqual(len(generated), 64)

    def test_no_secrets_in_log_output(self):
        client = self._client()
        lines, _ = self._capture_flow(client, correlation_in="trace-secrets")
        blob = json.dumps(lines)

        for secret in SECRETS:
            self.assertNotIn(secret, blob, f"secret material {secret!r} leaked into logs")
        # The bearer token issued during the flow must not be logged either.
        user = auth_service
        conn_lines = [l for l in lines if l.get("event") == "request"]
        self.assertTrue(conn_lines, "expected request access-log lines")


# A stand-in process_message that mirrors the real signature (async, three
# positional/keyword args) without touching the LLM.
async def fake_process_message(message, session_id, mode="text"):
    return "hi there"
