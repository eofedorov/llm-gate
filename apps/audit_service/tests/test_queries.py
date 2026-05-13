"""Регрессия SQL-метрик audit_service по фактическим event_type."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_service.database import EVENTS_SCHEMA, get_connection
from audit_service.queries import get_contracts, get_overview, get_runs_list, get_timeseries, get_trace_events


def _init_db(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(path)
    conn.executescript(EVENTS_SCHEMA)
    return conn


class QueriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db_path = self._tmp.name
        self.conn = _init_db(self.db_path)

    def tearDown(self) -> None:
        self.conn.close()
        Path(self.db_path).unlink(missing_ok=True)

    def _insert(
        self,
        *,
        ts: str,
        trace_id: str,
        service: str,
        event_type: str,
        span_id: str,
        attrs_json: str = "{}",
        duration_ms: int | None = None,
        status: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO events (
                ts, trace_id, service, env, event_type, span_id, parent_span_id,
                severity, attrs_json, duration_ms, status, tool_name
            ) VALUES (?, ?, ?, 'dev', ?, ?, NULL, 'info', ?, ?, ?, ?)
            """,
            (ts, trace_id, service, event_type, span_id, attrs_json, duration_ms, status, tool_name),
        )
        self.conn.commit()

    def test_insufficient_from_decision_and_tools_per_trace(self) -> None:
        self._insert(
            ts="2025-01-15T10:00:00",
            trace_id="t1",
            service="orchestrator",
            event_type="run.finish",
            span_id="s1",
            attrs_json='{"duration_ms": 100, "status": "ok"}',
            duration_ms=100,
            status="ok",
        )
        self._insert(
            ts="2025-01-15T10:00:01",
            trace_id="t1",
            service="orchestrator",
            event_type="decision",
            span_id="s2",
            attrs_json='{"status": "insufficient_context", "reason": "parse_failed"}',
            status="insufficient_context",
        )
        self._insert(
            ts="2025-01-15T10:00:02",
            trace_id="t1",
            service="mcp_server",
            event_type="tool.call.finish",
            span_id="s3",
            attrs_json='{"tool_name": "kb_search"}',
            duration_ms=50,
            status="ok",
            tool_name="kb_search",
        )
        ov = get_overview(self.conn, "2025-01-01", "2025-12-31", service="orchestrator")
        self.assertEqual(ov["total_runs"], 1)
        self.assertGreater(ov["insufficient_rate"], 0.0)
        self.assertEqual(ov["avg_tool_calls"], 1.0)

    def test_schema_validation_and_repair_contracts(self) -> None:
        self._insert(
            ts="2025-01-15T11:00:00",
            trace_id="t2",
            service="orchestrator",
            event_type="schema_validation",
            span_id="a1",
            attrs_json='{"result": "fail"}',
        )
        self._insert(
            ts="2025-01-15T11:00:01",
            trace_id="t2",
            service="orchestrator",
            event_type="repair",
            span_id="a2",
            attrs_json='{"attempted": true, "success": true}',
        )
        c = get_contracts(self.conn, "2025-01-01", "2025-12-31", service="orchestrator")
        self.assertEqual(c["schema_fail_rate"], 1.0)
        self.assertEqual(c["repair_success_rate"], 1.0)

    def test_runs_list_insufficient_filter(self) -> None:
        self._insert(
            ts="2025-01-15T12:00:00",
            trace_id="t3",
            service="orchestrator",
            event_type="run.finish",
            span_id="r1",
            attrs_json="{}",
            duration_ms=10,
            status="ok",
        )
        self._insert(
            ts="2025-01-15T12:00:01",
            trace_id="t3",
            service="orchestrator",
            event_type="decision",
            span_id="r2",
            attrs_json='{"status": "insufficient_context"}',
            status="insufficient_context",
        )
        all_runs = get_runs_list(self.conn, "2025-01-01", "2025-12-31", None, None, 10)
        self.assertEqual(len(all_runs), 1)
        ins = get_runs_list(self.conn, "2025-01-01", "2025-12-31", "insufficient", None, 10)
        self.assertEqual(len(ins), 1)

    def test_timeseries_schema_fail(self) -> None:
        self._insert(
            ts="2025-01-15T13:00:00",
            trace_id="t4",
            service="orchestrator",
            event_type="schema_validation",
            span_id="z1",
            attrs_json='{"result": "ok"}',
        )
        self._insert(
            ts="2025-01-15T13:01:00",
            trace_id="t4",
            service="orchestrator",
            event_type="schema_validation",
            span_id="z2",
            attrs_json='{"result": "fail"}',
        )
        rows = get_timeseries(
            self.conn, "schema_fail_rate", "1h", "2025-01-01", "2025-12-31", service="orchestrator"
        )
        self.assertTrue(rows)
        self.assertAlmostEqual(rows[0]["value"], 0.5, places=2)

    def test_trace_attrs_are_dict(self) -> None:
        self._insert(
            ts="2025-01-15T14:00:00",
            trace_id="t5",
            service="orchestrator",
            event_type="decision",
            span_id="x1",
            attrs_json='{"foo": 1}',
        )
        ev = get_trace_events(self.conn, "t5")
        self.assertEqual(len(ev), 1)
        self.assertIsInstance(ev[0]["attrs"], dict)
        self.assertEqual(ev[0]["attrs"].get("foo"), 1)


if __name__ == "__main__":
    unittest.main()
