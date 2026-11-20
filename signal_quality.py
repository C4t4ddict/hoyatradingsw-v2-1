"""News/ML outcome tracking, quality gates, and causal market-regime policy."""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_title(title: str) -> str:
    value = re.sub(r"[^a-z0-9가-힣 ]+", " ", str(title).lower())
    return re.sub(r"\s+", " ", value).strip()


def deduplicate_events(events: Iterable[Dict[str, Any]], similarity_threshold: float = 0.88) -> List[Dict[str, Any]]:
    """Collapse syndicated headlines across sources while preserving strongest trust."""
    kept: List[Dict[str, Any]] = []
    for event in sorted(events, key=lambda item: float(item.get("trust", 0.0)), reverse=True):
        normalized = normalize_title(event.get("title", ""))
        if not normalized:
            continue
        duplicate = any(
            SequenceMatcher(None, normalized, normalize_title(existing.get("title", ""))).ratio() >= similarity_threshold
            for existing in kept
        )
        if not duplicate:
            kept.append(dict(event))
    return kept


def weight_events_by_source(events: Iterable[Dict[str, Any]], reliability_rows: Iterable[Dict[str, Any]], minimum_observations: int = 10) -> List[Dict[str, Any]]:
    """Apply shrunk realized source reliability only after enough observations."""
    learned = {
        row["source"]: float(row["reliability"])
        for row in reliability_rows
        if int(row.get("observations", 0)) >= minimum_observations
    }
    output = []
    for event in events:
        item = dict(event)
        reliability = learned.get(item.get("source"))
        if reliability is not None:
            factor = max(0.5, min(1.5, reliability / 0.5))
            item["score"] = float(item.get("score", 0.0)) * factor
            item["learned_source_reliability"] = reliability
        output.append(item)
    return output


def align_event_outcomes(events: Iterable[Dict[str, Any]], prices: pd.Series, horizon_bars: int) -> pd.DataFrame:
    """Align evaluation returns at/after publication; never backfill from a future event."""
    if horizon_bars <= 0:
        raise ValueError("horizon_bars must be positive")
    market = pd.Series(prices, dtype=float).sort_index()
    rows = []
    for event in events:
        event_time = pd.Timestamp(event["event_time"])
        if event_time.tzinfo is not None and getattr(market.index, "tz", None) is None:
            event_time = event_time.tz_convert(None)
        entry_position = market.index.searchsorted(event_time, side="left")
        exit_position = entry_position + horizon_bars
        if entry_position >= len(market) or exit_position >= len(market):
            continue
        entry_time = market.index[entry_position]
        rows.append({
            **event,
            "entry_time": entry_time,
            "exit_time": market.index[exit_position],
            "forward_return": float(market.iloc[exit_position] / market.iloc[entry_position] - 1.0),
        })
    return pd.DataFrame(rows)


def _correlation(left: List[float], right: List[float]) -> float:
    if len(left) < 3 or len(left) != len(right):
        return 0.0
    frame = pd.DataFrame({"left": left, "right": right}).dropna()
    if len(frame) < 3 or frame["left"].std(ddof=0) == 0 or frame["right"].std(ddof=0) == 0:
        return 0.0
    return float(frame.corr().iloc[0, 1])


