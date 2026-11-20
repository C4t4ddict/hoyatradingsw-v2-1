from performance import read_events, summarize
from market_intel import get_market_brief
from backend.app.services.ml_signal_service import build_signal_summary
from backend.app.services.news_translation_service import localize_market_brief


def get_overview_payload():
    events = read_events()
    summary = summarize(events)
    brief = get_market_brief(force_refresh=False)
    latest_event = (brief.get('top') or [{}])[0] if brief.get('top') else {}
    ml_signal = build_signal_summary(latest_event, brief) if latest_event else {}
    return {'summary': summary, 'market_brief': localize_market_brief(brief, limit=6), 'ml_signal': ml_signal}
