"""Email connector.

Sends outbound email through a standard SMTP transport (Gmail, Outlook/Microsoft,
or any SMTP provider) using only the Python standard library. The provider is
chosen entirely by configuration, so JARVIS core is not coupled to any one
email service.
"""

from __future__ import annotations

import logging
import smtplib
import socket
from email.message import EmailMessage

from app.connectors.base import ActionCode, ActionResult
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailConnector:
    """Sends email via SMTP. Recipients may be a single address or a list
    (used for group sends resolved from the CRM)."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool | None = None,
    ):
        self.host = (host if host is not None else settings.EMAIL_HOST) or ""
        self.port = port if port is not None else settings.EMAIL_PORT
        self.username = username if username is not None else settings.EMAIL_USERNAME
        self.password = password if password is not None else settings.EMAIL_PASSWORD
        self.use_tls = use_tls if use_tls is not None else settings.EMAIL_USE_TLS

    def is_configured(self) -> bool:
        return bool(self.host and self.username)

    def send(
        self,
        to: str | list[str],
        subject: str,
        body: str,
    ) -> ActionResult:
        recipients = [addr.strip() for addr in (to if isinstance(to, list) else [to])]
        recipients = [addr for addr in recipients if addr]

        if not self.is_configured():
            return ActionResult.failure(
                ActionCode.NOT_CONFIGURED,
                "Email isn't configured yet, so I couldn't send that.",
            )
        if not recipients:
            return ActionResult.failure(
                ActionCode.MISSING_FIELDS,
                "I don't have a valid email address to send to.",
            )
        if subject is None or not subject.strip():
            subject = "Message from JARVIS"
        if not body or not body.strip():
            return ActionResult.failure(
                ActionCode.MISSING_FIELDS,
                "There's no email content to send.",
            )

        message = EmailMessage()
        message["From"] = self.username
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject
        message.set_content(body)

        try:
            if self.use_tls:
                server = smtplib.SMTP(self.host, self.port, timeout=30)
                server.starttls()
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=30)
            with server:
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.send_message(message)
            return ActionResult.ok(
                f"I've emailed {', '.join(recipients)}.",
                details={"to": recipients, "subject": subject},
            )
        except smtplib.SMTPAuthenticationError as exc:
            logger.warning("Email authentication failed: %s", exc.smtp_error)
            return ActionResult.failure(
                ActionCode.PROVIDER_REJECTED,
                "The email service rejected the credentials, so it wasn't sent.",
            )
        except (smtplib.SMTPException, socket.error, TimeoutError, OSError) as exc:
            logger.exception("Email send failed: %s", exc)
            return ActionResult.failure(
                ActionCode.EXECUTION_ERROR,
                "I couldn't send the email right now. Please try again.",
            )

    def _build_message(self, recipients: list[str], subject: str, body: str) -> "EmailMessage":
        message = EmailMessage()
        message["From"] = self.username
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject
        message.set_content(body)
        return message

    async def send_async(
        self,
        to: str | list[str],
        subject: str,
        body: str,
    ) -> ActionResult:
        """Async twin of :meth:`send` (aiosmtplib) for route handlers.

        Bounded by the SMTP timebox (10 s) and the provider circuit breaker.
        """
        import aiosmtplib

        from app.core import resilience

        recipients = [addr.strip() for addr in (to if isinstance(to, list) else [to])]
        recipients = [addr for addr in recipients if addr]

        if not self.is_configured():
            return ActionResult.failure(
                ActionCode.NOT_CONFIGURED,
                "Email isn't configured yet, so I couldn't send that.",
            )
        if not recipients:
            return ActionResult.failure(
                ActionCode.MISSING_FIELDS,
                "I don't have a valid email address to send to.",
            )
        if subject is None or not subject.strip():
            subject = "Message from JARVIS"
        if not body or not body.strip():
            return ActionResult.failure(
                ActionCode.MISSING_FIELDS,
                "There's no email content to send.",
            )

        message = self._build_message(recipients, subject, body)
        breaker = resilience.get_breaker("smtp")

        async def _send():
            try:
                async with aiosmtplib.SMTP(
                    hostname=self.host,
                    port=self.port,
                    start_tls=self.use_tls,
                    timeout=settings.SMTP_TIMEOUT_SECONDS,
                ) as server:
                    if self.username and self.password:
                        await server.login(self.username, self.password)
                    await server.send(message)
            except aiosmtplib.SMTPAuthenticationError as exc:
                raise _SMTPAuthError(str(exc.smtp_error if hasattr(exc, "smtp_error") else exc)) from exc

        try:
            await resilience.timebox(
                resilience.call_with_breaker(breaker, _send),
                settings.SMTP_TIMEOUT_SECONDS,
                "SMTP",
            )
            return ActionResult.ok(
                f"I've emailed {', '.join(recipients)}.",
                details={"to": recipients, "subject": subject},
            )
        except _SMTPAuthError as exc:
            breaker.on_success()  # the server answered; auth failure is not an outage
            logger.warning("Email authentication failed: %s", exc)
            return ActionResult.failure(
                ActionCode.PROVIDER_REJECTED,
                "The email service rejected the credentials, so it wasn't sent.",
            )
        except (aiosmtplib.SMTPException, socket.error, TimeoutError,
                resilience.ProviderTimeoutError, resilience.CircuitOpenError, OSError) as exc:
            logger.exception("Email async send failed: %s", exc)
            return ActionResult.failure(
                ActionCode.EXECUTION_ERROR,
                "I couldn't send the email right now. Please try again.",
            )


class _SMTPAuthError(Exception):
    """Authentication rejected by the SMTP server (provider answered)."""


_email_instance: EmailConnector | None = None


def get_email_connector() -> EmailConnector:
    global _email_instance
    if _email_instance is None:
        _email_instance = EmailConnector()
    return _email_instance


def set_email_connector(instance: EmailConnector) -> None:
    global _email_instance
    _email_instance = instance