class SignalQualityStore:
    """Persist realized outcomes and compute activation gates by signal type."""

    def __init__(self, path: str = "data/signal_quality.sqlite3", min_observations: int = 30):
        self.path = path
        self.min_observations = int(min_observations)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS signal_outcomes (
                    observation_id TEXT PRIMARY KEY,
                    signal_type TEXT NOT NULL,
                    source TEXT,
                    horizon TEXT NOT NULL,
                    predicted_probability REAL NOT NULL,
                    actual INTEGER NOT NULL,
                    signed_score REAL NOT NULL,
                    forward_return REAL NOT NULL,
                    occurred_at TEXT NOT NULL
                )
                """
            )

    def record(
        self,
        *,
        signal_type: str,
        horizon: str,
        predicted_probability: float,
        actual: int,
        signed_score: float,
        forward_return: float,
        source: Optional[str] = None,
        occurred_at: Optional[str] = None,
        observation_id: Optional[str] = None,
    ) -> bool:
        probability = min(1.0, max(0.0, float(predicted_probability)))
        if int(actual) not in {0, 1}:
            raise ValueError("actual must be 0 or 1")
        try:
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO signal_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (observation_id or str(uuid.uuid4()), signal_type, source, horizon, probability, int(actual), float(signed_score), float(forward_return), occurred_at or _now()),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def summary(self, signal_type: str, horizon: Optional[str] = None) -> Dict[str, Any]:
        with self._connection() as connection:
            if horizon is None:
                rows = connection.execute(
                    "SELECT * FROM signal_outcomes WHERE signal_type = ? ORDER BY occurred_at",
                    (signal_type,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM signal_outcomes WHERE signal_type = ? AND horizon = ? ORDER BY occurred_at",
                    (signal_type, horizon),
                ).fetchall()
        probabilities = [float(row["predicted_probability"]) for row in rows]
        actuals = [int(row["actual"]) for row in rows]
        scores = [float(row["signed_score"]) for row in rows]
        returns = [float(row["forward_return"]) for row in rows]
        count = len(rows)
        brier = sum((probability - actual) ** 2 for probability, actual in zip(probabilities, actuals)) / count if count else 1.0
        accuracy = sum((probability >= 0.5) == bool(actual) for probability, actual in zip(probabilities, actuals)) / count if count else 0.0
        information_coefficient = _correlation(scores, returns)
        enabled = count >= self.min_observations and brier <= 0.25 and (accuracy >= 0.52 or abs(information_coefficient) >= 0.05)
        return {
            "signal_type": signal_type,
            "horizon": horizon or "all",
            "observations": count,
            "brier_score": brier,
            "accuracy": accuracy,
            "information_coefficient": information_coefficient,
            "enabled": enabled,
            "minimum_observations": self.min_observations,
        }

    def horizon_summaries(self, signal_type: str) -> List[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT horizon FROM signal_outcomes WHERE signal_type = ? ORDER BY horizon",
                (signal_type,),
            ).fetchall()
        return [self.summary(signal_type, row["horizon"]) for row in rows]

    def source_reliability(self) -> List[Dict[str, Any]]:
        with self._connection() as connection:
            sources = connection.execute("SELECT DISTINCT source FROM signal_outcomes WHERE signal_type = 'intel' AND source IS NOT NULL").fetchall()
            output = []
            for source_row in sources:
                source = source_row["source"]
                rows = connection.execute("SELECT predicted_probability, actual FROM signal_outcomes WHERE signal_type = 'intel' AND source = ?", (source,)).fetchall()
                count = len(rows)
                correct = sum((float(row["predicted_probability"]) >= 0.5) == bool(row["actual"]) for row in rows)
                # Beta(2,2) shrinkage avoids extreme trust from tiny samples.
                reliability = (correct + 2.0) / (count + 4.0)
                output.append({"source": source, "observations": count, "reliability": reliability})
        return sorted(output, key=lambda item: item["reliability"], reverse=True)


def analyze_market_regime(
    closes: Iterable[float],
    *,
    volumes: Optional[Iterable[float]] = None,
    funding_rate: float = 0.0,
    alt_returns: Optional[Iterable[float]] = None,
    as_of_index: Optional[int] = None,
) -> Dict[str, Any]:
    """Use only observations at or before as_of_index and return an exposure multiplier."""
    prices = [float(value) for value in closes]
    if as_of_index is not None:
        prices = prices[:as_of_index + 1]
    if len(prices) < 61:
        return {"direction": "unknown", "volatility": "unknown", "exposure_multiplier": 0.0, "reasons": ["insufficient_history"]}
    returns = [prices[index] / prices[index - 1] - 1.0 for index in range(1, len(prices))]
    fast = sum(prices[-20:]) / 20
    slow = sum(prices[-60:]) / 60
    direction = "bull" if fast > slow * 1.01 else "bear" if fast < slow * 0.99 else "sideways"
    recent = returns[-30:]
    volatility = pd.Series(recent).std(ddof=0) * math.sqrt(365)
    volatility_regime = "high" if volatility >= 0.60 else "normal"
    multiplier, reasons = 1.0, []
    if direction == "bear":
        multiplier *= 0.50; reasons.append("bear_trend")
    elif direction == "sideways":
        multiplier *= 0.80; reasons.append("sideways")
    if volatility_regime == "high":
        multiplier *= 0.65; reasons.append("high_volatility")
    liquidity = "unknown"
    if volumes is not None:
        volume_values = [float(value) for value in volumes]
        if as_of_index is not None:
            volume_values = volume_values[:as_of_index + 1]
        if len(volume_values) >= 30:
            ratio = volume_values[-1] / max(sum(volume_values[-30:]) / 30, 1e-9)
            liquidity = "thin" if ratio < 0.50 else "normal"
            if liquidity == "thin":
                multiplier *= 0.50; reasons.append("thin_liquidity")
    funding = "overheated" if abs(float(funding_rate)) >= 0.0005 else "normal"
    if funding == "overheated":
        multiplier *= 0.70; reasons.append("funding_overheated")
    alt_correlation = None
    if alt_returns is not None:
        alts = [float(value) for value in alt_returns]
        if as_of_index is not None:
            alts = alts[:as_of_index]
        window = min(30, len(returns), len(alts))
        alt_correlation = _correlation(returns[-window:], alts[-window:]) if window >= 3 else 0.0
        if alt_correlation >= 0.85 and direction == "bear":
            multiplier *= 0.80; reasons.append("correlated_risk_off")
    return {
        "direction": direction,
        "volatility": volatility_regime,
        "annualized_volatility": float(volatility),
        "liquidity": liquidity,
        "funding": funding,
        "alt_correlation": alt_correlation,
        "exposure_multiplier": max(0.0, min(1.0, multiplier)),
        "reasons": reasons,
    }


def derive_signal_policy(intel_quality: Dict[str, Any], ml_quality: Dict[str, Any], regime: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convert validated quality into dynamic weights; disabled signals receive zero."""
    def quality_score(summary: Dict[str, Any]) -> float:
        if not summary.get("enabled"):
            return 0.0
        return max(0.01, (1.0 - float(summary.get("brier_score", 1.0))) + max(0.0, float(summary.get("accuracy", 0.0)) - 0.5) + abs(float(summary.get("information_coefficient", 0.0))))

    intel_score, ml_score = quality_score(intel_quality), quality_score(ml_quality)
    total = intel_score + ml_score
    weights = {"intel": intel_score / total if total else 0.0, "ml": ml_score / total if total else 0.0}
    exposure = float((regime or {}).get("exposure_multiplier", 1.0))
    return {
        "weights": weights,
        "signals_enabled": total > 0.0,
        "exposure_multiplier": max(0.0, min(1.0, exposure)),
        "intel_quality": intel_quality,
        "ml_quality": ml_quality,
    }
