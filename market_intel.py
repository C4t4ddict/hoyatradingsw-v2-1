import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
import hashlib
from urllib.parse import quote, urlencode

import feedparser

CACHE_PATH = Path(os.getenv('MARKET_INTEL_CACHE_PATH', 'data/market_intel_cache.json'))
CACHE_TTL_SEC = int(os.getenv('MARKET_INTEL_CACHE_TTL_SEC', '300'))


@dataclass
class Source:
    name: str
    url: str
    kind: str  # news | official | tweet
    trust: float
    tier: str = 'standard'  # elite | strong | standard


DEFAULT_SOURCES: List[Source] = [
    Source('Cointelegraph', 'https://cointelegraph.com/rss', 'news', 0.82, 'strong'),
    Source('The Block', 'https://www.theblock.co/rss.xml', 'news', 0.85, 'strong'),
    Source('Federal Reserve Press', 'https://www.federalreserve.gov/feeds/press_all.xml', 'official', 1.0, 'elite'),
    Source('SEC Press', 'https://www.sec.gov/news/pressreleases.rss', 'official', 0.98, 'elite'),
]

BULLISH = ['etf inflow','approval','rate cut','easing','institutional buy','adoption','record high','short squeeze','accumulation','halving','bullish','surge','beat']
BEARISH = ['hack','lawsuit','ban','crackdown','rate hike','inflation spike','liquidation','outflow','recession','bankruptcy','bearish','dump','sell-off','sanction']
BTC_WORDS = ['bitcoin','btc','crypto','etf','halving','coinbase','binance','stablecoin']
MACRO_WORDS = ['fed','fomc','cpi','ppi','nfp','inflation','yield','bond','dxy','rate cut','rate hike','treasury','liquidity','recession']
GEO_WORDS = ['war','tariff','sanction','china','taiwan','russia','ukraine','middle east','oil','election','white house','geopolitical','hormuz','strait of hormuz','shipping lane','shipping route']
TRUMP_WORDS = ['trump','donald trump','trump administration','white house','truth social']
SCHEDULE_WORDS = ['fomc','cpi','ppi','nfp','rate decision','press conference','speech','minutes','scheduled','calendar']


def _contains_any(text: str, words: List[str]) -> int:
    t = text.lower()
    return sum(1 for w in words if w in t)


def _clean(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '')).strip()


def _parse_entry_time(e) -> datetime:
    try:
        if hasattr(e, 'published_parsed') and e.published_parsed:
            return datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
    except Exception:
        pass
    for key in ['published', 'updated']:
        try:
            value = getattr(e, key, '')
            if value:
                return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(timezone.utc)
        except Exception:
            continue
    return datetime.now(timezone.utc)


def _classify_topic(title: str, summary: str) -> str:
    text = f'{title} {summary}'.lower()
    btc_hits = _contains_any(text, BTC_WORDS)
    macro_hits = _contains_any(text, MACRO_WORDS)
    geo_hits = _contains_any(text, GEO_WORDS)
    mx = max(btc_hits, macro_hits, geo_hits)
    if mx <= 0:
        return 'other'
    if mx == macro_hits:
        return 'macro'
    if mx == geo_hits:
        return 'geopolitics'
    return 'crypto'


def _reason_tags(title: str, summary: str) -> List[str]:
    text = f'{title} {summary}'.lower()
    tags = []
    if _contains_any(text, TRUMP_WORDS):
        tags.append('trump')
    if _contains_any(text, SCHEDULE_WORDS):
        tags.append('scheduled')
    if _contains_any(text, MACRO_WORDS):
        tags.append('macro')
    if _contains_any(text, GEO_WORDS):
        tags.append('geopolitics')
    if _contains_any(text, BTC_WORDS):
        tags.append('crypto')
    if _contains_any(text, BULLISH):
        tags.append('bullish_kw')
    if _contains_any(text, BEARISH):
        tags.append('bearish_kw')
    return tags[:6]


def _recency_weight(event_time: datetime) -> float:
    age_hours = max(0.0, (datetime.now(timezone.utc) - event_time).total_seconds() / 3600.0)
    if age_hours <= 2:
        return 1.25
    if age_hours <= 6:
        return 1.15
    if age_hours <= 24:
        return 1.0
    if age_hours <= 72:
        return 0.8
    return 0.6


