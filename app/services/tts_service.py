import asyncio
import logging
import time
import uuid
from pathlib import Path

from app.core import resilience
from app.core.config import settings

AUDIO_DIR = Path(settings.AUDIO_DIR).resolve()
logger = logging.getLogger("uvicorn.error")

# Default: delete audio files older than 1 hour (3600 seconds)
AUDIO_MAX_AGE_SECONDS = settings.AUDIO_MAX_AGE_SECONDS
INSTRUCTION_CAPABLE_TTS_MODEL_PREFIXES = ("gpt-4o-mini-tts",)


def ensure_audio_directory():
    AUDIO_DIR.mkdir(exist_ok=True)


def cleanup_partial_audio_file(filepath: Path):
    try:
        filepath.unlink(missing_ok=True)
    except OSError:
        logger.exception("Failed to remove partial audio file %s", filepath.name)


def cleanup_old_audio_files(max_age_seconds: int = AUDIO_MAX_AGE_SECONDS):
    """
    Deletes .mp3 files in the audio directory that are older than max_age_seconds.
    Keeps files temporarily for browser playback while preventing disk buildup.
    """
    now = time.time()
    if not AUDIO_DIR.exists():
        return

    for file in AUDIO_DIR.glob("*.mp3"):
        try:
            if file.is_file():
                file_age = now - file.stat().st_mtime
                if file_age > max_age_seconds:
                    file.unlink(missing_ok=True)
        except OSError:
            logger.exception("Failed to clean up audio file %s", file.name)


def _supports_tts_instructions(model: str) -> bool:
    normalized_model = model.strip().lower()
    return normalized_model.startswith(INSTRUCTION_CAPABLE_TTS_MODEL_PREFIXES)


def _build_openai_speech_options(
    model: str,
    voice: str,
    speed: float,
    instructions: str = "",
) -> dict:
    options = {
        "model": model,
        "voice": voice,
        "speed": speed,
    }
    if instructions and _supports_tts_instructions(model):
        options["instructions"] = instructions
    return options


def generate_speech_elevenlabs(text: str, filepath: Path):
    from elevenlabs import VoiceSettings
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)

    audio = client.text_to_speech.convert(
        voice_id=settings.ELEVENLABS_VOICE_ID,
        model_id=settings.ELEVENLABS_MODEL_ID,
        text=text,
        voice_settings=VoiceSettings(
            stability=settings.ELEVENLABS_STABILITY,
            similarity_boost=settings.ELEVENLABS_SIMILARITY_BOOST,
            style=settings.ELEVENLABS_STYLE,
            use_speaker_boost=settings.ELEVENLABS_USE_SPEAKER_BOOST,
            speed=settings.ELEVENLABS_SPEED,
        ),
    )
    with open(filepath, "wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)


def generate_speech_openai_tts(text: str, filepath: Path):
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.TTS_API_KEY,
        base_url=settings.TTS_BASE_URL if settings.TTS_BASE_URL else None,
    )
    response = client.audio.speech.create(
        input=text,
        **_build_openai_speech_options(
            model=settings.TTS_MODEL,
            voice=settings.TTS_VOICE,
            speed=settings.TTS_SPEED,
            instructions=settings.TTS_INSTRUCTIONS,
        ),
    )
    response.stream_to_file(filepath)


def generate_speech_gtts(text: str, filepath: Path):
    from gtts import gTTS
    tts = gTTS(text=text, lang="en", slow=False)
    tts.save(str(filepath))


def generate_speech(text: str) -> str:
    ensure_audio_directory()

    # Automatically clean up audio files older than 1 hour (3600 seconds)
    cleanup_old_audio_files()

    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = AUDIO_DIR / filename

    # 1. ElevenLabs (if key present)
    if settings.ELEVENLABS_API_KEY and not settings.ELEVENLABS_API_KEY.startswith("your_"):
        try:
            logger.info(
                "TTS attempt provider=ElevenLabs model=%s voice=%s",
                settings.ELEVENLABS_MODEL_ID,
                settings.ELEVENLABS_VOICE_ID,
            )
            generate_speech_elevenlabs(text, filepath)
            logger.info(
                "TTS success provider=ElevenLabs model=%s voice=%s file=%s",
                settings.ELEVENLABS_MODEL_ID,
                settings.ELEVENLABS_VOICE_ID,
                filename,
            )
            return filename
        except Exception:
            cleanup_partial_audio_file(filepath)
            logger.exception(
                "TTS failure provider=ElevenLabs model=%s voice=%s",
                settings.ELEVENLABS_MODEL_ID,
                settings.ELEVENLABS_VOICE_ID,
            )

    # 2. Custom / OpenAI-compatible TTS (if key present)
    if settings.TTS_API_KEY and not settings.TTS_API_KEY.startswith("your_"):
        try:
            logger.info(
                "TTS attempt provider=Custom/OpenAI-compatible model=%s voice=%s",
                settings.TTS_MODEL,
                settings.TTS_VOICE,
            )
            generate_speech_openai_tts(text, filepath)
            logger.info(
                "TTS success provider=Custom/OpenAI-compatible model=%s voice=%s file=%s",
                settings.TTS_MODEL,
                settings.TTS_VOICE,
                filename,
            )
            return filename
        except Exception:
            cleanup_partial_audio_file(filepath)
            logger.exception(
                "TTS failure provider=Custom/OpenAI-compatible model=%s voice=%s",
                settings.TTS_MODEL,
                settings.TTS_VOICE,
            )

    # 3. Free gTTS fallback
    try:
        logger.info("TTS attempt provider=gTTS model=gtts voice=en-default")
        generate_speech_gtts(text, filepath)
        logger.info(
            "TTS success provider=gTTS model=gtts voice=en-default file=%s",
            filename,
        )
        return filename
    except Exception:
        cleanup_partial_audio_file(filepath)
        logger.exception("gTTS fallback failed")
        raise


