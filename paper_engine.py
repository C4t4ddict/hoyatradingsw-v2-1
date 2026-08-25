"""Deterministic event-driven paper engine for long/cash volatility targeting."""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from statistics import pstdev
from typing import Any, Dict, List, Optional

from paper_ledger import TradingLedger


FOUR_HOURS_MS = 4 * 60 * 60 * 1000
YEAR_BARS_4H = 365 * 6
DEFAULT_BASE_WEIGHTS = {
    "BTC/USDT": 0.60,
    "ETH/USDT": 0.30,
    "SOL/USDT": 0.10,
}


def _iso(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


def _ema(values: List[float], period: int) -> float:
    if len(values) < period:
        raise ValueError(f"need at least {period} closes")
    alpha = 2.0 / (period + 1.0)
    value = values[-period]
    for item in values[-period + 1:]:
        value = item * alpha + value * (1.0 - alpha)
    return value


def _annualized_volatility(values: List[float], period: int) -> float:
    if len(values) < period + 1:
        raise ValueError(f"need at least {period + 1} closes")
    window = values[-(period + 1):]
    returns = [math.log(window[i] / window[i - 1]) for i in range(1, len(window))]
    return pstdev(returns) * math.sqrt(YEAR_BARS_4H)


def _event_id(*parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class StrategyDecision:
    as_of_ms: int
    target_weights: Dict[str, float]
    cash_weight: float
    signals: Dict[str, Dict[str, Any]]
    data_quality: Dict[str, Any]
    strategy_version: str = "vol-target-momentum-v1"


class VolTargetMomentumStrategy:
    """Long/cash momentum strategy selected by the independent research study."""

    def __init__(
        self,
        *,
        base_weights: Optional[Dict[str, float]] = None,
        ema_bars: int = 1200,
        momentum_bars: int = 540,
        volatility_bars: int = 180,
        target_volatility: float = 0.20,
        exposure_multiplier: float = 1.0,
    ):
        self.base_weights = dict(base_weights or DEFAULT_BASE_WEIGHTS)
        self.ema_bars = int(ema_bars)
        self.momentum_bars = int(momentum_bars)
        self.volatility_bars = int(volatility_bars)
        self.target_volatility = min(max(float(target_volatility), 0.01), 0.25)
        self.exposure_multiplier = min(max(float(exposure_multiplier), 0.0), 1.0)

    def evaluate(self, histories: Dict[str, List[List[float]]], as_of_ms: int) -> StrategyDecision:
        targets: Dict[str, float] = {}
        signals: Dict[str, Dict[str, Any]] = {}
        errors: List[str] = []
        required = max(self.ema_bars, self.momentum_bars + 1, self.volatility_bars + 1)

        for symbol, base_weight in self.base_weights.items():
            candles = histories.get(symbol) or []
            if len(candles) < required:
                errors.append(f"{symbol}: insufficient candles {len(candles)}/{required}")
                targets[symbol] = 0.0
                continue
            timestamps = [int(row[0]) for row in candles]
            gaps = sum(1 for left, right in zip(timestamps, timestamps[1:]) if right - left != FOUR_HOURS_MS)
            if gaps:
                errors.append(f"{symbol}: {gaps} missing 4h intervals")
                targets[symbol] = 0.0
                continue
            closes = [float(row[4]) for row in candles]
            ema_value = _ema(closes, self.ema_bars)
            momentum = closes[-1] / closes[-1 - self.momentum_bars] - 1.0
            realized_vol = _annualized_volatility(closes, self.volatility_bars)
            active = closes[-1] > ema_value and momentum > 0.0
            scale = min(1.0, self.target_volatility / max(realized_vol, 1e-9)) if active else 0.0
            target = max(0.0, float(base_weight) * scale * self.exposure_multiplier)
            targets[symbol] = target
            signals[symbol] = {
                "active": active,
                "close": closes[-1],
                "ema": ema_value,
                "momentum": momentum,
                "realized_volatility": realized_vol,
                "volatility_scale": scale,
                "target_weight": target,
                "regime_exposure_multiplier": self.exposure_multiplier,
                "bar_timestamp_ms": timestamps[-1],
            }

        total = min(sum(targets.values()), 1.0)
        decision_as_of = min(
            (int(signal["bar_timestamp_ms"]) for signal in signals.values()),
            default=as_of_ms,
        )
        return StrategyDecision(
            as_of_ms=decision_as_of,
            target_weights=targets,
            cash_weight=max(0.0, 1.0 - total),
            signals=signals,
            data_quality={"ok": not errors, "errors": errors, "required_bars": required},
        )


@dataclass
class RiskPolicy:
    daily_loss_limit_pct: float = 0.02
    reduce_risk_drawdown_pct: float = 0.10
    block_new_buy_drawdown_pct: float = 0.15
    max_spread_bps: float = 25.0
    stale_after_ms: int = 6 * 60 * 60 * 1000
    max_order_nav_pct: float = 0.35


@dataclass
class RiskContext:
    initial_equity: float
    current_equity: float
    equity_peak: float
    daily_realized_pnl: float = 0.0
    latest_bar_ms: int = 0
    now_ms: int = 0
    spread_bps: float = 0.0
    balance_consistent: bool = True


def evaluate_order_risk(side: str, notional: float, context: RiskContext, policy: RiskPolicy) -> Dict[str, Any]:
    reasons: List[str] = []
    adjusted = max(0.0, float(notional))
    drawdown = 1.0 - context.current_equity / max(context.equity_peak, 1e-9)
    if not context.balance_consistent:
        reasons.append("balance_mismatch")
    if context.now_ms - context.latest_bar_ms > policy.stale_after_ms:
        reasons.append("stale_market_data")
    if context.spread_bps > policy.max_spread_bps:
        reasons.append("spread_limit")
    if context.daily_realized_pnl <= -abs(context.initial_equity * policy.daily_loss_limit_pct):
        reasons.append("daily_loss_limit")
    if side == "sell":
        reasons = [reason for reason in reasons if reason not in {"daily_loss_limit"}]
    if side == "buy" and drawdown >= policy.block_new_buy_drawdown_pct:
        reasons.append("drawdown_buy_block")
    elif side == "buy" and drawdown >= policy.reduce_risk_drawdown_pct:
        adjusted *= 0.5
    adjusted = min(adjusted, context.current_equity * policy.max_order_nav_pct)
    return {
        "allowed": not reasons and adjusted > 0.0,
        "requested_notional": notional,
        "adjusted_notional": adjusted,
        "drawdown_pct": drawdown,
        "reasons": sorted(set(reasons)),
    }


@dataclass
class PaperPortfolio:
    initial_cash: float
    cash: float
    units: Dict[str, float] = field(default_factory=dict)
    average_cost: Dict[str, float] = field(default_factory=dict)
    equity_peak: float = 0.0
    daily_realized_pnl: float = 0.0

    def equity(self, prices: Dict[str, float]) -> float:
        return self.cash + sum(self.units.get(symbol, 0.0) * price for symbol, price in prices.items())

    def weights(self, prices: Dict[str, float]) -> Dict[str, float]:
        nav = self.equity(prices)
        return {symbol: self.units.get(symbol, 0.0) * price / max(nav, 1e-9) for symbol, price in prices.items()}


class EventDrivenPaperEngine:
    """Create orders at a confirmed close and execute them at the next bar open."""

    def __init__(
        self,
        *,
        session_id: str,
        initial_cash: float,
        ledger: TradingLedger,
        strategy: Optional[VolTargetMomentumStrategy] = None,
        risk_policy: Optional[RiskPolicy] = None,
        fee_pct: float = 0.0005,
        slippage_pct: float = 0.0005,
        rebalance_threshold: float = 0.05,
    ):
        self.session_id = session_id
        self.ledger = ledger
        self.strategy = strategy or VolTargetMomentumStrategy()
        self.risk_policy = risk_policy or RiskPolicy()
        self.fee_pct = max(0.0, float(fee_pct))
        self.slippage_pct = max(0.0, float(slippage_pct))
        self.rebalance_threshold = max(0.0, float(rebalance_threshold))
        self.portfolio = PaperPortfolio(initial_cash, initial_cash, equity_peak=initial_cash)
        self.pending_orders: List[Dict[str, Any]] = []
        self.last_rebalance_ms: Optional[int] = None
        self.last_signal_ms: Optional[int] = None

    def on_bar_close(
        self,
        histories: Dict[str, List[List[float]]],
        *,
        now_ms: int,
        spreads_bps: Optional[Dict[str, float]] = None,
        balance_consistent: bool = True,
    ) -> Dict[str, Any]:
        decision = self.strategy.evaluate(histories, now_ms)
        if not decision.data_quality["ok"]:
            event_id = _event_id(self.session_id, "signal_rejected", now_ms)
            self.ledger.append_event(
                event_id=event_id,
                session_id=self.session_id,
                event_type="signal_rejected",
                payload=asdict(decision),
                strategy_version=decision.strategy_version,
            )
            return {"decision": asdict(decision), "orders": [], "rejected": decision.data_quality["errors"]}
        if self.last_signal_ms == decision.as_of_ms:
            return {"decision": asdict(decision), "orders": [], "duplicate": True}

        prices = {symbol: float(history[-1][4]) for symbol, history in histories.items() if history}
        nav = self.portfolio.equity(prices)
        self.portfolio.equity_peak = max(self.portfolio.equity_peak, nav)
        current_weights = self.portfolio.weights(prices)
        max_drift = max(
            abs(decision.target_weights.get(symbol, 0.0) - current_weights.get(symbol, 0.0))
            for symbol in decision.target_weights
        )
        daily_due = self.last_rebalance_ms is None or now_ms - self.last_rebalance_ms >= 24 * 60 * 60 * 1000
        if not daily_due and max_drift < self.rebalance_threshold:
            self.last_signal_ms = decision.as_of_ms
            return {"decision": asdict(decision), "orders": [], "rebalance_due": False}

        orders = []
        for symbol, target_weight in decision.target_weights.items():
            current_value = self.portfolio.units.get(symbol, 0.0) * prices[symbol]
            delta = nav * target_weight - current_value
            if abs(delta) < max(1.0, nav * 0.001):
                continue
            side = "buy" if delta > 0 else "sell"
            signal_bar_ms = int(histories[symbol][-1][0])
            order_id = _event_id(self.session_id, symbol, signal_bar_ms, round(target_weight, 8))
            context = RiskContext(
                initial_equity=self.portfolio.initial_cash,
                current_equity=nav,
                equity_peak=self.portfolio.equity_peak,
                daily_realized_pnl=self.portfolio.daily_realized_pnl,
                latest_bar_ms=signal_bar_ms,
                now_ms=now_ms,
                spread_bps=float((spreads_bps or {}).get(symbol, 0.0)),
                balance_consistent=balance_consistent,
            )
            risk = evaluate_order_risk(side, abs(delta), context, self.risk_policy)
            payload = {
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "target_weight": target_weight,
                "signal_bar_ms": signal_bar_ms,
                "execute_after_ms": signal_bar_ms + FOUR_HOURS_MS,
                "risk": risk,
            }
            if not risk["allowed"]:
                self.ledger.append_event(
                    event_id=order_id,
                    session_id=self.session_id,
                    event_type="order_rejected",
                    payload=payload,
                    strategy_version=decision.strategy_version,
                )
                orders.append({**payload, "status": "rejected"})
                continue
            payload["notional"] = risk["adjusted_notional"]
            if self.ledger.append_event(
                event_id=order_id,
                session_id=self.session_id,
                event_type="order_pending",
                payload=payload,
                strategy_version=decision.strategy_version,
            ):
                self.pending_orders.append(payload)
                orders.append({**payload, "status": "pending"})

        self.last_signal_ms = decision.as_of_ms
        if orders:
            self.last_rebalance_ms = now_ms
        return {"decision": asdict(decision), "orders": orders, "rebalance_due": True}

    def on_bar_open(self, *, timestamp_ms: int, open_prices: Dict[str, float]) -> List[Dict[str, Any]]:
        executions = []
        remaining = []
        for order in self.pending_orders:
            symbol = order["symbol"]
            if timestamp_ms < order["execute_after_ms"] or symbol not in open_prices:
                remaining.append(order)
                continue
            raw_price = float(open_prices[symbol])
            side = order["side"]
            price = raw_price * (1 + self.slippage_pct if side == "buy" else 1 - self.slippage_pct)
            notional = float(order["notional"])
            if side == "buy":
                notional = min(notional, self.portfolio.cash / (1.0 + self.fee_pct))
                units = notional / max(price, 1e-9)
                fee = notional * self.fee_pct
                previous_units = self.portfolio.units.get(symbol, 0.0)
                previous_cost = self.portfolio.average_cost.get(symbol, 0.0)
                self.portfolio.cash -= notional + fee
                total_units = previous_units + units
                self.portfolio.units[symbol] = total_units
                self.portfolio.average_cost[symbol] = (
                    (previous_units * previous_cost + units * price + fee) / max(total_units, 1e-9)
                )
                realized_pnl = 0.0
            else:
                units = min(self.portfolio.units.get(symbol, 0.0), notional / max(price, 1e-9))
                notional = units * price
                fee = notional * self.fee_pct
                realized_pnl = (price - self.portfolio.average_cost.get(symbol, price)) * units - fee
                self.portfolio.units[symbol] = self.portfolio.units.get(symbol, 0.0) - units
                self.portfolio.cash += notional - fee
                self.portfolio.daily_realized_pnl += realized_pnl
                if self.portfolio.units[symbol] <= 1e-12:
                    self.portfolio.units[symbol] = 0.0
                    self.portfolio.average_cost.pop(symbol, None)
            execution = {
                **order,
                "status": "filled",
                "execution_ms": timestamp_ms,
                "price": price,
                "units": units,
                "notional": notional,
                "fee": fee,
                "realized_pnl": realized_pnl,
            }
            execution_id = _event_id(order["order_id"], "filled")
            self.ledger.append_event(
                event_id=execution_id,
                session_id=self.session_id,
                event_type="order_filled",
                payload=execution,
                occurred_at=_iso(timestamp_ms),
                strategy_version=self.strategy.__class__.__name__,
            )
            executions.append(execution)
        self.pending_orders = remaining
        return executions

    def snapshot(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "portfolio": asdict(self.portfolio),
            "pending_orders": self.pending_orders,
            "last_rebalance_ms": self.last_rebalance_ms,
            "last_signal_ms": self.last_signal_ms,
        }

    def restore(self, snapshot: Dict[str, Any]) -> None:
        portfolio = snapshot.get("portfolio") or {}
        if portfolio:
            self.portfolio = PaperPortfolio(**portfolio)
        self.pending_orders = list(snapshot.get("pending_orders") or [])
        self.last_rebalance_ms = snapshot.get("last_rebalance_ms")
        self.last_signal_ms = snapshot.get("last_signal_ms")
