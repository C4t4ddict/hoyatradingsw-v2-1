from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ml_dataset import DATASET_CSV
from ml_training import MIN_CLASS_ROWS, MIN_ROWS
from market_pattern import get_market_pattern_readiness


MODEL_DIR = Path("data/models_bidirectional")
MODEL_REPORT = MODEL_DIR / "report.json"
TARGETS = [
    "label_up_5m", "label_down_5m",
    "label_up_15m", "label_down_15m",
    "label_up_30m", "label_down_30m",
    "label_up_1h", "label_down_1h",
    "label_up_4h", "label_down_4h",
    "label_up_24h", "label_down_24h",
]
REQUIRED_FEATURES = [
    "event_id", "event_time", "title", "source", "kind", "topic",
    "score", "trust", "is_trump", "is_scheduled", "market_feature_time",
    "market_ret_1h", "market_ret_4h", "market_volatility_12h", "market_volume_ratio",
]
MAX_FEATURE_MISSING_RATE = 0.05


def _empty_result(dataset_path: Path, model_dir: Path) -> dict:
    return {
        "status": "collecting",
        "training_ready": False,
        "inference_ready": False,
        "dataset": {
            "exists": False,
            "path": dataset_path.as_posix(),
            "rows": 0,
            "unique_events": 0,
            "duplicate_events": 0,
            "invalid_event_times": 0,
            "future_events": 0,
            "feature_leakage_rows": 0,
            "started_at": None,
            "ended_at": None,
            "age_hours": None,
            "feature_missing_rates": {feature: 1.0 for feature in REQUIRED_FEATURES},
        },
        "models": {"directory": model_dir.as_posix(), "validated": 0, "required": len(TARGETS)},
        "targets": [],
        "blockers": ["ML 데이터셋이 아직 없습니다. 공개 뉴스와 시세 데이터를 먼저 수집해야 합니다."],
        "warnings": [],
        "thresholds": {
            "minimum_rows": MIN_ROWS,
            "minimum_class_rows": MIN_CLASS_ROWS,
            "maximum_feature_missing_rate": MAX_FEATURE_MISSING_RATE,
        },
    }


