import json
import os
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx

from etl import llm_enrich


class LlmEnrichTests(unittest.TestCase):
    def test_orchestrator_http_timeout_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            timeout = llm_enrich._orchestrator_http_timeout()
        self.assertEqual(timeout.connect, 30.0)
        self.assertEqual(timeout.read, 600.0)

    def test_orchestrator_http_timeout_invalid_or_non_positive(self) -> None:
        for value in ("bad", "0", "-5"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {llm_enrich.ORCHESTRATOR_HTTP_TIMEOUT_ENV: value}, clear=False):
                    timeout = llm_enrich._orchestrator_http_timeout()
                self.assertEqual(timeout.read, 600.0)

    def test_llm_enrich_sleep_seconds_default_and_invalid(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            self.assertEqual(llm_enrich._llm_enrich_sleep_seconds(), 5.0)
        with patch.dict(os.environ, {llm_enrich.LLM_ENRICH_SLEEP_SECONDS_ENV: "abc"}, clear=False):
            self.assertEqual(llm_enrich._llm_enrich_sleep_seconds(), 5.0)

    def test_call_run_posts_to_expected_url_and_body(self) -> None:
        fake_response = MagicMock()
        fake_response.json.return_value = {"ok": True}
        fake_client = MagicMock()
        fake_client.__enter__.return_value = fake_client
        fake_client.post.return_value = fake_response
        with (
            patch("etl.llm_enrich._orchestrator_url", return_value="http://orch:8004"),
            patch("etl.llm_enrich.httpx.Client", return_value=fake_client) as client_ctor,
        ):
            out = llm_enrich._call_run("classify_v1", "task-name", {"id": 1})
        self.assertEqual(out, {"ok": True})
        client_ctor.assert_called_once()
        fake_client.post.assert_called_once_with(
            "http://orch:8004/run/classify_v1",
            json={"task": "task-name", "input": {"id": 1}},
        )
        fake_response.raise_for_status.assert_called_once()

    def test_llm_enrich_returns_when_no_rows(self) -> None:
        fake_cur = MagicMock()
        fake_cur.fetchall.return_value = []
        fake_ctx = MagicMock()
        fake_ctx.__enter__.return_value = fake_cur
        with (
            patch("etl.llm_enrich.get_cursor", return_value=fake_ctx),
            patch("etl.llm_enrich._call_run") as call_run_mock,
            patch("etl.llm_enrich.time.sleep") as sleep_mock,
        ):
            llm_enrich.llm_enrich()
        call_run_mock.assert_not_called()
        sleep_mock.assert_not_called()
        self.assertEqual(fake_cur.execute.call_count, 1)

    def test_llm_enrich_processes_rows_and_upserts(self) -> None:
        created_at = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        row = (42, "t", "d", created_at, "alice")
        fake_cur = MagicMock()
        fake_cur.fetchall.return_value = [row]
        fake_ctx = MagicMock()
        fake_ctx.__enter__.return_value = fake_cur

        def fake_call_run(prompt_name: str, task: str, input_payload: dict):
            if prompt_name == "classify_v1":
                return {"label": "bug", "confidence": "0.9"}
            if prompt_name == "extract_v1":
                return {"entities": [{"name": "postgres"}], "summary": "sum"}
            raise AssertionError(prompt_name)

        with (
            patch("etl.llm_enrich.get_cursor", return_value=fake_ctx),
            patch("etl.llm_enrich._call_run", side_effect=fake_call_run) as call_run_mock,
            patch("etl.llm_enrich._llm_enrich_sleep_seconds", return_value=2.0),
            patch("etl.llm_enrich.time.sleep") as sleep_mock,
            patch("etl.llm_enrich.datetime") as datetime_mock,
        ):
            datetime_mock.now.return_value = datetime(2026, 5, 8, tzinfo=timezone.utc)
            llm_enrich.llm_enrich()

        self.assertEqual(call_run_mock.call_count, 2)
        sleep_mock.assert_any_call(2.0)
        self.assertEqual(sleep_mock.call_count, 2)

        self.assertEqual(fake_cur.execute.call_count, 2)
        _, insert_params = fake_cur.execute.call_args_list[1][0]
        self.assertEqual(insert_params[0], 42)
        self.assertEqual(insert_params[1], "bug")
        self.assertEqual(insert_params[6], "sum")
        self.assertEqual(insert_params[7], 0.9)
        self.assertEqual(json.loads(insert_params[5]), [{"name": "postgres"}])


if __name__ == "__main__":
    unittest.main()
