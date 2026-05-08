import types
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.llm import client as llm_client


class FakeAPIStatusError(Exception):
    def __init__(self, status_code: int, response=None, body=None):
        super().__init__(f"status={status_code}")
        self.status_code = status_code
        self.response = response
        self.body = body


class LlmClientTests(unittest.TestCase):
    def setUp(self) -> None:
        llm_client._settings.llm_retry_sleep_seconds = 0.25

    def test_is_retriable_http_status_only_5xx_gateway(self) -> None:
        self.assertTrue(llm_client._is_retriable_llm_http_status(500))
        self.assertTrue(llm_client._is_retriable_llm_http_status(503))
        self.assertFalse(llm_client._is_retriable_llm_http_status(429))
        self.assertFalse(llm_client._is_retriable_llm_http_status(400))

    def test_sleep_before_retry_uses_configured_seconds(self) -> None:
        with patch("orchestrator.llm.client.time.sleep") as sleep_mock:
            llm_client._settings.llm_retry_sleep_seconds = 1.5
            llm_client._sleep_before_llm_retry()
            sleep_mock.assert_called_once_with(1.5)

    def test_call_llm_success_returns_trimmed_content(self) -> None:
        completion = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="  ok  "))]
        )
        create_mock = MagicMock(return_value=completion)
        fake_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create_mock))
        )
        with patch("orchestrator.llm.client._make_client", return_value=fake_client):
            result = llm_client.call_llm([{"role": "user", "content": "hi"}], max_retries=0)
        self.assertEqual(result, "ok")
        self.assertEqual(create_mock.call_count, 1)

    def test_call_llm_does_not_retry_on_429(self) -> None:
        response = types.SimpleNamespace(url="https://example.test", headers={"retry-after": "3"})
        create_mock = MagicMock(side_effect=FakeAPIStatusError(429, response=response, body={"x": 1}))
        fake_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create_mock))
        )
        with (
            patch("orchestrator.llm.client._make_client", return_value=fake_client),
            patch("orchestrator.llm.client.APIStatusError", FakeAPIStatusError),
            patch("orchestrator.llm.client._sleep_before_llm_retry") as sleep_mock,
        ):
            with self.assertRaises(FakeAPIStatusError):
                llm_client.call_llm([{"role": "user", "content": "hi"}], max_retries=3)
        self.assertEqual(create_mock.call_count, 1)
        sleep_mock.assert_not_called()

    def test_call_llm_retries_on_503_then_succeeds(self) -> None:
        completion = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="done"))]
        )
        response = types.SimpleNamespace(url="https://example.test", headers={})
        create_mock = MagicMock(
            side_effect=[FakeAPIStatusError(503, response=response), completion],
        )
        fake_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create_mock))
        )
        with (
            patch("orchestrator.llm.client._make_client", return_value=fake_client),
            patch("orchestrator.llm.client.APIStatusError", FakeAPIStatusError),
            patch("orchestrator.llm.client._sleep_before_llm_retry") as sleep_mock,
        ):
            result = llm_client.call_llm([{"role": "user", "content": "hi"}], max_retries=2)
        self.assertEqual(result, "done")
        self.assertEqual(create_mock.call_count, 2)
        sleep_mock.assert_called_once()

    def test_call_llm_with_tools_retries_timeout_exception(self) -> None:
        completion = types.SimpleNamespace(choices=[])
        create_mock = MagicMock(side_effect=[RuntimeError("timeout while calling api"), completion])
        fake_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create_mock))
        )
        with (
            patch("orchestrator.llm.client._make_client", return_value=fake_client),
            patch("orchestrator.llm.client._sleep_before_llm_retry") as sleep_mock,
        ):
            result = llm_client.call_llm_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                max_retries=2,
            )
        self.assertIs(result, completion)
        self.assertEqual(create_mock.call_count, 2)
        sleep_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
