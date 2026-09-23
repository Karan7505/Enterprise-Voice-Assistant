"""One-shot migration: local audio files -> S3, plus stale-row cleanup.

Reads the ``audio_files`` ownership table, uploads any file that still exists
on the local disk into the S3 bucket under its per-user key, and removes rows
whose object exists in neither the local store nor S3 (audio is ephemeral by
design — the 1-hour local TTL means most rows predate this migration and have
no surviving file; serving them would 404 anyway).

Idempotent: S3 ``put_object`` overwrites, so re-running after new audio is
generated just refreshes objects.

Environment: DATABASE_URL (defaults to the local assistant DB), S3_ENDPOINT_URL
(empty skips S3 upload and only reports), plus S3_BUCKET / S3_ACCESS_KEY /
S3_SECRET_KEY.
"""

import os
import sys

import psycopg2

# Make the repo root importable when run as a plain script.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings  # noqa: E402
from app.services.audio_storage import audio_key, s3_enabled  # noqa: E402


def main() -> None:
    url = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT filename, session_id FROM audio_files")
    rows = cur.fetchall()
    print(f"audio_files rows: {len(rows)}")

    from pathlib import Path

    local_dir = Path(settings.AUDIO_DIR).resolve()
    s3 = None
    if s3_enabled():
        from app.core.s3_client import get_s3

        s3 = get_s3()

    uploaded = kept_local = orphaned = 0
    for filename, session_id in rows:
        local = local_dir / filename
        exists_local = local.is_file()
        exists_s3 = False
        if s3 is not None:
            try:
                s3.head_object(Bucket=settings.S3_BUCKET, Key=audio_key(session_id, filename))
                exists_s3 = True
            except Exception:
                exists_s3 = False

        if exists_local and s3 is not None:
            s3.upload_file(str(local), settings.S3_BUCKET, audio_key(session_id, filename))
            uploaded += 1
            try:
                local.unlink()  # S3 is now authoritative
            except OSError:
                pass
        elif exists_local or exists_s3:
            kept_local += 1
        else:
            cur.execute(
                "DELETE FROM audio_files WHERE filename = %s AND session_id = %s",
                (filename, session_id),
            )
            orphaned += 1

    cur.execute("SELECT count(*) FROM audio_files")
    print(
        f"uploaded to S3: {uploaded}; "
        f"kept (already present): {kept_local}; "
        f"stale rows removed: {orphaned}; "
        f"rows remaining: {cur.fetchone()[0]}"
    )
    conn.close()


if __name__ == "__main__":
    main()
