import asyncio
import unittest
from unittest.mock import patch

from app.api import chat as chat_api
from app.api.chat import ChatRequest, chat


FAKE_USER = {"user_id": 1, "username": "test", "session_id": "user:1"}


class NoKeyFallbackTests(unittest.TestCase):
    def test_chat_returns_clear_503_when_no_llm_configured(self):
        # Simulate a deployment where no LLM key is set.
        with patch.object(chat_api, "active_llm", []):
            with self.assertRaises(Exception) as ctx:
                asyncio.run(chat(ChatRequest(message="hi", response_mode="text"), user=FAKE_USER))
        exc = ctx.exception
        self.assertEqual(getattr(exc, "status_code", None), 503)
        detail = getattr(exc, "detail", "")
        self.assertIn("LLM provider", detail)
        self.assertIn("OPENROUTER_API_KEY", detail)

    def test_chat_proceeds_when_an_llm_is_configured(self):
        with patch.object(chat_api, "active_llm", ["OpenRouter (model)"]):
            with patch.object(chat_api, "process_message", return_value="Hello") as pm, \
                 patch.object(chat_api, "get_all_memories", return_value={}):
                response = asyncio.run(
                    chat(ChatRequest(message="hi", response_mode="text"), user=FAKE_USER)
                )
        self.assertEqual(response.reply, "Hello")
        self.assertEqual(response.audio_url, "")
        pm.assert_called_once_with("hi", "user:1", mode="text")


if __name__ == "__main__":
    unittest.main()
