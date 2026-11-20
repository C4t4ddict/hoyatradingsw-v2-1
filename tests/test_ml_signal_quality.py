import unittest
from unittest.mock import patch

from backend.app.services.ml_signal_service import build_signal_summary


class FakeStore:
    def __init__(self, summaries):
        self.summaries = summaries

    def summary(self, signal_type):
        return self.summaries[signal_type]


class MlSignalQualityTests(unittest.TestCase):
    predictions = {
        "label_up_5m": {"probability": 0.9, "ok": True},
        "label_up_30m": {"probability": 0.8, "ok": True},
        "label_up_1h": {"probability": 0.7, "ok": True},
        "label_up_4h": {"probability": 0.6, "ok": True},
        "label_up_24h": {"probability": 0.6, "ok": True},
        "label_down_5m": {"probability": 0.1, "ok": True},
        "label_down_15m": {"probability": 0.1, "ok": True},
        "label_down_30m": {"probability": 0.2, "ok": True},
        "label_down_1h": {"probability": 0.3, "ok": True},
        "label_down_4h": {"probability": 0.4, "ok": True},
        "label_down_24h": {"probability": 0.4, "ok": True},
        "label_up_15m": {"probability": 0.8, "ok": True},
    }

    def quality(self, enabled):
        return {
            "enabled": enabled,
            "observations": 40,
            "brier_score": 0.15 if enabled else 1.0,
            "accuracy": 0.65 if enabled else 0.0,
            "information_coefficient": 0.10 if enabled else 0.0,
        }

    @patch("backend.app.services.ml_signal_service.predict_event_bidirectional")
    @patch("backend.app.services.ml_signal_service.positive_probability", side_effect=lambda value: value["probability"])
    def test_unvalidated_inputs_are_neutral(self, _, predict):
        predict.return_value = self.predictions
        disabled = self.quality(False)
        result = build_signal_summary(
            {"title": "event"}, {"long_score": 10.0, "short_score": 0.0},
            quality_store=FakeStore({"intel": disabled, "ml": disabled}),
        )

        self.assertEqual(result["decision"]["bias"], "neutral")
        self.assertEqual(result["decision"]["trigger_source"], "quality_gate")
        self.assertFalse(result["decision"]["long_trigger"])

    @patch("backend.app.services.ml_signal_service.predict_event_bidirectional")
    @patch("backend.app.services.ml_signal_service.positive_probability", side_effect=lambda value: value["probability"])
    def test_validated_ml_uses_dynamic_weight_and_regime_multiplier(self, _, predict):
        predict.return_value = self.predictions
        result = build_signal_summary(
            {"title": "event"}, {"long_score": 100.0, "short_score": 0.0},
            quality_store=FakeStore({"intel": self.quality(False), "ml": self.quality(True)}),
            regime={"exposure_multiplier": 0.4},
        )

        self.assertEqual(result["quality_policy"]["weights"], {"intel": 0.0, "ml": 1.0})
        self.assertEqual(result["decision"]["position_size_multiplier"], 0.4)
        self.assertEqual(result["decision"]["bias"], "long")
        self.assertEqual(result["decision"]["trigger_source"], "ml")

    @patch("backend.app.services.ml_signal_service.predict_event_bidirectional")
    @patch("backend.app.services.ml_signal_service.positive_probability", side_effect=lambda value: value["probability"])
    def test_incomplete_model_set_has_zero_ml_weight(self, _, predict):
        predictions = {target: dict(value) for target, value in self.predictions.items()}
        predictions["label_down_24h"]["ok"] = False
        predict.return_value = predictions
        result = build_signal_summary(
            {"title": "event"}, {"long_score": 0.0, "short_score": 0.0},
            quality_store=FakeStore({"intel": self.quality(False), "ml": self.quality(True)}),
        )

        self.assertFalse(result["model_ready"])
        self.assertEqual(result["quality_policy"]["weights"]["ml"], 0.0)
        self.assertEqual(result["decision"]["bias"], "neutral")

    @patch("backend.app.services.ml_signal_service.predict_event_bidirectional")
    @patch("backend.app.services.ml_signal_service.positive_probability", side_effect=lambda value: value["probability"])
    def test_validated_market_pattern_can_supply_ml_component(self, _, predict):
        predictions = {target: dict(value) for target, value in self.predictions.items()}
        predictions["label_down_24h"]["ok"] = False
        predict.return_value = predictions
        result = build_signal_summary(
            {"title": "event"}, {"long_score": 0.0, "short_score": 0.0},
            quality_store=FakeStore({
                "intel": self.quality(False),
                "ml": self.quality(False),
                "pattern": self.quality(True),
            }),
            market_pattern={"ready": True, "long_score": 0.80, "short_score": 0.10, "bias": "long"},
        )

        self.assertFalse(result["event_model_ready"])
        self.assertTrue(result["pattern_model_ready"])
        self.assertFalse(result["event_component_enabled"])
        self.assertTrue(result["pattern_component_enabled"])
        self.assertAlmostEqual(result["scores"]["ml_long_score"], 1.6)
        self.assertEqual(result["quality_policy"]["weights"]["ml"], 1.0)
        self.assertEqual(result["decision"]["trigger_source"], "market_pattern")

    @patch("backend.app.services.ml_signal_service.predict_event_bidirectional")
    @patch("backend.app.services.ml_signal_service.positive_probability", side_effect=lambda value: value["probability"])
    def test_unvalidated_pattern_cannot_influence_validated_event_model(self, _, predict):
        predict.return_value = self.predictions
        result = build_signal_summary(
            {"title": "event"}, {"long_score": 0.0, "short_score": 0.0},
            quality_store=FakeStore({
                "intel": self.quality(False),
                "ml": self.quality(True),
                "pattern": self.quality(False),
            }),
            market_pattern={"ready": True, "long_score": 0.01, "short_score": 0.99, "bias": "short"},
        )

        self.assertTrue(result["event_component_enabled"])
        self.assertFalse(result["pattern_component_enabled"])
        self.assertEqual(result["decision"]["trigger_source"], "ml")
        self.assertGreater(result["scores"]["ml_long_score"], result["scores"]["ml_short_score"])


if __name__ == "__main__":
    unittest.main()
