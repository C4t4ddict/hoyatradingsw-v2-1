import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from ml_dataset import enrich_with_price_labels
from ml_market_data import completed_candles, fetch_ohlcv_range
from ml_training import chronological_purged_split


def candle(timestamp: datetime, price: float) -> list:
    milliseconds = int(timestamp.timestamp() * 1000)
    return [milliseconds, price, price + 1, price - 1, price + 0.5, 10]


class FakeExchange:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        self.calls += 1
        return [row for row in self.rows if row[0] >= since][:limit]


class MarketDataTests(unittest.TestCase):
    def test_only_completed_candles_are_returned(self):
        now = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)
        rows = [
            candle(datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc), 100),
            candle(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc), 101),
        ]
        result = completed_candles(rows, "1h", int(now.timestamp() * 1000))
        self.assertEqual(len(result), 1)

    def test_range_fetch_paginates_and_deduplicates(self):
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        start = now - timedelta(days=1)
        rows = [candle(start + timedelta(hours=index), 100 + index) for index in range(24)]
        exchange = FakeExchange(rows)
        result = fetch_ohlcv_range(exchange, "BTC/USDT", "1h", 1, limit_per_call=5, now=now)
        self.assertEqual(len(result), 24)
        self.assertGreater(exchange.calls, 1)
        self.assertEqual(len({row[0] for row in result}), len(result))


class DatasetLeakageTests(unittest.TestCase):
    def test_features_use_only_candles_closed_before_event(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        one_hour = [candle(start + timedelta(hours=index), 100 + index) for index in range(40)]
        five_minute = [candle(start + timedelta(minutes=5 * index), 100 + index / 10) for index in range(480)]
        fifteen_minute = [candle(start + timedelta(minutes=15 * index), 100 + index / 5) for index in range(160)]
        event_time = start + timedelta(hours=20, minutes=30)
        event = {"event_id": "event-1", "event_time": event_time.isoformat(), "title": "event"}
        as_of = int((start + timedelta(days=3)).timestamp() * 1000)

        first = enrich_with_price_labels(
            [event], one_hour, five_minute, fifteen_minute, as_of_ms=as_of, persist=False
        ).iloc[0]
        changed = [row.copy() for row in one_hour]
        changed[21][1] = changed[21][4] = 50_000
        second = enrich_with_price_labels(
            [event], changed, five_minute, fifteen_minute, as_of_ms=as_of, persist=False
        ).iloc[0]

        for feature in ("market_ret_1h", "market_ret_4h", "market_volatility_12h", "market_volume_ratio"):
            self.assertEqual(first[feature], second[feature])
        self.assertLessEqual(pd.Timestamp(first["market_feature_time"]), pd.Timestamp(event["event_time"]))
        self.assertIn("label_up_30m", first.index)
        self.assertIn("label_down_24h", first.index)


class ChronologicalSplitTests(unittest.TestCase):
    def test_newest_period_is_held_out_with_purge_gap(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        frame = pd.DataFrame([
            {
                "event_id": f"event-{index}",
                "event_time": (start + timedelta(hours=index)).isoformat(),
                "label_up_1h": index % 2,
            }
            for index in range(120)
        ])
        split = chronological_purged_split(
            frame,
            "label_up_1h",
            min_rows=100,
            min_class_rows=10,
            purge_hours=12,
        )
        train_end = pd.to_datetime(split.train["event_time"], utc=True).max()
        test_start = pd.to_datetime(split.test["event_time"], utc=True).min()
        self.assertGreaterEqual(test_start - train_end, pd.to_timedelta(12, unit="h"))
        self.assertGreater(split.metadata["purged_rows"], 0)


if __name__ == "__main__":
    unittest.main()
