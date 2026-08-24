"""Reproducible crypto strategy study using Binance public USD-M data.

Signals are formed at bar close and applied at the next bar open. The study is
research-only: it does not place orders or read account credentials.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data" / "matplotlib_cache"))

import ccxt
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


CACHE_DIR = ROOT / "data" / "research_cache"
OUTPUT_DIR = ROOT / "research" / "output"
TIMEFRAME = "4h"
BARS_PER_DAY = 6
BARS_PER_YEAR = 365 * BARS_PER_DAY
START = "2021-01-01T00:00:00Z"
SYMBOLS = {
    "BTC": "BTC/USDT:USDT",
    "ETH": "ETH/USDT:USDT",
    "SOL": "SOL/USDT:USDT",
}


@dataclass(frozen=True)
class StrategySpec:
    name: str
    market: str
    signal: Callable[[pd.DataFrame], pd.Series]


def _exchange():
    return ccxt.binanceusdm({"enableRateLimit": True, "options": {"defaultType": "future"}})


def _cache_name(asset: str, kind: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{asset.lower()}_{TIMEFRAME}_{kind}.csv"


def fetch_ohlcv(asset: str, symbol: str, refresh: bool = False) -> pd.DataFrame:
    path = _cache_name(asset, "ohlcv")
    if path.exists() and not refresh:
        frame = pd.read_csv(path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], format="mixed", utc=True)
        return frame.set_index("timestamp")

    exchange = _exchange()
    since = exchange.parse8601(START)
    end_ms = exchange.milliseconds()
    rows: list[list[float]] = []
    while since < end_ms:
        batch = exchange.fetch_ohlcv(symbol, TIMEFRAME, since=since, limit=1500)
        if not batch:
            break
        rows.extend(batch)
        next_since = int(batch[-1][0]) + 1
        if next_since <= since:
            break
        since = next_since
        if len(batch) < 2:
            break

    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    frame = frame.drop_duplicates("timestamp").sort_values("timestamp")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    current_bar = pd.Timestamp.now(tz="UTC").floor("4h")
    frame = frame[frame["timestamp"] < current_bar]
    frame.to_csv(path, index=False)
    return frame.set_index("timestamp")


def fetch_funding(asset: str, symbol: str, refresh: bool = False) -> pd.DataFrame:
    path = _cache_name(asset, "funding")
    if path.exists() and not refresh:
        frame = pd.read_csv(path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], format="mixed", utc=True)
        return frame.set_index("timestamp")

    exchange = _exchange()
    since = exchange.parse8601(START)
    end_ms = exchange.milliseconds()
    rows: list[dict] = []
    while since < end_ms:
        batch = exchange.fetch_funding_rate_history(symbol, since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        next_since = int(batch[-1]["timestamp"]) + 1
        if next_since <= since:
            break
        since = next_since
        if len(batch) < 2:
            break

    normalized = [
        {"timestamp": row["timestamp"], "funding_rate": float(row.get("fundingRate") or 0.0)}
        for row in rows
        if row.get("timestamp") is not None
    ]
    frame = pd.DataFrame(normalized)
    if frame.empty:
        frame = pd.DataFrame(columns=["timestamp", "funding_rate"])
    else:
        frame = frame.drop_duplicates("timestamp").sort_values("timestamp")
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame.to_csv(path, index=False)
    return frame.set_index("timestamp") if not frame.empty else frame


def _rsi(close: pd.Series, periods: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / periods, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / periods, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def _carry_state(entries_long: pd.Series, entries_short: pd.Series, exits_long: pd.Series, exits_short: pd.Series) -> pd.Series:
    state = 0.0
    result = []
    for long_entry, short_entry, long_exit, short_exit in zip(entries_long, entries_short, exits_long, exits_short):
        if state > 0 and long_exit:
            state = 0.0
        elif state < 0 and short_exit:
            state = 0.0
        if long_entry:
            state = 1.0
        elif short_entry:
            state = -1.0
        result.append(state)
    return pd.Series(result, index=entries_long.index, dtype=float)


def signal_buy_hold(frame: pd.DataFrame) -> pd.Series:
    return pd.Series(1.0, index=frame.index)


def signal_ema_long_cash(frame: pd.DataFrame) -> pd.Series:
    return signal_ema_long_cash_params(frame, 50, 200)


def signal_ema_long_cash_params(frame: pd.DataFrame, fast_days: int, slow_days: int) -> pd.Series:
    fast = frame["close"].ewm(span=fast_days * BARS_PER_DAY, adjust=False).mean()
    slow = frame["close"].ewm(span=slow_days * BARS_PER_DAY, adjust=False).mean()
    return (fast > slow).astype(float)


def signal_ema_long_short(frame: pd.DataFrame) -> pd.Series:
    base = signal_ema_long_cash(frame)
    return base.replace({0.0: -1.0})


def signal_donchian_long_short(frame: pd.DataFrame) -> pd.Series:
    entry_window = 55 * BARS_PER_DAY
    exit_window = 20 * BARS_PER_DAY
    prior_high = frame["high"].rolling(entry_window).max().shift(1)
    prior_low = frame["low"].rolling(entry_window).min().shift(1)
    exit_low = frame["low"].rolling(exit_window).min().shift(1)
    exit_high = frame["high"].rolling(exit_window).max().shift(1)
    return _carry_state(
        frame["close"] > prior_high,
        frame["close"] < prior_low,
        frame["close"] < exit_low,
        frame["close"] > exit_high,
    )


def signal_rsi_pullback_long_cash(frame: pd.DataFrame) -> pd.Series:
    slow = frame["close"].ewm(span=200 * BARS_PER_DAY, adjust=False).mean()
    rsi = _rsi(frame["close"], 14 * BARS_PER_DAY)
    long_entry = (frame["close"] > slow) & (rsi < 35)
    long_exit = (rsi > 55) | (frame["close"] < slow)
    zeros = pd.Series(False, index=frame.index)
    return _carry_state(long_entry, zeros, long_exit, zeros).clip(lower=0)


def signal_vol_target_momentum(frame: pd.DataFrame) -> pd.Series:
    return signal_vol_target_params(frame, 90, 200, 0.35)


def signal_vol_target_params(frame: pd.DataFrame, momentum_days: int, slow_days: int, target_vol: float) -> pd.Series:
    slow = frame["close"].ewm(span=slow_days * BARS_PER_DAY, adjust=False).mean()
    momentum = frame["close"].pct_change(momentum_days * BARS_PER_DAY)
    log_return = np.log(frame["close"]).diff()
    realized_vol = log_return.rolling(30 * BARS_PER_DAY).std() * math.sqrt(BARS_PER_YEAR)
    scale = (target_vol / realized_vol.replace(0, np.nan)).clip(0.0, 1.0).fillna(0.0)
    return (((frame["close"] > slow) & (momentum > 0)).astype(float) * scale).clip(0.0, 1.0)


STRATEGIES = [
    StrategySpec("buy_hold", "spot", signal_buy_hold),
    StrategySpec("ema_50d_200d_long_cash", "spot", signal_ema_long_cash),
    StrategySpec("rsi_pullback_long_cash", "spot", signal_rsi_pullback_long_cash),
    StrategySpec("vol_target_momentum_long_cash", "spot", signal_vol_target_momentum),
    StrategySpec("ema_50d_200d_long_short", "futures", signal_ema_long_short),
    StrategySpec("donchian_55d_20d_long_short", "futures", signal_donchian_long_short),
]


def _funding_by_bar(funding: pd.DataFrame, index: pd.DatetimeIndex) -> pd.Series:
    if funding.empty:
        return pd.Series(0.0, index=index)
    rates = funding["funding_rate"].resample("4h").sum()
    return rates.reindex(index, fill_value=0.0)


def backtest(frame: pd.DataFrame, funding: pd.DataFrame, spec: StrategySpec, cost_override: float | None = None) -> pd.DataFrame:
    raw_signal = spec.signal(frame).clip(-1.0, 1.0)
    position = raw_signal.shift(1).fillna(0.0)
    open_to_open = frame["open"].shift(-1) / frame["open"] - 1.0
    turnover = position.diff().abs().fillna(position.abs())
    per_unit_cost = cost_override if cost_override is not None else (0.0013 if spec.market == "spot" else 0.0008)
    funding_rate = _funding_by_bar(funding, frame.index) if spec.market == "futures" else pd.Series(0.0, index=frame.index)
    net_return = position * open_to_open - turnover * per_unit_cost - position * funding_rate
    result = pd.DataFrame({
        "position": position,
        "turnover": turnover,
        "gross_return": position * open_to_open,
        "cost": turnover * per_unit_cost,
        "funding": position * funding_rate,
        "net_return": net_return,
    }).iloc[:-1]
    result = result.loc[result.index >= pd.Timestamp("2021-08-01", tz="UTC")]
    if not result.empty:
        result.iloc[0, result.columns.get_loc("turnover")] = abs(result["position"].iloc[0])
        result["cost"] = result["turnover"] * per_unit_cost
        result["net_return"] = result["gross_return"] - result["cost"] - result["funding"]
    result["equity"] = (1.0 + result["net_return"].fillna(0.0)).cumprod()
    return result


def metrics(result: pd.DataFrame) -> dict[str, float]:
    returns = result["net_return"].dropna()
    years = len(returns) / BARS_PER_YEAR
    total_return = result["equity"].iloc[-1] - 1.0
    cagr = result["equity"].iloc[-1] ** (1 / years) - 1.0 if years > 0 and result["equity"].iloc[-1] > 0 else -1.0
    annual_vol = returns.std(ddof=0) * math.sqrt(BARS_PER_YEAR)
    sharpe = returns.mean() / returns.std(ddof=0) * math.sqrt(BARS_PER_YEAR) if returns.std(ddof=0) > 0 else 0.0
    downside = returns.clip(upper=0)
    sortino = returns.mean() / downside.std(ddof=0) * math.sqrt(BARS_PER_YEAR) if downside.std(ddof=0) > 0 else 0.0
    drawdown = result["equity"] / result["equity"].cummax() - 1.0
    max_drawdown = drawdown.min()
    monthly = result["net_return"].resample("ME").apply(lambda values: (1 + values).prod() - 1)
    return {
        "total_return_pct": total_return * 100,
        "cagr_pct": cagr * 100,
        "annual_vol_pct": annual_vol * 100,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown_pct": max_drawdown * 100,
        "calmar": cagr / abs(max_drawdown) if max_drawdown < 0 else 0.0,
        "turnover_units": result["turnover"].sum(),
        "round_trips_est": result["turnover"].sum() / 2,
        "positive_month_pct": (monthly > 0).mean() * 100,
        "funding_drag_pct": result["funding"].sum() * 100,
        "cost_drag_pct": result["cost"].sum() * 100,
    }


def _period_return(result: pd.DataFrame, start: str, end: str | None = None) -> float:
    subset = result.loc[start:end, "net_return"]
    return ((1 + subset).prod() - 1) * 100 if len(subset) else np.nan


def _portfolio_result(results: dict[tuple[str, str], pd.DataFrame], strategy: str, weights: dict[str, float]) -> pd.DataFrame:
    pieces = []
    for asset, weight in weights.items():
        part = results[(asset, strategy)][["position", "turnover", "gross_return", "cost", "funding", "net_return"]].copy()
        part = part * float(weight)
        pieces.append(part)
    combined = sum(pieces[1:], pieces[0])
    combined["equity"] = (1 + combined["net_return"].fillna(0.0)).cumprod()
    return combined


def _market_snapshot(asset: str, frame: pd.DataFrame, funding: pd.DataFrame) -> dict:
    close = frame["close"]
    ema50 = close.ewm(span=50 * BARS_PER_DAY, adjust=False).mean()
    ema200 = close.ewm(span=200 * BARS_PER_DAY, adjust=False).mean()
    rv30 = np.log(close).diff().tail(30 * BARS_PER_DAY).std(ddof=0) * math.sqrt(BARS_PER_YEAR)
    recent_funding = (
        funding.loc[funding.index >= funding.index.max() - pd.Timedelta("7D"), "funding_rate"]
        if not funding.empty
        else pd.Series(dtype=float)
    )
    return {
        "asset": asset,
        "as_of_utc": frame.index[-1].isoformat(),
        "close": close.iloc[-1],
        "return_30d_pct": (close.iloc[-1] / close.iloc[-30 * BARS_PER_DAY] - 1) * 100,
        "return_90d_pct": (close.iloc[-1] / close.iloc[-90 * BARS_PER_DAY] - 1) * 100,
        "distance_ema200d_pct": (close.iloc[-1] / ema200.iloc[-1] - 1) * 100,
        "ema50_vs_ema200_pct": (ema50.iloc[-1] / ema200.iloc[-1] - 1) * 100,
        "ema50_above_ema200": bool(ema50.iloc[-1] > ema200.iloc[-1]),
        "realized_vol_30d_pct": rv30 * 100,
        "funding_7d_avg_bps": recent_funding.mean() * 10000 if len(recent_funding) else np.nan,
    }


def _plot_outputs(summary: pd.DataFrame, results: dict[tuple[str, str], pd.DataFrame], sensitivity: pd.DataFrame, robustness: pd.DataFrame, portfolios: dict[str, pd.DataFrame]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"figure.facecolor": "white", "axes.facecolor": "white", "font.size": 10})
    palette = {"BTC": "#2463EB", "ETH": "#B7791F", "SOL": "#D97757"}

    selected = ["buy_hold", "ema_50d_200d_long_cash", "vol_target_momentum_long_cash", "donchian_55d_20d_long_short"]
    fig, ax = plt.subplots(figsize=(11, 6))
    for strategy in selected:
        result = results.get(("BTC", strategy))
        if result is not None:
            ax.plot(result.index, result["equity"], label=strategy, linewidth=1.6)
    ax.set_title("BTC strategy equity curves")
    ax.set_xlabel("UTC date")
    ax.set_ylabel("Growth of $1, net of modeled costs")
    ax.grid(alpha=0.2)
    ax.legend(frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "btc_equity_curves.png", dpi=160)
    plt.close(fig)

    ranked = summary.groupby("strategy").agg(median_cagr_pct=("cagr_pct", "median"), median_mdd_pct=("max_drawdown_pct", "median")).sort_values("median_cagr_pct")
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.barh(ranked.index, ranked["median_cagr_pct"], color="#2463EB", edgecolor="#173B6C")
    ax.axvline(0, color="#333333", linewidth=0.8)
    ax.set_title("Median annualized return across BTC, ETH and SOL")
    ax.set_xlabel("CAGR (%)")
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "strategy_cagr_comparison.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    for strategy, group in sensitivity.groupby("strategy"):
        ax.plot(group["cost_bps"], group["cagr_pct"], marker="o", label=strategy)
    ax.set_title("BTC cost sensitivity")
    ax.set_xlabel("One-way fee + slippage (bps per 1x turnover)")
    ax.set_ylabel("CAGR (%)")
    ax.grid(alpha=0.2)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "btc_cost_sensitivity.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    families = list(robustness["family"].drop_duplicates())
    values = [robustness.loc[robustness["family"] == family, "holdout_return_pct"].dropna() for family in families]
    boxes = ax.boxplot(values, tick_labels=families, patch_artist=True, showfliers=True)
    for box in boxes["boxes"]:
        box.set(facecolor="#DCE8FA", edgecolor="#173B6C")
    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.set_title("Parameter robustness: 2024-current holdout returns")
    ax.set_ylabel("Holdout total return (%)")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "parameter_robustness_holdout.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 6))
    for name, result in portfolios.items():
        ax.plot(result.index, result["equity"], label=name, linewidth=1.6)
    ax.set_title("Portfolio equity curves")
    ax.set_xlabel("UTC date")
    ax.set_ylabel("Growth of $1, net of modeled costs")
    ax.grid(alpha=0.2)
    ax.legend(frameon=False, fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "portfolio_equity_curves.png", dpi=160)
    plt.close(fig)


def run_study(refresh: bool = False) -> dict[str, pd.DataFrame]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict] = []
    yearly_rows: list[dict] = []
    snapshot_rows: list[dict] = []
    results: dict[tuple[str, str], pd.DataFrame] = {}
    source_rows: list[dict] = []

    for asset, symbol in SYMBOLS.items():
        frame = fetch_ohlcv(asset, symbol, refresh=refresh)
        funding = fetch_funding(asset, symbol, refresh=refresh)
        source_rows.append({"asset": asset, "ohlcv_rows": len(frame), "funding_rows": len(funding), "start": frame.index.min().isoformat(), "end": frame.index.max().isoformat(), "duplicate_timestamps": int(frame.index.duplicated().sum()), "null_cells": int(frame.isna().sum().sum())})
        snapshot_rows.append(_market_snapshot(asset, frame, funding))

        for spec in STRATEGIES:
            result = backtest(frame, funding, spec)
            results[(asset, spec.name)] = result
            row = {"asset": asset, "strategy": spec.name, "market": spec.market, **metrics(result)}
            row["return_2021_2023_pct"] = _period_return(result, "2021-08-01", "2023-12-31")
            row["return_2024_current_pct"] = _period_return(result, "2024-01-01")
            row["return_2025_current_pct"] = _period_return(result, "2025-01-01")
            summary_rows.append(row)
            annual = result["net_return"].groupby(result.index.year).apply(lambda values: (1 + values).prod() - 1)
            yearly_rows.extend({"asset": asset, "strategy": spec.name, "year": int(year), "return_pct": value * 100} for year, value in annual.items())

    summary = pd.DataFrame(summary_rows)
    yearly = pd.DataFrame(yearly_rows)
    snapshot = pd.DataFrame(snapshot_rows)
    sources = pd.DataFrame(source_rows)

    portfolio_definitions = {
        "equal_weight_buy_hold": ("buy_hold", {"BTC": 1 / 3, "ETH": 1 / 3, "SOL": 1 / 3}),
        "quality_tilt_buy_hold": ("buy_hold", {"BTC": 0.6, "ETH": 0.3, "SOL": 0.1}),
        "equal_weight_vol_target": ("vol_target_momentum_long_cash", {"BTC": 1 / 3, "ETH": 1 / 3, "SOL": 1 / 3}),
        "quality_tilt_vol_target": ("vol_target_momentum_long_cash", {"BTC": 0.6, "ETH": 0.3, "SOL": 0.1}),
        "btc_only_vol_target": ("vol_target_momentum_long_cash", {"BTC": 1.0}),
    }
    portfolios = {
        name: _portfolio_result(results, strategy, weights)
        for name, (strategy, weights) in portfolio_definitions.items()
    }
    portfolio_rows = []
    for name, result in portfolios.items():
        row = {"portfolio": name, **metrics(result)}
        row["return_2024_current_pct"] = _period_return(result, "2024-01-01")
        row["return_2025_current_pct"] = _period_return(result, "2025-01-01")
        portfolio_rows.append(row)
    portfolio_summary = pd.DataFrame(portfolio_rows).sort_values("sharpe", ascending=False)
    exposure_rows = []
    for name, (strategy, weights) in portfolio_definitions.items():
        for asset, weight in weights.items():
            current_position = float(results[(asset, strategy)]["position"].iloc[-1])
            exposure_rows.append({"portfolio": name, "asset": asset, "base_weight": weight, "signal_position": current_position, "current_net_exposure": weight * current_position})
    portfolio_exposure = pd.DataFrame(exposure_rows)
    scenario_rows = []
    quality_weights = {"BTC": 0.6, "ETH": 0.3, "SOL": 0.1}
    for target_vol in [0.20, 0.25, 0.35, 0.45]:
        pieces = []
        current_exposure = 0.0
        for asset, symbol in SYMBOLS.items():
            frame = fetch_ohlcv(asset, symbol)
            funding = fetch_funding(asset, symbol)
            spec = StrategySpec(
                "risk_target_scenario",
                "spot",
                lambda data, target_vol=target_vol: signal_vol_target_params(data, 90, 200, target_vol),
            )
            result = backtest(frame, funding, spec)
            pieces.append(result[["position", "turnover", "gross_return", "cost", "funding", "net_return"]] * quality_weights[asset])
            current_exposure += float(result["position"].iloc[-1]) * quality_weights[asset]
        portfolio = sum(pieces[1:], pieces[0])
        portfolio["equity"] = (1 + portfolio["net_return"]).cumprod()
        scenario_rows.append({
            "target_vol_pct": target_vol * 100,
            **metrics(portfolio),
            "return_2024_current_pct": _period_return(portfolio, "2024-01-01"),
            "return_2025_current_pct": _period_return(portfolio, "2025-01-01"),
            "current_net_exposure_pct": current_exposure * 100,
        })
    risk_scenarios = pd.DataFrame(scenario_rows)

    robustness_rows = []
    for asset, symbol in SYMBOLS.items():
        frame = fetch_ohlcv(asset, symbol)
        funding = fetch_funding(asset, symbol)
        for fast_days in [30, 50, 80]:
            for slow_days in [150, 200, 250]:
                if fast_days >= slow_days:
                    continue
                spec = StrategySpec(
                    "ema_grid",
                    "spot",
                    lambda data, fast_days=fast_days, slow_days=slow_days: signal_ema_long_cash_params(data, fast_days, slow_days),
                )
                result = backtest(frame, funding, spec)
                robustness_rows.append({
                    "asset": asset,
                    "family": "ema_long_cash",
                    "params": f"fast={fast_days},slow={slow_days}",
                    "train_return_pct": _period_return(result, "2021-08-01", "2023-12-31"),
                    "holdout_return_pct": _period_return(result, "2024-01-01"),
                    "full_sharpe": metrics(result)["sharpe"],
                    "full_max_drawdown_pct": metrics(result)["max_drawdown_pct"],
                })
        for momentum_days in [60, 90, 120]:
            for slow_days in [150, 200, 250]:
                for target_vol in [0.25, 0.35, 0.45]:
                    spec = StrategySpec(
                        "vol_target_grid",
                        "spot",
                        lambda data, momentum_days=momentum_days, slow_days=slow_days, target_vol=target_vol: signal_vol_target_params(data, momentum_days, slow_days, target_vol),
                    )
                    result = backtest(frame, funding, spec)
                    robustness_rows.append({
                        "asset": asset,
                        "family": "vol_target_momentum",
                        "params": f"mom={momentum_days},slow={slow_days},vol={target_vol:.2f}",
                        "train_return_pct": _period_return(result, "2021-08-01", "2023-12-31"),
                        "holdout_return_pct": _period_return(result, "2024-01-01"),
                        "full_sharpe": metrics(result)["sharpe"],
                        "full_max_drawdown_pct": metrics(result)["max_drawdown_pct"],
                    })
    robustness = pd.DataFrame(robustness_rows)
    selected_rows = []
    for (asset, family), group in robustness.groupby(["asset", "family"]):
        chosen = group.loc[group["train_return_pct"].idxmax()]
        selected_rows.append(chosen.to_dict())
    walk_forward = pd.DataFrame(selected_rows)

    btc_frame = fetch_ohlcv("BTC", SYMBOLS["BTC"])
    btc_funding = fetch_funding("BTC", SYMBOLS["BTC"])
    sensitivity_rows = []
    for spec in STRATEGIES:
        for cost in [0.0004, 0.0008, 0.0013, 0.0020]:
            result = backtest(btc_frame, btc_funding, spec, cost_override=cost)
            sensitivity_rows.append({"strategy": spec.name, "cost_bps": cost * 10000, **metrics(result)})
    sensitivity = pd.DataFrame(sensitivity_rows)

    summary.to_csv(OUTPUT_DIR / "strategy_summary.csv", index=False)
    yearly.to_csv(OUTPUT_DIR / "yearly_returns.csv", index=False)
    snapshot.to_csv(OUTPUT_DIR / "market_snapshot.csv", index=False)
    sensitivity.to_csv(OUTPUT_DIR / "cost_sensitivity.csv", index=False)
    sources.to_csv(OUTPUT_DIR / "source_quality.csv", index=False)
    robustness.to_csv(OUTPUT_DIR / "parameter_robustness.csv", index=False)
    walk_forward.to_csv(OUTPUT_DIR / "walk_forward_selection.csv", index=False)
    portfolio_summary.to_csv(OUTPUT_DIR / "portfolio_summary.csv", index=False)
    portfolio_exposure.to_csv(OUTPUT_DIR / "portfolio_current_exposure.csv", index=False)
    risk_scenarios.to_csv(OUTPUT_DIR / "risk_target_scenarios.csv", index=False)
    _plot_outputs(summary, results, sensitivity, robustness, portfolios)

    aggregate = summary.groupby("strategy").agg(
        median_cagr_pct=("cagr_pct", "median"),
        median_sharpe=("sharpe", "median"),
        worst_max_drawdown_pct=("max_drawdown_pct", "min"),
        min_holdout_return_pct=("return_2024_current_pct", "min"),
        median_round_trips=("round_trips_est", "median"),
    ).reset_index()
    aggregate["robust_score"] = aggregate["median_sharpe"] + aggregate["min_holdout_return_pct"] / 100 + aggregate["worst_max_drawdown_pct"] / 100
    aggregate = aggregate.sort_values("robust_score", ascending=False)
    aggregate.to_csv(OUTPUT_DIR / "aggregate_ranking.csv", index=False)

    validation = {
        "as_of_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "execution": "signal at close; position begins next bar open",
        "price_interval": TIMEFRAME,
        "warmup_start": "2021-08-01 UTC",
        "spot_cost_bps_per_turnover": 13,
        "futures_cost_bps_per_turnover": 8,
        "funding": "actual Binance USD-M history; positive rate is paid by longs and received by shorts",
        "leverage": "maximum absolute exposure 1.0x",
        "known_limits": [
            "OHLCV bars cannot model order-book depth or gap-dependent fills.",
            "The same USD-M perpetual price series is used as a price proxy for spot strategies.",
            "No tax, exchange outage, delisting, or account-specific fee tier is modeled.",
            "Fixed-rule validation is not proof of future profitability.",
        ],
    }
    (OUTPUT_DIR / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"summary": summary, "yearly": yearly, "snapshot": snapshot, "sensitivity": sensitivity, "sources": sources, "aggregate": aggregate, "robustness": robustness, "walk_forward": walk_forward, "portfolio_summary": portfolio_summary, "portfolio_exposure": portfolio_exposure, "risk_scenarios": risk_scenarios}


if __name__ == "__main__":
    study = run_study(refresh=False)
    print(study["sources"].to_string(index=False))
    print("\nAggregate ranking")
    print(study["aggregate"].round(3).to_string(index=False))
    print("\nMarket snapshot")
    print(study["snapshot"].round(3).to_string(index=False))
