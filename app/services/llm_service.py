from google import genai
from google.genai import types
from google.genai.errors import ClientError

from app.core.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)

PRIMARY_MODEL = "gemini-flash-latest"
FALLBACK_MODEL = "gemini-2.0-flash"


class LLMError(Exception):
    pass


def generate(prompt: str) -> str:
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.startswith("your_"):
        raise LLMError(
            "GEMINI_API_KEY is missing or invalid. Please add your Gemini API key to the .env file."
        )

    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]
    last_error = None
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
    )

    for model in models_to_try:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            return response.text
        except ClientError as e:
            last_error = e
            if "404" in str(e):
                continue
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                raise LLMError(f"Gemini API quota exceeded: {e}")
            raise LLMError(str(e))
        except Exception as e:
            last_error = e
            raise LLMError(str(e))

    raise LLMError(f"Failed to generate response: {last_error}")