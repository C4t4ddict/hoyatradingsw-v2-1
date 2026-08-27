import os
import time
from datetime import datetime, timedelta, timezone

from exchange import get_exchange
from market_intel import fetch_items
from ml_dataset import append_events, load_events, enrich_with_price_labels
from ml_market_data import fetch_ohlcv_range

INTERVAL_SEC = 300  # 5 minutes
MAX_SECONDS = 8 * 60 * 60  # 8 hours
LABEL_LOOKBACK_DAYS = int(os.getenv("ML_LABEL_LOOKBACK_DAYS", "30"))
LABEL_REFRESH_SEC = int(os.getenv("ML_LABEL_REFRESH_SEC", "3600"))


def main():
    started = time.time()
    last_label_refresh = 0.0
    while (time.time() - started) < MAX_SECONDS:
        try:
            items = fetch_items(per_source=12)
            written = append_events(items)
            print(f"[{datetime.now(timezone.utc).isoformat()}] fetched={len(items)} written={written}", flush=True)

            if time.time() - last_label_refresh >= LABEL_REFRESH_SEC:
                last_label_refresh = time.time()
                ex = get_exchange(read_only=True, market_type="swap")
                events = load_events()
                cutoff = datetime.now(timezone.utc) - timedelta(days=LABEL_LOOKBACK_DAYS)
                recent_events = []
                for event in events:
                    try:
                        event_time = datetime.fromisoformat(event["event_time"].replace("Z", "+00:00"))
                    except (KeyError, ValueError):
                        continue
                    if event_time.astimezone(timezone.utc) >= cutoff:
                        recent_events.append(event)
                candles_1h = fetch_ohlcv_range(ex, "BTC/USDT:USDT", "1h", LABEL_LOOKBACK_DAYS + 2)
                candles_15m = fetch_ohlcv_range(ex, "BTC/USDT:USDT", "15m", LABEL_LOOKBACK_DAYS + 2)
                candles_5m = fetch_ohlcv_range(ex, "BTC/USDT:USDT", "5m", LABEL_LOOKBACK_DAYS + 2)
                df = enrich_with_price_labels(
                    recent_events,
                    candles_1h,
                    candles_5m,
                    candles_15m,
                    merge_existing=True,
                )
                print(f"[{datetime.now(timezone.utc).isoformat()}] dataset_rows={len(df)}", flush=True)
        except Exception as e:
            print(f"[{datetime.now(timezone.utc).isoformat()}] fetch_error={e}", flush=True)

        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
