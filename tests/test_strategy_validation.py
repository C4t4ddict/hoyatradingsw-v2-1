import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from strategy_validation import (
    apply_cost_stress,
    benchmark_comparison,
    classify_market_regimes,
    monte_carlo_trade_paths,
    purged_walk_forward_report,
    purged_walk_forward_splits,
    run_validation_suite,
    strategy_correlation,
)


class StrategyValidationTests(unittest.TestCase):
    def test_purged_walk_forward_has_no_train_test_overlap(self):
        folds = purged_walk_forward_splits(240, train_bars=100, test_bars=30, purge_bars=5, embargo_bars=7)

        self.assertTrue(folds)
        for fold in folds:
            self.assertGreaterEqual(fold.test_start - fold.train_end, 5)
            self.assertLessEqual(fold.train_end, fold.test_start)
        for previous, current in zip(folds, folds[1:]):
            self.assertGreaterEqual(current.train_end - previous.test_end, 7)
        report = purged_walk_forward_report(pd.Series([0.001] * 240), folds)
        self.assertEqual(len(report), len(folds))
        self.assertTrue(all(column in report for column in ("train_sharpe", "test_sharpe")))

    def test_future_returns_do_not_change_past_regime_labels(self):
        original = pd.Series([0.002] * 60 + [-0.003] * 60)
        changed = original.copy()
        changed.iloc[80:] = 0.10
        first = classify_market_regimes(original, trend_window=10, volatility_window=10)
        second = classify_market_regimes(changed, trend_window=10, volatility_window=10)

        pd.testing.assert_frame_equal(first.iloc[:80], second.iloc[:80])

    def test_cost_stress_is_monotonic_for_positive_turnover(self):
        gross = pd.Series([0.01, -0.005, 0.008, 0.002])
        turnover = pd.Series([1.0, 1.0, 0.5, 2.0])
        table = apply_cost_stress(gross, turnover, cost_bps_scenarios=(0, 10, 25))

        self.assertEqual(list(table["cost_bps"]), [0.0, 10.0, 25.0])
        self.assertGreater(table.iloc[0]["total_return_pct"], table.iloc[1]["total_return_pct"])
        self.assertGreater(table.iloc[1]["total_return_pct"], table.iloc[2]["total_return_pct"])

    def test_monte_carlo_is_reproducible_and_reports_tail_risk(self):
        trades = [0.03, -0.02, 0.01, -0.01, 0.04, -0.03]
        first = monte_carlo_trade_paths(trades, simulations=300, seed=7)
        second = monte_carlo_trade_paths(trades, simulations=300, seed=7)

        self.assertEqual(first, second)
        self.assertGreaterEqual(first["max_drawdown_p95_pct"], 0.0)
        self.assertGreaterEqual(first["loss_probability_pct"], 0.0)

    def test_strategy_correlation_and_benchmark_comparison(self):
        index = pd.RangeIndex(6)
        alpha = pd.Series([0.01, 0.02, -0.01, 0.03, 0.00, 0.02], index=index)
        clone = alpha * 2
        benchmark = pd.Series([0.0, 0.01, -0.01, 0.01, 0.0, 0.01], index=index)

        corr = strategy_correlation({"alpha": alpha, "clone": clone, "benchmark": benchmark})
        comparison = benchmark_comparison(alpha, benchmark)
        self.assertAlmostEqual(corr.loc["alpha", "clone"], 1.0)
        self.assertGreater(comparison["excess_total_return_pct"], 0.0)

    def test_validation_suite_writes_reproducible_artifacts(self):
        frame = pd.DataFrame({
            "strategy_return": [0.001, -0.002, 0.003, 0.001] * 20,
            "benchmark_return": [0.0005, -0.001, 0.001, 0.0] * 20,
            "turnover": [0.2, 0.0, 0.3, 0.1] * 20,
            "funding_return": [0.0] * 80,
            "alternate_return": [0.0002, -0.001, 0.002, 0.0] * 20,
        })
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = run_validation_suite(
                frame,
                strategy_column="strategy_return",
                benchmark_column="benchmark_return",
                output_dir=output,
                seed=11,
            )
            payload = json.loads((output / "validation_report.json").read_text(encoding="utf-8"))
            self.assertTrue((output / "regime_performance.csv").exists())
            self.assertTrue((output / "cost_stress.csv").exists())
            self.assertTrue((output / "purged_walk_forward.csv").exists())
            self.assertTrue((output / "strategy_correlation.csv").exists())

        self.assertEqual(payload["methodology"]["monte_carlo_seed"], 11)
        self.assertTrue(report["methodology"]["causal_regimes"])


if __name__ == "__main__":
    unittest.main()
