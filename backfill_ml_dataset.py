from datetime import datetime, timedelta, timezone
import hashlib

import feedparser

from exchange import get_exchange
from market_intel import _iter_sources, _clean, _event_score, _contains_any, TRUMP_WORDS, SCHEDULE_WORDS, _classify_topic
from ml_dataset import append_events, load_events, enrich_with_price_labels


def main():
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    rows = []
    for src in _iter_sources():
        try:
            feed = feedparser.parse(src.url)
            for e in (feed.entries or [])[:200]:
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
                if dt < cutoff:
                    continue
                score = _event_score(title, summary, src.trust)
                if score == 0.0:
                    continue
                event_id = hashlib.sha1(f"{src.name}|{title}|{published}|{link}".encode('utf-8')).hexdigest()
                rows.append({
                    'event_id': event_id,
                    'event_time': dt.isoformat(),
                    'source': src.name,
                    'kind': src.kind,
                    'topic': _classify_topic(title, summary),
                    'title': title,
                    'summary': summary,
                    'link': link,
                    'published': published,
                    'score': score,
                    'trust': src.trust,
                    'is_trump': _contains_any(f"{title} {summary}", TRUMP_WORDS) > 0,
                    'is_scheduled': _contains_any(f"{title} {summary}", SCHEDULE_WORDS) > 0,
                })
        except Exception:
            continue

    written = append_events(rows)
    print('backfill_rows=', len(rows), 'written=', written)

    ex = get_exchange(read_only=True, market_type='swap')
    candles = ex.fetch_ohlcv('BTC/USDT:USDT', timeframe='1h', limit=24 * 365)
    df = enrich_with_price_labels(load_events(), candles)
    print('dataset_rows=', len(df))


if __name__ == '__main__':
    main()
