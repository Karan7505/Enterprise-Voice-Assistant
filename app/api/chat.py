import asyncio
import logging
from pathlib import Path
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.auth import require_user
from app.services.audio_storage import AudioStoreError, stream_audio, store_audio
from app.services.session_service import (
    process_message,
    clear_session,
    clear_chat_history,
    clear_memory_data,
)
from app.services.memory_service import get_all_memories
from app.services.database_chat_history import get_messages
from app.services.llm_service import LLMError
from app.services.tts_service import generate_speech_async
from app.core.config import active_llm, active_tts, settings
from app.core.database import get_connection
from app.core.rate_limiter import check_rate_limit, client_ip
from app.connectors import SUPPORTED_ACTIONS

router = APIRouter()
logger = logging.getLogger(__name__)

AUDIO_DIR = Path(settings.AUDIO_DIR).resolve()
AUDIO_FILENAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.mp3$")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=settings.MAX_MESSAGE_LENGTH)
    # Preserve the API's historical voice-first behavior for callers that do
    # not yet send a mode. The frontend always sends its mode explicitly.
    response_mode: Literal["text", "voice"] = "voice"


class ChatResponse(BaseModel):
    reply: str
    audio_url: str
    memories: dict


def _own_audio_file(filename: str, session_id: str) -> bool:
    """Return True if the generated audio file belongs to this user session.

    The lookup is deliberately scoped to the caller's session_id, so a file
    stored under another user's key (or a raw S3 path guess) is unreachable
    even though the store itself is shared.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT filename FROM audio_files WHERE filename = ? AND session_id = ?",
            (filename, session_id),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _record_audio_file(filename: str, session_id: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO audio_files (filename, session_id) VALUES (?, ?) "
            "ON CONFLICT (filename) DO UPDATE SET session_id = excluded.session_id",
            (filename, session_id),
        )
        conn.commit()
    finally:
        conn.close()


async def _chat_rate_limited(user: dict = Depends(require_user)) -> dict:
    """Rate-limit ``/chat`` per authenticated user. Runs only over HTTP, so the
    endpoint function stays free of DB access for direct unit tests."""
    allowed, retry = await asyncio.to_thread(
        check_rate_limit,
        "chat", f"user:{user['user_id']}", settings.RATE_LIMIT_CHAT,
        settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="You're sending a little too fast. Please wait a moment.",
            headers={"Retry-After": str(retry)},
        )
    return user


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: dict = Depends(_chat_rate_limited)):
    session_id = user["session_id"]

    # The assistant needs at least one LLM provider. There is no keyless LLM
    # fallback (unlike TTS, which falls back to gTTS), so fail with a clear
    # message instead of an opaque provider error when none is configured.
    if not active_llm:
        raise HTTPException(
            status_code=503,
            detail=(
                "No LLM provider is configured. Add OPENROUTER_API_KEY, "
                "NVIDIA_API_KEY, or GEMINI_API_KEY to the backend .env and restart."
            ),
        )

    try:
        reply = await process_message(
            request.message,
            session_id,
            mode=request.response_mode,
        )
    except LLMError:
        logger.warning("Chat request could not produce a valid LLM response")
        raise HTTPException(
            status_code=503,
            detail="The assistant is temporarily unavailable. Please try again.",
        ) from None

    audio_url = ""
    if request.response_mode == "voice":
        try:
            filename = await generate_speech_async(reply)
            if filename:
                # Persist into the audio store (S3 in staging/production). A
                # selected-but-unreachable store is a 503, not a silent drop.
                try:
                    await asyncio.to_thread(
                        store_audio, session_id, filename, AUDIO_DIR / filename
                    )
                except AudioStoreError:
                    logger.exception("audio store unavailable; voice reply cannot be served")
                    raise HTTPException(
                        status_code=503,
                        detail="The assistant's audio service is temporarily unavailable. "
                        "Please try again in a moment.",
                    ) from None
                await asyncio.to_thread(_record_audio_file, filename, session_id)
                audio_url = f"/audio/{filename}"
        except HTTPException:
            raise
        except Exception:
            logger.exception("TTS generation failed; returning the text response without audio")

    memories = await asyncio.to_thread(get_all_memories, session_id)

    return ChatResponse(
        reply=reply,
        audio_url=audio_url,
        memories=memories,
    )


@router.get("/memories")
def memories(user: dict = Depends(require_user)):
    return {"memories": get_all_memories(user["session_id"])}


@router.get("/history")
def history(user: dict = Depends(require_user)):
    messages = get_messages(user["session_id"])
    return {
        "messages": [
            {
                "sender": "You" if msg.role == "user" else "AI",
                "text": msg.content,
                "mode": msg.mode,
            }
            for msg in messages
        ]
    }


@router.post("/clear-chat")
def clear_chat_route(user: dict = Depends(require_user)):
    clear_chat_history(user["session_id"])
    return {"status": "chat_cleared"}


@router.post("/clear-memories")
def clear_memories_route(user: dict = Depends(require_user)):
    clear_memory_data(user["session_id"])
    return {"status": "memories_cleared"}


@router.post("/clear")
def clear(user: dict = Depends(require_user)):
    clear_session(user["session_id"])
    return {"status": "cleared"}


def _configured_connectors() -> list[str]:
    """Report which connectors are ready (by config), never their secrets."""
    connectors = []
    if settings.CRM_PROVIDER == "directory" and settings.CRM_CONTACTS:
        connectors.append("crm")
    elif settings.CRM_PROVIDER == "rest" and settings.CRM_REST_BASE_URL:
        connectors.append("crm")
    if settings.WA_TOKEN and settings.WA_PHONE_NUMBER_ID:
        connectors.append("whatsapp")
    if settings.EMAIL_HOST and settings.EMAIL_USERNAME:
        connectors.append("email")
    return connectors


@router.get("/status")
def status():
    # Public health check only. Capability/architecture detail (which providers
    # and which outbound connectors are armed) requires authentication, so an
    # anonymous caller can't fingerprint the deployment.
    return {"status": "online"}


@router.get("/status/detail")
def status_detail(user: dict = Depends(require_user)):
    return {
        "status": "online",
        "llm_engine": active_llm[0] if active_llm else "None configured",
        "llm_providers": active_llm,
        "tts_engine": active_tts[0] if active_tts else "None configured",
        "tts_providers": active_tts,
        "connectors": _configured_connectors(),
        "supported_actions": sorted(SUPPORTED_ACTIONS),
    }


@router.get("/audio/{filename}")
async def get_audio(filename: str, user: dict = Depends(require_user)):
    if not AUDIO_FILENAME_PATTERN.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Invalid audio filename")

    owned = await asyncio.to_thread(_own_audio_file, filename, user["session_id"])
    if not owned:
        raise HTTPException(status_code=404, detail="Audio file not found")

    try:
        data, _size = await asyncio.to_thread(stream_audio, user["session_id"], filename)
    except AudioStoreError as exc:
        if str(exc) == "missing":
            raise HTTPException(status_code=404, detail="Audio file not found") from None
        # Store selected but unreachable: fail loudly, never serve stale state.
        raise HTTPException(status_code=503, detail="The audio service is temporarily unavailable.") from None

    return Response(
        content=data,
        media_type="audio/mpeg",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
