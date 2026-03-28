from datetime import datetime, timedelta, timezone
import hashlib
from urllib.parse import urlencode

import feedparser
import pandas as pd

from exchange import get_exchange
from market_intel import _clean, _event_score, _contains_any, TRUMP_WORDS, SCHEDULE_WORDS, _classify_topic
from ml_dataset import append_events, load_events, enrich_with_price_labels


def google_news_rss(query: str) -> str:
    q = urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return f"https://news.google.com/rss/search?{q}"


def detect_price_shocks():
    ex = get_exchange(read_only=True, market_type='swap')
    candles = ex.fetch_ohlcv('BTC/USDT:USDT', timeframe='1h', limit=24 * 365)
    cdf = pd.DataFrame(candles, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    cdf['ret_pct'] = cdf['close'].pct_change() * 100.0
    shocks = cdf[cdf['ret_pct'].abs() >= 3.0].copy()
    return shocks, candles


def build_queries(ts_ms: int):
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    d = dt.strftime('%Y-%m-%d')
    return [
        f'bitcoin {d} war OR sanctions OR conflict',
        f'bitcoin {d} fed OR cpi OR inflation OR rate',
        f'bitcoin {d} trump OR white house OR election',
        f'bitcoin {d} etf OR sec OR treasury',
        f'btc {d} crash OR rally OR surge OR dump',
    ]


def main():
    shocks, candles = detect_price_shocks()
    rows = []
    for _, r in shocks.tail(80).iterrows():
        for q in build_queries(int(r['ts'])):
            try:
                feed = feedparser.parse(google_news_rss(q))
                for e in (feed.entries or [])[:10]:
                    title = _clean(getattr(e, 'title', ''))
                    summary = _clean(getattr(e, 'summary', ''))
                    link = getattr(e, 'link', '')
                    published = getattr(e, 'published', '')
                    try:
                        if hasattr(e, 'published_parsed') and e.published_parsed:
                            dt = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
                        else:
                            dt = datetime.now(timezone.utc)
                    except Exception:
                        dt = datetime.now(timezone.utc)
                    score = _event_score(title, summary, 0.72)
                    if score == 0.0:
                        continue
                    event_id = hashlib.sha1(f"shock|{q}|{title}|{published}|{link}".encode('utf-8')).hexdigest()
                    rows.append({
                        'event_id': event_id,
                        'event_time': dt.isoformat(),
                        'source': f'GoogleNewsShock:{q[:40]}',
                        'kind': 'news',
                        'topic': _classify_topic(title, summary),
                        'title': title,
                        'summary': summary,
                        'link': link,
                        'published': published,
                        'score': score,
                        'trust': 0.72,
                        'is_trump': _contains_any(f"{title} {summary}", TRUMP_WORDS) > 0,
                        'is_scheduled': _contains_any(f"{title} {summary}", SCHEDULE_WORDS) > 0,
                    })
            except Exception:
                continue

    written = append_events(rows)
    print('shock_rows=', len(rows), 'written=', written)
    df = enrich_with_price_labels(load_events(), candles)
    print('dataset_rows=', len(df))


if __name__ == '__main__':
    main()
