import tempfile
import unittest
from pathlib import Path

import pandas as pd

from signal_quality import (
    SignalQualityStore,
    align_event_outcomes,
    analyze_market_regime,
    deduplicate_events,
    derive_signal_policy,
    weight_events_by_source,
)


class EventQualityTests(unittest.TestCase):
    def test_syndicated_headlines_are_deduplicated_across_sources(self):
        events = [
            {"title": "Bitcoin ETF inflows surge after approval", "source": "A", "trust": 0.9},
            {"title": "Bitcoin ETF inflows surge after approval!", "source": "B", "trust": 0.8},
            {"title": "Federal Reserve leaves rates unchanged", "source": "Fed", "trust": 1.0},
        ]
        result = deduplicate_events(events)

        self.assertEqual(len(result), 2)
        self.assertEqual(sum("Bitcoin" in row["title"] for row in result), 1)

    def test_source_reliability_requires_enough_observations(self):
        events = [{"title": "one", "source": "A", "score": 2.0}]
        insufficient = weight_events_by_source(events, [{"source": "A", "observations": 9, "reliability": 0.8}])
        sufficient = weight_events_by_source(events, [{"source": "A", "observations": 10, "reliability": 0.75}])

        self.assertEqual(insufficient[0]["score"], 2.0)
        self.assertEqual(sufficient[0]["score"], 3.0)

    def test_event_outcome_starts_at_first_price_after_publication(self):
        index = pd.date_range("2026-01-01T10:00:00", periods=5, freq="1h")
        prices = pd.Series([100, 101, 102, 103, 104], index=index)
        events = [{"event_time": "2026-01-01T10:05:00", "title": "event", "score": 1.0}]
        result = align_event_outcomes(events, prices, horizon_bars=2)

        self.assertEqual(result.iloc[0]["entry_time"], index[1])
        self.assertEqual(result.iloc[0]["exit_time"], index[3])
        self.assertAlmostEqual(result.iloc[0]["forward_return"], 103 / 101 - 1)


class SignalQualityStoreTests(unittest.TestCase):
    def setUp(self):
        Path("data/test_tmp").mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir="data/test_tmp")
        self.store = SignalQualityStore(str(Path(self.directory.name) / "quality.sqlite3"), min_observations=10)

    def tearDown(self):
        self.directory.cleanup()

    def _record_good(self, signal_type, count=10, source=None):
        for index in range(count):
            actual = index % 2
            probability = 0.8 if actual else 0.2
            score = 1.0 if actual else -1.0
            forward = 0.02 if actual else -0.01
            self.store.record(
                signal_type=signal_type,
                horizon="4h",
                predicted_probability=probability,
                actual=actual,
                signed_score=score,
                forward_return=forward,
                source=source,
            )

    def test_quality_gate_enables_only_after_validated_observations(self):
        self._record_good("ml", count=9)
        self.assertFalse(self.store.summary("ml")["enabled"])
        self._record_good("intel", count=10)
        self.assertTrue(self.store.summary("intel")["enabled"])

    def test_bad_calibration_is_disabled(self):
        for index in range(10):
            self.store.record(
                signal_type="ml", horizon="4h", predicted_probability=0.99,
                actual=0, signed_score=1.0, forward_return=-0.01,
            )
        summary = self.store.summary("ml")
        self.assertFalse(summary["enabled"])
        self.assertGreater(summary["brier_score"], 0.25)

    def test_source_reliability_is_shrunk(self):
        self._record_good("intel", count=10, source="Source A")
        row = self.store.source_reliability()[0]
        self.assertGreater(row["reliability"], 0.5)
        self.assertLess(row["reliability"], 1.0)

    def test_calibration_is_reported_by_horizon(self):
        self._record_good("ml", count=10)
        self.store.record(
            signal_type="ml", horizon="24h", predicted_probability=0.9,
            actual=0, signed_score=1.0, forward_return=-0.05,
        )

        summaries = {row["horizon"]: row for row in self.store.horizon_summaries("ml")}
        self.assertEqual(summaries["4h"]["observations"], 10)
        self.assertTrue(summaries["4h"]["enabled"])
        self.assertEqual(summaries["24h"]["observations"], 1)
        self.assertFalse(summaries["24h"]["enabled"])


class RegimeAndPolicyTests(unittest.TestCase):
    def test_regime_uses_only_values_at_or_before_as_of(self):
        past = [100 + index * 0.5 for index in range(80)]
        with_future_shock = past + [10_000, 1, 20_000]
        first = analyze_market_regime(past, as_of_index=79)
        second = analyze_market_regime(with_future_shock, as_of_index=79)

        self.assertEqual(first, second)

    def test_bear_high_risk_regime_reduces_exposure_without_strategy_switch(self):
        closes = [200 - index * 1.5 for index in range(80)]
        regime = analyze_market_regime(closes, funding_rate=0.001)

        self.assertEqual(regime["direction"], "bear")
        self.assertLess(regime["exposure_multiplier"], 0.5)
        self.assertIn("funding_overheated", regime["reasons"])

    def test_dynamic_policy_disables_unvalidated_signals(self):
        disabled = {"enabled": False, "brier_score": 1.0, "accuracy": 0.0, "information_coefficient": 0.0}
        enabled = {"enabled": True, "brier_score": 0.15, "accuracy": 0.60, "information_coefficient": 0.10}
        none = derive_signal_policy(disabled, disabled)
        intel_only = derive_signal_policy(enabled, disabled, {"exposure_multiplier": 0.4})

        self.assertFalse(none["signals_enabled"])
        self.assertEqual(none["weights"], {"intel": 0.0, "ml": 0.0})
        self.assertEqual(intel_only["weights"], {"intel": 1.0, "ml": 0.0})
        self.assertEqual(intel_only["exposure_multiplier"], 0.4)


if __name__ == "__main__":
    unittest.main()
