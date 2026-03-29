from market_intel import get_market_brief
from predict_model import predict_event


def get_intel_payload():
    brief = get_market_brief(force_refresh=True)
    latest_event = (brief.get('top') or [{}])[0] if brief.get('top') else {}
    ml = predict_event(latest_event) if latest_event else {}
    return {'market_brief': brief, 'latest_event': latest_event, 'ml_pred': ml}
