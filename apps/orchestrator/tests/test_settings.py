import os
import unittest
from unittest.mock import patch

from orchestrator.settings import Settings


class SettingsTests(unittest.TestCase):
    def test_default_llm_retry_sleep_seconds(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
        self.assertEqual(settings.llm_retry_sleep_seconds, 2.0)

    def test_llm_retry_sleep_seconds_from_env(self) -> None:
        with patch.dict(os.environ, {"LLM_RETRY_SLEEP_SECONDS": "7.25"}, clear=True):
            settings = Settings()
        self.assertEqual(settings.llm_retry_sleep_seconds, 7.25)


if __name__ == "__main__":
    unittest.main()
