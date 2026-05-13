"""Публичный API AuditClient (без сетевого flush)."""
import unittest

from audit.client import AuditClient


class AuditClientApiTests(unittest.TestCase):
    def test_schedule_emit_exists(self) -> None:
        client = AuditClient("http://127.0.0.1:9")
        self.assertTrue(callable(getattr(client, "schedule_emit", None)))


if __name__ == "__main__":
    unittest.main()
