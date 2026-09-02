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
            voice="ash",
            speed=1.0,
            instructions="Use a conversational delivery.",
        )

        self.assertEqual(options["instructions"], "Use a conversational delivery.")


class ProviderFallbackTests(unittest.TestCase):
    def test_elevenlabs_failure_uses_custom_after_partial_file_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_dir = Path(temp_dir)

            def fail_elevenlabs(_, filepath):
                filepath.write_bytes(b"partial")
                raise RuntimeError("ElevenLabs failed")

            def succeed_custom(_, filepath):
                self.assertFalse(filepath.exists())
                filepath.write_bytes(b"complete")

            with (
                patch.object(tts_service, "AUDIO_DIR", audio_dir),
                patch.object(settings, "ELEVENLABS_API_KEY", "test-elevenlabs-key"),
                patch.object(settings, "TTS_API_KEY", "test-custom-key"),
                patch.object(
                    tts_service,
                    "generate_speech_elevenlabs",
                    side_effect=fail_elevenlabs,
                ),
                patch.object(
                    tts_service,
                    "generate_speech_openai_tts",
                    side_effect=succeed_custom,
                ) as custom_mock,
                patch.object(tts_service, "generate_speech_gtts") as gtts_mock,
            ):
                filename = tts_service.generate_speech("Hello")

            self.assertTrue((audio_dir / filename).is_file())
            custom_mock.assert_called_once()
            gtts_mock.assert_not_called()

    def test_full_chain_runs_in_order_and_cleans_partial_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_dir = Path(temp_dir)
            attempts = []

            def fail_elevenlabs(_, filepath):
                attempts.append("ElevenLabs")
                filepath.write_bytes(b"partial")
                raise RuntimeError("ElevenLabs failed")

            def fail_custom(_, filepath):
                attempts.append("Custom")
                self.assertFalse(filepath.exists())
                filepath.write_bytes(b"partial")
                raise RuntimeError("Custom TTS failed")

            def succeed_gtts(_, filepath):
                attempts.append("gTTS")
                self.assertFalse(filepath.exists())
                filepath.write_bytes(b"complete")

            with (
                patch.object(tts_service, "AUDIO_DIR", audio_dir),
                patch.object(settings, "ELEVENLABS_API_KEY", "test-elevenlabs-key"),
                patch.object(settings, "TTS_API_KEY", "test-custom-key"),
                patch.object(
                    tts_service,
                    "generate_speech_elevenlabs",
                    side_effect=fail_elevenlabs,
                ),
                patch.object(
                    tts_service,
                    "generate_speech_openai_tts",
                    side_effect=fail_custom,
                ),
                patch.object(
                    tts_service,
                    "generate_speech_gtts",
                    side_effect=succeed_gtts,
                ),
            ):
                filename = tts_service.generate_speech("Hello")

            self.assertTrue((audio_dir / filename).is_file())
            self.assertEqual(attempts, ["ElevenLabs", "Custom", "gTTS"])

    def test_custom_provider_is_skipped_without_a_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_dir = Path(temp_dir)

            def succeed_gtts(_, filepath):
                filepath.write_bytes(b"complete")

            with (
                patch.object(tts_service, "AUDIO_DIR", audio_dir),
                patch.object(settings, "ELEVENLABS_API_KEY", ""),
                patch.object(settings, "TTS_API_KEY", ""),
                patch.object(tts_service, "generate_speech_openai_tts") as custom_mock,
                patch.object(
                    tts_service,
                    "generate_speech_gtts",
                    side_effect=succeed_gtts,
                ) as gtts_mock,
            ):
                filename = tts_service.generate_speech("Hello")

            self.assertTrue((audio_dir / filename).is_file())
            custom_mock.assert_not_called()
            gtts_mock.assert_called_once()

    def test_final_gtts_failure_removes_partial_audio_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_dir = Path(temp_dir)

            def fail_gtts(_, filepath):
                filepath.write_bytes(b"partial")
                raise RuntimeError("gTTS failed")

            with (
                patch.object(tts_service, "AUDIO_DIR", audio_dir),
                patch.object(settings, "ELEVENLABS_API_KEY", ""),
                patch.object(settings, "TTS_API_KEY", ""),
                patch.object(
                    tts_service,
                    "generate_speech_gtts",
                    side_effect=fail_gtts,
                ),
            ):
                with self.assertRaises(RuntimeError):
                    tts_service.generate_speech("Hello")

            self.assertEqual(list(audio_dir.glob("*.mp3")), [])


if __name__ == "__main__":
    unittest.main()
