from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

from news_panel import _translate_to_korean


def localize_market_brief(brief: Dict[str, Any], limit: int = 12) -> Dict[str, Any]:
    """Add display-only Korean titles while preserving original signal inputs."""
    localized = {**(brief or {})}
    rows = [dict(row) for row in (localized.get("top") or [])]
    candidates = [row for row in rows[: max(0, limit)] if row.get("title") and not row.get("title_ko")]

    if candidates:
        titles = [row["title"] for row in candidates]
        workers = min(6, len(titles))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            translated = list(executor.map(_translate_to_korean, titles))
        for row, title_ko in zip(candidates, translated):
            row["title_ko"] = title_ko or row["title"]

    localized["top"] = rows
    return localized
