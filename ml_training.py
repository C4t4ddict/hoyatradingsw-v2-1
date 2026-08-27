from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd


MIN_ROWS = int(os.getenv("ML_MIN_TRAIN_ROWS", "200"))
MIN_CLASS_ROWS = int(os.getenv("ML_MIN_CLASS_ROWS", "20"))
HOLDOUT_FRACTION = float(os.getenv("ML_HOLDOUT_FRACTION", "0.20"))
PURGE_HOURS = int(os.getenv("ML_PURGE_HOURS", "24"))


@dataclass(frozen=True)
class ChronologicalSplit:
    train: pd.DataFrame
    test: pd.DataFrame
    metadata: dict


def chronological_purged_split(
    frame: pd.DataFrame,
    target: str,
    *,
    min_rows: int = MIN_ROWS,
    min_class_rows: int = MIN_CLASS_ROWS,
    holdout_fraction: float = HOLDOUT_FRACTION,
    purge_hours: int = PURGE_HOURS,
) -> ChronologicalSplit:
    """Create a newest-period holdout and purge observations near its boundary."""
    if target not in frame.columns:
        raise ValueError(f"missing target column: {target}")
    if "event_time" not in frame.columns:
        raise ValueError("missing event_time column")
    if not 0.05 <= holdout_fraction <= 0.5:
        raise ValueError("holdout_fraction must be between 0.05 and 0.5")

    data = frame.dropna(subset=[target, "event_time"]).copy()
    data["_event_time"] = pd.to_datetime(data["event_time"], utc=True, errors="coerce")
    data = data.dropna(subset=["_event_time"])
    if "event_id" in data.columns:
        data = data.drop_duplicates(subset=["event_id"], keep="first")
    data = data.sort_values("_event_time").reset_index(drop=True)
    data[target] = data[target].astype(int)

    if len(data) < min_rows:
        raise ValueError(f"{target}: rows {len(data)} < required {min_rows}")
    class_counts = data[target].value_counts().to_dict()
    if set(class_counts) != {0, 1} or min(class_counts.values()) < min_class_rows:
        raise ValueError(f"{target}: each class needs at least {min_class_rows} rows")

    split_index = max(1, min(len(data) - 1, int(len(data) * (1 - holdout_fraction))))
    test_start = data.iloc[split_index]["_event_time"]
    purge_boundary = test_start - pd.to_timedelta(purge_hours, unit="h")
    train = data[data["_event_time"] < purge_boundary].copy()
    test = data[data["_event_time"] >= test_start].copy()

    for name, subset in (("train", train), ("test", test)):
        counts = subset[target].value_counts().to_dict()
        if set(counts) != {0, 1}:
            raise ValueError(f"{target}: {name} period must contain both classes")

    metadata = {
        "target": target,
        "rows": int(len(data)),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "purged_rows": int(len(data) - len(train) - len(test)),
        "train_end": train["_event_time"].max().isoformat(),
        "test_start": test["_event_time"].min().isoformat(),
        "holdout_fraction": holdout_fraction,
        "purge_hours": purge_hours,
    }
    return ChronologicalSplit(
        train=train.drop(columns=["_event_time"]),
        test=test.drop(columns=["_event_time"]),
        metadata=metadata,
    )
