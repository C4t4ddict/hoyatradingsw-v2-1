import math
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from backend.app.services.backtest_service import _completed_candles, run_backtest_analysis


def synthetic_candles(count=480):
    rows = []
    previous = 100.0
    start_ms = 1_735_689_600_000
    for index in range(count):
        close = 100.0 + index * 0.03 + math.sin(index / 8.0) * 9.0
        high = max(previous, close) + 1.0
        low = min(previous, close) - 1.0
        rows.append([start_ms + index * 3_600_000, previous, high, low, close, 1000.0 + index])
        previous = close
    return rows


class BacktestDashboardServiceTests(unittest.TestCase):
    def defaults(self):
        return {
            "asset": "BTC",
            "market_type": "spot",
            "timeframe": "1h",
            "start_date": date(2025, 1, 1),
            "end_date": date(2025, 3, 31),
            "strategy": "ema_cross",
            "position_mode": "long",
            "initial_usdt": 1000.0,
            "fee_pct": 0.0005,
            "slippage_pct": 0.0005,
            "leverage": 1.0,
        }

    @patch("backend.app.services.backtest_service.fetch_ohlcv", return_value=synthetic_candles())
    @patch("backend.app.services.backtest_service.get_exchange", return_value=object())
    def test_analysis_returns_source_metrics_and_compact_curve(self, get_exchange, fetch_ohlcv):
        result = run_backtest_analysis(**self.defaults())

        self.assertEqual(result["request"]["symbol"], "BTC/USDT")
        self.assertEqual(result["source"]["provider"], "Binance 공개 OHLCV")
        self.assertFalse(result["source"]["authenticated"])
        self.assertEqual(result["source"]["candle_count"], 480)
        self.assertLessEqual(len(result["equity_curve"]), 360)
        self.assertIn("max_drawdown_pct", result["metrics"])
        self.assertIn("benchmark_return_pct", result["metrics"])
        self.assertIn("sharpe", result["metrics"])
        get_exchange.assert_called_once_with(read_only=True, market_type="spot")
        fetch_ohlcv.assert_called_once()

    @patch("backend.app.services.backtest_service.fetch_funding_rates", return_value=[{"timestamp": 1_735_700_000_000, "fundingRate": 0.0001}])
    @patch("backend.app.services.backtest_service.fetch_ohlcv", return_value=synthetic_candles(120))
    @patch("backend.app.services.backtest_service.get_exchange", return_value=object())
    def test_futures_uses_public_funding_history(self, get_exchange, fetch_ohlcv, fetch_funding):
        request = self.defaults()
        request.update({"market_type": "futures", "position_mode": "both", "leverage": 2.0})

        result = run_backtest_analysis(**request)

        self.assertEqual(result["request"]["symbol"], "BTC/USDT:USDT")
        self.assertEqual(result["source"]["funding_event_count"], 1)
        fetch_funding.assert_called_once()

    def test_invalid_period_is_rejected_before_exchange_access(self):
        request = self.defaults()
        request["end_date"] = request["start_date"] - timedelta(days=1)

        with patch("backend.app.services.backtest_service.get_exchange") as get_exchange:
            with self.assertRaisesRegex(ValueError, "종료일"):
                run_backtest_analysis(**request)
            get_exchange.assert_not_called()

    def test_incomplete_current_candle_is_excluded(self):
        rows = synthetic_candles(3)
        cutoff = rows[-1][0] + 1_800_000

        completed = _completed_candles(rows, "1h", now_ms=cutoff)

        self.assertEqual(completed, rows[:-1])


if __name__ == "__main__":
    unittest.main()
