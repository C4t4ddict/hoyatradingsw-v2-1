from pathlib import Path
import joblib
import pandas as pd

MODEL_DIR = Path("data/models")
MODEL_DIR_XGB_SHORT = Path("data/models_xgb_short")


def _json_scalar(value):
    return value.item() if hasattr(value, "item") else value


def positive_probability(result: dict) -> float:
    if not result or not result.get("ok"):
        return 0.0
    if "positive_proba" in result:
        return float(result["positive_proba"])

    probabilities = result.get("proba") or []
    classes = result.get("classes") or list(range(len(probabilities)))
    positive_index = next((index for index, label in enumerate(classes) if label == 1), None)
    return float(probabilities[positive_index]) if positive_index is not None else 0.0


def _load_bundle(target_col: str):
    # 정책: 5m/15m은 XGBoost short 전용, 1h/4h/24h는 기존 안정 모델 유지
    search_dirs = [MODEL_DIR_XGB_SHORT] if target_col in ["label_up_5m", "label_up_15m"] else [MODEL_DIR]
    for base in search_dirs:
        model_path = base / f"{target_col}.joblib"
        if model_path.exists():
            bundle = joblib.load(model_path)
            bundle["_model_path"] = str(model_path)
            bundle["_model_family"] = "xgboost-short" if base == MODEL_DIR_XGB_SHORT else "sklearn-stable"
            return bundle
    return None


def _predict_one(event: dict, target_col: str) -> dict:
    bundle = _load_bundle(target_col)
    if bundle is None:
        return {"ok": False, "reason": "model not found"}

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
    X = pd.DataFrame([row])
    Xt = prep.transform(X)
    if hasattr(Xt, "toarray"):
        Xt = Xt.toarray()
    if hasattr(model, "predict_proba"):
        proba = [float(value) for value in model.predict_proba(Xt)[0]]
        classes = [_json_scalar(value) for value in getattr(model, "classes_", range(len(proba)))]
        positive_index = next((index for index, label in enumerate(classes) if label == 1), None)
        positive_proba = proba[positive_index] if positive_index is not None else 0.0
    else:
        score = float(model.predict(Xt)[0])
        proba = [1.0 - score, score]
        classes = [0, 1]
        positive_proba = score
    pred = int(model.predict(Xt)[0])
    return {
        "ok": True,
        "pred_up": pred,
        "proba": proba,
        "classes": classes,
        "positive_proba": float(positive_proba),
        "model_family": bundle.get("_model_family"),
        "model_path": bundle.get("_model_path"),
    }


def predict_event(event: dict) -> dict:
    out = {}
    for target_col in ["label_up_5m", "label_up_15m", "label_up_1h", "label_up_4h", "label_up_24h"]:
        out[target_col] = _predict_one(event, target_col)
    return out
