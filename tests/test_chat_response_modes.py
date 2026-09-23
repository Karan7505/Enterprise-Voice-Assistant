import asyncio
import unittest
from unittest import mock
from unittest.mock import patch

from app.api.chat import ChatRequest, chat

FAKE_USER = {"user_id": 1, "username": "test", "session_id": "user:1"}


class ChatResponseModeTests(unittest.TestCase):
    @patch("app.api.chat.get_all_memories", return_value={"name": "Karan"})
    @patch("app.api.chat.generate_speech_async")
    @patch("app.api.chat.process_message", return_value="Hello, Karan.")
    def test_text_mode_skips_tts_and_preserves_memory(
        self,
        process_message,
        generate_speech,
        get_all_memories,
    ):
        response = asyncio.run(
            chat(ChatRequest(message="Hello", response_mode="text"), user=FAKE_USER)
        )

        self.assertEqual(
            response.model_dump(),
            {
                "reply": "Hello, Karan.",
                "audio_url": "",
                "memories": {"name": "Karan"},
            },
        )
        process_message.assert_called_once_with(
            "Hello", "user:1", mode="text"
        )
        generate_speech.assert_not_called()
        get_all_memories.assert_called_once_with("user:1")

    @patch("app.api.chat.get_all_memories", return_value={"name": "Karan"})
    @patch("app.api.chat.generate_speech_async", return_value="reply.mp3")
    @patch("app.api.chat.store_audio")
    @patch("app.api.chat._record_audio_file")
    @patch("app.api.chat.process_message", return_value="Hello, Karan.")
    def test_voice_mode_generates_tts_with_the_same_memory_flow(
        self,
        process_message,
        _record_audio,
        store_audio,
        generate_speech,
        get_all_memories,
    ):
        response = asyncio.run(
            chat(ChatRequest(message="Hello", response_mode="voice"), user=FAKE_USER)
        )

        self.assertEqual(
            response.model_dump(),
            {
                "reply": "Hello, Karan.",
                "audio_url": "/audio/reply.mp3",
                "memories": {"name": "Karan"},
            },
        )
        process_message.assert_called_once_with(
            "Hello", "user:1", mode="voice"
        )
        generate_speech.assert_called_once_with("Hello, Karan.")
        get_all_memories.assert_called_once_with("user:1")
        store_audio.assert_called_once_with("user:1", "reply.mp3", mock.ANY)
        _record_audio.assert_called_once_with("reply.mp3", "user:1")


if __name__ == "__main__":
    unittest.main()
