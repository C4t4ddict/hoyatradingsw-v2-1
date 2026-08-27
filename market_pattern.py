from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

from ml_market_data import completed_candles
DATASET_CSV = Path("data/market_pattern_dataset.csv")
MODEL_DIR = Path("data/models_market_pattern")
REPORT_PATH = MODEL_DIR / "report.json"
TIMEFRAME = "4h"
TARGETS = ["label_up_4h", "label_down_4h", "label_up_24h", "label_down_24h"]
FEATURES = [
    "return_4h", "return_12h", "return_24h", "return_72h",
    "trend_24h", "trend_72h", "trend_7d", "volatility_24h", "volatility_7d",
    "range_pct", "body_pct", "volume_ratio_7d", "drawdown_7d", "rsi_14",
]
THRESHOLD_4H = float(os.getenv("MARKET_PATTERN_LABEL_THRESHOLD_4H", "0.003"))
THRESHOLD_24H = float(os.getenv("MARKET_PATTERN_LABEL_THRESHOLD_24H", "0.008"))
MIN_PATTERN_ROWS = int(os.getenv("MARKET_PATTERN_MIN_ROWS", "1000"))
MIN_PATTERN_CLASS_ROWS = int(os.getenv("MARKET_PATTERN_MIN_CLASS_ROWS", "100"))


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    change = close.diff()
    gains = change.clip(lower=0).rolling(window, min_periods=window).mean()
    losses = (-change.clip(upper=0)).rolling(window, min_periods=window).mean()
    relative_strength = gains / losses.replace(0, float("nan"))
    return (100.0 - (100.0 / (1.0 + relative_strength))).fillna(50.0)


def build_market_pattern_dataset(
    candles: list[list],
    *,
    as_of_ms: int | None = None,
    persist: bool = True,
) -> pd.DataFrame:
    rows = completed_candles(candles, TIMEFRAME, as_of_ms)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    close = frame["close"]
    frame["return_4h"] = close.pct_change(1)
    frame["return_12h"] = close.pct_change(3)
    frame["return_24h"] = close.pct_change(6)
    frame["return_72h"] = close.pct_change(18)
    frame["trend_24h"] = close / close.rolling(6, min_periods=6).mean() - 1.0
    frame["trend_72h"] = close / close.rolling(18, min_periods=18).mean() - 1.0
    frame["trend_7d"] = close / close.rolling(42, min_periods=42).mean() - 1.0
    frame["volatility_24h"] = frame["return_4h"].rolling(6, min_periods=6).std(ddof=0)
    frame["volatility_7d"] = frame["return_4h"].rolling(42, min_periods=42).std(ddof=0)
    frame["range_pct"] = (frame["high"] - frame["low"]) / frame["open"]
    frame["body_pct"] = (frame["close"] - frame["open"]) / frame["open"]
    frame["volume_ratio_7d"] = frame["volume"] / frame["volume"].rolling(42, min_periods=42).mean()
    frame["drawdown_7d"] = close / close.rolling(42, min_periods=42).max() - 1.0
    frame["rsi_14"] = _rsi(close)

    entry_open = frame["open"].shift(-1)
    frame["forward_return_4h"] = frame["open"].shift(-2) / entry_open - 1.0
    frame["forward_return_24h"] = frame["open"].shift(-7) / entry_open - 1.0
    frame["label_up_4h"] = (frame["forward_return_4h"] >= THRESHOLD_4H).astype("Int64")
    frame["label_down_4h"] = (frame["forward_return_4h"] <= -THRESHOLD_4H).astype("Int64")
    frame["label_up_24h"] = (frame["forward_return_24h"] >= THRESHOLD_24H).astype("Int64")
    frame["label_down_24h"] = (frame["forward_return_24h"] <= -THRESHOLD_24H).astype("Int64")
    frame.loc[frame["forward_return_4h"].isna(), ["label_up_4h", "label_down_4h"]] = pd.NA
    frame.loc[frame["forward_return_24h"].isna(), ["label_up_24h", "label_down_24h"]] = pd.NA

    frame["event_time"] = pd.to_datetime(frame["timestamp"] + 4 * 60 * 60 * 1000, unit="ms", utc=True)
    frame["event_id"] = frame["timestamp"].map(lambda value: f"BTCUSDT-4h-{int(value)}")
    frame["dataset_version"] = "next-open-v1"
    frame = frame.dropna(subset=FEATURES).replace([math.inf, -math.inf], pd.NA).dropna(subset=FEATURES)
    if persist:
        DATASET_CSV.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(DATASET_CSV, index=False)
    return frame.reset_index(drop=True)


