"""Leakage-resistant validation utilities for strategy approval evidence."""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import pandas as pd


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    purge_bars: int
    embargo_bars: int


def purged_walk_forward_splits(
    length: int,
    *,
    train_bars: int,
    test_bars: int,
    purge_bars: int = 1,
    embargo_bars: int = 1,
) -> List[WalkForwardFold]:
    """Return expanding-time folds with explicit gaps around every test set."""
    if min(length, train_bars, test_bars) <= 0 or purge_bars < 0 or embargo_bars < 0:
        raise ValueError("invalid split configuration")
    folds = []
    train_end = train_bars
    fold = 0
    while True:
        test_start = train_end + purge_bars
        test_end = test_start + test_bars
        if test_end > length:
            break
        folds.append(WalkForwardFold(fold, 0, train_end, test_start, test_end, purge_bars, embargo_bars))
        fold += 1
        train_end = test_end + embargo_bars
    return folds


def performance_metrics(returns: pd.Series, annualization: int = 365) -> Dict[str, float]:
    values = pd.Series(returns, dtype=float).dropna()
    if values.empty:
        return {"total_return_pct": 0.0, "annualized_return_pct": 0.0, "sharpe": 0.0, "max_drawdown_pct": 0.0, "positive_period_pct": 0.0}
    equity = (1.0 + values).cumprod()
    total = float(equity.iloc[-1] - 1.0)
    years = max(len(values) / annualization, 1.0 / annualization)
    annualized = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if equity.iloc[-1] > 0 else -1.0
    volatility = float(values.std(ddof=0))
    sharpe = float(values.mean() / volatility * math.sqrt(annualization)) if volatility > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    return {
        "total_return_pct": total * 100.0,
        "annualized_return_pct": annualized * 100.0,
        "sharpe": sharpe,
        "max_drawdown_pct": abs(float(drawdown.min())) * 100.0,
        "positive_period_pct": float((values > 0).mean()) * 100.0,
    }


def purged_walk_forward_report(
    returns: pd.Series,
    folds: Sequence[WalkForwardFold],
    annualization: int = 365,
) -> pd.DataFrame:
    """Evaluate each train and untouched test interval without joining the purge gap."""
    values = pd.Series(returns, dtype=float).reset_index(drop=True)
    rows = []
    for fold in folds:
        train = values.iloc[fold.train_start:fold.train_end]
        test = values.iloc[fold.test_start:fold.test_end]
        rows.append({
            **asdict(fold),
            **{f"train_{key}": value for key, value in performance_metrics(train, annualization).items()},
            **{f"test_{key}": value for key, value in performance_metrics(test, annualization).items()},
        })
    return pd.DataFrame(rows)


def classify_market_regimes(
    benchmark_returns: pd.Series,
    *,
    trend_window: int = 30,
    volatility_window: int = 30,
    trend_threshold: float = 0.001,
    high_volatility_annualized: float = 0.60,
    annualization: int = 365,
) -> pd.DataFrame:
    """Classify each row using trailing data only; no full-sample quantiles."""
    values = pd.Series(benchmark_returns, dtype=float)
    trailing_trend = values.rolling(trend_window, min_periods=trend_window).mean()
    trailing_vol = values.rolling(volatility_window, min_periods=volatility_window).std(ddof=0) * math.sqrt(annualization)
    direction = pd.Series("unknown", index=values.index, dtype="object")
    direction.loc[trailing_trend > trend_threshold] = "bull"
    direction.loc[trailing_trend < -trend_threshold] = "bear"
    direction.loc[(trailing_trend >= -trend_threshold) & (trailing_trend <= trend_threshold)] = "sideways"
    volatility = pd.Series("unknown", index=values.index, dtype="object")
    volatility.loc[trailing_vol < high_volatility_annualized] = "normal_vol"
    volatility.loc[trailing_vol >= high_volatility_annualized] = "high_vol"
    return pd.DataFrame({"direction": direction, "volatility": volatility, "trailing_mean": trailing_trend, "trailing_volatility": trailing_vol})


def regime_performance(strategy_returns: pd.Series, regimes: pd.DataFrame, annualization: int = 365) -> pd.DataFrame:
    aligned = pd.DataFrame({"return": strategy_returns}).join(regimes[["direction", "volatility"]], how="inner").dropna()
    rows = []
    for (direction, volatility), group in aligned.groupby(["direction", "volatility"]):
        if direction == "unknown" or volatility == "unknown":
            continue
        rows.append({"direction": direction, "volatility": volatility, "periods": len(group), **performance_metrics(group["return"], annualization)})
    return pd.DataFrame(rows)


def apply_cost_stress(
    gross_returns: pd.Series,
    turnover: pd.Series,
    *,
    cost_bps_scenarios: Sequence[float] = (0.0, 5.0, 10.0, 25.0),
    funding_returns: pd.Series | None = None,
    annualization: int = 365,
) -> pd.DataFrame:
    gross = pd.Series(gross_returns, dtype=float)
    traded = pd.Series(turnover, dtype=float).reindex(gross.index).fillna(0.0)
    funding = pd.Series(0.0, index=gross.index) if funding_returns is None else pd.Series(funding_returns, dtype=float).reindex(gross.index).fillna(0.0)
    rows = []
    for cost_bps in cost_bps_scenarios:
        net = gross - traded.abs() * (float(cost_bps) / 10000.0) + funding
        rows.append({"cost_bps": float(cost_bps), **performance_metrics(net, annualization)})
    return pd.DataFrame(rows)


