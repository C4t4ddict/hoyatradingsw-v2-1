from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Iterable


TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "1h": 60}


def timeframe_ms(timeframe: str) -> int:
    try:
        return TIMEFRAME_MINUTES[timeframe] * 60 * 1000
    except KeyError as exc:
        raise ValueError(f"unsupported timeframe: {timeframe}") from exc


def completed_candles(candles: Iterable[list], timeframe: str, as_of_ms: int | None = None) -> list[list]:
    """Return sorted, deduplicated candles that were fully closed by ``as_of_ms``."""
    cutoff = as_of_ms if as_of_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    duration = timeframe_ms(timeframe)
    unique: dict[int, list] = {}
    for candle in candles:
        if len(candle) < 6:
            continue
        timestamp = int(candle[0])
        if timestamp + duration <= cutoff:
            unique[timestamp] = list(candle[:6])
    return [unique[timestamp] for timestamp in sorted(unique)]


def fetch_ohlcv_range(
    exchange,
    symbol: str,
    timeframe: str,
    days: int,
    *,
    limit_per_call: int = 1000,
    now: datetime | None = None,
) -> list[list]:
    """Fetch a public OHLCV range without assuming one exchange call can return it all."""
    if days <= 0:
        raise ValueError("days must be positive")
    if limit_per_call <= 0:
        raise ValueError("limit_per_call must be positive")

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    end_ms = int(current.timestamp() * 1000)
    cursor = int((current - timedelta(days=days)).timestamp() * 1000)
    duration = timeframe_ms(timeframe)
    expected_rows = max(1, ceil(days * 24 * 60 / TIMEFRAME_MINUTES[timeframe]))
    max_requests = ceil(expected_rows / limit_per_call) + 3
    rows: list[list] = []

    for _ in range(max_requests):
        if cursor >= end_ms:
            break
        chunk = exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            since=cursor,
            limit=limit_per_call,
        )
        if not chunk:
            break
        rows.extend(chunk)
        next_cursor = int(chunk[-1][0]) + duration
        if next_cursor <= cursor:
            break
        cursor = next_cursor

    return completed_candles(rows, timeframe, as_of_ms=end_ms)
