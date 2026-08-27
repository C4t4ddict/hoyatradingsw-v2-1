import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

import market_pattern
from market_pattern import FEATURES, TARGETS, build_market_pattern_dataset, get_market_pattern_readiness, predict_market_pattern
from train_market_pattern_model import _walk_forward_metrics


def candle(timestamp: datetime, price: float, volume: float = 100.0) -> list:
    milliseconds = int(timestamp.timestamp() * 1000)
    return [milliseconds, price, price * 1.01, price * 0.99, price * 1.002, volume]


class MarketPatternDatasetTests(unittest.TestCase):
    def test_features_are_causal_and_labels_enter_at_next_open(self):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        candles = [candle(start + timedelta(hours=4 * index), 100 + index) for index in range(80)]
        as_of = int((start + timedelta(hours=4 * 81)).timestamp() * 1000)
        frame = build_market_pattern_dataset(candles, as_of_ms=as_of, persist=False)
        row = frame.iloc[10]
        source_index = int(row["timestamp"] / (4 * 60 * 60 * 1000) - candles[0][0] / (4 * 60 * 60 * 1000))
        expected = candles[source_index + 2][1] / candles[source_index + 1][1] - 1.0

        self.assertAlmostEqual(float(row["forward_return_4h"]), expected)
        self.assertEqual(pd.Timestamp(row["event_time"]), pd.Timestamp(candles[source_index][0] + 4 * 60 * 60 * 1000, unit="ms", tz="UTC"))

    def test_future_candle_changes_do_not_change_past_features(self):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        candles = [candle(start + timedelta(hours=4 * index), 100 + index) for index in range(90)]
        as_of = int((start + timedelta(hours=4 * 91)).timestamp() * 1000)
        first = build_market_pattern_dataset(candles, as_of_ms=as_of, persist=False)
        changed = [row.copy() for row in candles]
        changed[70][1:5] = [50_000, 50_500, 49_500, 50_100]
        second = build_market_pattern_dataset(changed, as_of_ms=as_of, persist=False)

        first_row = first[first["timestamp"] == candles[60][0]].iloc[0]
        second_row = second[second["timestamp"] == candles[60][0]].iloc[0]
        for feature in FEATURES:
            self.assertEqual(first_row[feature], second_row[feature])


class MarketPatternReadinessTests(unittest.TestCase):
    @patch("market_pattern.joblib.load")
    def test_latest_failed_validation_blocks_stale_model_file(self, load_model):
        with tempfile.TemporaryDirectory() as directory:
            model_dir = Path(directory)
            for target in TARGETS:
                (model_dir / f"{target}.joblib").write_bytes(b"stale")
            row = {"event_time": "2026-01-01T00:00:00+00:00", **{feature: 0.1 for feature in FEATURES}}
            with (
                patch.object(market_pattern, "MODEL_DIR", model_dir),
                patch("market_pattern._report_rows", return_value={target: {"validation_passed": False} for target in TARGETS}),
            ):
                result = predict_market_pattern(pd.DataFrame([row]))

        self.assertFalse(result["ready"])
        self.assertTrue(all(value["reason"] == "latest validation not passed" for value in result["predictions"].values()))
        load_model.assert_not_called()

    def test_clean_historical_dataset_is_training_ready_without_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "market.csv"
            model_dir = root / "models"
            report = model_dir / "report.json"
            start = datetime(2025, 1, 1, tzinfo=timezone.utc)
            rows = []
            for index in range(1200):
                row = {
                    "event_id": f"bar-{index}",
                    "event_time": (start + timedelta(hours=4 * index)).isoformat(),
                    **{feature: 0.1 for feature in FEATURES},
                }
                for target in TARGETS:
                    row[target] = index % 2
                rows.append(row)
            pd.DataFrame(rows).to_csv(dataset, index=False)
            with (
                patch.object(market_pattern, "DATASET_CSV", dataset),
                patch.object(market_pattern, "MODEL_DIR", model_dir),
                patch.object(market_pattern, "REPORT_PATH", report),
            ):
                result = get_market_pattern_readiness(now=start + timedelta(days=300))

        self.assertTrue(result["training_ready"])
        self.assertFalse(result["inference_ready"])
        self.assertEqual(result["models"]["validated"], 0)

    @patch("train_market_pattern_model._fit_model")
    def test_walk_forward_uses_expanding_train_windows_with_purge(self, fit_model):
        model = MagicMock()
        model.predict_proba.side_effect = lambda features: np.column_stack([
            np.full(len(features), 0.5),
            np.full(len(features), 0.5),
        ])
        fit_model.return_value = model
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = []
        for index in range(1200):
            row = {
                "event_id": f"bar-{index}",
                "event_time": (start + timedelta(hours=4 * index)).isoformat(),
                "label_up_4h": index % 2,
                "forward_return_4h": 0.01 if index % 2 else -0.01,
            }
            row.update({feature: float(index % 17) for feature in FEATURES})
            rows.append(row)

        result = _walk_forward_metrics(pd.DataFrame(rows), "label_up_4h")

        self.assertEqual(len(result["folds"]), 4)
        self.assertEqual([fold["train_rows"] for fold in result["folds"]], [714, 834, 954, 1074])
        self.assertEqual([fold["test_rows"] for fold in result["folds"]], [120, 120, 120, 120])


if __name__ == "__main__":
    unittest.main()