def _report_rows() -> dict[str, dict]:
    if not REPORT_PATH.exists():
        return {}
    try:
        payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        str(row.get("target")): row
        for row in payload.get("targets", [])
        if isinstance(row, dict) and row.get("target")
    }


def predict_market_pattern(frame: pd.DataFrame | None = None) -> dict:
    source = frame
    if source is None:
        if not DATASET_CSV.exists():
            return {"ready": False, "predictions": {}, "bias": "neutral"}
        source = pd.read_csv(DATASET_CSV)
    if source.empty:
        return {"ready": False, "predictions": {}, "bias": "neutral"}
    latest = source.dropna(subset=FEATURES).iloc[-1]
    report = _report_rows()
    predictions = {}
    for target in TARGETS:
        path = MODEL_DIR / f"{target}.joblib"
        if not path.exists():
            predictions[target] = {"ok": False, "reason": "model not found"}
            continue
        latest_validation = report.get(target, {})
        if latest_validation.get("validation_passed") is not True:
            predictions[target] = {"ok": False, "reason": "latest validation not passed"}
            continue
        bundle = joblib.load(path)
        metadata = bundle.get("metadata") or {}
        if metadata.get("validation_passed") is not True:
            predictions[target] = {"ok": False, "reason": "model validation not passed"}
            continue
        if metadata.get("trained_at") != latest_validation.get("trained_at"):
            predictions[target] = {"ok": False, "reason": "model does not match latest validation"}
            continue
        model = bundle["model"]
        probability = float(model.predict_proba(pd.DataFrame([latest[FEATURES]]))[:, 1][0])
        predictions[target] = {"ok": True, "positive_proba": probability, "validation": metadata}

    ready = all(predictions.get(target, {}).get("ok") is True for target in TARGETS)
    up_4h = float(predictions.get("label_up_4h", {}).get("positive_proba", 0.0))
    down_4h = float(predictions.get("label_down_4h", {}).get("positive_proba", 0.0))
    up_24h = float(predictions.get("label_up_24h", {}).get("positive_proba", 0.0))
    down_24h = float(predictions.get("label_down_24h", {}).get("positive_proba", 0.0))
    long_score = up_4h * 0.65 + up_24h * 0.35
    short_score = down_4h * 0.65 + down_24h * 0.35
    bias = "neutral"
    if ready and long_score >= 0.60 and long_score > short_score + 0.10:
        bias = "long"
    elif ready and short_score >= 0.60 and short_score > long_score + 0.10:
        bias = "short"
    return {
        "ready": ready,
        "as_of": str(latest["event_time"]),
        "predictions": predictions,
        "long_score": round(long_score, 6),
        "short_score": round(short_score, 6),
        "bias": bias,
    }


