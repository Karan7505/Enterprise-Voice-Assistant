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


_email_instance: EmailConnector | None = None


def get_email_connector() -> EmailConnector:
    global _email_instance
    if _email_instance is None:
        _email_instance = EmailConnector()
    return _email_instance


def set_email_connector(instance: EmailConnector) -> None:
    global _email_instance
    _email_instance = instance
