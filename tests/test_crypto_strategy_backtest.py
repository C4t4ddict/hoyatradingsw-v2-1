import unittest

import pandas as pd

from research.crypto_strategy_backtest import StrategySpec, _combine_components, _training_sharpe, backtest, current_signal


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


def _gapped_frame(opens, drop_positions):
    frame = _frame(opens)
    return frame.drop(frame.index[list(drop_positions)])


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

    def test_gapped_price_series_is_rejected(self):
        frame = _gapped_frame([100, 101, 102, 103, 104], [2])
        signal = pd.Series(1.0, index=frame.index)
        spec = StrategySpec("gapped", "spot", lambda data: signal)

        with self.assertRaisesRegex(ValueError, "missing 4h interval"):
            backtest(frame, pd.DataFrame(), spec, cost_override=0.0)

    def test_portfolio_components_align_missing_asset_rows_as_zero(self):
        columns = ["position", "turnover", "gross_return", "cost", "funding", "net_return"]
        first = pd.DataFrame([[1, 0, 0.1, 0, 0, 0.1]], index=[pd.Timestamp("2022-01-01", tz="UTC")], columns=columns)
        second = pd.DataFrame([[1, 0, 0.2, 0, 0, 0.2]], index=[pd.Timestamp("2022-01-01 04:00", tz="UTC")], columns=columns)

        combined = _combine_components([first, second])

        self.assertFalse(combined.isna().any().any())
        self.assertEqual(combined["net_return"].tolist(), [0.1, 0.2])
        self.assertAlmostEqual(combined["equity"].iloc[-1], 1.32)

    def test_risk_target_selection_sharpe_excludes_holdout(self):
        training_index = pd.date_range("2023-12-30", periods=8, freq="4h", tz="UTC")
        training_returns = pd.Series([0.01, -0.005] * 4, index=training_index)
        training = pd.DataFrame(
            {
                "net_return": training_returns,
                "equity": (1 + training_returns).cumprod(),
                "turnover": 0.0,
                "funding": 0.0,
                "cost": 0.0,
            }
        )
        holdout = training.copy()
        holdout.index = pd.date_range("2024-01-01", periods=8, freq="4h", tz="UTC")
        holdout["net_return"] = 0.5
        combined = pd.concat([training, holdout])
        combined["equity"] = (1 + combined["net_return"]).cumprod()

        self.assertAlmostEqual(_training_sharpe(training), _training_sharpe(combined))


if __name__ == "__main__":
    unittest.main()
