import subprocess
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd

import run_ml_collection
import run_ml_retrain_8h


class MlCollectionTests(unittest.TestCase):
    @patch("run_ml_collection.enrich_with_price_labels")
    @patch("run_ml_collection.fetch_ohlcv_range")
    @patch("run_ml_collection.get_exchange")
    @patch("run_ml_collection.load_events")
    def test_label_refresh_uses_public_multitimeframe_pagination(self, events, exchange, fetch, enrich):
        now = datetime(2026, 8, 1, tzinfo=timezone.utc)
        events.return_value = [
            {"event_id": "recent", "event_time": "2026-07-31T00:00:00+00:00"},
            {"event_id": "old", "event_time": "2025-01-01T00:00:00+00:00"},
        ]
        fetch.side_effect = [[[1, 1, 1, 1, 1, 1]], [[2, 1, 1, 1, 1, 1]], [[3, 1, 1, 1, 1, 1]]]
        enrich.return_value = pd.DataFrame([{"event_id": "recent"}])

        result = run_ml_collection.refresh_labels_once(now=now)

        self.assertEqual([call.args[2] for call in fetch.call_args_list], ["1h", "15m", "5m"])
        self.assertTrue(all(call.kwargs["now"] == now for call in fetch.call_args_list))
        self.assertEqual(enrich.call_args.args[0][0]["event_id"], "recent")
        self.assertTrue(enrich.call_args.kwargs["merge_existing"])
        self.assertEqual(result["dataset_rows"], 1)

    @patch("run_ml_collection.refresh_labels_once", return_value={"dataset_rows": 10})
    @patch("run_ml_collection.collect_news_once", return_value={"fetched": 2, "written": 1})
    def test_collect_once_combines_news_and_labels(self, _, __):
        result = run_ml_collection.collect_once()
        self.assertEqual(result["news"]["written"], 1)
        self.assertEqual(result["labels"]["dataset_rows"], 10)


class MlRetrainRunnerTests(unittest.TestCase):
    @patch("run_ml_retrain_8h.subprocess.run")
    def test_training_uses_current_interpreter_and_bidirectional_script(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, stdout="trained", stderr="")
        result = run_ml_retrain_8h.run_training()

        command = run.call_args.args[0]
        self.assertEqual(command[0], sys.executable)
        self.assertTrue(command[1].endswith("train_model_bidirectional.py"))
        self.assertEqual(result["exit_code"], 0)

    @patch("run_ml_retrain_8h.run_training", return_value={"exit_code": 0})
    @patch("run_ml_retrain_8h.collect_once", return_value={"news": {}, "labels": {}})
    def test_cycle_collects_before_training(self, collect, train):
        result = run_ml_retrain_8h.run_cycle()
        self.assertTrue(result["ok"])
        collect.assert_called_once()
        train.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
