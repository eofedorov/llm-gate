"""Хелперы audit UI (gateway)."""
import unittest

from gateway.api.routes_audit import _merge_timeseries_charts


class MergeTimeseriesTests(unittest.TestCase):
    def test_merge_aligns_second_series_by_bucket(self) -> None:
        a = [{"bucket": "b1", "value": 0.1}, {"bucket": "b2", "value": 0.2}]
        b = [{"bucket": "b2", "value": 0.9}]
        chart = _merge_timeseries_charts(a, "A", b, "B")
        self.assertEqual(chart["labels"], ["b1", "b2"])
        self.assertEqual(len(chart["datasets"]), 2)
        self.assertEqual(chart["datasets"][0]["data"], [0.1, 0.2])
        self.assertEqual(chart["datasets"][1]["data"], [None, 0.9])


if __name__ == "__main__":
    unittest.main()
