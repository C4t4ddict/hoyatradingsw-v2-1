from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.metrics import balanced_accuracy_score, brier_score_loss, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ml_dataset import DATASET_CSV
from ml_readiness import MODEL_DIR, TARGETS
from ml_training import chronological_purged_split


MIN_BALANCED_ACCURACY = float(os.getenv("ML_MIN_BALANCED_ACCURACY", "0.52"))
TEXT_FEATURE = "text"
CATEGORICAL_FEATURES = ["source", "kind", "topic"]
NUMERIC_FEATURES = [
    "score", "trust", "is_trump", "is_scheduled",
    "market_ret_1h", "market_ret_4h", "market_volatility_12h", "market_volume_ratio",
]
FEATURES = [TEXT_FEATURE, *CATEGORICAL_FEATURES, *NUMERIC_FEATURES]


def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    for column in ("title", "summary"):
        if column not in prepared.columns:
            prepared[column] = ""
    prepared[TEXT_FEATURE] = prepared["title"].fillna("") + " " + prepared["summary"].fillna("")
    for column in CATEGORICAL_FEATURES:
        if column not in prepared.columns:
            prepared[column] = "unknown"
    for column in NUMERIC_FEATURES:
        if column not in prepared.columns:
            prepared[column] = 0.0
    return prepared


def _preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("text", TfidfVectorizer(max_features=4000, ngram_range=(1, 2), min_df=2), TEXT_FEATURE),
            ("cat", Pipeline([
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]), CATEGORICAL_FEATURES),
            ("num", Pipeline([
                ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
            ]), NUMERIC_FEATURES),
        ],
        sparse_threshold=0.3,
    )


def train_one(frame: pd.DataFrame, target: str) -> dict:
    split = chronological_purged_split(_prepare(frame), target)
    train = split.train
    test = split.test
    prep = _preprocessor()
    train_features = prep.fit_transform(train[FEATURES])
    test_features = prep.transform(test[FEATURES])
    if hasattr(train_features, "toarray"):
        train_features = train_features.toarray()
        test_features = test_features.toarray()

    model = HistGradientBoostingClassifier(
        max_depth=4,
        learning_rate=0.05,
        max_iter=300,
        random_state=42,
    )
    train_labels = train[target].astype(int)
    test_labels = test[target].astype(int)
    model.fit(train_features, train_labels)
    probabilities = model.predict_proba(test_features)[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    prior = float(train_labels.mean())
    balanced_accuracy = float(balanced_accuracy_score(test_labels, predictions))
    brier_score = float(brier_score_loss(test_labels, probabilities))
    baseline_brier = float(brier_score_loss(test_labels, [prior] * len(test_labels)))
    validation_passed = balanced_accuracy >= MIN_BALANCED_ACCURACY and brier_score < baseline_brier
    metadata = {
        **split.metadata,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "balanced_accuracy": round(balanced_accuracy, 6),
        "precision": round(float(precision_score(test_labels, predictions, zero_division=0)), 6),
        "recall": round(float(recall_score(test_labels, predictions, zero_division=0)), 6),
        "brier_score": round(brier_score, 6),
        "baseline_brier_score": round(baseline_brier, 6),
        "validation_passed": validation_passed,
        "minimum_balanced_accuracy": MIN_BALANCED_ACCURACY,
    }
    if validation_passed:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        destination = MODEL_DIR / f"{target}.joblib"
        temporary = destination.with_suffix(".joblib.tmp")
        joblib.dump({"prep": prep, "model": model, "metadata": metadata}, temporary)
        temporary.replace(destination)
    return metadata


def main() -> None:
    if not DATASET_CSV.exists():
        print("dataset not found")
        return
    frame = pd.read_csv(DATASET_CSV)
    results = []
    for target in TARGETS:
        try:
            result = train_one(frame, target)
        except ValueError as exc:
            result = {"target": target, "validation_passed": False, "reason": str(exc)}
        results.append(result)
        print(json.dumps(result, ensure_ascii=False))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "targets": results,
    }
    (MODEL_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
