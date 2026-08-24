from pathlib import Path

import joblib
import pandas as pd


MODEL_DIR = Path("data/models_bidirectional")
TARGETS = [
    "label_up_5m", "label_down_5m",
    "label_up_15m", "label_down_15m",
    "label_up_30m", "label_down_30m",
    "label_up_1h", "label_down_1h",
    "label_up_4h", "label_down_4h",
    "label_up_24h", "label_down_24h",
]


def _json_scalar(value):
    return value.item() if hasattr(value, "item") else value


def _probability_payload(model, transformed, prediction: int) -> tuple[list[float], list, float]:
    if not hasattr(model, "predict_proba"):
        probabilities = [float(1 - prediction), float(prediction)]
        return probabilities, [0, 1], float(prediction)

    probabilities = [float(value) for value in model.predict_proba(transformed)[0]]
    classes = [_json_scalar(value) for value in getattr(model, "classes_", range(len(probabilities)))]
    positive_index = next((index for index, label in enumerate(classes) if label == 1), None)
    positive_probability = probabilities[positive_index] if positive_index is not None else 0.0
    return probabilities, classes, float(positive_probability)


def positive_probability(result: dict) -> float:
    if not result or not result.get("ok"):
        return 0.0
    if "positive_proba" in result:
        return float(result["positive_proba"])

    probabilities = result.get("proba") or []
    classes = result.get("classes") or list(range(len(probabilities)))
    positive_index = next((index for index, label in enumerate(classes) if label == 1), None)
    return float(probabilities[positive_index]) if positive_index is not None else 0.0


def _predict_one(event: dict, target_col: str):
    model_path = MODEL_DIR / f"{target_col}.joblib"
    if not model_path.exists():
        return {"ok": False, "reason": "model not found"}

    bundle = joblib.load(model_path)
    prep = bundle["prep"]
    model = bundle["model"]
    row = {
        "text": f"{event.get('title', '')} {event.get('summary', '')}",
        "source": event.get("source"),
        "kind": event.get("kind"),
        "topic": event.get("topic"),
        "score": event.get("score", 0.0),
        "trust": event.get("trust", 0.0),
        "is_trump": event.get("is_trump", False),
        "is_scheduled": event.get("is_scheduled", False),
        "market_ret_1h": event.get("market_ret_1h", 0.0),
        "market_ret_4h": event.get("market_ret_4h", 0.0),
        "market_volatility_12h": event.get("market_volatility_12h", 0.0),
        "market_volume_ratio": event.get("market_volume_ratio", 0.0),
    }
    transformed = prep.transform(pd.DataFrame([row]))
    prediction = int(model.predict(transformed)[0])
    probabilities, classes, positive_proba = _probability_payload(model, transformed, prediction)
    return {
        "ok": True,
        "pred": prediction,
        "proba": probabilities,
        "classes": classes,
        "positive_proba": positive_proba,
        "model_path": str(model_path),
    }


def predict_event_bidirectional(event: dict):
    return {target: _predict_one(event, target) for target in TARGETS}
