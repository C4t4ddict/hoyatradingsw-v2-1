from market_intel import get_market_brief
from backend.app.services.ml_signal_service import build_signal_summary
from predict_model import predict_event


def get_intel_payload():
    brief = get_market_brief(force_refresh=False)
    latest_event = (brief.get('top') or [{}])[0] if brief.get('top') else {}
    ml = predict_event(latest_event) if latest_event else {}
    signal = build_signal_summary(latest_event, brief) if latest_event else {}
    return {
        'market_brief': brief,
        'latest_event': latest_event,
        'ml_pred': ml,
        'ml_signal': signal,
        'signal_quality': signal.get('quality_policy', {}),
    }
