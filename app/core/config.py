from dotenv import load_dotenv
import os

load_dotenv()


class Settings:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

    USE_MOCK_AI = os.getenv("USE_MOCK_AI", "false").lower() == "true"


settings = Settings()