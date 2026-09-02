import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import clean_bool, clean_float, settings
from app.services import tts_service


class ConfigurationParsingTests(unittest.TestCase):
    def test_clean_float_rejects_invalid_and_out_of_range_values(self):
        self.assertEqual(clean_float("invalid", 1.0, 0.7, 1.2), 1.0)
        self.assertEqual(clean_float("0.6", 1.0, 0.7, 1.2), 1.0)
        self.assertEqual(clean_float("1.3", 1.0, 0.7, 1.2), 1.0)
        self.assertEqual(clean_float("0.95", 1.0, 0.7, 1.2), 0.95)

    def test_clean_bool_accepts_expected_values_and_uses_default_otherwise(self):
        self.assertTrue(clean_bool("yes", False))
        self.assertFalse(clean_bool("OFF", True))
        self.assertTrue(clean_bool("unexpected", True))


class SpeechOptionTests(unittest.TestCase):
    def test_legacy_tts_model_does_not_receive_instructions(self):
        options = tts_service._build_openai_speech_options(
            model="tts-1",
            voice="onyx",
            speed=1.0,
            instructions="Use a conversational delivery.",
        )

        self.assertEqual(options["voice"], "onyx")
        self.assertNotIn("instructions", options)

    def test_instruction_capable_model_receives_profile(self):
        options = tts_service._build_openai_speech_options(
            model="gpt-4o-mini-tts-2025-12-15",
            voice="onyx",
            speed=1.0,
            instructions="Use a conversational delivery.",
        )

        self.assertEqual(options["instructions"], "Use a conversational delivery.")

    def test_bytez_payload_includes_only_explicit_model_parameters(self):
        with (
            patch.object(settings, "BYTEZ_TTS_VOICE", "ash"),
            patch.object(settings, "BYTEZ_TTS_SPEED", 0.95),
        ):
            payload = tts_service._build_bytez_payload("Hello")

        self.assertEqual(payload["text"], "Hello")
        self.assertFalse(payload["json"])
        self.assertEqual(payload["params"], {"voice": "ash", "speed": 0.95})


class ProviderFallbackTests(unittest.TestCase):
    def test_bytez_is_skipped_without_a_configured_tts_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_dir = Path(temp_dir)

            def write_fallback(_, filepath):
                filepath.write_bytes(b"complete")

            with (
                patch.object(tts_service, "AUDIO_DIR", audio_dir),
                patch.object(settings, "ELEVENLABS_API_KEY", ""),
                patch.object(settings, "BYTEZ_API_KEY", "test-key"),
                patch.object(settings, "BYTEZ_TTS_MODEL", ""),
                patch.object(settings, "TTS_API_KEY", ""),
                patch.object(tts_service, "generate_speech_bytez") as bytez_mock,
                patch.object(
                    tts_service,
                    "generate_speech_gtts",
                    side_effect=write_fallback,
                ) as gtts_mock,
            ):
                filename = tts_service.generate_speech("Hello")

            self.assertTrue((audio_dir / filename).is_file())
            bytez_mock.assert_not_called()
            gtts_mock.assert_called_once()

    def test_partial_file_is_removed_before_next_provider_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_dir = Path(temp_dir)

            def fail_with_partial_file(_, filepath):
                filepath.write_bytes(b"partial")
                raise RuntimeError("provider failed")

            def succeed_after_cleanup(_, filepath):
                self.assertFalse(filepath.exists())
                filepath.write_bytes(b"complete")

            with (
                patch.object(tts_service, "AUDIO_DIR", audio_dir),
                patch.object(settings, "ELEVENLABS_API_KEY", "test-key"),
                patch.object(settings, "BYTEZ_API_KEY", "test-key"),
                patch.object(settings, "BYTEZ_TTS_MODEL", "vendor/test-tts"),
                patch.object(settings, "TTS_API_KEY", ""),
                patch.object(
                    tts_service,
                    "generate_speech_elevenlabs",
                    side_effect=fail_with_partial_file,
                ),
                patch.object(
                    tts_service,
                    "generate_speech_bytez",
                    side_effect=succeed_after_cleanup,
                ) as bytez_mock,
                patch.object(tts_service, "generate_speech_gtts") as gtts_mock,
            ):
                filename = tts_service.generate_speech("Hello")

            self.assertTrue((audio_dir / filename).is_file())
            bytez_mock.assert_called_once()
            gtts_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
