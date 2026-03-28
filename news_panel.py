import html
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict

def _fetch_rss(url: str, timeout: int = 2) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _parse_items(xml_text: str) -> List[Dict[str, str]]:
    out = []
    root = ET.fromstring(xml_text)
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if title and link:
            out.append({
                "title": html.unescape(title),
                "link": link,
                "summary": html.unescape(desc),
                "published": pub,
            })
    return out


def _is_low_quality(title: str) -> bool:
    t = (title or "").lower()
    bad = ["sponsored", "promo", "advertorial", "giveaway", "buy now", "click here"]
    return any(k in t for k in bad)


def _impact_label(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()

    bearish = ["rate hike", "hawkish", "tightening", "inflation rise", "ban", "lawsuit", "crackdown"]
    bullish = ["rate cut", "dovish", "etf inflow", "approval", "easing", "support", "adoption"]

    b_score = sum(1 for k in bullish if k in text)
    s_score = sum(1 for k in bearish if k in text)

    if b_score > s_score:
        return "🟢 상승 가능성"
    if s_score > b_score:
        return "🔴 하락 가능성"
    return "🟡 중립"


def _priority_score(title: str, summary: str) -> int:
    text = f"{title} {summary}".lower()
    score = 0
    if "federal reserve" in text or "fed" in text or "fomc" in text:
        score += 5
    if "interest rate" in text or "rate cut" in text or "rate hike" in text:
        score += 4
    if "trump" in text:
        score += 3
    if "sec" in text or "treasury" in text:
        score += 2
    if "bitcoin" in text or "crypto" in text:
        score += 1
    return score


_CACHE_PATH = os.getenv("NEWS_TRANSLATION_CACHE_PATH", "data/news_translation_cache.json")
_CACHE_TTL_SEC = int(os.getenv("NEWS_TRANSLATION_CACHE_TTL_SEC", str(60 * 60 * 12)))


def _load_cache() -> Dict[str, Dict[str, str]]:
    if not os.path.exists(_CACHE_PATH):
        return {}
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_cache(cache: Dict[str, Dict[str, str]]):
    parent = os.path.dirname(_CACHE_PATH)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    try:
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass


def _translate_to_korean(text: str) -> str:
    if not text:
        return ""

    key = text.strip()
    now = int(time.time())
    cache = _load_cache()
    hit = cache.get(key)
    if isinstance(hit, dict):
        ts = int(hit.get("ts", 0)) if str(hit.get("ts", "")).isdigit() else 0
        if ts and (now - ts) <= _CACHE_TTL_SEC:
            v = hit.get("ko")
            if isinstance(v, str) and v:
                return v

    try:
        q = urllib.parse.quote(text)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ko&dt=t&q={q}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        translated = "".join(part[0] for part in data[0] if part and part[0])
        translated = translated or text

        cache[key] = {"ko": translated, "ts": now}
        if len(cache) > 2000:
            keys = list(cache.keys())[:500]
            for k in keys:
                cache.pop(k, None)
        _save_cache(cache)
        return translated
    except Exception:
        return text


_NEWS_CACHE_PATH = os.getenv("NEWS_ITEMS_CACHE_PATH", "data/news_items_cache.json")


def _load_news_cache() -> List[Dict[str, str]]:
    if not os.path.exists(_NEWS_CACHE_PATH):
        return []
    try:
        with open(_NEWS_CACHE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, list) else []
    except Exception:
        return []


def _save_news_cache(items: List[Dict[str, str]]):
    parent = os.path.dirname(_NEWS_CACHE_PATH)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    try:
        with open(_NEWS_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
    except Exception:
        pass


def get_macro_crypto_news(limit: int = 12) -> List[Dict[str, str]]:
    queries = [
        "Trump crypto",
        "Federal Reserve interest rate crypto",
        "FOMC Bitcoin",
    ]

    items: List[Dict[str, str]] = []
    seen = set()

    started = time.time()
    for q in queries:
        url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(q) + "&hl=en-US&gl=US&ceid=US:en"
        try:
            xml_text = _fetch_rss(url)
            parsed = _parse_items(xml_text)
        except Exception:
            parsed = []

        for it in parsed:
            if time.time() - started > 4:
                break
            title = it["title"]
            if title in seen:
                continue
            if _is_low_quality(title):
                continue

            seen.add(title)
            it["impact"] = _impact_label(it.get("title", ""), it.get("summary", ""))
            it["priority"] = _priority_score(it.get("title", ""), it.get("summary", ""))
            items.append(it)

    items = sorted(items, key=lambda x: x.get("priority", 0), reverse=True)
    items = items[:limit]

    # 수집 실패 시 직전 캐시 뉴스 fallback
    if not items:
        cached = _load_news_cache()
        return cached[:limit]

    # 화면 노출 상위 일부만 번역(지연 최소화)
    for idx, it in enumerate(items):
        if idx < 4:
            it["title_ko"] = _translate_to_korean(it.get("title", ""))
            it["summary_ko"] = _translate_to_korean((it.get("summary", "") or "")[:220])
        else:
            it["title_ko"] = it.get("title", "")
            it["summary_ko"] = it.get("summary", "")

    _save_news_cache(items)
    return items
