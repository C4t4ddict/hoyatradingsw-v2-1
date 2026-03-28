import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

STATE_PATH = os.getenv("RISK_STATE_PATH", "data/risk_state.json")


@dataclass
class GuardConfig:
    daily_loss_limit_usdt: float
    max_consecutive_losses: int


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _ensure_parent(path: str):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def load_state(path: str = STATE_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {
            "date": _today_utc(),
            "daily_realized_pnl": 0.0,
            "consecutive_losses": 0,
            "halted": False,
            "reason": None,
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}

    if state.get("date") != _today_utc():
        state = {
            "date": _today_utc(),
            "daily_realized_pnl": 0.0,
            "consecutive_losses": 0,
            "halted": False,
            "reason": None,
        }

    return state


def save_state(state: Dict[str, Any], path: str = STATE_PATH):
    _ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def evaluate_halt(state: Dict[str, Any], cfg: GuardConfig) -> Dict[str, Any]:
    state["halted"] = False
    state["reason"] = None

    if state.get("daily_realized_pnl", 0.0) <= -abs(cfg.daily_loss_limit_usdt):
        state["halted"] = True
        state["reason"] = f"daily loss limit reached: {state.get('daily_realized_pnl'):.2f} USDT"
        return state

    if state.get("consecutive_losses", 0) >= cfg.max_consecutive_losses:
        state["halted"] = True
        state["reason"] = f"max consecutive losses reached: {state.get('consecutive_losses')}"
        return state

    return state


def apply_trade_result(realized_pnl: float, cfg: GuardConfig, path: str = STATE_PATH) -> Dict[str, Any]:
    state = load_state(path)
    state["daily_realized_pnl"] = float(state.get("daily_realized_pnl", 0.0)) + float(realized_pnl)

    if realized_pnl < 0:
        state["consecutive_losses"] = int(state.get("consecutive_losses", 0)) + 1
    else:
        state["consecutive_losses"] = 0

    state = evaluate_halt(state, cfg)
    save_state(state, path)
    return state


def can_trade(cfg: GuardConfig, path: str = STATE_PATH) -> Dict[str, Any]:
    state = load_state(path)
    state = evaluate_halt(state, cfg)
    save_state(state, path)
    return {
        "allowed": not state.get("halted", False),
        "state": state,
    }
