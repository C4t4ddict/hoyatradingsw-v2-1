import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from ml_readiness import REQUIRED_FEATURES, TARGETS, get_ml_readiness


class MlReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.dataset = self.root / "ml_dataset.csv"
        self.models = self.root / "models_bidirectional"

    def tearDown(self):
        self.temporary.cleanup()

    def test_missing_dataset_is_collecting(self):
        result = get_ml_readiness(self.dataset, self.models)
        self.assertEqual(result["status"], "collecting")
        self.assertFalse(result["inference_ready"])

    def _write_ready_dataset(self):
        now = datetime(2026, 8, 1, tzinfo=timezone.utc)
        rows = []
        for index in range(240):
            event_time = now - timedelta(hours=240 - index)
            row = {
                "event_id": f"event-{index}",
                "event_time": event_time.isoformat(),
                "title": f"headline {index}",
                "source": "source",
                "kind": "news",
                "topic": "market",
                "score": 1.0,
                "trust": 0.8,
                "is_trump": False,
                "is_scheduled": False,
                "market_feature_time": (event_time - timedelta(minutes=1)).isoformat(),
                "market_ret_1h": 0.1,
                "market_ret_4h": 0.2,
                "market_volatility_12h": 0.3,
                "market_volume_ratio": 1.0,
            }
            for target in TARGETS:
                row[target] = index % 2
            rows.append(row)
        frame = pd.DataFrame(rows)
        self.assertTrue(set(REQUIRED_FEATURES).issubset(frame.columns))
        frame.to_csv(self.dataset, index=False)
        return now

    def test_validated_models_and_clean_dataset_are_ready(self):
        now = self._write_ready_dataset()
        self.models.mkdir()
        report = []
        for target in TARGETS:
            (self.models / f"{target}.joblib").touch()
            report.append({"target": target, "validation_passed": True, "balanced_accuracy": 0.6})
        (self.models / "report.json").write_text(json.dumps({"targets": report}), encoding="utf-8")

        result = get_ml_readiness(self.dataset, self.models, now=now)
        self.assertTrue(result["training_ready"])
        self.assertTrue(result["inference_ready"])
        self.assertEqual(result["models"]["validated"], len(TARGETS))

    def test_feature_time_after_event_blocks_training(self):
        now = self._write_ready_dataset()
        frame = pd.read_csv(self.dataset)
        frame.loc[0, "market_feature_time"] = (now + timedelta(hours=1)).isoformat()
        frame.to_csv(self.dataset, index=False)

        result = get_ml_readiness(self.dataset, self.models, now=now)
        self.assertFalse(result["training_ready"])
        self.assertEqual(result["dataset"]["feature_leakage_rows"], 1)


if __name__ == "__main__":
    unittest.main()
