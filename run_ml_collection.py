import time
from datetime import datetime, timezone

from exchange import get_exchange
from market_intel import fetch_items
from ml_dataset import append_events, load_events, enrich_with_price_labels

INTERVAL_SEC = 300  # 5 minutes
MAX_SECONDS = 8 * 60 * 60  # 8 hours


def main():
    started = time.time()
    while (time.time() - started) < MAX_SECONDS:
        try:
            items = fetch_items(per_source=12)
            written = append_events(items)
            print(f"[{datetime.now(timezone.utc).isoformat()}] fetched={len(items)} written={written}", flush=True)

            try:
                ex = get_exchange(read_only=True, market_type="swap")
                candles = ex.fetch_ohlcv("BTC/USDT:USDT", timeframe="1h", limit=1000)
                df = enrich_with_price_labels(load_events(), candles)
                print(f"[{datetime.now(timezone.utc).isoformat()}] dataset_rows={len(df)}", flush=True)
            except Exception as e:
                print(f"[{datetime.now(timezone.utc).isoformat()}] label_error={e}", flush=True)
        except Exception as e:
            print(f"[{datetime.now(timezone.utc).isoformat()}] fetch_error={e}", flush=True)

        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
