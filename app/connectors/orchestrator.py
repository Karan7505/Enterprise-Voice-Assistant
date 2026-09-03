"""Connector orchestrator.

This is the single entry point JARVIS core uses to run a business action. It
keeps provider logic out of the chat flow:

    BusinessAction (from the LLM)
        -> CRM resolves the recipient / group
        -> the appropriate connector executes the action
        -> a clean ActionResult is returned to the user

Adding a new connector later means: (1) add an ActionCode/branch here, (2) add
its config keys, and (3) teach the LLM the new action type in the prompt. No
other chat/voice/memory/TTS code changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.connectors.base import ActionCode, ActionResult
from app.connectors.crm_connector import get_crm
from app.connectors.email_connector import get_email_connector
from app.connectors.whatsapp_connector import get_whatsapp_connector

logger = logging.getLogger(__name__)

# The actions the LLM may currently request. Extend this set to add connectors.
SUPPORTED_ACTIONS = {"whatsapp_message", "email"}
# Connectors that need a recipient resolved from the CRM.
_RECIPIENT_ACTIONS = {"whatsapp_message", "email"}


@dataclass
class BusinessAction:
    """A structured business action the LLM has decided to perform."""

    action: str
    recipient: str | None = None
    message: str | None = None
    subject: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "BusinessAction | None":
        """Build a BusinessAction from the LLM's ``action`` JSON block.

        Returns ``None`` when there is no action or it is malformed, so the
        caller can fall back to a plain conversational reply.
        """
        if not data or not isinstance(data, dict):
            return None
        action = str(data.get("action") or "").strip()
        if action not in SUPPORTED_ACTIONS:
            return None
        return cls(
            action=action,
            recipient=(str(data["recipient"]).strip() if data.get("recipient") else None),
            message=(str(data["message"]).strip() if data.get("message") else None),
            subject=(str(data["subject"]).strip() if data.get("subject") else None),
            extra={k: v for k, v in data.items() if k not in {"action", "recipient", "message", "subject"}},
        )

    def is_complete(self) -> bool:
        """Whether the LLM supplied enough to attempt the action."""
        if self.action == "email":
            return bool(self.recipient and self.message)
        if self.action == "whatsapp_message":
            return bool(self.recipient and self.message)
        return False


def _resolve_group_members(contact) -> list[str]:
    """Return the email/phone members of a CRM group contact, if present."""
    raw = getattr(contact, "raw", None) or {}
    members = raw.get("members")
    if isinstance(members, list):
        return [str(m).strip() for m in members if str(m).strip()]
    return []


def execute_action(business: BusinessAction) -> ActionResult:
    """Run a business action end-to-end.

    Resolution order:
      1. Validate the action shape.
      2. Resolve the recipient against the CRM (person or group).
      3. Dispatch to the connector for the action type.
    """
    if business.action not in SUPPORTED_ACTIONS:
        return ActionResult.failure(ActionCode.INVALID_ACTION)

    # --- recipient resolution via CRM -------------------------------------
    if business.action in _RECIPIENT_ACTIONS:
        if not business.recipient:
            return ActionResult.failure(
                ActionCode.MISSING_FIELDS,
                "Who should I send this to? Could you give me a name?",
            )

        contact = get_crm().resolve(business.recipient)
        if contact is None:
            return ActionResult.failure(
                ActionCode.RECIPIENT_NOT_FOUND,
                f'I couldn\'t find "{business.recipient}" in your contacts, so I didn\'t send anything.',
            )

        if business.action == "whatsapp_message":
            phone = contact.phone
            if phone:
                return get_whatsapp_connector().send_text(phone, business.message or "")
            # A group has no single number; send to each member that carries a phone.
            phones = [m for m in _resolve_group_members(contact) if m.startswith("+") or m.isdigit()]
            if phones:
                results = [get_whatsapp_connector().send_text(p, business.message or "") for p in phones]
                return _combine(results, "WhatsApp message")
            return ActionResult.failure(
                ActionCode.PHONE_UNAVAILABLE,
                f'I found {contact.name}, but they don\'t have a WhatsApp number on file.',
            )

        # email action
        email = contact.email
        if email:
            return get_email_connector().send(email, business.subject or "", business.message or "")
        # A group resolves to its member addresses; the connector handles a list.
        members = _resolve_group_members(contact)
        if members:
            return get_email_connector().send(members, business.subject or "", business.message or "")
        return ActionResult.failure(
            ActionCode.EMAIL_UNAVAILABLE,
            f'I found {contact.name}, but they don\'t have an email address on file.',
        )

    return ActionResult.failure(ActionCode.INVALID_ACTION)


def run_business_action(
    reply: str,
    action_data: dict[str, Any] | None,
) -> str:
    """Run a business action (if the LLM requested one) and return the final
    user-facing reply.

    This is the only bridge between the chat flow and the connector layer, so
    provider execution never lives inside the LLM/prompting code. When there is
    no valid action it simply returns ``reply`` unchanged.
    """
    business = BusinessAction.from_dict(action_data)
    if business is None:
        return reply

    result = execute_action(business)
    logger.info(
        "Business action %s -> %s (success=%s)",
        business.action,
        result.code.value,
        result.success,
    )

    # Combine the LLM's acknowledgement with the concrete delivery outcome.
    ack = (reply or "").strip()
    return f"{ack} {result.message}".strip() if ack else result.message


def _combine(results: list[ActionResult], kind: str) -> ActionResult:
    """Fold per-recipient results into a single user-facing result."""
    if not results:
        return ActionResult.failure(ActionCode.EXECUTION_ERROR)
    if all(r.success for r in results):
        return ActionResult.ok(
            f"I've sent {kind} to {len(results)} recipient(s)." if len(results) > 1
            else f"I've sent the {kind}.",
            details={"count": len(results)},
        )
    successes = sum(1 for r in results if r.success)
    return ActionResult.failure(
        ActionCode.PROVIDER_REJECTED,
        f"I sent {kind} to {successes} of {len(results)} recipient(s); the rest failed.",
        details={"successes": successes, "total": len(results)},
    )
