import unittest
from unittest.mock import MagicMock

from app.connectors import orchestrator
from app.connectors.base import ActionCode, ActionResult
from app.connectors.crm_connector import Contact
from app.connectors.orchestrator import BusinessAction, execute_action, run_business_action


class _StubCRM:
    """Deterministic stand-in for the real CRM during tests."""

    def __init__(self, contacts):
        self._contacts = {c.name: c for c in contacts}

    def resolve(self, name):
        name = (name or "").strip()
        for key, contact in self._contacts.items():
            if name.lower() in key.lower():
                return contact
        return None


RAHUL = Contact(name="Rahul", phone="+919812345678", email="rahul@acme.com")
PRIYA = Contact(name="Priya", email="priya@acme.com")
SALES = Contact(
    name="Sales Team",
    kind="group",
    raw={"members": ["rahul@acme.com", "priya@acme.com"]},
)


def _whatsapp_stub(*, configured=True, to=None, sent=True):
    stub = MagicMock()
    stub.is_configured.return_value = configured
    if sent:
        stub.send_text.return_value = ActionResult.ok(
            "I've sent the WhatsApp message.", details={"to": to}
        )
    else:
        stub.send_text.return_value = ActionResult.failure(
            ActionCode.PROVIDER_REJECTED, "declined"
        )
    return stub


class BusinessActionParsingTests(unittest.TestCase):
    def test_from_dict_builds_valid_action(self):
        action = BusinessAction.from_dict(
            {"action": "email", "recipient": "Priya", "subject": "Hi", "message": "There"}
        )
        self.assertIsNotNone(action)
        self.assertEqual(action.action, "email")
        self.assertEqual(action.recipient, "Priya")
        self.assertTrue(action.is_complete())

    def test_from_dict_rejects_unknown_action(self):
        self.assertIsNone(BusinessAction.from_dict({"action": "sms", "recipient": "Rahul"}))
        self.assertIsNone(BusinessAction.from_dict(None))
        self.assertIsNone(BusinessAction.from_dict({"recipient": "Rahul"}))

    def test_run_business_action_without_action_returns_reply_unchanged(self):
        self.assertEqual(run_business_action("Hello", None), "Hello")


