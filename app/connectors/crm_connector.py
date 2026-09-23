"""CRM connector.

Resolves a person or group mentioned by the user into the contact details that
downstream connectors (WhatsApp, Email) need. The provider is replaceable:
``BaseCRM`` defines the contract and the default ``DirectoryCRM`` is an
in-memory implementation that can be swapped for a real CRM (Salesforce, HubSpot,
a custom REST API, ...) by subclassing and returning it from ``get_crm()``.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class Contact:
    """A single contact record returned by a CRM."""

    name: str
    phone: str | None = None
    email: str | None = None
    role: str | None = None
    kind: str = "person"  # "person" or "group"
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "role": self.role,
            "kind": self.kind,
        }


class BaseCRM(ABC):
    """Interface every CRM provider must implement."""

    @abstractmethod
    def find_contact(self, name: str) -> Contact | None:
        """Resolve a person by (fuzzy) name. Return ``None`` if not found."""

    @abstractmethod
    def find_group(self, name: str) -> Contact | None:
        """Resolve a named group/roster (e.g. "sales team"). Return ``None`` if not found."""

    @abstractmethod
    def list_contacts(self) -> list[Contact]:
        """Return all known contacts (for debugging / capability checks)."""

    # --- convenience helpers shared by every provider --------------------
    def resolve(self, name: str) -> Contact | None:
        """Try a person first, then a group. Returns the first match."""
        if not name or not name.strip():
            return None
        return self.find_contact(name) or self.find_group(name)

    async def resolve_async(self, name: str) -> Contact | None:
        """Async resolution. The default runs the sync resolver off the
        event loop; HTTP-backed providers override with a native async path."""
        import asyncio

        return await asyncio.to_thread(self.resolve, name)


class DirectoryCRM(BaseCRM):
    """In-memory reference CRM.

    Contacts are loaded from configuration so a developer can wire up a real
    directory without changing JARVIS core logic. Swap the mapping source for a
    live CRM by subclassing ``BaseCRM`` instead.
    """

    def __init__(self, contacts: list[dict[str, Any]] | None = None):
        self._contacts: list[Contact] = [
            Contact(
                name=c["name"],
                phone=c.get("phone"),
                email=c.get("email"),
                role=c.get("role"),
                kind=c.get("kind", "person"),
                raw=c,
            )
            for c in (contacts or [])
        ]

    @staticmethod
    def _norm(value: str) -> str:
        return " ".join(value.lower().split())

    def find_contact(self, name: str) -> Contact | None:
        needle = self._norm(name)
        if not needle:
            return None
        for contact in self._contacts:
            if contact.kind != "person":
                continue
            if needle in self._norm(contact.name) or self._norm(contact.name) in needle:
                return contact
        return None

    def find_group(self, name: str) -> Contact | None:
        needle = self._norm(name)
        if not needle:
            return None
        for contact in self._contacts:
            if contact.kind != "group":
                continue
            if needle in self._norm(contact.name) or self._norm(contact.name) in needle:
                return contact
        return None

    def list_contacts(self) -> list[Contact]:
        return list(self._contacts)


class RestCRM(BaseCRM):
    """A real external CRM reached over HTTP, configured entirely by env vars.

    This is provider-agnostic: it issues a single search request and maps the
    returned items onto ``Contact`` using configurable field names (with
    common aliases), so a specific CRM such as Salesforce, HubSpot, or a
    custom internal API can be wired up purely through ``.env`` — no code
    edits. All provider-specific concerns (endpoint, auth header, response
    shape) are captured by configuration, not hardcoded.

    Configuration (see ``app/core/config.py``):
      CRM_PROVIDER=rest
      CRM_REST_BASE_URL, CRM_REST_API_KEY, CRM_REST_AUTH_HEADER,
      CRM_REST_AUTH_SCHEME, CRM_REST_SEARCH_PATH, CRM_REST_QUERY_PARAM,
      CRM_REST_RESULTS_KEY, CRM_REST_TIMEOUT, CRM_REST_*_FIELD.
    """

    logger = logging.getLogger(__name__)

    # Common aliases tried (in order) when a configured field is absent.
    _NAME_ALIASES = ("name", "full_name", "display_name", "title", "subject")
    _PHONE_ALIASES = ("phone", "phone_number", "mobile", "mobile_phone", "work_phone", "mobile_phone_number")
    _EMAIL_ALIASES = ("email", "email_address", "primary_email")

    def __init__(self, settings):
        self._s = settings
        self._contacts: list[Contact] = []

    # -- field extraction ----------------------------------------------------
    @staticmethod
    def _first(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _map_item(self, item: dict[str, Any]) -> Contact | None:
        if not isinstance(item, dict):
            return None
        s = self._s
        name = self._first(item, (s.CRM_REST_NAME_FIELD, *self._NAME_ALIASES))
        if not name:
            return None
        phone = self._first(item, (s.CRM_REST_PHONE_FIELD, *self._PHONE_ALIASES))
        email = self._first(item, (s.CRM_REST_EMAIL_FIELD, *self._EMAIL_ALIASES))
        role = self._first(item, ("role", "title", "job_title"))
        kind = str(item.get("kind", "person")).strip().lower() or "person"
        return Contact(name=name, phone=phone, email=email, role=role, kind=kind, raw=item)

    # -- HTTP ---------------------------------------------------------------
    def _search(self, name: str) -> list[dict[str, Any]]:
        s = self._s
        if not s.CRM_REST_BASE_URL:
            return []
        url = s.CRM_REST_BASE_URL + s.CRM_REST_SEARCH_PATH
        if s.CRM_REST_QUERY_PARAM:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urllib.parse.urlencode({s.CRM_REST_QUERY_PARAM: name})}"

        request = urllib.request.Request(url)
        if s.CRM_REST_API_KEY:
            scheme = f"{s.CRM_REST_AUTH_SCHEME} " if s.CRM_REST_AUTH_SCHEME else ""
            request.add_header(s.CRM_REST_AUTH_HEADER, f"{scheme}{s.CRM_REST_API_KEY}")
        request.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=s.CRM_REST_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, ValueError) as exc:
            self.logger.warning("CRM search request failed for %r: %s", name, exc)
            return []

        # The list of items may be top-level, nested under a configured key, or
        # a common envelope such as {"data": [...]} / {"results": [...]} /
        # {"contacts": [...]} / {"items": [...]} / {"records": [...]}.
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in (s.CRM_REST_RESULTS_KEY, "data", "results", "contacts", "items", "records"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _extract_items(s, payload) -> list:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in (s.CRM_REST_RESULTS_KEY, "data", "results", "contacts", "items", "records"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    async def resolve_async(self, name: str) -> Contact | None:
        """Native async resolution: one HTTP search, person-first matching.

        Bounded by the CRM timebox (5 s) and the provider circuit breaker.
        """
        import httpx

        from app.core import resilience
        from app.core.config import settings

        s = self._s
        needle = self._norm(name)
        if not needle or not s.CRM_REST_BASE_URL:
            return None
        timeout = settings.CRM_TIMEOUT_SECONDS

        url = s.CRM_REST_BASE_URL + s.CRM_REST_SEARCH_PATH
        if s.CRM_REST_QUERY_PARAM:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urllib.parse.urlencode({s.CRM_REST_QUERY_PARAM: name})}"
        headers = {"Accept": "application/json"}
        if s.CRM_REST_API_KEY:
            scheme = f"{s.CRM_REST_AUTH_SCHEME} " if s.CRM_REST_AUTH_SCHEME else ""
            headers[s.CRM_REST_AUTH_HEADER] = f"{scheme}{s.CRM_REST_API_KEY}"

        breaker = resilience.get_breaker("crm")

        async def _fetch():
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                return resp.json()

        try:
            payload = await resilience.timebox(
                resilience.call_with_breaker(breaker, _fetch),
                timeout,
                "CRM",
            )
        except Exception as exc:
            self.logger.warning("CRM async search failed for %r: %s", name, exc)
            return None

        items = self._extract_items(s, payload)
        for kind in ("person", "group"):
            for item in items:
                contact = self._map_item(item)
                if contact is None or contact.kind != kind:
                    continue
                if needle in self._norm(contact.name) or self._norm(contact.name) in needle:
                    return contact
        return None

    def _norm(self, value: str) -> str:
        return " ".join(value.lower().split())

    def _load(self) -> None:
        # A live CRM is queried per name; this is a best-effort list endpoint
        # used only for capability checks. It returns what is configured.
        self._contacts = []

    def find_contact(self, name: str) -> Contact | None:
        needle = self._norm(name)
        if not needle:
            return None
        for item in self._search(name):
            contact = self._map_item(item)
            if contact is None or contact.kind != "person":
                continue
            if needle in self._norm(contact.name) or self._norm(contact.name) in needle:
                return contact
        return None

    def find_group(self, name: str) -> Contact | None:
        needle = self._norm(name)
        if not needle:
            return None
        for item in self._search(name):
            contact = self._map_item(item)
            if contact is None or contact.kind != "group":
                continue
            if needle in self._norm(contact.name) or self._norm(contact.name) in needle:
                return contact
        return None

    def list_contacts(self) -> list[Contact]:
        return list(self._contacts)


def load_directory_from_config() -> list[dict[str, Any]]:
    """Build the directory CRM from ``CRM_CONTACTS`` env config.

    ``CRM_CONTACTS`` is a JSON array of contact objects, e.g.::

        [
          {"name": "Rahul", "phone": "+919812345678", "email": "rahul@acme.com", "role": "engineer"},
          {"name": "Sales Team", "kind": "group", "members": ["rahul@acme.com"]}
        ]

    Kept as JSON so the file/env stays a single source of truth and no real
    CRM credential is required for the reference directory.
    """
    from app.core.config import settings

    logger = logging.getLogger(__name__)
    raw = (settings.CRM_CONTACTS or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("CRM_CONTACTS is not valid JSON; using an empty directory.")
        return []
    if not isinstance(data, list):
        logger.warning("CRM_CONTACTS must be a JSON array; using an empty directory.")
        return []
    return data


_crm_instance: BaseCRM | None = None


def get_crm() -> BaseCRM:
    """Return the process-wide CRM instance, selected by ``CRM_PROVIDER``.

    ``directory`` uses the in-memory reference CRM; ``rest`` uses the
    HTTP-based ``RestCRM`` configured entirely by environment variables. JARVIS
    core logic is unaffected by which provider is active.
    """
    global _crm_instance
    if _crm_instance is None:
        from app.core.config import settings

        provider = (settings.CRM_PROVIDER or "directory").strip().lower()
        if provider == "rest":
            _crm_instance = RestCRM(settings)
        else:
            _crm_instance = DirectoryCRM(load_directory_from_config())
    return _crm_instance


def set_crm(instance: BaseCRM) -> None:
    """Override the active CRM (used by tests and custom provider wiring)."""
    global _crm_instance
    _crm_instance = instance
