import os
import tempfile
import unittest
from pathlib import Path

from app.core.config import load_project_environment


class ProjectEnvironmentLoadingTests(unittest.TestCase):
    TEST_KEY = "JARVIS_CONFIG_PRECEDENCE_TEST"

    def setUp(self):
        self.previous_value = os.environ.get(self.TEST_KEY)

    def tearDown(self):
        if self.previous_value is None:
            os.environ.pop(self.TEST_KEY, None)
        else:
            os.environ[self.TEST_KEY] = self.previous_value

    def test_dotenv_value_overrides_an_inherited_process_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                f"{self.TEST_KEY}=from-project-dotenv\n",
                encoding="utf-8",
            )
            os.environ[self.TEST_KEY] = "stale-terminal-value"

            self.assertTrue(load_project_environment(dotenv_path))
            self.assertEqual(os.environ[self.TEST_KEY], "from-project-dotenv")

    def test_missing_dotenv_keeps_deployment_environment_unchanged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ[self.TEST_KEY] = "platform-value"

            self.assertFalse(
                load_project_environment(Path(temp_dir) / "missing.env")
            )
            self.assertEqual(os.environ[self.TEST_KEY], "platform-value")
