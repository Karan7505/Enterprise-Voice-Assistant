from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.gemini_service import ask_gemini
from app.services.tts_service import generate_speech
from app.services.database_chat_history import add_message

router = APIRouter()

AUDIO_DIR = Path("audio")
DEFAULT_SESSION_ID = "default"


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    audio_url: str


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    add_message("user", request.message, DEFAULT_SESSION_ID)

    reply = ask_gemini(request.message)

    add_message("assistant", reply, DEFAULT_SESSION_ID)

    filename = generate_speech(reply)

    return ChatResponse(
        reply=reply,
        audio_url=f"/audio/{filename}",
    )


@router.get("/audio/{filename}")
def get_audio(filename: str):
    file_path = AUDIO_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        path=file_path,
        media_type="audio/mpeg",
        filename=filename,
    )