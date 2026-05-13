import json
import subprocess
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.llm import client as llm_client
from orchestrator.llm import cursor_sdk_client


class FakeSettings:
    cursor_api_key = "cursor_test_key"
    cursor_model = "composer-2"
    cursor_agent_cwd = str(Path(__file__).resolve().parent)
    cursor_cli_script = str(Path(__file__).resolve())
    cursor_node_command = "node"
    cursor_cli_timeout = 600
    mcp_server_url = "http://mcp-server:8001/mcp"


class CursorSdkClientTests(unittest.TestCase):
    def test_run_cursor_agent_success_returns_result(self) -> None:
        completed = types.SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "ok": True,
                "status": "finished",
                "result": "  ok  ",
                "agentId": "agent-1",
                "runId": "run-1",
                "durationMs": 12,
            }),
            stderr="",
        )
        with (
            patch("orchestrator.llm.cursor_sdk_client.Settings", return_value=FakeSettings()),
            patch("orchestrator.llm.cursor_sdk_client.subprocess.run", return_value=completed) as run_mock,
        ):
            result = cursor_sdk_client.run_cursor_agent(
                mode="prompt",
                messages=[{"role": "user", "content": "hi"}],
            )

        self.assertEqual(result.text, "ok")
        self.assertEqual(result.agent_id, "agent-1")
        payload = json.loads(run_mock.call_args.kwargs["input"])
        self.assertEqual(payload["mode"], "prompt")
        self.assertEqual(payload["model"], "composer-2")
        self.assertEqual(run_mock.call_args.kwargs["env"]["CURSOR_API_KEY"], "cursor_test_key")

    def test_run_cursor_agent_raises_on_cli_error_status(self) -> None:
        completed = types.SimpleNamespace(
            returncode=1,
            stdout=json.dumps({
                "ok": False,
                "status": "startup_error",
                "error": "auth failed",
                "retryable": True,
            }),
            stderr="",
        )
        with (
            patch("orchestrator.llm.cursor_sdk_client.Settings", return_value=FakeSettings()),
            patch("orchestrator.llm.cursor_sdk_client.subprocess.run", return_value=completed),
        ):
            with self.assertRaises(cursor_sdk_client.CursorSdkError) as ctx:
                cursor_sdk_client.run_cursor_agent(mode="prompt", messages=[{"role": "user", "content": "hi"}])

        self.assertEqual(ctx.exception.status, "startup_error")
        self.assertTrue(ctx.exception.retryable)

    def test_run_cursor_agent_raises_on_invalid_stdout(self) -> None:
        completed = types.SimpleNamespace(returncode=0, stdout="not-json", stderr="")
        with (
            patch("orchestrator.llm.cursor_sdk_client.Settings", return_value=FakeSettings()),
            patch("orchestrator.llm.cursor_sdk_client.subprocess.run", return_value=completed),
        ):
            with self.assertRaises(cursor_sdk_client.CursorSdkError):
                cursor_sdk_client.run_cursor_agent(mode="prompt", messages=[{"role": "user", "content": "hi"}])

    def test_run_cursor_agent_raises_retryable_on_timeout(self) -> None:
        with (
            patch("orchestrator.llm.cursor_sdk_client.Settings", return_value=FakeSettings()),
            patch(
                "orchestrator.llm.cursor_sdk_client.subprocess.run",
                side_effect=subprocess.TimeoutExpired("node", 1),
            ),
        ):
            with self.assertRaises(cursor_sdk_client.CursorSdkError) as ctx:
                cursor_sdk_client.run_cursor_agent(mode="prompt", messages=[{"role": "user", "content": "hi"}])

        self.assertTrue(ctx.exception.retryable)

    def test_run_cursor_agent_requires_api_key(self) -> None:
        settings = FakeSettings()
        settings.cursor_api_key = ""
        with patch("orchestrator.llm.cursor_sdk_client.Settings", return_value=settings):
            with self.assertRaises(cursor_sdk_client.CursorSdkError) as ctx:
                cursor_sdk_client.run_cursor_agent(mode="prompt", messages=[{"role": "user", "content": "hi"}])

        self.assertEqual(ctx.exception.status, "startup_error")


class LlmFacadeTests(unittest.TestCase):
    def setUp(self) -> None:
        llm_client._settings.llm_backend = "cursor_sdk"
        llm_client._settings.cursor_model = "composer-2"
        llm_client._settings.llm_max_retries = 1
        llm_client._settings.llm_retry_sleep_seconds = 0.25

    def test_call_llm_uses_cursor_sdk_backend(self) -> None:
        with patch("orchestrator.llm.client.cursor_sdk_client.call_prompt", return_value="ok") as call_mock:
            result = llm_client.call_llm([{"role": "user", "content": "hi"}])

        self.assertEqual(result, "ok")
        call_mock.assert_called_once()

    def test_call_llm_retries_retryable_cursor_error(self) -> None:
        err = cursor_sdk_client.CursorSdkError("temporary", retryable=True)
        with (
            patch("orchestrator.llm.client.cursor_sdk_client.call_prompt", side_effect=[err, "done"]) as call_mock,
            patch("orchestrator.llm.client._sleep_before_llm_retry") as sleep_mock,
        ):
            result = llm_client.call_llm([{"role": "user", "content": "hi"}], max_retries=1)

        self.assertEqual(result, "done")
        self.assertEqual(call_mock.call_count, 2)
        sleep_mock.assert_called_once()

    def test_call_llm_can_use_external_poc_backend(self) -> None:
        llm_client._settings.llm_backend = "external_poc"
        with patch("orchestrator.llm.client.external_llm_poc.call_llm", return_value="legacy") as call_mock:
            result = llm_client.call_llm([{"role": "user", "content": "hi"}])

        self.assertEqual(result, "legacy")
        call_mock.assert_called_once()

    def test_call_llm_with_tools_is_external_poc_only(self) -> None:
        llm_client._settings.llm_backend = "cursor_sdk"
        with self.assertRaises(RuntimeError):
            llm_client.call_llm_with_tools([{"role": "user", "content": "hi"}], [])


if __name__ == "__main__":
    unittest.main()
