import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Always resolve configuration relative to the repository, not the command's
# working directory. In local development, a checked-out project's root .env
# is intentionally authoritative over inherited shell/session variables.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ENV_FILE = PROJECT_ROOT / ".env"


def load_project_environment(dotenv_path: Path = PROJECT_ENV_FILE) -> bool:
    """Load a project dotenv file with local-development precedence.

    When the root .env exists, its values replace inherited process values
    before Settings is created. A deployment without that file keeps its
    platform-provided process environment unchanged.
    """
    return load_dotenv(dotenv_path=dotenv_path, override=True)


load_project_environment()


def clean_str(val: str | None, default: str = "") -> str:
    if not val:
        return default
    return val.strip().strip('"').strip("'")


def clean_int(val: str | None, default: int, minimum: int | None = None) -> int:
    try:
        parsed = int(clean_str(val, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid integer configuration value %r; using %s", val, default)
        return default

    if minimum is not None and parsed < minimum:
        logger.warning(
            "Configuration value %r is below the minimum %s; using %s",
            val,
            minimum,
            default,
        )
        return default
    return parsed


def clean_float(
    val: str | None,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    try:
        parsed = float(clean_str(val, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid numeric configuration value %r; using %s", val, default)
        return default

    if minimum is not None and parsed < minimum:
        logger.warning(
            "Configuration value %r is below the minimum %s; using %s",
            val,
            minimum,
            default,
        )
        return default
    if maximum is not None and parsed > maximum:
        logger.warning(
            "Configuration value %r is above the maximum %s; using %s",
            val,
            maximum,
            default,
        )
        return default
    return parsed


def clean_bool(val: str | None, default: bool) -> bool:
    normalized = clean_str(val).lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    logger.warning("Invalid boolean configuration value %r; using %s", val, default)
    return default


def clean_origins(val: str | None, default: str) -> list[str]:
    origins = [origin.strip().rstrip("/") for origin in clean_str(val).split(",")]
    return [origin for origin in origins if origin] or [default.rstrip("/")]


DEFAULT_TTS_INSTRUCTIONS = (
    "Speak in a warm, calm, confident, slightly deep male voice with a clear neutral "
    "international English accent. Use a natural conversational cadence at a medium "
    "pace, with subtle sophistication and natural pauses. Sound professional and "
    "composed, never robotic, announcer-like, overly cheerful, or bass-heavy."
)


class Settings:
    # Frontend / deployment
    FRONTEND_URL: str = clean_str(os.getenv("FRONTEND_URL"), "http://localhost:5173").rstrip("/")
    CORS_ORIGINS: list[str] = clean_origins(
        os.getenv("CORS_ORIGINS"),
        FRONTEND_URL,
    )

    # OpenRouter API
    OPENROUTER_API_KEY: str = clean_str(os.getenv("OPENROUTER_API_KEY"))
    OPENROUTER_MODEL: str = clean_str(os.getenv("OPENROUTER_MODEL"), "google/gemini-2.0-flash-001")

    # NVIDIA NIM API
    NVIDIA_API_KEY: str = clean_str(os.getenv("NVIDIA_API_KEY"))
    NVIDIA_MODEL: str = clean_str(os.getenv("NVIDIA_MODEL"), "meta/llama-3.3-70b-instruct")

    # Google Gemini API
    GEMINI_API_KEY: str = clean_str(os.getenv("GEMINI_API_KEY"))

    # TTS / Speech Synthesis
    ELEVENLABS_API_KEY: str = clean_str(os.getenv("ELEVENLABS_API_KEY"))
    ELEVENLABS_VOICE_ID: str = clean_str(
        os.getenv("ELEVENLABS_VOICE_ID"),
        "myFdf83MJZVXe8yKeA6H",
    )
    ELEVENLABS_MODEL_ID: str = clean_str(
        os.getenv("ELEVENLABS_MODEL_ID"),
        "eleven_multilingual_v2",
    )
    ELEVENLABS_STABILITY: float = clean_float(
        os.getenv("ELEVENLABS_STABILITY"),
        default=0.62,
        minimum=0.0,
        maximum=1.0,
    )
    ELEVENLABS_SIMILARITY_BOOST: float = clean_float(
        os.getenv("ELEVENLABS_SIMILARITY_BOOST"),
        default=0.78,
        minimum=0.0,
        maximum=1.0,
    )
    ELEVENLABS_STYLE: float = clean_float(
        os.getenv("ELEVENLABS_STYLE"),
        default=0.08,
        minimum=0.0,
        maximum=1.0,
    )
    ELEVENLABS_USE_SPEAKER_BOOST: bool = clean_bool(
        os.getenv("ELEVENLABS_USE_SPEAKER_BOOST"),
        default=True,
    )
    ELEVENLABS_SPEED: float = clean_float(
        os.getenv("ELEVENLABS_SPEED"),
        default=1.0,
        minimum=0.7,
        maximum=1.2,
    )

    # Optional OpenAI-compatible audio/speech endpoint.
    TTS_API_KEY: str = clean_str(os.getenv("TTS_API_KEY"))
    TTS_BASE_URL: str = clean_str(os.getenv("TTS_BASE_URL"))
    TTS_MODEL: str = clean_str(os.getenv("TTS_MODEL"), "gpt-4o-mini-tts")
    TTS_VOICE: str = clean_str(os.getenv("TTS_VOICE"), "ash")
    TTS_SPEED: float = clean_float(
        os.getenv("TTS_SPEED"),
        default=1.0,
        minimum=0.25,
        maximum=4.0,
    )
    TTS_INSTRUCTIONS: str = clean_str(
        os.getenv("TTS_INSTRUCTIONS"),
        DEFAULT_TTS_INSTRUCTIONS,
    )

    # Chat context window
    MAX_HISTORY_MESSAGES: int = clean_int(
        os.getenv("MAX_HISTORY_MESSAGES"),
        default=10,
        minimum=0,
    )

    # Generated audio retention
    AUDIO_MAX_AGE_SECONDS: int = clean_int(
        os.getenv("AUDIO_MAX_AGE_SECONDS"),
        default=3600,
        minimum=0,
    )

    # --- Connectors (modular business-system layer) ---
    # CRM: a reference directory loaded from a JSON array in the environment.
    # Swap for a live CRM provider by overriding get_crm(); no core changes.
    CRM_PROVIDER: str = clean_str(os.getenv("CRM_PROVIDER"), "directory")
    CRM_CONTACTS: str = clean_str(os.getenv("CRM_CONTACTS"))

    # WhatsApp Business (Meta Cloud API). Never expose to the frontend.
    WA_TOKEN: str = clean_str(os.getenv("WA_TOKEN"))
    WA_PHONE_NUMBER_ID: str = clean_str(os.getenv("WA_PHONE_NUMBER_ID"))
    WA_GRAPH_VERSION: str = clean_str(os.getenv("WA_GRAPH_VERSION"), "v19.0")

    # Email (any SMTP provider: Gmail, Microsoft/Outlook, custom relay).
    EMAIL_HOST: str = clean_str(os.getenv("EMAIL_HOST"))
    EMAIL_PORT: int = clean_int(os.getenv("EMAIL_PORT"), default=587, minimum=1)
    EMAIL_USERNAME: str = clean_str(os.getenv("EMAIL_USERNAME"))
    EMAIL_PASSWORD: str = clean_str(os.getenv("EMAIL_PASSWORD"))
    EMAIL_USE_TLS: bool = clean_bool(os.getenv("EMAIL_USE_TLS"), default=True)


settings = Settings()

# Startup provider detection logging
active_llm = []
if settings.OPENROUTER_API_KEY and not settings.OPENROUTER_API_KEY.startswith("your_"):
    active_llm.append(f"OpenRouter ({settings.OPENROUTER_MODEL})")
if settings.NVIDIA_API_KEY and not settings.NVIDIA_API_KEY.startswith("your_"):
    active_llm.append(f"NVIDIA ({settings.NVIDIA_MODEL})")
if settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("your_"):
    active_llm.append("Google Gemini")

if active_llm:
    print(f"[LLM CONFIG] Active Provider(s): {', '.join(active_llm)}")
else:
    print("[CONFIG WARNING] No LLM API Key detected in .env! (Add OPENROUTER_API_KEY, NVIDIA_API_KEY, or GEMINI_API_KEY)")

active_tts = []
if settings.ELEVENLABS_API_KEY and not settings.ELEVENLABS_API_KEY.startswith("your_"):
    active_tts.append("ElevenLabs")
if settings.TTS_API_KEY and not settings.TTS_API_KEY.startswith("your_"):
    active_tts.append("Custom OpenAI-compatible TTS")
active_tts.append("gTTS (Free Fallback)")

print(f"[TTS CONFIG] Active Audio Engine(s): {', '.join(active_tts)}")

# Connector availability (credentials are never printed, only configured/not).
active_connectors = []
if settings.CRM_CONTACTS:
    active_connectors.append("CRM (directory)")
if settings.WA_TOKEN and settings.WA_PHONE_NUMBER_ID:
    active_connectors.append("WhatsApp")
if settings.EMAIL_HOST and settings.EMAIL_USERNAME:
    active_connectors.append("Email (SMTP)")
if active_connectors:
    print(f"[CONNECTOR CONFIG] Active Connector(s): {', '.join(active_connectors)}")
else:
    print("[CONNECTOR CONFIG] No connectors configured yet (CRM/WhatsApp/Email).")
