"""Modular connector layer.

External business systems plug in here, behind stable interfaces, so JARVIS
core (chat, voice, STT, LLM, memory, TTS, persistence) never touches a
provider directly.

    JARVIS Core
        |
        +-- CRM connector        (resolve people/groups -> contact details)
        +-- WhatsApp connector   (send_text via WhatsApp Cloud API)
        +-- Email connector      (send via SMTP)

``orchestrator.execute_action`` is the single routing entry point.
"""

from app.connectors.base import ActionCode, ActionResult
from app.connectors.crm_connector import BaseCRM, Contact, DirectoryCRM, get_crm, set_crm
from app.connectors.email_connector import EmailConnector, get_email_connector, set_email_connector
from app.connectors.orchestrator import BusinessAction, SUPPORTED_ACTIONS, execute_action
from app.connectors.whatsapp_connector import (
    WhatsAppConnector,
    get_whatsapp_connector,
    set_whatsapp_connector,
)

__all__ = [
    "ActionCode",
    "ActionResult",
    "BaseCRM",
    "Contact",
    "DirectoryCRM",
    "get_crm",
    "set_crm",
    "EmailConnector",
    "get_email_connector",
    "set_email_connector",
    "BusinessAction",
    "SUPPORTED_ACTIONS",
    "execute_action",
    "WhatsAppConnector",
    "get_whatsapp_connector",
    "set_whatsapp_connector",
]
