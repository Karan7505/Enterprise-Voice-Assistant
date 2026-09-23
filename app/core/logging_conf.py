"""Structured (JSON) logging via structlog, bridged onto stdlib logging.

Every existing ``logging.getLogger(...)`` call in the codebase is bridged
through a ``ProcessorFormatter`` handler, so the whole application — including
third-party emitters — emits one JSON object per line with:

  * ``timestamp`` (ISO-8601 UTC)
  * ``level``, ``event``, ``logger``
  * ``correlation_id`` — bound by the X-Correlation-ID middleware for the
    lifetime of the request (and inherited by worker threads via
    contextvars, so ``asyncio.to_thread`` work stays attributable)
  * any extra key/value passed to the log call

Set ``LOG_FORMAT=console`` for human-readable local output; the default is
``json`` (staging/production).
"""

from __future__ import annotations

import logging
import logging.config
import os
import sys

import structlog

_configured = False


def _shared_processors() -> list:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.UnicodeDecoder(),
    ]


def setup_logging(force: bool = False) -> None:
    """Configure root logging once (idempotent). Call early in startup."""
    global _configured
    if _configured and not force:
        return

    as_json = os.getenv("LOG_FORMAT", "json").strip().lower() != "console"
    renderer = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if as_json
        else structlog.dev.ConsoleRenderer()
    )

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        renderer,
                    ],
                    "foreign_pre_chain": _shared_processors(),
                }
            },
            "handlers": {
                "default": {
                    "level": "INFO",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "json",
                }
            },
            "root": {"level": "INFO", "handlers": ["default"]},
            # The uvicorn access log duplicates the app's own request logging;
            # the app logs requests at the middleware with full context.
            "loggers": {
                "uvicorn.access": {"level": "WARNING", "handlers": ["default"], "propagate": False},
            },
        }
    )

    structlog.configure(
        processors=_shared_processors() + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None):
    """App-facing logger: a structlog logger bound through stdlib, so all
    output flows through the JSON handler and carries request context."""
    if not _configured:
        setup_logging()
    return structlog.get_logger(name)
