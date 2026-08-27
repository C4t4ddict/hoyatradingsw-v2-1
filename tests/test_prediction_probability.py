import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import predict_model
import predict_model_bidirectional


class IdentityPreprocessor:
    def transform(self, frame):
        return frame


class SingleClassModel:
    def __init__(self, label):
        self.classes_ = np.array([label])

    def predict(self, transformed):
        return np.array([self.classes_[0]])

    def predict_proba(self, transformed):
        return np.array([[1.0]])


class ReversedClassModel:
    classes_ = np.array([1, 0])

    def predict(self, transformed):
        return np.array([1])

    def predict_proba(self, transformed):
        return np.array([[0.8, 0.2]])


class PredictionProbabilityTests(unittest.TestCase):
    def test_bidirectional_single_class_probability_for_all_targets(self):
        predict_model_bidirectional.clear_model_cache()
        event = {"title": "test", "summary": "event"}
        for target in predict_model_bidirectional.TARGETS:
            for label, expected in ((0, 0.0), (1, 1.0)):
                with self.subTest(target=target, label=label), tempfile.TemporaryDirectory() as directory:
                    model_dir = Path(directory)
                    (model_dir / f"{target}.joblib").touch()
                    bundle = {
                        "prep": IdentityPreprocessor(),
                        "model": SingleClassModel(label),
                        "metadata": {"validation_passed": True},
                    }
                    with (
                        patch.object(predict_model_bidirectional, "MODEL_DIR", model_dir),
                        patch.object(predict_model_bidirectional.joblib, "load", return_value=bundle),
                    ):
                        result = predict_model_bidirectional._predict_one(event, target)
                self.assertEqual(result["classes"], [label])
                self.assertEqual(result["positive_proba"], expected)
                self.assertEqual(predict_model_bidirectional.positive_probability(result), expected)

    def test_bidirectional_model_cache_can_be_invalidated(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "label_up_5m.joblib"
            model_path.touch()
            bundle = {"prep": IdentityPreprocessor(), "model": SingleClassModel(1)}
            predict_model_bidirectional.clear_model_cache()
            with patch.object(predict_model_bidirectional.joblib, "load", return_value=bundle) as load:
                first = predict_model_bidirectional._load_model_bundle(model_path)
                second = predict_model_bidirectional._load_model_bundle(model_path)
                self.assertIs(first, second)
                self.assertEqual(load.call_count, 1)

                predict_model_bidirectional.clear_model_cache(model_path)
                predict_model_bidirectional._load_model_bundle(model_path)
                self.assertEqual(load.call_count, 2)

    def test_bidirectional_model_without_validation_metadata_is_rejected(self):
        event = {"title": "test", "summary": "event"}
        with tempfile.TemporaryDirectory() as directory:
            model_dir = Path(directory)
            model_path = model_dir / "label_up_5m.joblib"
            model_path.touch()
            bundle = {"prep": IdentityPreprocessor(), "model": SingleClassModel(1)}
            predict_model_bidirectional.clear_model_cache()
            with (
                patch.object(predict_model_bidirectional, "MODEL_DIR", model_dir),
                patch.object(predict_model_bidirectional.joblib, "load", return_value=bundle),
            ):
                result = predict_model_bidirectional._predict_one(event, "label_up_5m")

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "model validation not passed")

    def test_positive_probability_uses_class_label_not_list_position(self):
        probabilities, classes, positive = predict_model_bidirectional._probability_payload(
            ReversedClassModel(), np.array([[0.0]]), prediction=1
        )
        self.assertEqual(probabilities, [0.8, 0.2])
        self.assertEqual(classes, [1, 0])
        self.assertEqual(positive, 0.8)

    def test_primary_predictor_consumer_supports_single_and_reversed_classes(self):
        self.assertEqual(
            predict_model.positive_probability(
                {"ok": True, "classes": [1], "proba": [1.0], "positive_proba": 1.0}
            ),
            1.0,
        )
        self.assertEqual(
            predict_model.positive_probability(
                {"ok": True, "classes": [1, 0], "proba": [0.75, 0.25]}
            ),
            0.75,
        )

    def test_primary_predictor_emits_single_class_positive_probability(self):
        event = {"title": "test", "summary": "event"}
        for label, expected in ((0, 0.0), (1, 1.0)):
            bundle = {
                "prep": IdentityPreprocessor(),
                "model": SingleClassModel(label),
                "_model_family": "test",
                "_model_path": "test.joblib",
            }
            with self.subTest(label=label), patch.object(
                predict_model, "_load_bundle", return_value=bundle
            ):
                result = predict_model._predict_one(event, "label_up_1h")
            self.assertEqual(result["classes"], [label])
            self.assertEqual(result["positive_proba"], expected)
            self.assertEqual(predict_model.positive_probability(result), expected)


if __name__ == "__main__":
    unittest.main()
