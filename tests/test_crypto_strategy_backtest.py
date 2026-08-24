import unittest

import pandas as pd

from research.crypto_strategy_backtest import StrategySpec, backtest, current_signal


def _frame(opens):
    index = pd.date_range("2022-01-01", periods=len(opens), freq="4h", tz="UTC")
    values = pd.Series(opens, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": values,
            "high": values,
            "low": values,
            "close": values,
            "volume": 1.0,
        },
        index=index,
    )


class CryptoStrategyBacktestTests(unittest.TestCase):
    def test_close_signal_is_applied_to_following_open_interval(self):
        frame = _frame([100, 110, 121, 133.1])
        signal = pd.Series([0.0, 1.0, 1.0, 0.0], index=frame.index)
        spec = StrategySpec("alignment", "spot", lambda data: signal)

        result = backtest(frame, pd.DataFrame(), spec, cost_override=0.0)

        self.assertEqual(result["position"].tolist(), [0.0, 0.0, 1.0])
        self.assertAlmostEqual(result["gross_return"].iloc[2], 0.1)

    def test_positive_funding_is_received_by_short_position(self):
        frame = _frame([100, 100, 100, 100])
        signal = pd.Series(-1.0, index=frame.index)
        spec = StrategySpec("short", "futures", lambda data: signal)
        funding = pd.DataFrame(
            {"funding_rate": [0.001]},
            index=pd.DatetimeIndex([frame.index[1]]),
        )

        result = backtest(frame, funding, spec, cost_override=0.0)

        self.assertAlmostEqual(result.loc[frame.index[1], "net_return"], 0.001)

    def test_current_signal_uses_latest_completed_bar(self):
        frame = _frame([100, 101, 102, 103])
        signal = pd.Series([0.0, 0.1, 0.2, 0.7], index=frame.index)
        spec = StrategySpec("latest", "spot", lambda data: signal)

        self.assertEqual(current_signal(frame, spec), 0.7)


if __name__ == "__main__":
    unittest.main()
