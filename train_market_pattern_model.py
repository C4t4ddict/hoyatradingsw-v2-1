from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import balanced_accuracy_score, brier_score_loss, precision_score, recall_score

from market_pattern import (
    DATASET_CSV,
    FEATURES,
    MIN_PATTERN_CLASS_ROWS,
    MIN_PATTERN_ROWS,
    MODEL_DIR,
    REPORT_PATH,
    TARGETS,
)
from ml_training import chronological_purged_split


MIN_BALANCED_ACCURACY = float(os.getenv("MARKET_PATTERN_MIN_BALANCED_ACCURACY", "0.52"))
MIN_NET_SHARPE = float(os.getenv("MARKET_PATTERN_MIN_NET_SHARPE", "0.30"))
MIN_TRADES = int(os.getenv("MARKET_PATTERN_MIN_TRADES", "20"))
PROBABILITY_THRESHOLD = float(os.getenv("MARKET_PATTERN_PROBABILITY_THRESHOLD", "0.60"))
ROUND_TRIP_COST = float(os.getenv("MARKET_PATTERN_ROUND_TRIP_COST", "0.0018"))
WALK_FORWARD_FOLDS = int(os.getenv("MARKET_PATTERN_WALK_FORWARD_FOLDS", "4"))


def _new_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_depth=4,
        learning_rate=0.04,
        max_iter=300,
        l2_regularization=1.0,
        random_state=42,
    )


def _fit_model(train: pd.DataFrame, target: str) -> HistGradientBoostingClassifier:
    labels = train[target].astype(int)
    counts = labels.value_counts()
    sample_weights = labels.map({label: len(labels) / (2 * count) for label, count in counts.items()})
    model = _new_model()
    model.fit(train[FEATURES], labels, sample_weight=sample_weights)
    return model


def _economic_metrics(test: pd.DataFrame, target: str, probabilities) -> dict:
    horizon = "24h" if target.endswith("24h") else "4h"
    forward = pd.to_numeric(test[f"forward_return_{horizon}"], errors="coerce").reset_index(drop=True)
    probability = pd.Series(probabilities, dtype=float).reset_index(drop=True)
    direction = -1.0 if "down" in target else 1.0
    position = (probability >= PROBABILITY_THRESHOLD).astype(float) * direction
    net = position * forward - position.abs() * ROUND_TRIP_COST
    if horizon == "24h":
        net = net.iloc[::6]
        position = position.iloc[::6]
        annualization = 365
    else:
        annualization = 6 * 365
    trades = int(position.abs().sum())
    equity = (1.0 + net.fillna(0.0)).cumprod()
    volatility = float(net.std(ddof=0))
    sharpe = float(net.mean() / volatility * math.sqrt(annualization)) if volatility > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0 if not equity.empty else pd.Series([0.0])
    return {
        "trades": trades,
        "net_return_pct": round(float((equity.iloc[-1] - 1.0) * 100.0) if not equity.empty else 0.0, 6),
        "net_sharpe": round(sharpe, 6),
        "max_drawdown_pct": round(abs(float(drawdown.min())) * 100.0, 6),
        "probability_threshold": PROBABILITY_THRESHOLD,
        "round_trip_cost": ROUND_TRIP_COST,
    }