def _tier_weight(tier: str) -> float:
    return {'elite': 1.15, 'strong': 1.05, 'standard': 1.0}.get(tier, 1.0)


def _event_direction_scores(title: str, summary: str, trust: float, event_time: datetime = None, tier: str = 'standard'):
    text = f'{title} {summary}'.lower()
    relevance = _contains_any(text, BTC_WORDS) + _contains_any(text, MACRO_WORDS) + _contains_any(text, GEO_WORDS)
    if relevance == 0:
        return 0.0, 0.0

    bullish_hits = _contains_any(text, BULLISH)
    bearish_hits = _contains_any(text, BEARISH)
    trump_hits = _contains_any(text, TRUMP_WORDS)
    schedule_hits = _contains_any(text, SCHEDULE_WORDS)

    recency = _recency_weight(event_time or datetime.now(timezone.utc))
    tier_w = _tier_weight(tier)
    base = trust * tier_w * recency * min(2.2, 0.8 + relevance * 0.22)

    long_score = float(bullish_hits) * base
    short_score = float(bearish_hits) * base

    if bullish_hits == 0 and bearish_hits == 0 and (trump_hits > 0 or schedule_hits > 0):
        long_score += 0.2 * base
        short_score += 0.2 * base

    if trump_hits > 0:
        long_score *= min(1.4, 1.0 + trump_hits * 0.12)
        short_score *= min(1.8, 1.0 + trump_hits * 0.2)

    if schedule_hits > 0:
        long_score *= min(1.35, 1.0 + schedule_hits * 0.1)
        short_score *= min(1.35, 1.0 + schedule_hits * 0.1)

    return long_score, short_score


def _event_score(title: str, summary: str, trust: float, event_time: datetime = None, tier: str = 'standard') -> float:
    long_score, short_score = _event_direction_scores(title, summary, trust, event_time, tier)
    return long_score - short_score


