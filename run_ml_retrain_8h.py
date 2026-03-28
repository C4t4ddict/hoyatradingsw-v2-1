import os
import subprocess
import time
from datetime import datetime, timezone

MAX_SECONDS = 8 * 60 * 60
INTERVAL_SEC = 60 * 60

ENV = os.environ.copy()
ENV['DYLD_LIBRARY_PATH'] = f"/opt/homebrew/opt/libomp/lib:{ENV.get('DYLD_LIBRARY_PATH', '')}"
ENV['LDFLAGS'] = "-L/opt/homebrew/opt/libomp/lib"
ENV['CPPFLAGS'] = "-I/opt/homebrew/opt/libomp/include"

REBUILD_CMD = "from exchange import get_exchange; from ml_dataset import load_events, enrich_with_price_labels; ex=get_exchange(read_only=True, market_type='swap'); candles=ex.fetch_ohlcv('BTC/USDT:USDT', timeframe='1h', limit=24*365); df=enrich_with_price_labels(load_events(), candles); print('rebuilt_rows=', len(df))"


def run(cmd):
    print(f"[{datetime.now(timezone.utc).isoformat()}] run: {' '.join(cmd)}", flush=True)
    p = subprocess.run(cmd, env=ENV, capture_output=True, text=True)
    print(p.stdout, flush=True)
    if p.stderr:
        print(p.stderr, flush=True)
    print(f"exit={p.returncode}", flush=True)
    return p.returncode


def main():
    started = time.time()
    while (time.time() - started) < MAX_SECONDS:
        run(["python3", "-c", REBUILD_CMD])
        run(["python3", "train_model_xgb.py"])
        remain = MAX_SECONDS - (time.time() - started)
        if remain <= 0:
            break
        time.sleep(min(INTERVAL_SEC, remain))


if __name__ == "__main__":
    main()
