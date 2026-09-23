"""Shared S3 client for the assistant audio store.

A single lazily-created boto3 client is reused process-wide. The endpoint is
read at first use (not import time) so tests and deployment scripts can point
the app at a different S3-compatible endpoint via ``S3_ENDPOINT_URL``.

When ``S3_ENDPOINT_URL`` is empty the app runs in local-filesystem mode and
nothing in this module should be used (see ``app.services.audio_storage``).
"""

from __future__ import annotations

import logging
import os

import boto3

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None


def _endpoint() -> str:
    # An explicitly empty env value (S3_ENDPOINT_URL="") selects local-FS
    # mode and must not fall back to the settings default.
    val = os.environ.get("S3_ENDPOINT_URL")
    if val is None:
        val = settings.S3_ENDPOINT_URL
    return (val or "").strip()


def s3_enabled() -> bool:
    return bool(_endpoint())


def get_s3():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=_endpoint(),
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY") or settings.S3_ACCESS_KEY,
            aws_secret_access_key=os.environ.get("S3_SECRET_KEY") or settings.S3_SECRET_KEY,
            region_name="us-east-1",
        )
    return _client


def close_s3() -> None:
    global _client
    _client = None
