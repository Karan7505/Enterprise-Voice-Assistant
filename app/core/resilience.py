"""Provider resilience: timeboxes, retries, and circuit breakers.

Blueprint values (Change 5):
  timeouts   LLM 10 s / TTS 15 s / CRM 5 s / WhatsApp 10 s / SMTP 10 s
  retries    LLM 3 attempts / TTS 2 attempts
  breaker    fail_max=5 consecutive failures -> open, reset after 60 s

The breaker is per provider name (e.g. "openrouter", "elevenlabs", "crm").
A tripped breaker raises :class:`CircuitOpenError` immediately so a dead
provider stops consuming the thread pool and queueing clients.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.core.config import settings

logger = logging.getLogger(__name__)


class ProviderTimeoutError(Exception):
    """A provider call exceeded its timebox."""


class CircuitOpenError(Exception):
    """The provider's circuit breaker is open; fail fast."""


class CircuitBreaker:
    def __init__(self, name: str, fail_max: int, reset_timeout: float):
        self.name = name
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if time.monotonic() - self._opened_at >= self.reset_timeout:
            return "half-open"
        return "open"

    def before_call(self) -> None:
        current = self.state
        if current == "open":
            raise CircuitOpenError(f"provider '{self.name}' circuit is open")

    def on_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.fail_max:
            if self._opened_at is None:
                logger.warning(
                    "circuit OPEN for '%s' after %d consecutive failures; "
                    "resetting in %.0fs",
                    self.name, self._failures, self.reset_timeout,
                )
            self._opened_at = time.monotonic()

    def trip(self) -> None:
        """Test hook: force the breaker open."""
        self._failures = self.fail_max
        self._opened_at = time.monotonic()


_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(name: str) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(
            name,
            fail_max=settings.CIRCUIT_FAIL_MAX,
            reset_timeout=settings.CIRCUIT_RESET_SECONDS,
        )
    return _breakers[name]


def reset_breakers() -> None:
    """Reset all breakers (used by tests)."""
    _breakers.clear()


async def timebox(coro, seconds: float, name: str):
    """Await ``coro`` bounded by ``seconds``; raise ProviderTimeoutError on overrun."""
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError as exc:
        raise ProviderTimeoutError(f"{name} timed out after {seconds:.0f}s") from exc


async def call_with_breaker(breaker: CircuitBreaker, func, *args, **kwargs):
    """Run ``func(*args, **kwargs)`` (async) under the breaker's open/close rules."""
    breaker.before_call()
    try:
        result = await func(*args, **kwargs)
    except Exception:
        breaker.on_failure()
        raise
    breaker.on_success()
    return result


def async_retries(attempts: int, retry_on):
    """Tenacity decorator factory for async provider calls.

    ``retry_on`` is an exception tuple. No wait between attempts: provider
    latency is already dominated by the timebox, and immediate retries
    maximize the odds of recovering within the request's overall budget.
    """
    from tenacity import (
        before_sleep_log,
        retry,
        retry_if_exception_type,
        stop_after_attempt,
    )

    return retry(
        retry=retry_if_exception_type(retry_on),
        stop=stop_after_attempt(attempts),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