def _google_news_rss(query: str) -> str:
    q = urlencode({'q': query, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
    return f'https://news.google.com/rss/search?{q}'


def _iter_sources() -> List[Source]:
    extra = os.getenv('MARKET_INTEL_EXTRA_RSS', '').strip()
    tweet_rss = os.getenv('MARKET_INTEL_TWEET_RSS', '').strip()
    items = list(DEFAULT_SOURCES)

    auto_queries = [
        'bitcoin fed rate decision',
        'bitcoin etf inflow outflow',
        'trump bitcoin OR trump crypto',
        'bitcoin war oil sanctions',
        'bitcoin geopolitical risk',
        'btc risk off dollar yield',
        'bitcoin strait of hormuz oil shipping risk',
        'bitcoin hormuz geopolitical oil spike',
    ]
    for q in auto_queries:
        items.append(Source(name=f'GoogleNews:{q}', url=_google_news_rss(q), kind='news', trust=0.78, tier='standard'))

    if extra:
        for u in extra.split(','):
            u = u.strip()
            if u:
                items.append(Source(name=f'Custom:{quote(u)[:20]}', url=u, kind='news', trust=0.7, tier='standard'))

    if tweet_rss:
        chunks = [c.strip() for c in tweet_rss.split(';') if c.strip()]
        for c in chunks:
            try:
                name, url, trust = [x.strip() for x in c.split('|', 2)]
                items.append(Source(name=name, url=url, kind='tweet', trust=float(trust), tier='strong'))
            except Exception:
                continue

    return items


def fetch_items(per_source: int = 8) -> List[Dict]:
    rows: List[Dict] = []
    dedupe = set()
    for src in _iter_sources():
        try:
            feed = feedparser.parse(src.url)
            for e in (feed.entries or [])[:per_source]:
                title = _clean(getattr(e, 'title', ''))
                summary = _clean(getattr(e, 'summary', ''))
                link = getattr(e, 'link', '')
                published = getattr(e, 'published', '')
                event_time = _parse_entry_time(e)
                score = _event_score(title, summary, src.trust, event_time, src.tier)
                if score == 0.0:
                    continue
                topic = _classify_topic(title, summary)
                dedupe_key = f"{title.lower()}|{topic}|{published[:16]}"
                if dedupe_key in dedupe:
                    continue
                dedupe.add(dedupe_key)
                event_id = hashlib.sha1(f'{src.name}|{title}|{published}|{link}'.encode('utf-8')).hexdigest()
                long_event_score, short_event_score = _event_direction_scores(title, summary, src.trust, event_time, src.tier)
                rows.append({
                    'event_id': event_id,
                    'event_time': event_time.isoformat(),
                    'source': src.name,
                    'kind': src.kind,
                    'topic': topic,
                    'title': title,
                    'summary': summary,
                    'link': link,
                    'published': published,
                    'score': score,
                    'long_event_score': round(long_event_score, 4),
                    'short_event_score': round(short_event_score, 4),
                    'trust': src.trust,
                    'tier': src.tier,
                    'reason_tags': _reason_tags(title, summary),
                    'is_trump': _contains_any(f'{title} {summary}', TRUMP_WORDS) > 0,
                    'is_scheduled': _contains_any(f'{title} {summary}', SCHEDULE_WORDS) > 0,
                })
        except Exception:
            continue

    rows.sort(key=lambda x: abs(float(x.get('score', 0.0))), reverse=True)
    return rows


def summarize_market(rows: List[Dict]) -> Dict:
    if not rows:
        return {'score': 0.0, 'bias': 'neutral', 'confidence': 0.0, 'count': 0, 'count_news': 0, 'count_official': 0, 'count_tweet': 0, 'updated_at': datetime.now(timezone.utc).isoformat(), 'top': []}

    score = sum(float(r.get('score', 0.0)) for r in rows)
    long_score = sum(float(r.get('long_event_score', 0.0)) for r in rows)
    short_score = sum(float(r.get('short_event_score', 0.0)) for r in rows)
    confidence = min(1.0, (sum(float(r.get('trust', 0.0)) for r in rows) / max(1, len(rows))))
    if long_score > short_score + 1.2:
        bias = 'bullish'
    elif short_score > long_score + 1.2:
        bias = 'bearish'
    else:
        bias = 'neutral'
    count_news = sum(1 for r in rows if r.get('kind') == 'news')
    count_official = sum(1 for r in rows if r.get('kind') == 'official')
    count_tweet = sum(1 for r in rows if r.get('kind') == 'tweet')
    trump_count = sum(1 for r in rows if bool(r.get('is_trump', False)))
    scheduled_count = sum(1 for r in rows if bool(r.get('is_scheduled', False)))
    crypto_score = round(sum(float(r.get('score', 0.0)) for r in rows if r.get('topic') == 'crypto'), 4)
    macro_score = round(sum(float(r.get('score', 0.0)) for r in rows if r.get('topic') == 'macro'), 4)
    geo_score = round(sum(float(r.get('score', 0.0)) for r in rows if r.get('topic') == 'geopolitics'), 4)

    signal = '중립'
    if score >= 3 and confidence >= 0.7:
        signal = '공격'
    elif score <= -2 or geo_score <= -1.5 or macro_score <= -1.5:
        signal = '방어'

    return {
        'score': round(score, 4),
        'long_score': round(long_score, 4),
        'short_score': round(short_score, 4),
        'bias': bias,
        'confidence': round(confidence, 4),
        'count': len(rows),
        'count_news': count_news,
        'count_official': count_official,
        'count_tweet': count_tweet,
        'count_trump': trump_count,
        'count_scheduled': scheduled_count,
        'crypto_score': crypto_score,
        'macro_score': macro_score,
        'geo_score': geo_score,
        'signal': signal,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'top': rows[:20],
    }


def get_market_brief(force_refresh: bool = False) -> Dict:
    if not force_refresh and CACHE_PATH.exists():
        try:
            d = json.loads(CACHE_PATH.read_text(encoding='utf-8'))
            ts = float(d.get('_cached_at', 0))
            if (time.time() - ts) <= CACHE_TTL_SEC:
                d.pop('_cached_at', None)
                return d
        except Exception:
            pass

    rows = fetch_items(per_source=10)
    brief = summarize_market(rows)
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        out = dict(brief)
        out['_cached_at'] = time.time()
        CACHE_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass
    return brief
