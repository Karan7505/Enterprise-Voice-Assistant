import json
import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from pg_test_support import TestDatabase
from app.api.chat import ChatRequest
from app.core import database
from app.core.config import settings
from app.core.rate_limiter import check_rate_limit
from app.connectors import orchestrator
from app.connectors.base import ActionResult
from app.connectors.crm_connector import Contact
from app.services import action_policy
from app.services import auth_service
from app.services import session_service


class _StubCRM:
    """Deterministic CRM stand-in (mirrors tests/test_connectors.py)."""

    def __init__(self, contacts):
        self._contacts = {c.name: c for c in contacts}

    def resolve(self, name):
        name = (name or "").strip()
        for key, contact in self._contacts.items():
            if name.lower() in key.lower():
                return contact
        return None


def _canned_action_reply(action=None, reply="On it."):
    return json.dumps(
        {"reply": reply, "action": action, "memories": {}, "delete_memories": []}
    )


RAHUL = Contact(name="Rahul", phone="+919812345678")
ACTION = {"action": "whatsapp_message", "recipient": "Rahul", "message": "Meeting at 4"}


class SecurityControlTests(unittest.TestCase):
    def setUp(self):
        self._db = TestDatabase()
        self._db.start()

    def tearDown(self):
        self._db.stop()

    def _register(self, username="alice", password="password123"):
        return auth_service.register_user(username, password)

    def _whatsapp_stub(self):
        wa = MagicMock()
        wa.send_text.return_value = ActionResult.ok("I've sent the WhatsApp message.")
        return wa

    # --- M-1: token expiry -------------------------------------------------
    def test_token_is_rejected_after_expiry(self):
        self._register("alice")
        token = auth_service.authenticate("alice", "password123")
        self.assertIsNotNone(token)
        self.assertIsNotNone(auth_service.resolve_user(token))

        conn = database.get_connection()
        conn.execute(
            "UPDATE auth_sessions SET expires_at = '2000-01-01T00:00:00+00:00' "
            "WHERE token = ?",
            (token,),
        )
        conn.commit()
        conn.close()
        self.assertIsNone(auth_service.resolve_user(token))

    # --- M-2: input cap ----------------------------------------------------
    def test_chat_message_has_a_length_cap(self):
        ChatRequest(message="hi")  # within the cap -> valid
        with self.assertRaises(ValidationError):
            ChatRequest(message="x" * (settings.MAX_MESSAGE_LENGTH + 1))

    # --- M-2: rate limiter -------------------------------------------------
    def test_rate_limiter_enforces_window(self):
        self.assertTrue(check_rate_limit("t", "k", 2, 60)[0])
        self.assertTrue(check_rate_limit("t", "k", 2, 60)[0])
        allowed, retry = check_rate_limit("t", "k", 2, 60)
        self.assertFalse(allowed)
        self.assertGreater(retry, 0)

    # --- H-1: fail-closed by default --------------------------------------
    def test_business_action_disabled_by_default_does_not_send(self):
        user = self._register("alice")
        session_id = f"user:{user['id']}"
        wa = self._whatsapp_stub()
        with patch.object(orchestrator, "get_crm") as get_crm, \
             patch.object(orchestrator, "get_whatsapp_connector", return_value=wa), \
             patch.object(session_service, "generate",
                          return_value=_canned_action_reply(ACTION)):
            reply = session_service.process_message(
                "Send Rahul a WhatsApp: Meeting at 4", session_id, mode="text"
            )
        get_crm.assert_not_called()
        wa.send_text.assert_not_called()
        self.assertIn("isn't enabled", reply)

    # --- H-1/H-2: allowlisted user must confirm before a real send --------
    def test_enabled_allowlisted_action_requires_confirmation_then_sends(self):
        user = self._register("alice")
        session_id = f"user:{user['id']}"
        wa = self._whatsapp_stub()
        with patch.object(settings, "BUSINESS_ACTIONS_ENABLED", True), \
             patch.object(settings, "BUSINESS_ACTION_ALLOWED_USERS", "alice"), \
             patch.object(settings, "BUSINESS_ACTION_REQUIRE_CONFIRMATION", True), \
             patch.object(orchestrator, "get_crm", return_value=_StubCRM([RAHUL])), \
             patch.object(orchestrator, "get_whatsapp_connector", return_value=wa), \
             patch.object(session_service, "generate",
                          return_value=_canned_action_reply(ACTION)):
            first = session_service.process_message(
                "Send Rahul a WhatsApp: Meeting at 4", session_id, mode="text"
            )
            self.assertIn("shall I", first)
            wa.send_text.assert_not_called()

            second = session_service.process_message("yes", session_id, mode="text")
        self.assertIn("sent", second)
        wa.send_text.assert_called_once_with("+919812345678", "Meeting at 4")

    def test_confirmation_reject_does_not_send(self):
        user = self._register("alice")
        session_id = f"user:{user['id']}"
        wa = self._whatsapp_stub()
        with patch.object(settings, "BUSINESS_ACTIONS_ENABLED", True), \
             patch.object(settings, "BUSINESS_ACTION_ALLOWED_USERS", "alice"), \
             patch.object(settings, "BUSINESS_ACTION_REQUIRE_CONFIRMATION", True), \
             patch.object(orchestrator, "get_crm", return_value=_StubCRM([RAHUL])), \
             patch.object(orchestrator, "get_whatsapp_connector", return_value=wa), \
             patch.object(session_service, "generate",
                          return_value=_canned_action_reply(ACTION)):
            session_service.process_message(
                "Send Rahul a WhatsApp: Meeting at 4", session_id, mode="text"
            )
            second = session_service.process_message("no", session_id, mode="text")
        wa.send_text.assert_not_called()
        self.assertIn("cancel", second.lower())

    # --- H-1: a user outside the allowlist can never send ------------------
    def test_non_allowlisted_user_cannot_send(self):
        user = self._register("mallory")
        session_id = f"user:{user['id']}"
        wa = self._whatsapp_stub()
        with patch.object(settings, "BUSINESS_ACTIONS_ENABLED", True), \
             patch.object(settings, "BUSINESS_ACTION_ALLOWED_USERS", "alice"), \
             patch.object(orchestrator, "get_crm") as get_crm, \
             patch.object(orchestrator, "get_whatsapp_connector", return_value=wa), \
             patch.object(session_service, "generate",
                          return_value=_canned_action_reply(ACTION)):
            reply = session_service.process_message(
                "Send Rahul a WhatsApp: Meeting at 4", session_id, mode="text"
            )
        get_crm.assert_not_called()
        wa.send_text.assert_not_called()
        self.assertIn("isn't enabled for your account", reply)

    # --- H-1: trusted single-turn mode still sends exactly once ------------
    def test_no_confirmation_sends_in_single_turn_when_configured(self):
        user = self._register("alice")
        session_id = f"user:{user['id']}"
        wa = self._whatsapp_stub()
        with patch.object(settings, "BUSINESS_ACTIONS_ENABLED", True), \
             patch.object(settings, "BUSINESS_ACTION_ALLOWED_USERS", "alice"), \
             patch.object(settings, "BUSINESS_ACTION_REQUIRE_CONFIRMATION", False), \
             patch.object(orchestrator, "get_crm", return_value=_StubCRM([RAHUL])), \
             patch.object(orchestrator, "get_whatsapp_connector", return_value=wa), \
             patch.object(session_service, "generate",
                          return_value=_canned_action_reply(ACTION)):
            reply = session_service.process_message(
                "Send Rahul a WhatsApp: Meeting at 4", session_id, mode="text"
            )
        self.assertIn("sent", reply)
        wa.send_text.assert_called_once_with("+919812345678", "Meeting at 4")

    # --- H-2: confirmation classification is fail-safe ---------------------
    def test_confirmations_classified(self):
        self.assertEqual(action_policy.classify_confirmation("yes"), "yes")
        self.assertEqual(action_policy.classify_confirmation("YES"), "yes")
        self.assertEqual(action_policy.classify_confirmation("confirm"), "yes")
        self.assertEqual(action_policy.classify_confirmation("no"), "no")
        self.assertEqual(action_policy.classify_confirmation("cancel"), "no")
        self.assertIsNone(action_policy.classify_confirmation("what's the weather"))
        # A brand-new send request while a pending exists is not a confirmation.
        self.assertIsNone(action_policy.classify_confirmation("also send Priya"))

    # --- M-5: session delivered as an HttpOnly cookie + header fallback ------
    def test_token_from_request_prefers_header_then_cookie(self):
        from types import SimpleNamespace
        from app.api import auth

        both = SimpleNamespace(
            headers={"Authorization": "Bearer htok"},
            cookies={settings.COOKIE_NAME: "ctok"},
        )
        self.assertEqual(auth._token_from_request(both), "htok")
        cookie_only = SimpleNamespace(headers={}, cookies={settings.COOKIE_NAME: "ctok"})
        self.assertEqual(auth._token_from_request(cookie_only), "ctok")
        self.assertEqual(auth._token_from_request(SimpleNamespace(headers={}, cookies={})),"")

    def test_auth_cookie_is_httponly_and_scoped(self):
        from starlette.responses import Response as StarletteResponse
        from app.api import auth

        resp = StarletteResponse()
        auth.set_auth_cookie(resp, "tok123")
        set_cookie = resp.headers.get("set-cookie", "").lower()
        self.assertIn(f"{settings.COOKIE_NAME}=tok123", set_cookie)
        self.assertIn("httponly", set_cookie)
        self.assertIn("samesite", set_cookie)
        if settings.COOKIE_SECURE:
            self.assertIn("secure", set_cookie)

    # --- Log-injection: username charset is restricted at the API boundary ---
    def test_username_charset_rejects_log_injection(self):
        from app.api.auth import Credentials

        # A newline/CRLF in the username would otherwise forge a log line via
        # `logger.info("... username=%s", username)`.
        with self.assertRaises(ValidationError):
            Credentials(username="alice\n2026-01-01 INFO pwned", password="password123")
        with self.assertRaises(ValidationError):
            Credentials(username="bob\r\nlogout", password="password123")
        with self.assertRaises(ValidationError):
            Credentials(username="has spaces", password="password123")
        # A normal, safe username still passes validation.
        self.assertEqual(
            Credentials(username="alice_1-x", password="password123").username,
            "alice_1-x",
        )

    # --- H-1: a successful, policy-cleared send is written to the audit trail
    def test_successful_send_is_audited(self):
        user = self._register("alice")
        session_id = f"user:{user['id']}"
        wa = self._whatsapp_stub()
        with patch.object(settings, "BUSINESS_ACTIONS_ENABLED", True), \
             patch.object(settings, "BUSINESS_ACTION_ALLOWED_USERS", "alice"), \
             patch.object(settings, "BUSINESS_ACTION_REQUIRE_CONFIRMATION", False), \
             patch.object(orchestrator, "get_crm", return_value=_StubCRM([RAHUL])), \
             patch.object(orchestrator, "get_whatsapp_connector", return_value=wa), \
             patch.object(session_service, "generate",
                           return_value=_canned_action_reply(ACTION)):
            session_service.process_message(
                "Send Rahul a WhatsApp: Meeting at 4", session_id, mode="text"
            )
        rows = self._audit_rows(user["id"])
        self.assertTrue(
            any(r["outcome"] == "success" and r["recipient"] == "Rahul" for r in rows),
            f"expected a success audit row, got {rows}",
        )

    def _audit_rows(self, user_id):
        conn = database.get_connection()
        try:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM action_audit WHERE user_id = ?", (user_id,)
                ).fetchall()
            ]
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
