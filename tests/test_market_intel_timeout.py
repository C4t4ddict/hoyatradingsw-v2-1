import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import market_intel
from market_intel import Source


class _Response:
    def __init__(self, payload=b"<rss><channel></channel></rss>"):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class MarketIntelTimeoutTests(unittest.TestCase):
    @patch("market_intel.feedparser.parse")
    @patch("market_intel.urlopen", return_value=_Response())
    def test_source_connection_receives_explicit_timeout(self, urlopen, parse):
        parse.return_value.entries = []
        market_intel._parse_source(Source("one", "https://example.test/rss", "news", 1.0), 8, 1.25)

        self.assertEqual(urlopen.call_args.kwargs["timeout"], 1.25)

    def test_collection_returns_within_global_budget(self):
        sources = [Source(str(index), f"https://example.test/{index}", "news", 1.0) for index in range(4)]

        def slow_source(*args, **kwargs):
            time.sleep(0.20)
            return []

        with patch("market_intel._iter_sources", return_value=sources), \
                patch("market_intel._parse_source", side_effect=slow_source), \
                patch("market_intel.COLLECTION_BUDGET_SEC", 0.05), \
                patch("market_intel.MAX_SOURCE_WORKERS", 2):
            started = time.monotonic()
            result = market_intel._fetch_items_result()
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.15)
        self.assertTrue(result["status"]["timed_out"])

    def test_stale_cache_is_returned_when_all_sources_fail(self):
        cached = {
            "bias": "bullish",
            "score": 2.0,
            "top": [{"title": "cached bitcoin event"}],
            "_cached_at": 1,
        }
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "intel.json"
            cache_path.write_text(json.dumps(cached), encoding="utf-8")
            with patch("market_intel.CACHE_PATH", cache_path), \
                    patch("market_intel._fetch_items_result", return_value={
                        "rows": [],
                        "status": {"sources": 3, "completed": 3, "failed": [{"source": "all"}], "timed_out": [], "elapsed_ms": 20},
                    }):
                brief = market_intel.get_market_brief(force_refresh=True)

        self.assertEqual(brief["bias"], "bullish")
        self.assertTrue(brief["stale"])
        self.assertEqual(brief["collection_status"]["fallback"], "stale_cache")

    def test_empty_result_without_cache_is_neutral_fallback(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("market_intel.CACHE_PATH", Path(directory) / "missing.json"), \
                patch("market_intel._fetch_items_result", return_value={
                    "rows": [],
                    "status": {"sources": 1, "completed": 0, "failed": [], "timed_out": ["one"], "elapsed_ms": 50},
                }):
            brief = market_intel.get_market_brief(force_refresh=True)

        self.assertEqual(brief["bias"], "neutral")
        self.assertFalse(brief["stale"])
        self.assertEqual(brief["collection_status"]["timed_out"], ["one"])


if __name__ == "__main__":
    unittest.main()
