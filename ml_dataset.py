import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

import pandas as pd

EVENTS_PATH = Path("data/ml_events.jsonl")
DATASET_CSV = Path("data/ml_dataset.csv")

UP_TH_5M = float(os.getenv("ML_LABEL_UP_TH_5M", "0.20"))
UP_TH_15M = float(os.getenv("ML_LABEL_UP_TH_15M", "0.30"))
UP_TH_30M = float(os.getenv("ML_LABEL_UP_TH_30M", "0.40"))
UP_TH_1H = float(os.getenv("ML_LABEL_UP_TH_1H", "0.60"))
UP_TH_4H = float(os.getenv("ML_LABEL_UP_TH_4H", "1.20"))
UP_TH_24H = float(os.getenv("ML_LABEL_UP_TH_24H", "2.00"))
DOWN_TH_5M = float(os.getenv("ML_LABEL_DOWN_TH_5M", "-0.20"))
DOWN_TH_15M = float(os.getenv("ML_LABEL_DOWN_TH_15M", "-0.30"))
DOWN_TH_30M = float(os.getenv("ML_LABEL_DOWN_TH_30M", "-0.40"))
DOWN_TH_1H = float(os.getenv("ML_LABEL_DOWN_TH_1H", "-0.60"))
DOWN_TH_4H = float(os.getenv("ML_LABEL_DOWN_TH_4H", "-1.20"))
DOWN_TH_24H = float(os.getenv("ML_LABEL_DOWN_TH_24H", "-2.00"))


def append_events(rows: List[Dict]):
    if not rows:
        return 0
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    recent_keys = set()
    if EVENTS_PATH.exists():
        try:
            for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                existing.add(obj.get("event_id"))
                key = f"{str(obj.get('title', '')).strip().lower()}|{obj.get('topic')}|{obj.get('source')}"
                recent_keys.add(key)
        except Exception:
            pass

    written = 0
    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        for r in rows:
            if r.get("event_id") in existing:
                continue
            key = f"{str(r.get('title', '')).strip().lower()}|{r.get('topic')}|{r.get('source')}"
            if key in recent_keys:
                continue
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            written += 1
            recent_keys.add(key)
    return written


def load_events() -> List[Dict]:
    if not EVENTS_PATH.exists():
        return []
    rows = []
    for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _prepare_cdf(candles: List[List], tf_minutes: int) -> pd.DataFrame:
    cdf = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume"])
    cdf = cdf.sort_values("ts").reset_index(drop=True)
    cdf["ret_1"] = cdf["close"].pct_change() * 100.0
    cdf["ret_lookback"] = cdf["close"].pct_change(max(1, int(60 / tf_minutes))) * 100.0
    cdf["volatility_lookback"] = cdf["ret_1"].rolling(max(4, int(12 * (60 / tf_minutes)))).std()
    cdf["volume_ma"] = cdf["volume"].rolling(max(4, int(12 * (60 / tf_minutes)))).mean()
    cdf["volume_ratio"] = cdf["volume"] / cdf["volume_ma"]
    return cdf


def enrich_with_price_labels(events: List[Dict], candles_1h: List[List], candles_5m: List[List] = None, candles_15m: List[List] = None, candles_30m: List[List] = None) -> pd.DataFrame:
    if not events or not candles_1h:
        return pd.DataFrame()

    cdf_1h = _prepare_cdf(candles_1h, 60)
    cdf_5m = _prepare_cdf(candles_5m, 5) if candles_5m else None
    cdf_15m = _prepare_cdf(candles_15m, 15) if candles_15m else None
    cdf_30m = _prepare_cdf(candles_30m, 30) if candles_30m else None

    rows = []
    for e in events:
        try:
            et = datetime.fromisoformat(e["event_time"].replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            continue
        ets = int(et.timestamp() * 1000)

        base = cdf_1h[cdf_1h["ts"] >= ets]
        if base.empty:
            continue
        base_row = base.iloc[0]
        entry_close = float(base_row["close"])

        def future_return(cdf: pd.DataFrame, minutes: int):
            if cdf is None:
                return None
            target = ets + int(timedelta(minutes=minutes).total_seconds() * 1000)
            fut = cdf[cdf["ts"] >= target]
            if fut.empty:
                return None
            start = cdf[cdf["ts"] >= ets]
            if start.empty:
                return None
            px0 = float(start.iloc[0]["close"])
            px1 = float(fut.iloc[0]["close"])
            return ((px1 - px0) / px0) * 100.0

        r5m = future_return(cdf_5m, 5)
        r15m = future_return(cdf_15m, 15)
        r30m = future_return(cdf_30m, 30)
        r1h = future_return(cdf_1h, 60)
        r4h = future_return(cdf_1h, 240)
        r24h = future_return(cdf_1h, 1440)
        row = dict(e)
        row.update({
            "market_ret_1h": float(base_row.get("ret_1") or 0.0),
            "market_ret_4h": float(base_row.get("ret_lookback") or 0.0),
            "market_volatility_12h": float(base_row.get("volatility_lookback") or 0.0),
            "market_volume_ratio": float(base_row.get("volume_ratio") or 0.0),
            "return_5m": r5m,
            "return_15m": r15m,
            "return_30m": r30m,
            "return_1h": r1h,
            "return_4h": r4h,
            "return_24h": r24h,
            "label_up_5m": None if r5m is None else int(r5m >= UP_TH_5M),
            "label_down_5m": None if r5m is None else int(r5m <= DOWN_TH_5M),
            "label_up_15m": None if r15m is None else int(r15m >= UP_TH_15M),
            "label_down_15m": None if r15m is None else int(r15m <= DOWN_TH_15M),
            "label_up_30m": None if r30m is None else int(r30m >= UP_TH_30M),
            "label_down_30m": None if r30m is None else int(r30m <= DOWN_TH_30M),
            "label_up_1h": None if r1h is None else int(r1h >= UP_TH_1H),
            "label_down_1h": None if r1h is None else int(r1h <= DOWN_TH_1H),
            "label_up_4h": None if r4h is None else int(r4h >= UP_TH_4H),
            "label_down_4h": None if r4h is None else int(r4h <= DOWN_TH_4H),
            "label_up_24h": None if r24h is None else int(r24h >= UP_TH_24H),
            "label_down_24h": None if r24h is None else int(r24h <= DOWN_TH_24H),
        })
        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        corr_cols = [c for c in ["return_5m", "return_15m", "return_30m", "return_1h", "return_4h", "return_24h"] if c in df.columns]
        if len(corr_cols) >= 2:
            corr = df[corr_cols].corr(numeric_only=True).fillna(0.0)
            df.attrs["corr"] = corr.to_dict()
        DATASET_CSV.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(DATASET_CSV, index=False)
    return df
