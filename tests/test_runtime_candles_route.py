import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend.app.routes import runtime
from runtime_data import BAR_MS, RuntimeStore


class RuntimeCandlesRouteTests(unittest.TestCase):
    def test_route_caps_rows_and_filters_incomplete_candles(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RuntimeStore(Path(directory) / 'runtime.sqlite3')
            now_ms = 550 * BAR_MS + 1000
            sample = [[i * BAR_MS, 100, 102, 99, 101, 3] for i in range(551)]
            store.put_candles('ETH/USDT', sample, now_ms + BAR_MS)
            with patch.object(runtime, 'RuntimeStore', return_value=store), patch.object(runtime.time, 'time', return_value=now_ms / 1000):
                result = runtime.runtime_candles('ETH/USDT')
                self.assertEqual(result['interval_ms'], BAR_MS)
                self.assertEqual(len(result['rows']), 540)
                self.assertEqual(result['rows'][0][0], 10 * BAR_MS)
                self.assertEqual(result['rows'][-1][0], 549 * BAR_MS)
                self.assertFalse(result['stale'])
                empty = runtime.runtime_candles()
                self.assertEqual(empty['rows'], [])
                self.assertTrue(empty['stale'])
                with self.assertRaises(HTTPException) as error:
                    runtime.runtime_candles('DOGE/USDT')
                self.assertEqual(error.exception.status_code, 422)
