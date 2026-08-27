import math
import statistics
from datetime import date, datetime, time, timezone
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from backtest import fetch_funding_rates, fetch_ohlcv, run_backtest
from exchange import get_exchange


ASSET_SYMBOLS = {
    "spot": {
        "BTC": "BTC/USDT",
        "ETH": "ETH/USDT",
        "SOL": "SOL/USDT",
    },
    "futures": {
        "BTC": "BTC/USDT:USDT",
        "ETH": "ETH/USDT:USDT",
        "SOL": "SOL/USDT:USDT",
    },
}

TIMEFRAME_HOURS = {"15m": 0.25, "1h": 1.0, "4h": 4.0}
TIMEFRAME_MS = {key: int(hours * 3_600_000) for key, hours in TIMEFRAME_HOURS.items()}
KST = ZoneInfo("Asia/Seoul")


def _iso_bounds(start_date: date, end_date: date) -> tuple[str, str]:
    start = datetime.combine(start_date, time.min, tzinfo=KST)
    end = datetime.combine(end_date, time.max, tzinfo=KST)
    return start.isoformat(), end.isoformat()


def _sample_curve(curve: List[Dict[str, Any]], limit: int = 360) -> List[Dict[str, Any]]:
    if len(curve) <= limit:
        return curve
    step = max(1, math.ceil((len(curve) - 1) / (limit - 1)))
    sampled = curve[::step]
    if sampled[-1] != curve[-1]:
        sampled.append(curve[-1])
    return sampled


def _annualized_sharpe(curve: List[Dict[str, Any]], timeframe: str) -> float:
    values = [float(row["equity"]) for row in curve if float(row.get("equity") or 0) > 0]
    returns = [(values[i] / values[i - 1]) - 1.0 for i in range(1, len(values)) if values[i - 1] > 0]
    if len(returns) < 2:
        return 0.0
    deviation = statistics.stdev(returns)
    if deviation <= 0:
        return 0.0
    periods_per_year = 365.0 * 24.0 / TIMEFRAME_HOURS[timeframe]
    return statistics.mean(returns) / deviation * math.sqrt(periods_per_year)


def _completed_candles(candles: List[List[float]], timeframe: str, now_ms: int | None = None) -> List[List[float]]:
    cutoff = now_ms if now_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    duration = TIMEFRAME_MS[timeframe]
    return [row for row in candles if int(row[0]) + duration <= cutoff]


def run_backtest_analysis(
    *,
    asset: str,
    market_type: str,
    timeframe: str,
    start_date: date,
    end_date: date,
    strategy: str,
    position_mode: str,
    initial_usdt: float,
    fee_pct: float,
    slippage_pct: float,
    leverage: float,
) -> Dict[str, Any]:
    if end_date < start_date:
        raise ValueError("종료일은 시작일보다 빠를 수 없습니다.")
    period_days = (end_date - start_date).days + 1
    if period_days < 14:
        raise ValueError("백테스트 기간은 최소 14일이어야 합니다.")
    if period_days > 1095:
        raise ValueError("백테스트 기간은 최대 3년입니다.")
    if end_date > datetime.now(KST).date():
        raise ValueError("종료일은 오늘 이후일 수 없습니다.")

    symbol = ASSET_SYMBOLS[market_type][asset]
    start_iso, end_iso = _iso_bounds(start_date, end_date)
    exchange = get_exchange(read_only=True, market_type=market_type)
    candles = _completed_candles(fetch_ohlcv(exchange, symbol, timeframe, start_iso, end_iso), timeframe)
    if len(candles) < 80:
        raise ValueError(f"백테스트에 필요한 캔들이 부족합니다. 수집: {len(candles)}개, 최소: 80개")

    funding_events = []
    if market_type == "futures":
        funding_events = fetch_funding_rates(exchange, symbol, start_iso, end_iso)

    result = run_backtest(
        candles,
        strategy=strategy,
        initial_usdt=initial_usdt,
        fee_pct=fee_pct,
        slippage_pct=slippage_pct,
        funding_events=funding_events,
        position_mode=position_mode,
        leverage=leverage,
    )
    if result.get("error"):
        raise ValueError(str(result["error"]))

    first_open = float(candles[0][1])
    last_close = float(candles[-1][4])
    benchmark_entry = first_open * (1.0 + slippage_pct) * (1.0 + fee_pct)
    benchmark_exit = last_close * (1.0 - slippage_pct) * (1.0 - fee_pct)
    benchmark_return = ((benchmark_exit / benchmark_entry) - 1.0) * 100.0 if benchmark_entry > 0 else 0.0
    curve = result.get("equity_curve") or []
    total_fees = sum(float(trade.get("fees") or 0) for trade in result.get("trades") or [])
    total_funding = sum(float(trade.get("funding_fee") or 0) for trade in result.get("trades") or [])

    return {
        "request": {
            "asset": asset,
            "symbol": symbol,
            "market_type": market_type,
            "timeframe": timeframe,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "strategy": strategy,
            "position_mode": position_mode,
            "initial_usdt": initial_usdt,
            "leverage": leverage,
        },
        "metrics": {
            "return_pct": result["return_pct"],
            "benchmark_return_pct": benchmark_return,
            "excess_return_pct": result["return_pct"] - benchmark_return,
            "final_usdt": result["final_usdt"],
            "total_trades": result["total_trades"],
            "win_rate": result["win_rate"],
            "profit_factor": result["profit_factor"],
            "max_drawdown_pct": result["max_drawdown_pct"],
            "sharpe": _annualized_sharpe(curve, timeframe),
            "liquidation_count": result["liquidation_count"],
            "total_fees": total_fees,
            "total_funding": total_funding,
        },
        "equity_curve": _sample_curve(curve),
        "trades": (result.get("trades") or [])[-100:],
        "source": {
            "provider": "Binance 공개 OHLCV",
            "authenticated": False,
            "completed_candles_only": True,
            "candle_count": len(candles),
            "first_candle_at": datetime.fromtimestamp(candles[0][0] / 1000, tz=timezone.utc).isoformat(),
            "last_candle_at": datetime.fromtimestamp(candles[-1][0] / 1000, tz=timezone.utc).isoformat(),
            "funding_event_count": len(funding_events),
            "fee_pct": fee_pct,
            "slippage_pct": slippage_pct,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
