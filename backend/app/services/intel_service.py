from market_intel import get_market_brief
from backend.app.services.ml_signal_service import build_signal_summary


def get_intel_payload():
    brief = get_market_brief(force_refresh=True)
    latest_event = (brief.get('top') or [{}])[0] if brief.get('top') else {}
    ml = build_signal_summary(latest_event, brief) if latest_event else {}
    return {'market_brief': brief, 'latest_event': latest_event, 'ml_signal': ml}
