from google import genai
from google.genai.errors import ClientError

from app.core.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)

MODEL = "gemini-2.0-flash"


class LLMError(Exception):
    pass


def generate(prompt: str) -> str:
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )

        return response.text

    except ClientError as e:
        if (
            "429" in str(e)
            or "RESOURCE_EXHAUSTED" in str(e)
        ):
            raise LLMError(
                "Gemini API quota exceeded."
            )

        raise LLMError(str(e))