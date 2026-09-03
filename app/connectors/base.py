"""Shared types for the modular connector layer.

Connectors wrap external business systems (CRM, WhatsApp, Email, ...). The
JARVIS core never talks to a provider directly: it asks a connector to perform
an action and receives a normalized result it can speak back to the user.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ActionCode(str, Enum):
    """Stable, machine-readable outcome codes for a business action."""

    SUCCESS = "success"
    NOT_CONFIGURED = "not_configured"
    RECIPIENT_NOT_FOUND = "recipient_not_found"
    PHONE_UNAVAILABLE = "phone_unavailable"
    EMAIL_UNAVAILABLE = "email_unavailable"
    MISSING_FIELDS = "missing_fields"
    INVALID_ACTION = "invalid_action"
    PROVIDER_REJECTED = "provider_rejected"
    EXECUTION_ERROR = "execution_error"


# User-facing wording for each outcome. Provider-specific details are logged,
# never surfaced, so the user hears a clean, understandable sentence.
_OUTCOME_MESSAGES: dict[ActionCode, str] = {
    ActionCode.SUCCESS: "Done.",
    ActionCode.NOT_CONFIGURED: (
        "I can't run that right now because the connector isn't configured. "
        "Ask your administrator to add its credentials."
    ),
    ActionCode.RECIPIENT_NOT_FOUND: (
        "I couldn't identify the person you meant in your contacts."
    ),
    ActionCode.PHONE_UNAVAILABLE: (
        "I couldn't find a WhatsApp number for that person in your contacts."
    ),
    ActionCode.EMAIL_UNAVAILABLE: (
        "I couldn't find an email address for that person in your contacts."
    ),
    ActionCode.MISSING_FIELDS: "I'm missing some details needed to do that.",
    ActionCode.INVALID_ACTION: "I don't recognize that as something I can do.",
    ActionCode.PROVIDER_REJECTED: (
        "The service declined the request, so it was not sent."
    ),
    ActionCode.EXECUTION_ERROR: (
        "Something went wrong while carrying that out. Please try again."
    ),
}


@dataclass
class ActionResult:
    """Normalized outcome of a business action."""

    success: bool
    code: ActionCode
    message: str
    details: dict[str, Any] | None = None

    @classmethod
    def ok(cls, message: str = "Done.", details: dict[str, Any] | None = None) -> "ActionResult":
        return cls(success=True, code=ActionCode.SUCCESS, message=message, details=details)

    @classmethod
    def failure(
        cls,
        code: ActionCode,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> "ActionResult":
        return cls(
            success=False,
            code=code,
            message=message or _OUTCOME_MESSAGES[code],
            details=details,
        )
