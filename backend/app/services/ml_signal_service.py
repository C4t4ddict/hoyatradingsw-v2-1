import os

from predict_model_bidirectional import positive_probability, predict_event_bidirectional
from signal_quality import SignalQualityStore, derive_signal_policy


def build_signal_summary(
    event: dict,
    market_brief: dict = None,
    quality_store: SignalQualityStore = None,
    regime: dict = None,
    market_pattern: dict = None,
) -> dict:
    predictions = predict_event_bidirectional(event) if event else {}
    event_model_ready = bool(predictions) and all(
        predictions.get(target, {}).get("ok") is True
        for target in (
            "label_up_5m", "label_down_5m", "label_up_15m", "label_down_15m",
            "label_up_30m", "label_down_30m", "label_up_1h", "label_down_1h",
            "label_up_4h", "label_down_4h", "label_up_24h", "label_down_24h",
        )
    )
    pattern = market_pattern or {}
    pattern_model_ready = pattern.get("ready") is True
    model_ready = event_model_ready or pattern_model_ready
    probability = {
        target: positive_probability(predictions.get(target))
        for target in (
            "label_up_5m", "label_down_5m", "label_up_15m", "label_down_15m",
            "label_up_30m", "label_down_30m", "label_up_1h", "label_down_1h",
            "label_up_4h", "label_down_4h", "label_up_24h", "label_down_24h",
        )
    }

    event_long_score = (
        probability["label_up_5m"] * 1.2
        + probability["label_up_30m"] * 1.1
        + probability["label_up_1h"] * 0.8
        + probability["label_up_4h"] * 0.6
        + probability["label_up_24h"] * 0.4
    )
    event_short_score = (
        probability["label_down_15m"] * 1.3
        + probability["label_down_30m"] * 1.1
        + probability["label_down_5m"]
        + probability["label_down_1h"] * 0.8
        + probability["label_down_4h"] * 0.6
        + probability["label_down_24h"] * 0.4
    )
    pattern_long_score = float(pattern.get("long_score", 0.0))
    pattern_short_score = float(pattern.get("short_score", 0.0))
    intel_long = float((market_brief or {}).get("long_score", 0.0))
    intel_short = float((market_brief or {}).get("short_score", 0.0))
    store = quality_store or SignalQualityStore(os.getenv("SIGNAL_QUALITY_PATH", "data/signal_quality.sqlite3"))
    event_quality = store.summary("ml")
    pattern_quality = store.summary("pattern") if pattern_model_ready else {"enabled": False}
    event_component_enabled = event_model_ready and bool(event_quality.get("enabled"))
    pattern_component_enabled = pattern_model_ready and bool(pattern_quality.get("enabled"))
    if event_component_enabled and pattern_component_enabled:
        weakest_ic = min(
            (float(event_quality.get("information_coefficient", 0.0)), float(pattern_quality.get("information_coefficient", 0.0))),
            key=abs,
        )
        ml_quality = {
            "enabled": True,
            "observations": min(int(event_quality.get("observations", 0)), int(pattern_quality.get("observations", 0))),
            "brier_score": max(float(event_quality.get("brier_score", 1.0)), float(pattern_quality.get("brier_score", 1.0))),
            "accuracy": min(float(event_quality.get("accuracy", 0.0)), float(pattern_quality.get("accuracy", 0.0))),
            "information_coefficient": weakest_ic,
            "components": {"event": event_quality, "pattern": pattern_quality},
        }
    elif event_component_enabled:
        ml_quality = event_quality
    elif pattern_component_enabled:
        ml_quality = pattern_quality
    else:
        ml_quality = {**event_quality, "enabled": False, "readiness_blocked": True}
    ml_long_score = (event_long_score if event_component_enabled else 0.0) + (pattern_long_score * 2.0 if pattern_component_enabled else 0.0)
    ml_short_score = (event_short_score if event_component_enabled else 0.0) + (pattern_short_score * 2.0 if pattern_component_enabled else 0.0)
    policy = derive_signal_policy(store.summary("intel"), ml_quality, regime=regime)
    intel_weight = policy["weights"]["intel"]
    ml_weight = policy["weights"]["ml"]
    exposure = policy["exposure_multiplier"]
    long_score = (intel_long * intel_weight + ml_long_score * ml_weight) * exposure
    short_score = (intel_short * intel_weight + ml_short_score * ml_weight) * exposure

    intel_long_trigger = intel_long >= 6.0 and intel_long > intel_short + 1.5
    intel_short_trigger = intel_short >= 6.0 and intel_short > intel_long + 1.5
    ml_long_trigger = (
        event_component_enabled
        and probability["label_up_5m"] >= 0.70
        and probability["label_up_30m"] >= 0.60
        and probability["label_down_15m"] <= 0.35
    )
    ml_short_trigger = (
        event_component_enabled
        and probability["label_down_15m"] >= 0.75
        and probability["label_down_30m"] >= 0.60
        and probability["label_up_5m"] <= 0.35
    )
    pattern_long_trigger = pattern_component_enabled and pattern_long_score >= 0.60 and pattern_long_score > pattern_short_score + 0.10
    pattern_short_trigger = pattern_component_enabled and pattern_short_score >= 0.60 and pattern_short_score > pattern_long_score + 0.10

    if not policy["signals_enabled"]:
        bias, strength, trigger_source = "neutral", 0.0, "quality_gate"
    elif intel_short_trigger and intel_weight > 0:
        bias, strength, trigger_source = "short", short_score, "live_intel"
    elif intel_long_trigger and intel_weight > 0:
        bias, strength, trigger_source = "long", long_score, "live_intel"
    elif ml_short_trigger and ml_weight > 0 and short_score > long_score + 0.20:
        bias, strength, trigger_source = "short", short_score, "ml"
    elif ml_long_trigger and ml_weight > 0 and long_score > short_score + 0.20:
        bias, strength, trigger_source = "long", long_score, "ml"
    elif pattern_short_trigger and ml_weight > 0 and short_score > long_score + 0.20:
        bias, strength, trigger_source = "short", short_score, "market_pattern"
    elif pattern_long_trigger and ml_weight > 0 and long_score > short_score + 0.20:
        bias, strength, trigger_source = "long", long_score, "market_pattern"
    elif long_score > short_score + 0.75:
        bias, strength, trigger_source = "lean_long", long_score, "combined"
    elif short_score > long_score + 0.75:
        bias, strength, trigger_source = "lean_short", short_score, "combined"
    else:
        bias, strength, trigger_source = "neutral", max(long_score, short_score), "none"

    score_payload = {
        "intel_long_score": intel_long,
        "intel_short_score": intel_short,
        "ml_long_score": ml_long_score,
        "ml_short_score": ml_short_score,
        "pattern_long_score": pattern_long_score,
        "pattern_short_score": pattern_short_score,
        "long_score": long_score,
        "short_score": short_score,
        "up_5m": probability["label_up_5m"],
        "down_5m": probability["label_down_5m"],
        "up_15m": probability["label_up_15m"],
        "down_15m": probability["label_down_15m"],
        "up_30m": probability["label_up_30m"],
        "down_30m": probability["label_down_30m"],
        "up_1h": probability["label_up_1h"],
        "down_1h": probability["label_down_1h"],
        "up_4h": probability["label_up_4h"],
        "down_4h": probability["label_down_4h"],
        "up_24h": probability["label_up_24h"],
        "down_24h": probability["label_down_24h"],
    }
    return {
        "predictions": predictions,
        "scores": {key: round(value, 4) for key, value in score_payload.items()},
        "decision": {
            "bias": bias,
            "strength": round(strength, 4),
            "long_trigger": bool(policy["signals_enabled"] and ((intel_long_trigger and intel_weight > 0) or ((ml_long_trigger or pattern_long_trigger) and ml_weight > 0))),
            "short_trigger": bool(policy["signals_enabled"] and ((intel_short_trigger and intel_weight > 0) or ((ml_short_trigger or pattern_short_trigger) and ml_weight > 0))),
            "trigger_source": trigger_source,
            "position_size_multiplier": exposure,
        },
        "quality_policy": policy,
        "model_ready": model_ready,
        "event_model_ready": event_model_ready,
        "pattern_model_ready": pattern_model_ready,
        "event_component_enabled": event_component_enabled,
        "pattern_component_enabled": pattern_component_enabled,
        "market_pattern": pattern,
    }
