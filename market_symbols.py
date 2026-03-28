from typing import List


def _market_quote_volume_usdt(market: dict) -> float:
    info = market.get("info") if isinstance(market, dict) else None
    if not isinstance(info, dict):
        return 0.0

    # Binance spot/futures에서 자주 쓰이는 필드
    for k in ["quoteVolume", "quoteVolume24h", "volume"]:
        v = info.get(k)
        try:
            if v is not None:
                return float(v)
        except Exception:
            continue
    return 0.0


def fetch_symbols(exchange, market_type: str, min_quote_volume_usdt: float = 0.0) -> List[str]:
    """거래소 마켓 목록에서 spot/futures 심볼 리스트 추출 (USDT 마켓만)"""
    exchange.load_markets()
    out = []

    for sym, m in exchange.markets.items():
        quote = m.get("quote")
        vol = _market_quote_volume_usdt(m)

        if market_type == "spot":
            if m.get("spot") and quote == "USDT" and m.get("active", True):
                if vol >= min_quote_volume_usdt:
                    out.append(sym)
        else:
            is_swap = m.get("swap")
            if is_swap and quote == "USDT" and m.get("active", True):
                if vol >= min_quote_volume_usdt:
                    out.append(sym)

    return sorted(set(out))