def _walk_forward_metrics(frame: pd.DataFrame, target: str) -> dict:
    if WALK_FORWARD_FOLDS < 2:
        raise ValueError("MARKET_PATTERN_WALK_FORWARD_FOLDS must be at least 2")
    data = frame.dropna(subset=[target, "event_time", *FEATURES]).copy()
    data["_event_time"] = pd.to_datetime(data["event_time"], utc=True, errors="coerce")
    data = data.dropna(subset=["_event_time"]).sort_values("_event_time").reset_index(drop=True)
    if "event_id" in data.columns:
        data = data.drop_duplicates(subset=["event_id"], keep="first").reset_index(drop=True)
    initial_rows = int(len(data) * 0.60)
    fold_rows = (len(data) - initial_rows) // WALK_FORWARD_FOLDS
    if initial_rows < max(100, int(MIN_PATTERN_ROWS * 0.60)) or fold_rows <= 0:
        raise ValueError(f"{target}: not enough rows for walk-forward validation")

    folds = []
    for index in range(WALK_FORWARD_FOLDS):
        start = initial_rows + index * fold_rows
        end = len(data) if index == WALK_FORWARD_FOLDS - 1 else start + fold_rows
        test = data.iloc[start:end].drop(columns=["_event_time"])
        test_start = data.iloc[start]["_event_time"]
        purge_boundary = test_start - pd.to_timedelta(24, unit="h")
        train = data[data["_event_time"] < purge_boundary].drop(columns=["_event_time"])
        train_labels = train[target].astype(int)
        test_labels = test[target].astype(int)
        if set(train_labels.unique()) != {0, 1} or set(test_labels.unique()) != {0, 1}:
            folds.append({"fold": index + 1, "validation_passed": False, "reason": "both classes are required"})
            continue
        model = _fit_model(train, target)
        probabilities = model.predict_proba(test[FEATURES])[:, 1]
        predictions = (probabilities >= 0.5).astype(int)
        prior = float(train_labels.mean())
        balanced_accuracy = float(balanced_accuracy_score(test_labels, predictions))
        brier_score = float(brier_score_loss(test_labels, probabilities))
        baseline_brier = float(brier_score_loss(test_labels, [prior] * len(test_labels)))
        economic = _economic_metrics(test, target, probabilities)
        fold_passed = (
            balanced_accuracy >= MIN_BALANCED_ACCURACY
            and brier_score < baseline_brier
            and economic["trades"] >= MIN_TRADES
            and economic["net_return_pct"] > 0
            and economic["net_sharpe"] >= MIN_NET_SHARPE
        )
        folds.append({
            "fold": index + 1,
            "train_rows": len(train),
            "test_rows": len(test),
            "test_start": test_start.isoformat(),
            "test_end": data.iloc[end - 1]["_event_time"].isoformat(),
            "balanced_accuracy": round(balanced_accuracy, 6),
            "brier_score": round(brier_score, 6),
            "baseline_brier_score": round(baseline_brier, 6),
            **economic,
            "validation_passed": fold_passed,
        })
    required_passes = math.ceil(WALK_FORWARD_FOLDS * 0.75)
    passed_folds = sum(row.get("validation_passed") is True for row in folds)
    return {
        "folds": folds,
        "passed_folds": passed_folds,
        "required_passes": required_passes,
        "validation_passed": passed_folds >= required_passes,
    }


def train_one(frame: pd.DataFrame, target: str) -> dict:
    split = chronological_purged_split(
        frame,
        target,
        min_rows=MIN_PATTERN_ROWS,
        min_class_rows=MIN_PATTERN_CLASS_ROWS,
        purge_hours=24,
    )
    train = split.train
    test = split.test
    train_labels = train[target].astype(int)
    test_labels = test[target].astype(int)
    model = _fit_model(train, target)
    probabilities = model.predict_proba(test[FEATURES])[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    prior = float(train_labels.mean())
    balanced_accuracy = float(balanced_accuracy_score(test_labels, predictions))
    brier_score = float(brier_score_loss(test_labels, probabilities))
    baseline_brier = float(brier_score_loss(test_labels, [prior] * len(test_labels)))
    economic = _economic_metrics(test, target, probabilities)
    walk_forward = _walk_forward_metrics(frame, target)
    validation_passed = (
        balanced_accuracy >= MIN_BALANCED_ACCURACY
        and brier_score < baseline_brier
        and economic["trades"] >= MIN_TRADES
        and economic["net_return_pct"] > 0
        and economic["net_sharpe"] >= MIN_NET_SHARPE
        and walk_forward["validation_passed"]
    )
    metadata = {
        **split.metadata,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "balanced_accuracy": round(balanced_accuracy, 6),
        "precision": round(float(precision_score(test_labels, predictions, zero_division=0)), 6),
        "recall": round(float(recall_score(test_labels, predictions, zero_division=0)), 6),
        "brier_score": round(brier_score, 6),
        "baseline_brier_score": round(baseline_brier, 6),
        **economic,
        "walk_forward": walk_forward,
        "walk_forward_passed_folds": walk_forward["passed_folds"],
        "walk_forward_required_passes": walk_forward["required_passes"],
        "validation_passed": validation_passed,
        "minimum_balanced_accuracy": MIN_BALANCED_ACCURACY,
        "minimum_net_sharpe": MIN_NET_SHARPE,
        "minimum_trades": MIN_TRADES,
    }
    if validation_passed:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        destination = MODEL_DIR / f"{target}.joblib"
        temporary = destination.with_suffix(".joblib.tmp")
        joblib.dump({"model": model, "features": FEATURES, "metadata": metadata}, temporary)
        temporary.replace(destination)
    return metadata


def train_all(frame: pd.DataFrame | None = None) -> dict:
    if frame is None:
        if not DATASET_CSV.exists():
            return {"generated_at": datetime.now(timezone.utc).isoformat(), "targets": [], "error": "dataset not found"}
        frame = pd.read_csv(DATASET_CSV)
    results = []
    for target in TARGETS:
        try:
            result = train_one(frame, target)
        except ValueError as exc:
            result = {"target": target, "validation_passed": False, "reason": str(exc)}
        results.append(result)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "targets": results}
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    report = train_all()
    for result in report.get("targets", []):
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
