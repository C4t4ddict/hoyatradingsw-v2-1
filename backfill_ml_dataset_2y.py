from datetime import datetime, timedelta, timezone
import hashlib
from urllib.parse import urlencode

import feedparser

from exchange import get_exchange
from market_intel import _clean, _event_score, _contains_any, TRUMP_WORDS, SCHEDULE_WORDS, _classify_topic
from ml_dataset import append_events, load_events, enrich_with_price_labels


def google_news_rss(query: str, after: str = None, before: str = None) -> str:
    q = query
    if after:
        q += f" after:{after}"
    if before:
        q += f" before:{before}"
    params = urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return f"https://news.google.com/rss/search?{params}"


def parse_entry_time(e):
    try:
        if hasattr(e, 'published_parsed') and e.published_parsed:
            return datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        published = getattr(e, 'published', '') or getattr(e, 'updated', '')
        if published:
            return datetime.fromisoformat(str(published).replace('Z', '+00:00')).astimezone(timezone.utc)
    except Exception:
        pass
    return None


def iter_month_ranges(months: int = 24):
    now = datetime.now(timezone.utc)
    end = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    ranges = []
    cur = end
    for _ in range(months):
        start = (cur - timedelta(days=32)).replace(day=1)
        ranges.append((start.date().isoformat(), cur.date().isoformat()))
        cur = start
    return list(reversed(ranges))


def build_queries():
    return [
        'bitcoin OR btc OR ethereum OR solana crypto market',
        'bitcoin etf sec crypto regulation',
        'bitcoin fed rate inflation cpi fomc crypto',
        'trump bitcoin OR trump crypto OR trump tariff bitcoin',
        'stablecoin regulation sec treasury bitcoin',
        'binance bitcoin listing delisting investigation',
        'crypto hack exploit exchange bankruptcy bitcoin',
        'geopolitics war sanctions oil bitcoin crypto',
    ]


def main():
    rows = []
    month_ranges = iter_month_ranges(24)
    queries = build_queries()

    for after, before in month_ranges:
        for q in queries:
            feed = feedparser.parse(google_news_rss(q, after=after, before=before))
            for e in (feed.entries or [])[:100]:
                title = _clean(getattr(e, 'title', ''))
                summary = _clean(getattr(e, 'summary', ''))
                link = getattr(e, 'link', '')
                published = getattr(e, 'published', '')
                dt = parse_entry_time(e)
                if dt is None:
                    continue
                score = _event_score(title, summary, 0.8)
                if score == 0.0:
                    continue
                event_id = hashlib.sha1(f"gnews2y|{q}|{title}|{published}|{link}".encode('utf-8')).hexdigest()
                rows.append({
                    'event_id': event_id,
                    'event_time': dt.isoformat(),
                    'source': 'GoogleNews2Y',
                    'kind': 'news',
                    'topic': _classify_topic(title, summary),
                    'title': title,
                    'summary': summary,
                    'link': link,
                    'published': published,
                    'score': score,
                    'trust': 0.8,
                    'is_trump': _contains_any(f"{title} {summary}", TRUMP_WORDS) > 0,
                    'is_scheduled': _contains_any(f"{title} {summary}", SCHEDULE_WORDS) > 0,
                })

    written = append_events(rows)
    print('collected_rows=', len(rows), 'written=', written)

    ex = get_exchange(read_only=True, market_type='swap')
    def fetch_range(symbol: str, timeframe: str, days: int, limit_per_call: int = 1000):
        tf_minutes = {'5m': 5, '15m': 15, '30m': 30, '1h': 60}[timeframe]
        since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
        end = int(datetime.now(timezone.utc).timestamp() * 1000)
        rows = []
        cur = since
        while cur < end:
            chunk = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=cur, limit=limit_per_call)
            if not chunk:
                break
            rows.extend(chunk)
            last_ts = chunk[-1][0]
            nxt = last_ts + tf_minutes * 60 * 1000
            if nxt <= cur:
                break
            cur = nxt
            if len(chunk) < limit_per_call:
                break
        seen = set()
        out = []
        for r in rows:
            if r[0] in seen:
                continue
            seen.add(r[0])
            out.append(r)
        return out

    candles_1h = fetch_range('BTC/USDT:USDT', '1h', 730)
    candles_30m = fetch_range('BTC/USDT:USDT', '30m', 730)
    candles_15m = fetch_range('BTC/USDT:USDT', '15m', 730)
    candles_5m = fetch_range('BTC/USDT:USDT', '5m', 730)
    df = enrich_with_price_labels(load_events(), candles_1h, candles_5m, candles_15m, candles_30m)
    print('candles_1h=', len(candles_1h))
    print('candles_30m=', len(candles_30m))
    print('candles_15m=', len(candles_15m))
    print('candles_5m=', len(candles_5m))
    print('dataset_rows=', len(df))


if __name__ == '__main__':
    main()
