from datetime import datetime, timedelta, timezone

from exchange import get_exchange
from ml_dataset import load_events, enrich_with_price_labels


def fetch_range(ex, symbol: str, timeframe: str, days: int, limit_per_call: int = 1000):
    tf_minutes = {"5m": 5, "15m": 15, "1h": 60}[timeframe]
    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    end = int(datetime.now(timezone.utc).timestamp() * 1000)
    step = tf_minutes * 60 * 1000 * limit_per_call
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
    # dedupe
    seen = set()
    out = []
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(r[0])
        out.append(r)
    return out


def main():
    ex = get_exchange(read_only=True, market_type='swap')
    candles_1h = fetch_range(ex, 'BTC/USDT:USDT', '1h', 365)
    candles_15m = fetch_range(ex, 'BTC/USDT:USDT', '15m', 365)
    candles_5m = fetch_range(ex, 'BTC/USDT:USDT', '5m', 365)
    df = enrich_with_price_labels(load_events(), candles_1h, candles_5m, candles_15m)
    print('candles_1h=', len(candles_1h))
    print('candles_15m=', len(candles_15m))
    print('candles_5m=', len(candles_5m))
    print('dataset_rows=', len(df))
    if hasattr(df, 'attrs'):
        print('corr=', df.attrs.get('corr'))


if __name__ == '__main__':
    main()