class WhatsAppWorkflowTests(unittest.TestCase):
    def setUp(self):
        self._patchers = [
            unittest.mock.patch.object(orchestrator, "get_crm", return_value=_StubCRM([RAHUL, SALES])),
            unittest.mock.patch.object(
                orchestrator, "get_whatsapp_connector", return_value=_whatsapp_stub()
            ),
        ]
        self.crm = self.whatsapp = None
        for patcher in self._patchers:
            patcher.start()
        self.whatsapp = orchestrator.get_whatsapp_connector()

    def tearDown(self):
        for patcher in self._patchers:
            patcher.stop()

    def test_crm_resolves_and_whatsapp_sends(self):
        result = execute_action(
            BusinessAction(action="whatsapp_message", recipient="Rahul", message="Meeting at 4")
        )
        self.assertTrue(result.success, result.message)
        self.whatsapp.send_text.assert_called_once_with("+919812345678", "Meeting at 4")

    def test_recipient_not_found_does_not_send(self):
        result = execute_action(
            BusinessAction(action="whatsapp_message", recipient="Ghost", message="hi")
        )
        self.assertFalse(result.success)
        self.assertEqual(result.code, ActionCode.RECIPIENT_NOT_FOUND)
        self.whatsapp.send_text.assert_not_called()

    def test_contact_without_phone_reports_phone_unavailable(self):
        stub = _StubCRM([Contact(name="Amit", email="amit@acme.com")])
        with unittest.mock.patch.object(orchestrator, "get_crm", return_value=stub):
            result = execute_action(
                BusinessAction(action="whatsapp_message", recipient="Amit", message="hi")
            )
        self.assertFalse(result.success)
        self.assertEqual(result.code, ActionCode.PHONE_UNAVAILABLE)

    def test_group_whatsapp_fans_out_to_member_numbers(self):
        stub = _StubCRM(
            [Contact(name="Team", kind="group", raw={"members": ["+919000000001", "+919000000002"]})]
        )
        with unittest.mock.patch.object(orchestrator, "get_crm", return_value=stub):
            result = execute_action(
                BusinessAction(action="whatsapp_message", recipient="Team", message="bye")
            )
        self.assertTrue(result.success)
        self.assertEqual(self.whatsapp.send_text.call_count, 2)

    def test_unconfigured_whatsapp_returns_not_configured(self):
        # Use a real connector with no credentials so the is_configured() guard
        # actually runs (a stub would bypass it).
        from app.connectors.whatsapp_connector import WhatsAppConnector

        with unittest.mock.patch.object(
            orchestrator, "get_whatsapp_connector", return_value=WhatsAppConnector(token="", phone_number_id="")
        ):
            result = execute_action(
                BusinessAction(action="whatsapp_message", recipient="Rahul", message="hi")
            )
        self.assertFalse(result.success)
        self.assertEqual(result.code, ActionCode.NOT_CONFIGURED)

    def test_provider_rejection_is_reported_cleanly(self):
        with unittest.mock.patch.object(
            orchestrator, "get_whatsapp_connector", return_value=_whatsapp_stub(sent=False)
        ):
            result = execute_action(
                BusinessAction(action="whatsapp_message", recipient="Rahul", message="hi")
            )
        self.assertFalse(result.success)
        self.assertEqual(result.code, ActionCode.PROVIDER_REJECTED)
        self.assertNotIn("Bearer", result.message)

    def test_run_business_action_combines_ack_and_result(self):
        final = run_business_action(
            "On it - sending to Rahul.",
            {"action": "whatsapp_message", "recipient": "Rahul", "message": "Meeting at 4"},
        )
        self.assertIn("On it", final)
        self.assertIn("sent the WhatsApp message", final)


class EmailWorkflowTests(unittest.TestCase):
    def setUp(self):
        self._patchers = [
            unittest.mock.patch.object(orchestrator, "get_crm", return_value=_StubCRM([RAHUL, PRIYA, SALES])),
            unittest.mock.patch.object(
                orchestrator,
                "get_email_connector",
                return_value=MagicMock(
                    send=MagicMock(
                        return_value=ActionResult.ok(
                            "I've emailed priya@acme.com.", details={"to": ["priya@acme.com"]}
                        )
                    )
                ),
            ),
        ]
        self.email = None
        for patcher in self._patchers:
            patcher.start()
        self.email = orchestrator.get_email_connector()

    def tearDown(self):
        for patcher in self._patchers:
            patcher.stop()

    def test_crm_resolves_and_email_sends(self):
        result = execute_action(
            BusinessAction(action="email", recipient="Priya", subject="Update", message="Moved to tomorrow")
        )
        self.assertTrue(result.success, result.message)
        self.email.send.assert_called_once_with("priya@acme.com", "Update", "Moved to tomorrow")

    def test_contact_without_email_reports_unavailable(self):
        stub = _StubCRM([Contact(name="Ravi", phone="+919000000000")])
        with unittest.mock.patch.object(orchestrator, "get_crm", return_value=stub):
            result = execute_action(
                BusinessAction(action="email", recipient="Ravi", subject="Hi", message="there")
            )
        self.assertFalse(result.success)
        self.assertEqual(result.code, ActionCode.EMAIL_UNAVAILABLE)
        self.email.send.assert_not_called()

    def test_group_email_uses_member_list(self):
        result = execute_action(
            BusinessAction(action="email", recipient="Sales Team", subject="Note", message="Updated")
        )
        self.assertTrue(result.success)
        self.email.send.assert_called_once_with(
            ["rahul@acme.com", "priya@acme.com"], "Note", "Updated"
        )


if __name__ == "__main__":
    unittest.main()
