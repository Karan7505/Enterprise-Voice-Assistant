from elevenlabs.client import ElevenLabs
from app.core.config import settings
import uuid
from pathlib import Path

client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)

AUDIO_DIR = Path("audio")
AUDIO_DIR.mkdir(exist_ok=True)

VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # George

def generate_speech(text: str):
    if not settings.ELEVENLABS_API_KEY or settings.ELEVENLABS_API_KEY.startswith("your_"):
        raise ValueError("ELEVENLABS_API_KEY is not configured in .env")

    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = AUDIO_DIR / filename

    audio = client.text_to_speech.convert(
        voice_id=VOICE_ID,
        model_id="eleven_multilingual_v2",
        text=text
    )

    with open(filepath, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    return filename