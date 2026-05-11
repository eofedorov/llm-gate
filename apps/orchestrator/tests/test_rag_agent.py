import unittest
from unittest.mock import patch

from orchestrator.services import rag_agent


class RagAgentTests(unittest.TestCase):
    def test_ask_validates_cursor_agent_answer_contract(self) -> None:
        raw = """
        {
          "answer": "Найден ответ.",
          "confidence": 0.8,
          "sources": [
            {
              "chunk_id": "chunk-1",
              "doc_title": "Runbook",
              "quote": "важная цитата",
              "relevance": 0.9
            }
          ],
          "status": "ok"
        }
        """
        with patch("orchestrator.services.rag_agent.cursor_sdk_client.call_rag", return_value=raw):
            result = rag_agent.ask("что делать?", mcp_url="http://mcp-server:8001/mcp")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.answer, "Найден ответ.")
        self.assertEqual(result.sources[0].chunk_id, "chunk-1")

    def test_ask_returns_insufficient_context_on_invalid_cursor_output(self) -> None:
        with (
            patch("orchestrator.services.rag_agent.cursor_sdk_client.call_rag", return_value="not-json"),
            patch("orchestrator.services.rag_agent.llm_client.call_llm", return_value="still-not-json"),
        ):
            result = rag_agent.ask("что делать?", mcp_url="http://mcp-server:8001/mcp")

        self.assertEqual(result.status, "insufficient_context")
        self.assertEqual(result.confidence, 0.0)

    def test_ask_returns_insufficient_context_without_mcp_url(self) -> None:
        with patch.object(rag_agent._settings, "mcp_server_url", ""):
            result = rag_agent.ask("что делать?")

        self.assertEqual(result.status, "insufficient_context")


if __name__ == "__main__":
    unittest.main()