def get_market_pattern_readiness(*, now: datetime | None = None) -> dict:
    base = {
        "status": "collecting",
        "training_ready": False,
        "inference_ready": False,
        "dataset": {"exists": False, "rows": 0, "duplicates": 0, "gaps": 0, "started_at": None, "ended_at": None},
        "models": {"validated": 0, "required": len(TARGETS)},
        "targets": [],
        "blockers": ["과거 시장 패턴 데이터셋이 아직 없습니다."],
        "thresholds": {"minimum_rows": MIN_PATTERN_ROWS, "minimum_class_rows": MIN_PATTERN_CLASS_ROWS},
        "latest_prediction": {"ready": False, "predictions": {}, "bias": "neutral"},
    }
    if not DATASET_CSV.exists():
        return base
    try:
        frame = pd.read_csv(DATASET_CSV)
    except Exception as exc:
        base["status"] = "blocked"
        base["blockers"] = [f"과거 시장 패턴 데이터셋을 읽을 수 없습니다: {type(exc).__name__}"]
        return base

    times = pd.to_datetime(frame.get("event_time"), utc=True, errors="coerce")
    valid_times = times.dropna().sort_values()
    gaps = int((valid_times.diff().dropna() > pd.to_timedelta(4, unit="h")).sum())
    duplicates = int(frame.get("event_id", pd.Series(dtype="object")).duplicated().sum())
    missing_features = [feature for feature in FEATURES if feature not in frame.columns or frame[feature].isna().any()]
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    future_rows = int((times > current).fillna(False).sum())
    blockers = []
    if len(frame) < MIN_PATTERN_ROWS:
        blockers.append(f"과거 시장 패턴 관측치가 {len(frame)}행으로 최소 {MIN_PATTERN_ROWS}행보다 적습니다.")
    if duplicates:
        blockers.append(f"중복 4시간봉 키가 {duplicates}건 있습니다.")
    if gaps:
        blockers.append(f"4시간봉 연속성 공백이 {gaps}구간 있습니다.")
    if future_rows:
        blockers.append(f"완료되지 않은 미래 시점 행이 {future_rows}건 있습니다.")
    if missing_features:
        blockers.append(f"필수 시장 특성에 결측이 있습니다: {', '.join(missing_features)}")

    report = _report_rows()
    targets = []
    validated = 0
    for target in TARGETS:
        labels = pd.to_numeric(frame.get(target), errors="coerce") if target in frame.columns else pd.Series(dtype=float)
        labels = labels[labels.isin([0, 1])]
        positives = int((labels == 1).sum())
        negatives = int((labels == 0).sum())
        data_ready = len(labels) >= MIN_PATTERN_ROWS and min(positives, negatives) >= MIN_PATTERN_CLASS_ROWS
        validation = report.get(target, {})
        model_validated = bool((MODEL_DIR / f"{target}.joblib").exists() and validation.get("validation_passed") is True)
        validated += int(model_validated)
        targets.append({
            "target": target,
            "rows": int(len(labels)),
            "positives": positives,
            "negatives": negatives,
            "positive_rate": round(positives / len(labels), 4) if len(labels) else None,
            "data_ready": data_ready,
            "model_validated": model_validated,
            "balanced_accuracy": validation.get("balanced_accuracy"),
            "brier_score": validation.get("brier_score"),
            "net_sharpe": validation.get("net_sharpe"),
            "walk_forward_passed_folds": validation.get("walk_forward_passed_folds"),
            "walk_forward_required_passes": validation.get("walk_forward_required_passes"),
        })
        if not data_ready:
            blockers.append(f"{target} 클래스별 관측치가 부족합니다.")

    training_ready = not blockers
    if training_ready and validated < len(TARGETS):
        blockers.append(f"검증된 과거 시장 패턴 모델이 {validated}/{len(TARGETS)}개입니다.")
    inference_ready = training_ready and validated == len(TARGETS)
    return {
        **base,
        "status": "ready" if inference_ready else ("needs_training" if training_ready else "collecting"),
        "training_ready": training_ready,
        "inference_ready": inference_ready,
        "dataset": {
            "exists": True,
            "rows": len(frame),
            "duplicates": duplicates,
            "gaps": gaps,
            "future_rows": future_rows,
            "started_at": valid_times.min().isoformat() if not valid_times.empty else None,
            "ended_at": valid_times.max().isoformat() if not valid_times.empty else None,
        },
        "models": {"validated": validated, "required": len(TARGETS)},
        "targets": targets,
        "blockers": blockers,
        "latest_prediction": predict_market_pattern(frame),
    }
