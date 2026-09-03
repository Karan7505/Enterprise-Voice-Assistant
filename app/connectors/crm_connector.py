"""CRM connector.

Resolves a person or group mentioned by the user into the contact details that
downstream connectors (WhatsApp, Email) need. The provider is replaceable:
``BaseCRM`` defines the contract and the default ``DirectoryCRM`` is an
in-memory implementation that can be swapped for a real CRM (Salesforce, HubSpot,
a custom REST API, ...) by subclassing and returning it from ``get_crm()``.
"""

from __future__ import annotations

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


def load_directory_from_config() -> list[dict[str, Any]]:
    """Build the default directory from ``CRM_CONTACTS`` env config.

    ``CRM_CONTACTS`` is a JSON array of contact objects, e.g.::

        [
          {"name": "Rahul", "phone": "+919812345678", "email": "rahul@acme.com", "role": "engineer"},
          {"name": "Sales Team", "kind": "group", "members": ["rahul@acme.com"]}
        ]

    Kept as JSON so the file/env stays a single source of truth and no real
    CRM credential is required for the reference directory.
    """
    import json
    import logging
    import os

    logger = logging.getLogger(__name__)
    raw = (os.getenv("CRM_CONTACTS") or "").strip()
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
    """Return the process-wide CRM instance, building it once.

    To use a different CRM, set ``CRM_PROVIDER`` and register a factory, or
    replace the ``DirectoryCRM`` here. JARVIS core logic is unaffected.
    """
    global _crm_instance
    if _crm_instance is None:
        _crm_instance = DirectoryCRM(load_directory_from_config())
    return _crm_instance


def set_crm(instance: BaseCRM) -> None:
    """Override the active CRM (used by tests and custom provider wiring)."""
    global _crm_instance
    _crm_instance = instance
