from predict_model_bidirectional import predict_event_bidirectional


def _positive_probability(result: dict) -> float:
    if not result or not result.get("ok"):
        return 0.0
    probabilities = result.get("proba") or [0.0, 0.0]
    return float(probabilities[1]) if len(probabilities) >= 2 else 0.0


def build_signal_summary(event: dict, market_brief: dict = None) -> dict:
    predictions = predict_event_bidirectional(event) if event else {}
    probability = {
        target: _positive_probability(predictions.get(target))
        for target in (
            "label_up_5m", "label_down_5m", "label_up_15m", "label_down_15m",
            "label_up_30m", "label_down_30m", "label_up_1h", "label_down_1h",
            "label_up_4h", "label_down_4h", "label_up_24h", "label_down_24h",
        )
    }

    ml_long_score = (
        probability["label_up_5m"] * 1.2
        + probability["label_up_30m"] * 1.1
        + probability["label_up_1h"] * 0.8
        + probability["label_up_4h"] * 0.6
        + probability["label_up_24h"] * 0.4
    )
    ml_short_score = (
        probability["label_down_15m"] * 1.3
        + probability["label_down_30m"] * 1.1
        + probability["label_down_5m"]
        + probability["label_down_1h"] * 0.8
        + probability["label_down_4h"] * 0.6
        + probability["label_down_24h"] * 0.4
    )

    intel_long = float((market_brief or {}).get("long_score", 0.0))
    intel_short = float((market_brief or {}).get("short_score", 0.0))
    long_score = intel_long * 0.75 + ml_long_score * 0.25
    short_score = intel_short * 0.75 + ml_short_score * 0.25

    intel_long_trigger = intel_long >= 6.0 and intel_long > intel_short + 1.5
    intel_short_trigger = intel_short >= 6.0 and intel_short > intel_long + 1.5
    ml_long_trigger = (
        probability["label_up_5m"] >= 0.70
        and probability["label_up_30m"] >= 0.60
        and probability["label_down_15m"] <= 0.35
    )
    ml_short_trigger = (
        probability["label_down_15m"] >= 0.75
        and probability["label_down_30m"] >= 0.60
        and probability["label_up_5m"] <= 0.35
    )

    if intel_short_trigger:
        bias, strength, trigger_source = "short", short_score, "live_intel"
    elif intel_long_trigger:
        bias, strength, trigger_source = "long", long_score, "live_intel"
    elif ml_short_trigger and short_score > long_score + 0.20:
        bias, strength, trigger_source = "short", short_score, "ml"
    elif ml_long_trigger and long_score > short_score + 0.20:
        bias, strength, trigger_source = "long", long_score, "ml"
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
            "long_trigger": bool(intel_long_trigger or ml_long_trigger),
            "short_trigger": bool(intel_short_trigger or ml_short_trigger),
            "trigger_source": trigger_source,
        },
    }
