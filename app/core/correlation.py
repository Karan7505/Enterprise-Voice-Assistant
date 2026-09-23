"""Request correlation IDs (blueprint Change 6).

Every HTTP request gets an ``X-Correlation-ID``: a value supplied by the
client/gateway is honored (so upstream infrastructure can trace through us);
otherwise a fresh id is generated. The id is bound into the structlog
contextvars for the duration of the request — every log line emitted while
handling it (including work offloaded to ``asyncio.to_thread``, which copies
the current context) carries ``correlation_id`` — and echoed back in the
response headers so clients can reference it in support requests.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

HEADER = "X-Correlation-ID"
MAX_LENGTH = 64

logger = structlog.get_logger(__name__)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(HEADER, "")
        # Only accept sane upstream ids; never trust arbitrary payloads.
        if incoming and len(incoming) <= MAX_LENGTH and all(
            c.isalnum() or c in "-._:" for c in incoming
        ):
            correlation_id = incoming
        else:
            correlation_id = uuid.uuid4().hex

        request.state.correlation_id = correlation_id
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
        finally:
            # A downstream exception leaves `response` unset: still log the
            # attempt (as a 500) and clear context before it propagates.
            duration_ms = (time.perf_counter() - start) * 1000
            status = response.status_code if response is not None else 500
            logger.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=status,
                duration_ms=round(duration_ms, 2),
            )
            structlog.contextvars.clear_contextvars()
        response.headers[HEADER] = correlation_id
        return response