# --- async provider paths (route handlers) -----------------------------------
#
# The sync functions above remain for direct/legacy use and unit tests; the
# HTTP voice path uses these so provider latency never blocks the event loop.
# Each is bounded by the 15 s TTS timebox, retried up to 2 attempts, and
# guarded by a per-provider circuit breaker.


def _tts_retry_on():
    return (
        asyncio.TimeoutError,
        resilience.ProviderTimeoutError,
        ConnectionError,
    )


@resilience.async_retries(settings.TTS_MAX_RETRIES, _tts_retry_on())
async def generate_speech_elevenlabs_async(text: str, filepath: Path):
    from elevenlabs import VoiceSettings
    from elevenlabs.client import AsyncElevenLabs

    client = AsyncElevenLabs(
        api_key=settings.ELEVENLABS_API_KEY,
        httpx_args={"timeout": settings.TTS_TIMEOUT_SECONDS},
    )
    audio = await client.text_to_speech.convert(
        voice_id=settings.ELEVENLABS_VOICE_ID,
        model_id=settings.ELEVENLABS_MODEL_ID,
        text=text,
        voice_settings=VoiceSettings(
            stability=settings.ELEVENLABS_STABILITY,
            similarity_boost=settings.ELEVENLABS_SIMILARITY_BOOST,
            style=settings.ELEVENLABS_STYLE,
            use_speaker_boost=settings.ELEVENLABS_USE_SPEAKER_BOOST,
            speed=settings.ELEVENLABS_SPEED,
        ),
    )
    await asyncio.to_thread(_write_chunks, audio, filepath)


def _write_chunks(stream, filepath: Path):
    with open(filepath, "wb") as f:
        for chunk in stream:
            if chunk:
                f.write(chunk)


@resilience.async_retries(settings.TTS_MAX_RETRIES, _tts_retry_on())
async def generate_speech_openai_tts_async(text: str, filepath: Path):
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.TTS_API_KEY,
        base_url=settings.TTS_BASE_URL if settings.TTS_BASE_URL else None,
        timeout=settings.TTS_TIMEOUT_SECONDS,
    )
    response = await client.audio.speech.create(
        input=text,
        **_build_openai_speech_options(
            model=settings.TTS_MODEL,
            voice=settings.TTS_VOICE,
            speed=settings.TTS_SPEED,
            instructions=settings.TTS_INSTRUCTIONS,
        ),
    )
    # stream_to_file is blocking; run it off the loop.
    await asyncio.to_thread(response.stream_to_file, filepath)


async def generate_speech_gtts_async(text: str, filepath: Path):
    # gTTS is a small synchronous library with no async client; its network
    # call is bounded by the outer timebox.
    await asyncio.to_thread(generate_speech_gtts, text, filepath)


async def generate_speech_async(text: str) -> str:
    """Async twin of :func:`generate_speech` for route handlers.

    Same provider order (ElevenLabs -> OpenAI-compatible -> gTTS) and the
    same fail-through behavior; each attempt runs under the TTS timebox and
    provider circuit breaker.
    """
    ensure_audio_directory()
    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = AUDIO_DIR / filename
    box = settings.TTS_TIMEOUT_SECONDS

    if settings.ELEVENLABS_API_KEY and not settings.ELEVENLABS_API_KEY.startswith("your_"):
        try:
            logger.info("TTS attempt provider=ElevenLabs model=%s voice=%s", settings.ELEVENLABS_MODEL_ID, settings.ELEVENLABS_VOICE_ID)
            await resilience.timebox(
                resilience.call_with_breaker(
                    resilience.get_breaker("elevenlabs"),
                    generate_speech_elevenlabs_async, text, filepath,
                ),
                box, "ElevenLabs TTS",
            )
            logger.info("TTS success provider=ElevenLabs file=%s", filename)
            return filename
        except Exception:
            cleanup_partial_audio_file(filepath)
            logger.exception("TTS failure provider=ElevenLabs")

    if settings.TTS_API_KEY and not settings.TTS_API_KEY.startswith("your_"):
        try:
            logger.info("TTS attempt provider=Custom/OpenAI-compatible model=%s voice=%s", settings.TTS_MODEL, settings.TTS_VOICE)
            await resilience.timebox(
                resilience.call_with_breaker(
                    resilience.get_breaker("openai-tts"),
                    generate_speech_openai_tts_async, text, filepath,
                ),
                box, "OpenAI TTS",
            )
            logger.info("TTS success provider=Custom/OpenAI-compatible file=%s", filename)
            return filename
        except Exception:
            cleanup_partial_audio_file(filepath)
            logger.exception("TTS failure provider=Custom/OpenAI-compatible")

    try:
        logger.info("TTS attempt provider=gTTS model=gtts voice=en-default")
        await resilience.timebox(
            resilience.call_with_breaker(
                resilience.get_breaker("gtts"),
                generate_speech_gtts_async, text, filepath,
            ),
            box, "gTTS",
        )
        logger.info("TTS success provider=gTTS file=%s", filename)
        return filename
    except Exception:
        cleanup_partial_audio_file(filepath)
        logger.exception("gTTS fallback failed")
        raise
