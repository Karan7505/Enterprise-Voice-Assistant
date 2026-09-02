import logging

from openai import OpenAI
from google import genai
from google.genai import types
from google.genai.errors import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


def unique_models(*models: str) -> list[str]:
    return list(dict.fromkeys(model for model in models if model))


def generate_with_openrouter(prompt: str) -> str:
    key = settings.OPENROUTER_API_KEY
    models_to_try = unique_models(
        settings.OPENROUTER_MODEL,
        "google/gemini-2.0-flash-001",
        "meta-llama/llama-3.3-70b-instruct",
    )
    last_err = None

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
        default_headers={
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": settings.FRONTEND_URL,
            "X-Title": "Enterprise Voice Assistant",
        },
    )

    for model in models_to_try:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content
        except Exception as e:
            last_err = e
            # Try without strict response_format if model doesn't support json_object mode
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.choices[0].message.content
            except Exception as e2:
                last_err = e2

    raise last_err or LLMError("OpenRouter request failed")


def generate_with_nvidia(prompt: str) -> str:
    key = settings.NVIDIA_API_KEY
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=key,
    )
    response = client.chat.completions.create(
        model=settings.NVIDIA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def generate_with_gemini(prompt: str) -> str:
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    models_to_try = ["gemini-flash-latest", "gemini-2.0-flash"]
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
    )
    for model in models_to_try:
        try:
            res = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            return res.text
        except ClientError as e:
            if "404" in str(e):
                continue
            raise e
    raise LLMError("Gemini models failed")


def generate(prompt: str) -> str:
    failed_providers = []

    # Provider 1: OpenRouter
    if settings.OPENROUTER_API_KEY and not settings.OPENROUTER_API_KEY.startswith("your_"):
        try:
            return generate_with_openrouter(prompt)
        except Exception:
            logger.exception("OpenRouter request failed")
            failed_providers.append("OpenRouter")

    # Provider 2: NVIDIA NIM
    if settings.NVIDIA_API_KEY and not settings.NVIDIA_API_KEY.startswith("your_"):
        try:
            return generate_with_nvidia(prompt)
        except Exception:
            logger.exception("NVIDIA request failed")
            failed_providers.append("NVIDIA")

    # Provider 3: Direct Google Gemini
    if settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("your_"):
        try:
            return generate_with_gemini(prompt)
        except Exception:
            logger.exception("Gemini request failed")
            failed_providers.append("Gemini")

    if failed_providers:
        logger.error("All configured LLM providers failed: %s", ", ".join(failed_providers))
        raise LLMError("All configured LLM providers failed")

    logger.error("No LLM API key is configured")
    raise LLMError("No LLM provider is configured")
