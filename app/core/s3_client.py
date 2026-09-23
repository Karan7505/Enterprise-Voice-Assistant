"""Shared S3 client for the assistant audio store.

A single lazily-created boto3 client is reused process-wide. Endpoint and
credentials are read at first use (not import time) so tests, staging, and
deployment can point the app at different S3 targets via environment:

* ``S3_ENDPOINT_URL`` set (http URL) -> an S3-compatible endpoint
  (LocalStack, MinIO, moto). Credentials come from S3_ACCESS_KEY /
  S3_SECRET_KEY.
* ``S3_ENDPOINT_URL`` empty/unset    -> real AWS S3. Credentials resolve via
  the boto3 default chain: static S3_ACCESS_KEY / S3_SECRET_KEY if set,
  otherwise the ECS task role / instance profile (set the env vars to empty
  strings to force the default chain).
* ``S3_LOCAL_FS=1``                   -> keyless local-filesystem mode;
  nothing in this module should be used (see app.services.audio_storage).

When S3 is the selected store and it is unreachable, requests fail closed
(503) — see app.services.audio_storage.
"""

from __future__ import annotations

import logging
import os

import boto3

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None

TRUE_VALUES = ("1", "true", "yes")


def local_fs_mode() -> bool:
    """Keyless development/CI mode: audio stays on the local filesystem."""
    return (os.environ.get("S3_LOCAL_FS") or "").strip().lower() in TRUE_VALUES


def _endpoint() -> str:
    val = os.environ.get("S3_ENDPOINT_URL")
    if val is None:
        val = settings.S3_ENDPOINT_URL
    return (val or "").strip()


def s3_enabled() -> bool:
    return not local_fs_mode()


def _static_credentials() -> tuple[str | None, str | None]:
    # An explicitly-empty env value selects the boto3 default chain (e.g. an
    # ECS task role) instead of the dev-placeholder defaults in settings.
    key = os.environ.get("S3_ACCESS_KEY", settings.S3_ACCESS_KEY)
    secret = os.environ.get("S3_SECRET_KEY", settings.S3_SECRET_KEY)
    key = (key or "").strip() or None
    secret = (secret or "").strip() or None
    return key, secret


def get_s3():
    global _client
    if _client is None:
        kwargs = {"region_name": (os.environ.get("S3_REGION") or "us-east-1").strip()}
        endpoint = _endpoint()
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        key, secret = _static_credentials()
        if key:
            kwargs["aws_access_key_id"] = key
        if secret:
            kwargs["aws_secret_access_key"] = secret
        _client = boto3.client("s3", **kwargs)
    return _client


def close_s3() -> None:
    global _client
    _client = None
