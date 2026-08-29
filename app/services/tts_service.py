import uuid
from pathlib import Path
from app.core.config import settings

AUDIO_DIR = Path("audio")
AUDIO_DIR.mkdir(exist_ok=True)


def generate_speech_elevenlabs(text: str, filepath: Path):
    from elevenlabs.client import ElevenLabs
    client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
    voice_id = "JBFqnCBsd6RMkjVDRZzb"  # George

    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        model_id="eleven_multilingual_v2",
        text=text,
    )
    with open(filepath, "wb") as f:
        for chunk in audio:
            f.write(chunk)


def generate_speech_bytez(text: str, filepath: Path):
    from openai import OpenAI
    client = OpenAI(
        api_key=settings.BYTEZ_API_KEY,
        base_url="https://api.bytez.com/v1",
    )
    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
    )
    response.stream_to_file(filepath)


def generate_speech_openai_tts(text: str, filepath: Path):
    from openai import OpenAI
    client = OpenAI(
        api_key=settings.TTS_API_KEY or settings.OPENROUTER_API_KEY or settings.NVIDIA_API_KEY,
        base_url=settings.TTS_BASE_URL if settings.TTS_BASE_URL else None,
    )
    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
    )
    response.stream_to_file(filepath)


def generate_speech_gtts(text: str, filepath: Path):
    from gtts import gTTS
    tts = gTTS(text=text, lang="en", slow=False)
    tts.save(str(filepath))


def generate_speech(text: str) -> str:
    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = AUDIO_DIR / filename

    # 1. ElevenLabs (if key present)
    if settings.ELEVENLABS_API_KEY and not settings.ELEVENLABS_API_KEY.startswith("your_"):
        try:
            generate_speech_elevenlabs(text, filepath)
            return filename
        except Exception as e:
            print(f"[ElevenLabs TTS Error]: {e}")

    # 2. Bytez.com Audio API (if key present)
    if settings.BYTEZ_API_KEY and not settings.BYTEZ_API_KEY.startswith("your_"):
        try:
            generate_speech_bytez(text, filepath)
            return filename
        except Exception as e:
            print(f"[Bytez.com TTS Error]: {e}")

    # 3. Custom TTS / OpenAI Compatible Audio API (if key present)
    if settings.TTS_API_KEY and not settings.TTS_API_KEY.startswith("your_"):
        try:
            generate_speech_openai_tts(text, filepath)
            return filename
        except Exception as e:
            print(f"[Custom Audio API TTS Error]: {e}")

    # 4. Free gTTS Fallback (Always works, zero cost!)
    try:
        generate_speech_gtts(text, filepath)
        return filename
    except Exception as e:
        print(f"[gTTS Fallback Error]: {e}")
        raise e