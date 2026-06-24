from predict_model_bidirectional import predict_event_bidirectional


def _p(result: dict) -> float:
    if not result or not result.get('ok'):
        return 0.0
    proba = result.get('proba') or [0.0, 0.0]
    if len(proba) < 2:
        return 0.0
    return float(proba[1])


def build_signal_summary(event: dict, market_brief: dict = None) -> dict:
    preds = predict_event_bidirectional(event) if event else {}

    up_5m = _p(preds.get('label_up_5m'))
    down_5m = _p(preds.get('label_down_5m'))
    up_15m = _p(preds.get('label_up_15m'))
    down_15m = _p(preds.get('label_down_15m'))
    up_30m = _p(preds.get('label_up_30m'))
    down_30m = _p(preds.get('label_down_30m'))
    up_1h = _p(preds.get('label_up_1h'))
    down_1h = _p(preds.get('label_down_1h'))
    up_4h = _p(preds.get('label_up_4h'))
    down_4h = _p(preds.get('label_down_4h'))
    up_24h = _p(preds.get('label_up_24h'))
    down_24h = _p(preds.get('label_down_24h'))

    ml_long_score = (up_5m * 1.2) + (up_30m * 1.1) + (up_1h * 0.8) + (up_4h * 0.6) + (up_24h * 0.4)
    ml_short_score = (down_15m * 1.3) + (down_30m * 1.1) + (down_5m * 1.0) + (down_1h * 0.8) + (down_4h * 0.6) + (down_24h * 0.4)

    intel_long = float((market_brief or {}).get('long_score', 0.0))
    intel_short = float((market_brief or {}).get('short_score', 0.0))

    long_score = intel_long * 0.75 + ml_long_score * 0.25
    short_score = intel_short * 0.75 + ml_short_score * 0.25

    intel_long_trigger = intel_long >= 6.0 and intel_long > intel_short + 1.5
    intel_short_trigger = intel_short >= 6.0 and intel_short > intel_long + 1.5
    ml_long_trigger = up_5m >= 0.70 and up_30m >= 0.60 and down_15m <= 0.35
    ml_short_trigger = down_15m >= 0.75 and down_30m >= 0.60 and up_5m <= 0.35

    if intel_short_trigger:
        bias = 'short'
        strength = short_score
        trigger_source = 'live_intel'
    elif intel_long_trigger:
        bias = 'long'
        strength = long_score
        trigger_source = 'live_intel'
    elif ml_short_trigger and short_score > long_score + 0.20:
        bias = 'short'
        strength = short_score
        trigger_source = 'ml'
    elif ml_long_trigger and long_score > short_score + 0.20:
        bias = 'long'
        strength = long_score
        trigger_source = 'ml'
    else:
        if long_score > short_score + 0.75:
            bias = 'lean_long'
            strength = long_score
            trigger_source = 'combined'
        elif short_score > long_score + 0.75:
            bias = 'lean_short'
            strength = short_score
            trigger_source = 'combined'
        else:
            bias = 'neutral'
            strength = max(long_score, short_score)
            trigger_source = 'none'

    return {
        'predictions': preds,
        'scores': {
            'intel_long_score': round(intel_long, 4),
            'intel_short_score': round(intel_short, 4),
            'ml_long_score': round(ml_long_score, 4),
            'ml_short_score': round(ml_short_score, 4),
            'long_score': round(long_score, 4),
            'short_score': round(short_score, 4),
            'up_5m': round(up_5m, 4),
            'down_5m': round(down_5m, 4),
            'up_15m': round(up_15m, 4),
            'down_15m': round(down_15m, 4),
            'up_30m': round(up_30m, 4),
            'down_30m': round(down_30m, 4),
            'up_1h': round(up_1h, 4),
            'down_1h': round(down_1h, 4),
            'up_4h': round(up_4h, 4),
            'down_4h': round(down_4h, 4),
            'up_24h': round(up_24h, 4),
            'down_24h': round(down_24h, 4),
        },
        'decision': {
            'bias': bias,
            'strength': round(strength, 4),
            'long_trigger': bool(intel_long_trigger or ml_long_trigger),
            'short_trigger': bool(intel_short_trigger or ml_short_trigger),
            'trigger_source': trigger_source,
        }
    }
