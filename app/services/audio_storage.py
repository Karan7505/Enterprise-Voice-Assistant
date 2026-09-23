"""Audio storage: S3 in production/staging, local filesystem in keyless dev.

Generated speech is written to a local temp file by the TTS providers, then
handed to :func:`store_audio`, which persists it in the audio store. In S3
mode the object lives under a per-user key (``user-{id}/{filename}``) in the
configured bucket; the database (``audio_files``) stays the ownership record.

Failure semantics (blueprint Change 4): when S3 is the selected store and it
is unreachable, storage/streaming raises :class:`AudioStoreError` and the API
layer fails the request with 503 — it never silently downgrades to a local
file that no other instance can see.
"""

from __future__ import annotations

import logging
from pathlib import Path

import botocore.exceptions

from app.core.config import settings
from app.core.s3_client import get_s3, s3_enabled
from app.services.tts_service import AUDIO_DIR

logger = logging.getLogger(__name__)


class AudioStoreError(Exception):
    """The audio store is unavailable or the object is missing."""


def audio_mode() -> str:
    return "s3" if s3_enabled() else "local"


def _user_prefix(session_id: str) -> str:
    """Per-user key prefix for a session scope (``user:7`` -> ``user-7``)."""
    if session_id and session_id.startswith("user:"):
        return f"user-{session_id.split(':', 1)[1]}"
    return "user-default"


def audio_key(session_id: str, filename: str) -> str:
    return f"{_user_prefix(session_id)}/{filename}"


def store_audio(session_id: str, filename: str, local_path: Path) -> None:
    """Persist a freshly generated file in the audio store.

    In S3 mode the local file is removed after a successful upload (S3 + the
    90-day lifecycle own the data); in local mode it is kept in AUDIO_DIR.
    """
    if audio_mode() == "local":
        return  # the file is already where local mode serves from

    key = audio_key(session_id, filename)
    try:
        get_s3().upload_file(str(local_path), settings.S3_BUCKET, key)
    except (botocore.exceptions.BotoCoreError, OSError) as exc:
        # BotoCoreError covers API errors (ClientError) and connection-level
        # failures; OSError covers the source file vanishing mid-upload.
        raise AudioStoreError(f"audio upload failed: {exc}") from exc
    finally:
        # Best-effort local cleanup: the object is authoritative in S3.
        try:
            local_path.unlink(missing_ok=True)
        except OSError:
            pass


def stream_audio(session_id: str, filename: str) -> tuple[bytes, int]:
    """Fetch an object's bytes for streaming. Raises AudioStoreError when the
    store is unreachable or the object is absent (caller maps to 503/404)."""
    key = audio_key(session_id, filename)

    if audio_mode() == "local":
        path = AUDIO_DIR / filename
        if not path.is_file():
            raise AudioStoreError("missing")
        return path.read_bytes(), path.stat().st_size

    try:
        obj = get_s3().get_object(Bucket=settings.S3_BUCKET, Key=key)
    except botocore.exceptions.ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404", "NotFound"):
            raise AudioStoreError("missing") from exc
        raise AudioStoreError(f"audio fetch failed: {exc}") from exc
    except botocore.exceptions.BotoCoreError as exc:
        # Store selected but unreachable (connection refused/timeout).
        raise AudioStoreError(f"audio fetch failed: {exc}") from exc
    data = obj["Body"].read()
    return data, len(data)