def _load_report(report_path: Path) -> dict[str, dict]:
    if not report_path.exists():
        return {}
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("targets", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return {}
    return {str(row.get("target")): row for row in rows if isinstance(row, dict) and row.get("target")}


def get_ml_readiness(
    dataset_path: Path = DATASET_CSV,
    model_dir: Path = MODEL_DIR,
    *,
    now: datetime | None = None,
) -> dict:
    if not dataset_path.exists():
        return _empty_result(dataset_path, model_dir)

    result = _empty_result(dataset_path, model_dir)
    result["dataset"]["exists"] = True
    result["blockers"] = []
    try:
        frame = pd.read_csv(dataset_path)
    except Exception as exc:
        result["status"] = "blocked"
        result["blockers"].append(f"ML 데이터셋을 읽을 수 없습니다: {type(exc).__name__}")
        return result

    row_count = len(frame)
    events = frame.get("event_id", pd.Series(index=frame.index, dtype="object"))
    raw_event_times = frame["event_time"] if "event_time" in frame.columns else pd.Series(index=frame.index, dtype="object")
    raw_feature_times = frame["market_feature_time"] if "market_feature_time" in frame.columns else pd.Series(index=frame.index, dtype="object")
    event_times = pd.to_datetime(raw_event_times, utc=True, errors="coerce")
    feature_times = pd.to_datetime(raw_feature_times, utc=True, errors="coerce")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    valid_times = event_times.dropna()
    duplicate_events = int(events.dropna().duplicated().sum())
    future_events = int((event_times > current).fillna(False).sum())
    leakage_rows = int((feature_times > event_times).fillna(False).sum())
    missing_rates = {
        feature: round(float(frame[feature].isna().mean()), 4) if feature in frame.columns else 1.0
        for feature in REQUIRED_FEATURES
    }
    ended_at = valid_times.max() if not valid_times.empty else None

    result["dataset"].update({
        "rows": row_count,
        "unique_events": int(events.dropna().nunique()),
        "duplicate_events": duplicate_events,
        "invalid_event_times": int(event_times.isna().sum()),
        "future_events": future_events,
        "feature_leakage_rows": leakage_rows,
        "started_at": valid_times.min().isoformat() if not valid_times.empty else None,
        "ended_at": ended_at.isoformat() if ended_at is not None else None,
        "age_hours": round((current - ended_at.to_pydatetime()).total_seconds() / 3600, 1) if ended_at is not None else None,
        "feature_missing_rates": missing_rates,
    })

    if row_count < MIN_ROWS:
        result["blockers"].append(f"전체 관측치가 {row_count}건으로 최소 {MIN_ROWS}건보다 적습니다.")
    if duplicate_events:
        result["blockers"].append(f"중복 이벤트가 {duplicate_events}건 있습니다.")
    if result["dataset"]["invalid_event_times"]:
        result["blockers"].append("해석할 수 없는 이벤트 시각이 있습니다.")
    if future_events:
        result["blockers"].append(f"미래 시각 이벤트가 {future_events}건 있습니다.")
    if leakage_rows:
        result["blockers"].append(f"이벤트 이후 시장 특성을 사용한 행이 {leakage_rows}건 있습니다.")
    high_missing = [name for name, rate in missing_rates.items() if rate > MAX_FEATURE_MISSING_RATE]
    if high_missing:
        result["blockers"].append(f"필수 특성 누락률이 기준을 넘었습니다: {', '.join(high_missing)}")
    if result["dataset"]["age_hours"] is not None and result["dataset"]["age_hours"] > 24:
        result["warnings"].append("마지막 이벤트 수집 후 24시간 이상 지났습니다.")

    report = _load_report(model_dir / "report.json")
    validated_models = 0
    targets = []
    for target in TARGETS:
        labels = pd.to_numeric(frame.get(target), errors="coerce") if target in frame.columns else pd.Series(dtype="float64")
        labels = labels[labels.isin([0, 1])]
        positives = int((labels == 1).sum())
        negatives = int((labels == 0).sum())
        target_data_ready = len(labels) >= MIN_ROWS and min(positives, negatives) >= MIN_CLASS_ROWS
        model_path = model_dir / f"{target}.joblib"
        validation = report.get(target, {})
        model_validated = bool(model_path.exists() and validation.get("validation_passed") is True)
        validated_models += int(model_validated)
        targets.append({
            "target": target,
            "rows": int(len(labels)),
            "positives": positives,
            "negatives": negatives,
            "positive_rate": round(positives / len(labels), 4) if len(labels) else None,
            "data_ready": target_data_ready,
            "model_exists": model_path.exists(),
            "model_validated": model_validated,
            "balanced_accuracy": validation.get("balanced_accuracy"),
            "brier_score": validation.get("brier_score"),
        })
        if not target_data_ready:
            result["blockers"].append(f"{target} 라벨의 전체/클래스별 관측치가 부족합니다.")

    result["targets"] = targets
    result["models"] = {
        "directory": model_dir.as_posix(),
        "validated": validated_models,
        "required": len(TARGETS),
    }
    data_blockers = [message for message in result["blockers"] if "모델" not in message]
    result["training_ready"] = not data_blockers
    if result["training_ready"] and validated_models < len(TARGETS):
        result["blockers"].append(
            f"검증된 양방향 모델이 {validated_models}/{len(TARGETS)}개입니다. 시간순 홀드아웃 학습이 필요합니다."
        )
    result["inference_ready"] = result["training_ready"] and validated_models == len(TARGETS)
    result["status"] = "ready" if result["inference_ready"] else ("needs_training" if result["training_ready"] else "collecting")
    return result


def get_hybrid_ml_readiness() -> dict:
    event_readiness = get_ml_readiness()
    return {**event_readiness, "market_pattern": get_market_pattern_readiness()}
