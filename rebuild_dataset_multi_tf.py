from exchange import get_exchange
from ml_dataset import load_events, enrich_with_price_labels
from ml_market_data import fetch_ohlcv_range


def fetch_range(ex, symbol: str, timeframe: str, days: int, limit_per_call: int = 1000):
    return fetch_ohlcv_range(
        ex,
        symbol,
        timeframe,
        days,
        limit_per_call=limit_per_call,
    )


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
