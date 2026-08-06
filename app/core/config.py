from dotenv import load_dotenv
import os

load_dotenv()


class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")


settings = Settings()

# Startup warnings
if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.startswith("your_"):
    print("⚠️  [CONFIG WARNING] GEMINI_API_KEY is not configured in .env!")
    print("   Please create a .env file with: GEMINI_API_KEY=your_actual_key")

if not settings.ELEVENLABS_API_KEY or settings.ELEVENLABS_API_KEY.startswith("your_"):
    print("⚠️  [CONFIG WARNING] ELEVENLABS_API_KEY is not configured in .env.")
    print("   AI voice replies (TTS) will be skipped until key is added.")