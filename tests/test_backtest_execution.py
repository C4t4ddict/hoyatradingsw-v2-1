import unittest
from unittest.mock import patch

from backtest import run_backtest, run_ensemble_backtest


FOUR_HOURS_MS = 4 * 60 * 60 * 1000


def _candles(count=100, price=100.0, drift=0.0):
    rows = []
    for index in range(count):
        open_price = price + drift * index
        close_price = open_price + drift * 0.25
        rows.append([
            index * FOUR_HOURS_MS,
            open_price,
            max(open_price, close_price) + 0.01,
            min(open_price, close_price) - 0.01,
            close_price,
            1000.0,
        ])
    return rows


class BacktestExecutionTests(unittest.TestCase):
    @patch("backtest._exit_signal", return_value=False)
    @patch("backtest._entry_signal", side_effect=lambda strategy, index, *args: index == 79)
    def test_signal_from_close_executes_at_next_bar_open(self, _entry, _exit):
        candles = _candles(drift=0.1)
        result = run_backtest(candles, fee_pct=0.0, sl_pct=0.5, tp_rr=10.0)

        trade = result["trades"][0]
        self.assertEqual(trade["signal_i"], 79)
        self.assertEqual(trade["entry_i"], 80)
        self.assertEqual(trade["entry"], candles[80][1])
        self.assertEqual(trade["entry_ts"], candles[80][0])

    @patch("backtest._exit_signal_short", return_value=False)
    @patch("backtest._entry_signal_short", side_effect=lambda strategy, index, *args: index == 79)
    def test_positive_funding_is_received_by_short(self, _entry, _exit):
        candles = _candles()
        result = run_backtest(
            candles,
            position_mode="short",
            fee_pct=0.0,
            sl_pct=0.5,
            tp_rr=10.0,
            funding_events=[{"timestamp": candles[85][0], "fundingRate": 0.001}],
        )

        trade = result["trades"][0]
        self.assertLess(trade["funding_fee"], 0.0)
        self.assertGreater(trade["pnl"], 0.0)

    @patch("backtest._exit_signal", return_value=False)
    @patch("backtest._entry_signal", side_effect=lambda strategy, index, *args: index == 79)
    def test_positive_funding_is_paid_by_long(self, _entry, _exit):
        candles = _candles()
        result = run_backtest(
            candles,
            fee_pct=0.0,
            sl_pct=0.5,
            tp_rr=10.0,
            funding_events=[{"timestamp": candles[85][0], "fundingRate": 0.001}],
        )

        trade = result["trades"][0]
        self.assertGreater(trade["funding_fee"], 0.0)
        self.assertLess(trade["pnl"], 0.0)

    @patch("backtest._exit_signal", side_effect=lambda strategy, index, *args: index == 85)
    @patch("backtest._entry_signal", side_effect=lambda strategy, index, *args: index == 79)
    def test_close_exit_signal_executes_at_next_bar_open(self, _entry, _exit):
        candles = _candles(drift=0.1)
        result = run_backtest(candles, fee_pct=0.0, sl_pct=0.5, tp_rr=10.0)

        trade = result["trades"][0]
        self.assertEqual(trade["exit_i"], 86)
        self.assertEqual(trade["exit"], candles[86][1])

    @patch("backtest._exit_signal", return_value=False)
    @patch("backtest._entry_signal", side_effect=lambda strategy, index, *args: index == 79)
    def test_open_position_is_marked_to_market_and_closed_at_end(self, _entry, _exit):
        candles = _candles(drift=0.1)
        result = run_backtest(candles, fee_pct=0.0, sl_pct=0.5, tp_rr=10.0)

        self.assertGreater(result["equity_curve"][-2]["equity"], result["initial_usdt"])
        self.assertEqual(result["trades"][-1]["reason"], "end_of_test")
        self.assertAlmostEqual(result["equity_curve"][-1]["equity"], result["final_usdt"])

    @patch("backtest._exit_signal", return_value=False)
    @patch("backtest._entry_signal", side_effect=lambda strategy, index, *args: index == 79)
    def test_explicit_costs_reduce_result(self, _entry, _exit):
        candles = _candles(drift=0.1)
        free = run_backtest(candles, fee_pct=0.0, slippage_pct=0.0, sl_pct=0.5, tp_rr=10.0)
        normal = run_backtest(candles, fee_pct=0.0005, slippage_pct=0.0005, sl_pct=0.5, tp_rr=10.0)
        costly = run_backtest(
            candles,
            fee_pct=0.0,
            maker_fee_pct=0.0002,
            taker_fee_pct=0.001,
            slippage_pct=0.002,
            sl_pct=0.5,
            tp_rr=10.0,
        )

        self.assertLess(normal["final_usdt"], free["final_usdt"])
        self.assertLess(costly["final_usdt"], normal["final_usdt"])
        self.assertEqual(costly["fee_model"]["taker_fee_pct"], 0.001)

    def test_ensemble_preserves_continuous_market_timestamps(self):
        candles = _candles(count=140, drift=0.05)
        result = run_ensemble_backtest(candles, position_mode="long")

        self.assertNotIn("error", result)
        self.assertEqual(len(result["regime_by_bar"]), len(candles))
        self.assertEqual(
            [point["ts"] for point in result["equity_curve"]],
            [candle[0] for candle in candles[1:]],
        )


if __name__ == "__main__":
    unittest.main()
