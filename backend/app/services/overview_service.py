from performance import read_events, summarize
from market_intel import get_market_brief
from predict_model import predict_event


def get_overview_payload():
    events = read_events()
    summary = summarize(events)
    brief = get_market_brief(force_refresh=False)
    latest_event = (brief.get('top') or [{}])[0] if brief.get('top') else {}
    ml = predict_event(latest_event) if latest_event else {}
    return {'summary': summary, 'market_brief': brief, 'ml_pred': ml}
