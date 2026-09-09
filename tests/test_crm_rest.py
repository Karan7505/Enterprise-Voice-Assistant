import unittest
from unittest.mock import patch

from app.connectors.crm_connector import RestCRM, get_crm, set_crm, DirectoryCRM


class _FakeSettings:
    """Just the REST CRM fields the provider reads."""
    CRM_PROVIDER = "rest"
    CRM_REST_BASE_URL = "https://crm.example.com"
    CRM_REST_API_KEY = "secret"
    CRM_REST_AUTH_HEADER = "Authorization"
    CRM_REST_AUTH_SCHEME = "Bearer"
    CRM_REST_SEARCH_PATH = "/contacts/search"
    CRM_REST_QUERY_PARAM = "q"
    CRM_REST_RESULTS_KEY = "results"
    CRM_REST_TIMEOUT = 5.0
    CRM_REST_NAME_FIELD = "name"
    CRM_REST_PHONE_FIELD = "phone"
    CRM_REST_EMAIL_FIELD = "email"
    CRM_CONTACTS = ""


class _FakeHTTPResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class RestCRMTests(unittest.TestCase):
    def _search(self, query, payload):
        """Run a CRM search with urlopen mocked to return ``payload``."""
        import json
        crm = RestCRM(_FakeSettings())
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(json.dumps(payload).encode("utf-8")),
        ):
            return crm.find_contact(query)

    def test_finds_a_person_from_results_envelope(self):
        contact = self._search("Rahul", {
            "results": [
                {"name": "Rahul Sharma", "phone": "+919812345678", "email": "rahul@acme.com"},
            ]
        })
        self.assertIsNotNone(contact)
        self.assertEqual(contact.phone, "+919812345678")
        self.assertEqual(contact.email, "rahul@acme.com")

    def test_falls_back_to_field_aliases(self):
        contact = self._search("Priya", {
            "data": [
                {"display_name": "Priya Menon", "mobile": "+919000000000", "email_address": "priya@acme.com"},
            ]
        })
        self.assertIsNotNone(contact)
        self.assertEqual(contact.name, "Priya Menon")
        self.assertEqual(contact.phone, "+919000000000")
        self.assertEqual(contact.email, "priya@acme.com")

    def test_sends_authorization_header_and_query(self):
        import json
        import urllib.request
        crm = RestCRM(_FakeSettings())
        with patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = _FakeHTTPResponse(json.dumps({"results": []}).encode("utf-8"))
            crm.find_contact("Nobody")
            request = urlopen.call_args[0][0]
            self.assertEqual(request.get_header("Authorization"), "Bearer secret")
            self.assertIn("/contacts/search?q=Nobody", request.full_url)

    def test_get_crm_selects_provider_by_config(self):
        # Default (directory) when nothing is configured as rest.
        with patch("app.core.config.settings") as fake_settings:
            fake_settings.CRM_PROVIDER = "directory"
            fake_settings.CRM_CONTACTS = ""
            set_crm(None)
            self.assertIsInstance(get_crm(), DirectoryCRM)

            fake_settings.CRM_PROVIDER = "rest"
            fake_settings.CRM_REST_BASE_URL = "https://x"
            set_crm(None)
            self.assertIsInstance(get_crm(), RestCRM)


if __name__ == "__main__":
    unittest.main()
