from datetime import datetime, timedelta, timezone
import hashlib
from urllib.parse import urlencode

import feedparser

from market_intel import _clean, _event_score, _contains_any, TRUMP_WORDS, SCHEDULE_WORDS, _classify_topic
from ml_dataset import append_events


def google_news_rss(query: str, after: str = None, before: str = None) -> str:
    q = query
    if after:
        q += f' after:{after}'
    if before:
        q += f' before:{before}'
    params = urlencode({'q': q, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
    return f'https://news.google.com/rss/search?{params}'


def parse_entry_time(e):
    try:
        if hasattr(e, 'published_parsed') and e.published_parsed:
            return datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
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


def push_rows(rows, source_name, trust, kind='news'):
    out = []
    for e in rows:
        title = _clean(getattr(e, 'title', ''))
        summary = _clean(getattr(e, 'summary', ''))
        link = getattr(e, 'link', '')
        published = getattr(e, 'published', '')
        dt = parse_entry_time(e)
        if dt is None:
            continue
        score = _event_score(title, summary, trust)
        if score == 0.0:
            continue
        event_id = hashlib.sha1(f'{source_name}|{title}|{published}|{link}'.encode('utf-8')).hexdigest()
        out.append({
            'event_id': event_id,
            'event_time': dt.isoformat(),
            'source': source_name,
            'kind': kind,
            'topic': _classify_topic(title, summary),
            'title': title,
            'summary': summary,
            'link': link,
            'published': published,
            'score': score,
            'trust': trust,
            'is_trump': _contains_any(f'{title} {summary}', TRUMP_WORDS) > 0,
            'is_scheduled': _contains_any(f'{title} {summary}', SCHEDULE_WORDS) > 0,
        })
    return out


def main():
    rows = []

    # High trust current/history-ish feeds
    static_feeds = [
        ('SEC', 'https://www.sec.gov/news/pressreleases.rss', 0.98, 'official'),
        ('Fed', 'https://www.federalreserve.gov/feeds/press_all.xml', 1.0, 'official'),
        ('Cointelegraph', 'https://cointelegraph.com/rss', 0.82, 'news'),
        ('TheBlock', 'https://www.theblock.co/rss.xml', 0.85, 'news'),
    ]
    for name, url, trust, kind in static_feeds:
        feed = feedparser.parse(url)
        rows.extend(push_rows(feed.entries or [], name, trust, kind))

    # Google News monthly backfill queries
    queries = [
        'trump bitcoin OR trump crypto OR trump tariff bitcoin',
        'bitcoin etf sec crypto regulation',
        'bitcoin fed fomc inflation',
        'bitcoin sanctions war oil crypto',
        'binance investigation hack stablecoin sec',
        'iran us war bitcoin oil price',
        'iran attack bitcoin geopolitical risk',
        'strait of hormuz bitcoin oil shipping risk',
        'middle east conflict bitcoin risk off',
        'oil spike inflation bitcoin selloff',
        'sanctions tariff macro bitcoin volatility',
    ]
    for after, before in iter_month_ranges(24):
        for q in queries:
            feed = feedparser.parse(google_news_rss(q, after=after, before=before))
            rows.extend(push_rows(feed.entries or [], 'GoogleNewsPlus', 0.8, 'news'))

    # Trump's Truth archive RSS with date ranges
    for after, before in iter_month_ranges(24):
        url = f'https://www.trumpstruth.org/rss?start_date={after}&end_date={before}'
        feed = feedparser.parse(url)
        rows.extend(push_rows(feed.entries or [], 'TrumpsTruth', 0.9, 'tweet'))

    written = append_events(rows)
    print('plus_rows=', len(rows), 'written=', written)


if __name__ == '__main__':
    main()
