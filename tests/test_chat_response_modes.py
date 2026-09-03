import unittest
from unittest.mock import patch

from app.api.chat import ChatRequest, chat


class ChatResponseModeTests(unittest.TestCase):
    @patch("app.api.chat.get_all_memories", return_value={"name": "Karan"})
    @patch("app.api.chat.generate_speech")
    @patch("app.api.chat.process_message", return_value="Hello, Karan.")
    def test_text_mode_skips_tts_and_preserves_memory(
        self,
        process_message,
        generate_speech,
        get_all_memories,
    ):
        response = chat(
            ChatRequest(message="Hello", response_mode="text"),
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
            "Hello", "default", mode="text"
        )
        generate_speech.assert_not_called()
        get_all_memories.assert_called_once_with("default")

    @patch("app.api.chat.get_all_memories", return_value={"name": "Karan"})
    @patch("app.api.chat.generate_speech", return_value="reply.mp3")
    @patch("app.api.chat.process_message", return_value="Hello, Karan.")
    def test_voice_mode_generates_tts_with_the_same_memory_flow(
        self,
        process_message,
        generate_speech,
        get_all_memories,
    ):
        response = chat(
            ChatRequest(message="Hello", response_mode="voice"),
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
            "Hello", "default", mode="voice"
        )
        generate_speech.assert_called_once_with("Hello, Karan.")
        get_all_memories.assert_called_once_with("default")


if __name__ == "__main__":
    unittest.main()
