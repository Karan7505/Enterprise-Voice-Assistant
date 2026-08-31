from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.session_service import (
    process_message,
    clear_session,
    clear_chat_history,
    clear_memory_data,
    get_session,
)
from app.services.memory_service import get_all_memories
from app.services.database_chat_history import get_messages
from app.services.llm_service import LLMError
from app.services.tts_service import generate_speech
from app.core.config import active_llm, active_tts

router = APIRouter()

AUDIO_DIR = Path("audio")
DEFAULT_SESSION_ID = "default"


class ChatRequest(BaseModel):
    message: str
    session_id: str = DEFAULT_SESSION_ID


class ChatResponse(BaseModel):
    reply: str
    audio_url: str
    memories: dict


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    session_id = request.session_id or DEFAULT_SESSION_ID
    try:
        reply = process_message(
            request.message,
            session_id,
        )
    except LLMError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        )

    try:
        filename = generate_speech(reply)
        audio_url = f"/audio/{filename}"
    except Exception as e:
        print(f"TTS generation error: {e}")
        audio_url = ""

    memories = get_all_memories(session_id)

    return ChatResponse(
        reply=reply,
        audio_url=audio_url,
        memories=memories,
    )


@router.get("/memories")
def memories(session_id: str = DEFAULT_SESSION_ID):
    return {"memories": get_all_memories(session_id)}


@router.get("/history")
def history(session_id: str = DEFAULT_SESSION_ID):
    messages = get_messages(session_id)
    return {
        "messages": [
            {
                "sender": "You" if msg.role == "user" else "AI",
                "text": msg.content,
            }
            for msg in messages
        ]
    }


@router.post("/clear-chat")
def clear_chat_route(session_id: str = DEFAULT_SESSION_ID):
    clear_chat_history(session_id)
    return {"status": "chat_cleared", "session_id": session_id}


@router.post("/clear-memories")
def clear_memories_route(session_id: str = DEFAULT_SESSION_ID):
    clear_memory_data(session_id)
    return {"status": "memories_cleared", "session_id": session_id}


@router.post("/clear")
def clear(session_id: str = DEFAULT_SESSION_ID):
    clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}



@router.get("/status")
def status():
    return {
        "status": "online",
        "llm_engine": active_llm[0] if active_llm else "None configured",
        "llm_providers": active_llm,
        "tts_engine": active_tts[0] if active_tts else "None configured",
        "tts_providers": active_tts,
    }


@router.get("/audio/{filename}")
def get_audio(filename: str):
    file_path = AUDIO_DIR / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Audio file not found",
        )

    return FileResponse(
        path=file_path,
        media_type="audio/mpeg",
        filename=filename,
    )