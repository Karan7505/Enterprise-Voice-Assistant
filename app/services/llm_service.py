"""LLM provider fan-out (async).

Each provider call is bounded by a 10 s timebox, retried up to 3 attempts on
transient failures, and guarded by a per-provider circuit breaker (5
consecutive failures -> open for 60 s). The provider fallback order is
unchanged: OpenRouter -> NVIDIA -> Gemini.
"""

import asyncio
import logging

from openai import AsyncOpenAI
from google import genai
from google.genai.client import AsyncClient as GenAIAsyncClient
from google.genai import types
from google.genai.errors import ClientError

from app.core import resilience
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


def unique_models(*models: str) -> list[str]:
    return list(dict.fromkeys(model for model in models if model))


def _retry_on():
    return (
        asyncio.TimeoutError,
        resilience.ProviderTimeoutError,
        ConnectionError,
    )


@resilience.async_retries(settings.LLM_MAX_RETRIES, _retry_on())
async def _openrouter_attempt(client, model: str, prompt: str) -> str:
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
    except Exception:
        # Retry once without strict json mode if the model rejects it.
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
    return response.choices[0].message.content


async def generate_with_openrouter(prompt: str) -> str:
    key = settings.OPENROUTER_API_KEY
    models_to_try = unique_models(
        settings.OPENROUTER_MODEL,
        "google/gemini-2.0-flash-001",
        "meta-llama/llama-3.3-70b-instruct",
    )
    last_err: Exception | None = None

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        default_headers={
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": settings.FRONTEND_URL,
            "X-Title": "Enterprise Voice Assistant",
        },
    )

    for model in models_to_try:
        try:
            return await resilience.timebox(
                resilience.call_with_breaker(
                    resilience.get_breaker("openrouter"), _openrouter_attempt, client, model, prompt
                ),
                settings.LLM_TIMEOUT_SECONDS,
                "OpenRouter",
            )
        except Exception as e:
            last_err = e

    raise last_err or LLMError("OpenRouter request failed")


async def generate_with_nvidia(prompt: str) -> str:
    key = settings.NVIDIA_API_KEY
    client = AsyncOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=key,
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )

    @resilience.async_retries(settings.LLM_MAX_RETRIES, _retry_on())
    async def _attempt() -> str:
        response = await client.chat.completions.create(
            model=settings.NVIDIA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    return await resilience.timebox(
        resilience.call_with_breaker(resilience.get_breaker("nvidia"), _attempt),
        settings.LLM_TIMEOUT_SECONDS,
        "NVIDIA",
    )


async def generate_with_gemini(prompt: str) -> str:
    client = GenAIAsyncClient(api_key=settings.GEMINI_API_KEY)
    models_to_try = ["gemini-flash-latest", "gemini-2.0-flash"]
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
    )
    last_err: Exception | None = None
    for model in models_to_try:
        try:
            res = await resilience.timebox(
                client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                ),
                settings.LLM_TIMEOUT_SECONDS,
                "Gemini",
            )
            return res.text
        except ClientError as e:
            if "404" in str(e):
                continue
            last_err = e
            raise
        except Exception as e:
            last_err = e
    raise last_err or LLMError("Gemini models failed")


async def generate(prompt: str) -> str:
    failed_providers = []

    # Provider 1: OpenRouter
    if settings.OPENROUTER_API_KEY and not settings.OPENROUTER_API_KEY.startswith("your_"):
        try:
            return await generate_with_openrouter(prompt)
        except Exception:
            logger.exception("OpenRouter request failed")
            failed_providers.append("OpenRouter")

    # Provider 2: NVIDIA NIM
    if settings.NVIDIA_API_KEY and not settings.NVIDIA_API_KEY.startswith("your_"):
        try:
            return await generate_with_nvidia(prompt)
        except Exception:
            logger.exception("NVIDIA request failed")
            failed_providers.append("NVIDIA")

    # Provider 3: Direct Google Gemini
    if settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("your_"):
        try:
            return await generate_with_gemini(prompt)
        except Exception:
            logger.exception("Gemini request failed")
            failed_providers.append("Gemini")

    if failed_providers:
        logger.error("All configured LLM providers failed: %s", ", ".join(failed_providers))
        raise LLMError("All configured LLM providers failed")

    logger.error("No LLM API key is configured")
    raise LLMError("No LLM provider is configured")
