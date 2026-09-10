import unittest

from app.services.session_service import should_include_history


class ContextIsolationTests(unittest.TestCase):
    HISTORY = [{"role": "user", "content": "Send Rahul a WhatsApp message."}]

    def test_new_request_does_not_inherit_unrelated_history(self):
        self.assertFalse(
            should_include_history("What is the weather today?", self.HISTORY)
        )

    def test_properly_ignores_standalone_pronoun_questions(self):
        self.assertFalse(should_include_history("What is it?", self.HISTORY))

    def test_clear_follow_up_keeps_relevant_history(self):
        self.assertTrue(should_include_history("Send it now.", self.HISTORY))


if __name__ == "__main__":
    unittest.main()
