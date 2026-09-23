"""WhatsApp Business connector.

Sends text messages through the official WhatsApp Cloud API (Meta Graph API)
using only the Python standard library, so no extra dependency is introduced.
Provider-specific code stays inside this module; JARVIS core only receives an
``ActionResult``.
"""

from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request

from app.connectors.base import ActionCode, ActionResult
from app.core.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_GRAPH_VERSION = "v19.0"


class WhatsAppConnector:
    """Sends outbound WhatsApp messages via the Cloud API."""

    def __init__(
        self,
        token: str | None = None,
        phone_number_id: str | None = None,
        graph_version: str | None = None,
    ):
        # Values default to settings so tests can inject their own.
        self.token = (token if token is not None else settings.WA_TOKEN) or ""
        self.phone_number_id = (
            phone_number_id
            if phone_number_id is not None
            else settings.WA_PHONE_NUMBER_ID
        ) or ""
        self.graph_version = (
            graph_version
            if graph_version is not None
            else settings.WA_GRAPH_VERSION
        ) or _DEFAULT_GRAPH_VERSION
        self._ssl_context = ssl.create_default_context()

    def is_configured(self) -> bool:
        return bool(self.token and self.phone_number_id)

    def send_text(self, to: str, message: str) -> ActionResult:
        """Send a text message to a WhatsApp recipient identified by phone number.

        ``to`` must be an E.164-style number (with or without leading '+').
        """
        if not self.is_configured():
            return ActionResult.failure(
                ActionCode.NOT_CONFIGURED,
                "WhatsApp isn't configured yet, so I couldn't send the message.",
            )
        if not to or not to.strip():
            return ActionResult.failure(
                ActionCode.MISSING_FIELDS,
                "I don't have a WhatsApp number to send to.",
            )
        if not message or not message.strip():
            return ActionResult.failure(
                ActionCode.MISSING_FIELDS,
                "There's no message content to send.",
            )

        recipient = to.strip().lstrip("+")
        endpoint = (
            "https://graph.facebook.com"
            f"/{self.graph_version}/{urllib.parse.quote(self.phone_number_id)}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": message},
        }

        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, context=self._ssl_context) as response:
                body = response.read().decode("utf-8", "replace")
                try:
                    data = json.loads(body) if body else {}
                except json.JSONDecodeError:
                    data = {}
                message_id = (data.get("messages") or [{}])[0].get("id")
            return ActionResult.ok(
                "I've sent the WhatsApp message.",
                details={"message_id": message_id, "to": recipient},
            )
        except urllib.error.HTTPError as exc:
            detail = self._safe_error_detail(exc)
            logger.warning("WhatsApp request rejected (HTTP %s): %s", exc.code, detail)
            return ActionResult.failure(
                ActionCode.PROVIDER_REJECTED,
                "WhatsApp declined the message, so it was not sent.",
                details={"status": exc.code},
            )
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            logger.exception("WhatsApp request failed: %s", exc)
            return ActionResult.failure(
                ActionCode.EXECUTION_ERROR,
                "I couldn't reach WhatsApp right now, so the message wasn't sent.",
            )

    @staticmethod
    def _safe_error_detail(exc: urllib.error.HTTPError) -> str:
        # Log only a short, provider-neutral detail; never leak tokens.
        try:
            return (exc.read() or b"")[:300].decode("utf-8", "replace")
        except Exception:
            return exc.reason if getattr(exc, "reason", None) else ""

    async def send_text_async(self, to: str, message: str) -> ActionResult:
        """Async twin of :meth:`send_text` (httpx) for route handlers.

        Bounded by the WhatsApp timebox (10 s) and the provider circuit
        breaker; error mapping mirrors the sync path.
        """
        if not self.is_configured():
            return ActionResult.failure(
                ActionCode.NOT_CONFIGURED,
                "WhatsApp isn't configured yet, so I couldn't send the message.",
            )
        if not to or not to.strip():
            return ActionResult.failure(
                ActionCode.MISSING_FIELDS,
                "I don't have a WhatsApp number to send to.",
            )
        if not message or not message.strip():
            return ActionResult.failure(
                ActionCode.MISSING_FIELDS,
                "There's no message content to send.",
            )

        import httpx

        from app.core import resilience

        recipient = to.strip().lstrip("+")
        endpoint = (
            "https://graph.facebook.com"
            f"/{self.graph_version}/{urllib.parse.quote(self.phone_number_id)}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": message},
        }

        async def _call():
            async with httpx.AsyncClient(timeout=settings.WHATSAPP_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    endpoint,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                if resp.status_code >= 400:
                    raise _WhatsAppHTTPError(resp.status_code, resp.text[:300])
                try:
                    data = resp.json() if resp.content else {}
                except ValueError:
                    data = {}
                return (data.get("messages") or [{}])[0].get("id")

        breaker = resilience.get_breaker("whatsapp")
        try:
            message_id = await resilience.timebox(
                resilience.call_with_breaker(breaker, _call),
                settings.WHATSAPP_TIMEOUT_SECONDS,
                "WhatsApp",
            )
            return ActionResult.ok(
                "I've sent the WhatsApp message.",
                details={"message_id": message_id, "to": recipient},
            )
        except _WhatsAppHTTPError as exc:
            # A clean HTTP rejection means the provider answered: healthy,
            # so the breaker resets rather than tripping.
            breaker.on_success()
            logger.warning("WhatsApp request rejected (HTTP %s): %s", exc.code, exc.detail)
            return ActionResult.failure(
                ActionCode.PROVIDER_REJECTED,
                "WhatsApp declined the message, so it was not sent.",
                details={"status": exc.code},
            )
        except (httpx.HTTPError, resilience.ProviderTimeoutError, resilience.CircuitOpenError, OSError) as exc:
            logger.exception("WhatsApp async request failed: %s", exc)
            return ActionResult.failure(
                ActionCode.EXECUTION_ERROR,
                "I couldn't reach WhatsApp right now, so the message wasn't sent.",
            )


class _WhatsAppHTTPError(Exception):
    def __init__(self, code: int, detail: str):
        super().__init__(f"HTTP {code}")
        self.code = code
        self.detail = detail


_whatsapp_instance: WhatsAppConnector | None = None


def get_whatsapp_connector() -> WhatsAppConnector:
    global _whatsapp_instance
    if _whatsapp_instance is None:
        _whatsapp_instance = WhatsAppConnector()
    return _whatsapp_instance


def set_whatsapp_connector(instance: WhatsAppConnector) -> None:
    global _whatsapp_instance
    _whatsapp_instance = instance
