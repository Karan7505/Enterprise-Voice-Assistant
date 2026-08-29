from dotenv import load_dotenv
import os

load_dotenv()


def clean_str(val: str, default: str = "") -> str:
    if not val:
        return default
    return val.strip().strip('"').strip("'")


class Settings:
    # OpenRouter API
    OPENROUTER_API_KEY: str = clean_str(os.getenv("OPENROUTER_API_KEY"))
    OPENROUTER_MODEL: str = clean_str(os.getenv("OPENROUTER_MODEL"), "google/gemini-2.0-flash-001")

    # Bytez.com API
    BYTEZ_API_KEY: str = clean_str(os.getenv("BYTEZ_API_KEY"))
    BYTEZ_MODEL: str = clean_str(os.getenv("BYTEZ_MODEL"), "meta-llama/Llama-3.3-70B-Instruct")

    # NVIDIA NIM API
    NVIDIA_API_KEY: str = clean_str(os.getenv("NVIDIA_API_KEY"))
    NVIDIA_MODEL: str = clean_str(os.getenv("NVIDIA_MODEL"), "meta/llama-3.3-70b-instruct")

    # Google Gemini API
    GEMINI_API_KEY: str = clean_str(os.getenv("GEMINI_API_KEY"))

    # TTS / Speech Synthesis Keys
    ELEVENLABS_API_KEY: str = clean_str(os.getenv("ELEVENLABS_API_KEY"))
    TTS_API_KEY: str = clean_str(os.getenv("TTS_API_KEY"))
    TTS_BASE_URL: str = clean_str(os.getenv("TTS_BASE_URL"))


settings = Settings()

# Startup provider detection logging
active_llm = []
if settings.OPENROUTER_API_KEY and not settings.OPENROUTER_API_KEY.startswith("your_"):
    active_llm.append(f"OpenRouter ({settings.OPENROUTER_MODEL})")
if settings.BYTEZ_API_KEY and not settings.BYTEZ_API_KEY.startswith("your_"):
    active_llm.append(f"Bytez.com ({settings.BYTEZ_MODEL})")
if settings.NVIDIA_API_KEY and not settings.NVIDIA_API_KEY.startswith("your_"):
    active_llm.append(f"NVIDIA ({settings.NVIDIA_MODEL})")
if settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("your_"):
    active_llm.append("Google Gemini")

if active_llm:
    print(f"[LLM CONFIG] Active Provider(s): {', '.join(active_llm)}")
else:
    print("[CONFIG WARNING] No LLM API Key detected in .env! (Add OPENROUTER_API_KEY, BYTEZ_API_KEY, NVIDIA_API_KEY, or GEMINI_API_KEY)")

active_tts = []
if settings.ELEVENLABS_API_KEY and not settings.ELEVENLABS_API_KEY.startswith("your_"):
    active_tts.append("ElevenLabs")
if settings.BYTEZ_API_KEY and not settings.BYTEZ_API_KEY.startswith("your_"):
    active_tts.append("Bytez.com Audio API")
if settings.TTS_API_KEY and not settings.TTS_API_KEY.startswith("your_"):
    active_tts.append("Custom Audio API")
active_tts.append("gTTS (Free Fallback)")

print(f"[TTS CONFIG] Active Audio Engine(s): {', '.join(active_tts)}")