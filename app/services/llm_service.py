from openai import OpenAI
from google import genai
from google.genai import types
from google.genai.errors import ClientError

from app.core.config import settings


class LLMError(Exception):
    pass


def generate_with_openrouter(prompt: str) -> str:
    key = settings.OPENROUTER_API_KEY
    models_to_try = [settings.OPENROUTER_MODEL, "google/gemini-2.0-flash-001", "meta-llama/llama-3.3-70b-instruct"]
    last_err = None

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
        default_headers={
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "http://localhost:5173",
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


def generate_with_bytez(prompt: str) -> str:
    key = settings.BYTEZ_API_KEY
    models_to_try = [settings.BYTEZ_MODEL, "meta-llama/Llama-3.3-70B-Instruct", "Qwen/Qwen2.5-7B-Instruct"]
    last_err = None

    client = OpenAI(
        base_url="https://api.bytez.com/v1",
        api_key=key,
        default_headers={
            "Authorization": f"Bearer {key}",
        },
    )

    for model in models_to_try:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except Exception as e:
            last_err = e

    raise last_err or LLMError("Bytez.com request failed")


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
    errors = []

    # Provider 1: OpenRouter
    if settings.OPENROUTER_API_KEY and not settings.OPENROUTER_API_KEY.startswith("your_"):
        try:
            return generate_with_openrouter(prompt)
        except Exception as e:
            print(f"[OpenRouter Error]: {e}")
            errors.append(f"OpenRouter: {e}")

    # Provider 2: Bytez.com
    if settings.BYTEZ_API_KEY and not settings.BYTEZ_API_KEY.startswith("your_"):
        try:
            return generate_with_bytez(prompt)
        except Exception as e:
            print(f"[Bytez.com Error]: {e}")
            errors.append(f"Bytez.com: {e}")

    # Provider 3: NVIDIA NIM
    if settings.NVIDIA_API_KEY and not settings.NVIDIA_API_KEY.startswith("your_"):
        try:
            return generate_with_nvidia(prompt)
        except Exception as e:
            print(f"[NVIDIA Error]: {e}")
            errors.append(f"NVIDIA: {e}")

    # Provider 4: Direct Google Gemini
    if settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("your_"):
        try:
            return generate_with_gemini(prompt)
        except Exception as e:
            print(f"[Gemini Error]: {e}")
            errors.append(f"Gemini: {e}")

    if errors:
        raise LLMError(f"LLM API providers failed: {'; '.join(errors)}")

    raise LLMError(
        "No LLM API Key configured! Please add OPENROUTER_API_KEY, BYTEZ_API_KEY, NVIDIA_API_KEY, or GEMINI_API_KEY to your .env file."
    )