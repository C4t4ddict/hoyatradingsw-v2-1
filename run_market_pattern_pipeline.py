from __future__ import annotations

import json
import os

from exchange import get_exchange
from market_pattern import build_market_pattern_dataset, get_market_pattern_readiness
from ml_market_data import fetch_ohlcv_range
from train_market_pattern_model import train_all


SYMBOL = os.getenv("MARKET_PATTERN_SYMBOL", "BTC/USDT:USDT")
HISTORY_DAYS = int(os.getenv("MARKET_PATTERN_HISTORY_DAYS", str(5 * 365)))


def run_pipeline() -> dict:
    exchange = get_exchange(read_only=True, market_type="swap")
    candles = fetch_ohlcv_range(exchange, SYMBOL, "4h", HISTORY_DAYS)
    frame = build_market_pattern_dataset(candles)
    report = train_all(frame)
    readiness = get_market_pattern_readiness()
    return {
        "symbol": SYMBOL,
        "history_days": HISTORY_DAYS,
        "candles": len(candles),
        "dataset_rows": len(frame),
        "validated_models": readiness["models"]["validated"],
        "required_models": readiness["models"]["required"],
        "training_ready": readiness["training_ready"],
        "inference_ready": readiness["inference_ready"],
        "targets": report.get("targets", []),
    }


def main() -> None:
    print(json.dumps(run_pipeline(), ensure_ascii=False))


if __name__ == "__main__":
    main()
