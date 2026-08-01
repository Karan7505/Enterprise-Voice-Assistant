from google import genai
from google.genai import types
from google.genai.errors import ClientError

from app.core.config import settings
from app.services.database_chat_history import get_messages
from app.services.memory_service import save_memory, get_memory

client = genai.Client(api_key=settings.GEMINI_API_KEY)

MODEL = "gemini-2.0-flash"
DEFAULT_SESSION_ID = "default"


def ask_gemini(prompt: str, session_id: str = DEFAULT_SESSION_ID):
    # -------------------- MOCK MODE --------------------
    if settings.USE_MOCK_AI:
        prompt_lower = prompt.lower()

        # Save memories
        if "my name is " in prompt_lower:
            index = prompt_lower.find("my name is ")
            name = prompt[index + len("my name is "):].strip()
            save_memory("name", name, session_id)
            return f"Nice to meet you, {name}."

        if prompt_lower.startswith("i'm "):
            name = prompt[4:].strip()
            save_memory("name", name, session_id)
            return f"Nice to meet you, {name}."

        if prompt_lower.startswith("i am "):
            value = prompt[5:].strip()

            if "from " in value.lower():
                location = value.split("from", 1)[1].strip()
                save_memory("location", location, session_id)
                return f"I'll remember that you are from {location}."

            return f"Mock AI: {prompt}"

        # Recall memories
        if (
            "what's my name" in prompt_lower
            or "what is my name" in prompt_lower
            or "who am i" in prompt_lower
        ):
            name = get_memory("name", session_id)

            if name:
                return f"Your name is {name}."

            return "I don't know your name yet."

        if (
            "where do i live" in prompt_lower
            or "where am i from" in prompt_lower
        ):
            location = get_memory("location", session_id)

            if location:
                return f"You are from {location}."

            return "I don't know where you're from yet."

        return f"Mock AI: {prompt}"

    # -------------------- REAL GEMINI --------------------
    history = get_messages(session_id)

    contents = []

    for message in history:
        role = "user" if message.role == "user" else "model"

        contents.append(
            types.Content(
                role=role,
                parts=[
                    types.Part.from_text(
                        text=message.content
                    )
                ],
            )
        )

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
        )

        return response.text

    except ClientError as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return (
                "The free Gemini API quota has been reached. "
                "Please wait a little while and try again."
            )

        raise