def monte_carlo_trade_paths(
    trade_returns: Iterable[float],
    *,
    simulations: int = 1000,
    seed: int = 42,
) -> Dict[str, float]:
    samples = [float(value) for value in trade_returns]
    if not samples or simulations <= 0:
        raise ValueError("trade returns and simulations are required")
    rng = random.Random(seed)
    terminals, drawdowns = [], []
    for _ in range(simulations):
        path = [rng.choice(samples) for _ in samples]
        equity, peak, max_drawdown = 1.0, 1.0, 0.0
        for value in path:
            equity *= 1.0 + value
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, 1.0 - equity / max(peak, 1e-12))
        terminals.append(equity - 1.0)
        drawdowns.append(max_drawdown)
    terminals.sort()
    drawdowns.sort()

    def quantile(values: List[float], probability: float) -> float:
        index = min(len(values) - 1, max(0, round((len(values) - 1) * probability)))
        return float(values[index])

    return {
        "simulations": float(simulations),
        "terminal_return_p05_pct": quantile(terminals, 0.05) * 100.0,
        "terminal_return_median_pct": quantile(terminals, 0.50) * 100.0,
        "max_drawdown_p95_pct": quantile(drawdowns, 0.95) * 100.0,
        "loss_probability_pct": sum(value < 0 for value in terminals) / simulations * 100.0,
        "seed": float(seed),
    }


def strategy_correlation(return_series: Dict[str, pd.Series]) -> pd.DataFrame:
    frame = pd.DataFrame({name: pd.Series(series, dtype=float) for name, series in return_series.items()})
    return frame.corr(min_periods=3)


def benchmark_comparison(strategy_returns: pd.Series, benchmark_returns: pd.Series, annualization: int = 365) -> Dict[str, float]:
    aligned = pd.concat([pd.Series(strategy_returns, dtype=float), pd.Series(benchmark_returns, dtype=float)], axis=1, join="inner").dropna()
    aligned.columns = ["strategy", "benchmark"]
    if aligned.empty:
        raise ValueError("overlapping strategy and benchmark returns are required")
    excess = aligned["strategy"] - aligned["benchmark"]
    tracking_error = float(excess.std(ddof=0))
    information_ratio = float(excess.mean() / tracking_error * math.sqrt(annualization)) if tracking_error > 0 else 0.0
    return {
        "strategy_total_return_pct": performance_metrics(aligned["strategy"], annualization)["total_return_pct"],
        "benchmark_total_return_pct": performance_metrics(aligned["benchmark"], annualization)["total_return_pct"],
        "excess_total_return_pct": ((1 + aligned["strategy"]).prod() - (1 + aligned["benchmark"]).prod()) * 100.0,
        "information_ratio": information_ratio,
        "outperformance_period_pct": float((excess > 0).mean()) * 100.0,
    }


def run_validation_suite(frame: pd.DataFrame, *, strategy_column: str, benchmark_column: str, output_dir: Path, seed: int = 42) -> Dict[str, object]:
    required = {strategy_column, benchmark_column, "turnover"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    strategy_returns = pd.Series(frame[strategy_column], dtype=float)
    benchmark_returns = pd.Series(frame[benchmark_column], dtype=float)
    regimes = classify_market_regimes(benchmark_returns)
    train_bars = max(20, len(frame) // 2)
    test_bars = max(10, len(frame) // 5)
    folds = purged_walk_forward_splits(len(frame), train_bars=train_bars, test_bars=test_bars, purge_bars=1, embargo_bars=1)
    walk_forward = purged_walk_forward_report(strategy_returns, folds)
    report = {
        "strategy": performance_metrics(strategy_returns),
        "benchmark": benchmark_comparison(strategy_returns, benchmark_returns),
        "monte_carlo": monte_carlo_trade_paths(strategy_returns.dropna(), seed=seed),
        "methodology": {
            "causal_regimes": True,
            "monte_carlo_seed": seed,
            "selection_rule": "training and validation evidence only; final holdout remains evaluation-only",
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    regime_table = regime_performance(strategy_returns, regimes)
    cost_table = apply_cost_stress(strategy_returns, frame["turnover"], funding_returns=frame.get("funding_return"))
    candidate_columns = [column for column in frame.columns if column.endswith("_return") and column not in {benchmark_column, "funding_return"}]
    correlation = strategy_correlation({column: frame[column] for column in candidate_columns})
    (output_dir / "validation_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    regime_table.to_csv(output_dir / "regime_performance.csv", index=False)
    cost_table.to_csv(output_dir / "cost_stress.csv", index=False)
    walk_forward.to_csv(output_dir / "purged_walk_forward.csv", index=False)
    correlation.to_csv(output_dir / "strategy_correlation.csv")
    return {**report, "regime_performance": regime_table, "cost_stress": cost_table, "purged_walk_forward": walk_forward, "strategy_correlation": correlation}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run reproducible strategy validation")
    parser.add_argument("returns_csv")
    parser.add_argument("--strategy-column", default="strategy_return")
    parser.add_argument("--benchmark-column", default="benchmark_return")
    parser.add_argument("--output-dir", default="research/output/validation")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    frame = pd.read_csv(args.returns_csv)
    run_validation_suite(frame, strategy_column=args.strategy_column, benchmark_column=args.benchmark_column, output_dir=Path(args.output_dir), seed=args.seed)


if __name__ == "__main__":
    main()
