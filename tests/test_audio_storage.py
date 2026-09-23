"""Phase 3 verification: S3 audio storage (blueprint Change 4).

Covers per-user key layout, round-trip streaming, cross-user isolation,
fail-closed behavior when the selected store is down, and the local-FS
keyless-dev mode (S3_ENDPOINT_URL="").
"""

import os
import unittest
from pathlib import Path

from pg_test_support import TestDatabase
from app.core.config import settings
from app.core.s3_client import close_s3, get_s3, s3_enabled
from app.services import audio_storage
from app.services.audio_storage import AudioStoreError, stream_audio, store_audio
from app.services.tts_service import AUDIO_DIR

DEAD_S3_URL = "http://127.0.0.1:9999"


class AudioStorageTests(unittest.TestCase):
    def setUp(self):
        self._db = TestDatabase()
        self._db.start()
        # The default deployment (and this staging box) runs S3 mode.
        self._s3_mode = s3_enabled()

    def tearDown(self):
        os.environ.pop("S3_ENDPOINT_URL", None)
        close_s3()
        self._db.stop()

    def _write_local(self, content: bytes) -> tuple[str, Path]:
        filename = "a" * 31 + "1.mp3"  # matches the API filename pattern
        path = AUDIO_DIR / filename
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return filename, path

    # --- S3 mode -------------------------------------------------------------
    def test_store_creates_per_user_key(self):
        if not self._s3_mode:
            self.skipTest("local-FS mode")
        filename, path = self._write_local(b"audio-bytes")
        try:
            store_audio("user:42", filename, path)
        finally:
            path.unlink(missing_ok=True)

        s3 = get_s3()
        expected_key = audio_storage.audio_key("user:42", filename)
        self.assertTrue(expected_key.startswith("user-42/"))
        obj = s3.get_object(Bucket=settings.S3_BUCKET, Key=expected_key)
        self.assertEqual(obj["Body"].read(), b"audio-bytes")

    def test_stream_roundtrip_and_cross_user_isolation(self):
        if not self._s3_mode:
            self.skipTest("local-FS mode")
        filename, path = self._write_local(b"shared-name-different-user")
        try:
            store_audio("user:1", filename, path)
        finally:
            path.unlink(missing_ok=True)

        data, size = stream_audio("user:1", filename)
        self.assertEqual(data, b"shared-name-different-user")
        self.assertEqual(size, len(b"shared-name-different-user"))

        # The same filename under another user's key must not exist.
        with self.assertRaises(AudioStoreError) as ctx:
            stream_audio("user:2", filename)
        self.assertEqual(str(ctx.exception), "missing")

    def test_s3_down_fails_closed(self):
        os.environ["S3_ENDPOINT_URL"] = DEAD_S3_URL
        close_s3()
        try:
            filename, path = self._write_local(b"x")
            try:
                with self.assertRaises(AudioStoreError):
                    store_audio("user:1", filename, path)
            finally:
                path.unlink(missing_ok=True)

            with self.assertRaises(AudioStoreError) as ctx:
                stream_audio("user:1", filename)
            self.assertNotEqual(str(ctx.exception), "missing")  # store error, not absence
        finally:
            os.environ.pop("S3_ENDPOINT_URL", None)
            close_s3()

    # --- local-FS mode ---------------------------------------------------------
    def test_local_fs_mode_keeps_files(self):
        os.environ["S3_LOCAL_FS"] = "1"
        close_s3()
        try:
            self.assertEqual(audio_storage.audio_mode(), "local")
            filename, path = self._write_local(b"local-bytes")
            try:
                store_audio("user:9", filename, path)  # no-op in local mode
                self.assertTrue(path.is_file(), "local mode must keep the file")
                data, size = stream_audio("user:9", filename)
                self.assertEqual(data, b"local-bytes")
                with self.assertRaises(AudioStoreError) as ctx:
                    stream_audio("user:9", "b" * 31 + "1.mp3")
                self.assertEqual(str(ctx.exception), "missing")
            finally:
                path.unlink(missing_ok=True)
        finally:
            os.environ.pop("S3_LOCAL_FS", None)
            close_s3()


if __name__ == "__main__":
    unittest.main()
