import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from backtest import fetch_ohlcv, fetch_funding_rates, run_backtest, run_ensemble_backtest
from exchange import get_exchange
from notifier import send_telegram

STATE_PATH = os.getenv("PAPER_LIVE_STATE_PATH", "data/paper_live_state.json")
PID_PATH = os.getenv("PAPER_LIVE_PID_PATH", "data/paper_live_worker.pid")


def _ensure_parent(path: str):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state(path: str = STATE_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"running": False}
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {"running": False}
    except Exception:
        return {"running": False}


def save_state(state: Dict[str, Any], path: str = STATE_PATH):
    _ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _read_pid(path: str = PID_PATH) -> int:
    if not os.path.exists(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int((f.read() or "0").strip())
    except Exception:
        return 0


def _write_pid(pid: int, path: str = PID_PATH):
    _ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(pid))


def _clear_pid(path: str = PID_PATH):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def start_background_worker():
    pid = _read_pid()
    if _is_pid_alive(pid):
        return pid

    cwd = os.path.dirname(os.path.abspath(__file__))
    runner = os.path.join(cwd, "paper_live_runner.py")

    # 가상환경 python 경로 우선 사용
    venv_py = os.path.join(cwd, ".venv", "bin", "python")
    py_exec = venv_py if os.path.exists(venv_py) else sys.executable

    proc = subprocess.Popen([py_exec, runner], cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _write_pid(proc.pid)
    return proc.pid


def stop_background_worker():
    pid = _read_pid()
    if _is_pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    _clear_pid()


def start_session(config: Dict[str, Any], path: str = STATE_PATH):
    state = {
        "running": True,
        "paused": False,
        "started_at": _now_iso(),
        "last_update": None,
        "config": config,
        "metrics": {
            "virtual_balance": config.get("initial_usdt", 1000.0),
            "return_pct": 0.0,
            "trades": 0,
            "liquidations": 0,
        },
        "alert_last_trade_count": 0,
    }
    save_state(state, path)
    pid = start_background_worker()
    state["worker_pid"] = pid
    save_state(state, path)
    return state


def pause_session(path: str = STATE_PATH):
    state = load_state(path)
    state["running"] = False
    state["paused"] = True
    save_state(state, path)
    stop_background_worker()
    return state


def resume_session(config_updates: Dict[str, Any] = None, path: str = STATE_PATH):
    # 안전장치: 실수로 resume_session(live_cfg)처럼 호출되면 path 자리에 dict가 들어올 수 있음
    if isinstance(path, dict) and config_updates is None:
        config_updates = path
        path = STATE_PATH

    state = load_state(path)
    if not state:
        base_cfg = {"initial_usdt": 1000.0}
        if config_updates:
            base_cfg.update(config_updates)
        return start_session(base_cfg, path)

    state["running"] = True
    state["paused"] = False

    if config_updates:
        cfg = state.get("config") or {}
        cfg.update(config_updates)
        state["config"] = cfg

    if state.get("alert_last_trade_count") is None:
        state["alert_last_trade_count"] = int((state.get("metrics") or {}).get("trades", 0) or 0)

    save_state(state, path)
    pid = start_background_worker()
    state["worker_pid"] = pid
    save_state(state, path)
    return state


def stop_session(path: str = STATE_PATH):
    # 기존 stop은 pause 의미로 유지 (호환)
    return pause_session(path)


def reset_session(path: str = STATE_PATH):
    stop_background_worker()
    state = {"running": False, "paused": False, "reset_at": _now_iso(), "metrics": {"virtual_balance": 0.0, "return_pct": 0.0, "trades": 0, "liquidations": 0}}
    save_state(state, path)
    return state


def _notify_new_trades(state: Dict[str, Any], cfg: Dict[str, Any], result: Dict[str, Any]):
    trades = result.get("trades") or []
    if not isinstance(trades, list):
        return

    prev_count = int(state.get("alert_last_trade_count") or 0)
    new_count = len(trades)
    if new_count <= prev_count:
        state["alert_last_trade_count"] = new_count
        return

    symbol = cfg.get("symbol", "-")
    strategy = cfg.get("strategy", "-")
    timeframe = cfg.get("timeframe", "-")

    for t in trades[prev_count:new_count]:
        side = str(t.get("side", "-")).upper()
        entry = t.get("entry")
        exit_ = t.get("exit")
        pnl = t.get("pnl")
        pnl_pct = t.get("pnl_pct")
        msg = (
            "🧪 [Paper] 거래 체결\n"
            f"전략: {strategy} ({timeframe})\n"
            f"심볼: {symbol}\n"
            f"방향: {side}\n"
            f"진입: {entry}\n"
            f"청산: {exit_}\n"
            f"PnL: {pnl} ({pnl_pct}%)"
        )
        send_telegram(msg, channel="paper")

    state["alert_last_trade_count"] = new_count


def update_session(path: str = STATE_PATH) -> Dict[str, Any]:
    state = load_state(path)
    if not state.get("running"):
        return state

    cfg = state.get("config") or {}
    market_type = cfg.get("market_type", "futures")
    symbol = cfg.get("symbol", "BTC/USDT:USDT")
    timeframe = cfg.get("timeframe", "15m")
    strategy = cfg.get("strategy", "ensemble_regime")

    start_iso = state.get("started_at") or _now_iso()
    end_iso = _now_iso()

    ex = get_exchange(read_only=True, market_type=("swap" if market_type == "futures" else "spot"))
    candles = fetch_ohlcv(ex, symbol, timeframe, start_iso, end_iso)
    if len(candles) < 80:
        state["last_update"] = _now_iso()
        save_state(state, path)
        return state

    funding_events = None
    if market_type == "futures" and cfg.get("use_binance_funding", True):
        funding_events = fetch_funding_rates(ex, symbol, start_iso, end_iso)

    common = {
        "initial_usdt": float(cfg.get("initial_usdt", 1000.0)),
        "position_mode": cfg.get("position_mode", "both"),
        "leverage": float(cfg.get("leverage", 1)),
        "funding_rate_per_8h": float(cfg.get("funding_rate_per_8h", 0.0)),
        "funding_events": funding_events,
    }

    if strategy == "ensemble_regime":
        result = run_ensemble_backtest(
            candles,
            **common,
            trend_weight=float(cfg.get("ens_trend_w", 0.4)),
            reversal_weight=float(cfg.get("ens_rev_w", 0.3)),
            base_weight=float(cfg.get("ens_base_w", 0.3)),
            trend_spread_threshold=float(cfg.get("ens_spread_th", 0.01)),
            reversal_rsi_low=float(cfg.get("ens_rsi_low", 30)),
            reversal_rsi_high=float(cfg.get("ens_rsi_high", 70)),
        )
    else:
        result = run_backtest(
            candles,
            strategy=strategy,
            **common,
            ema_fast_period=int(cfg.get("ema_fast_period", 20)),
            ema_slow_period=int(cfg.get("ema_slow_period", 50)),
            rsi_period=int(cfg.get("rsi_period", 14)),
            rsi_lower=float(cfg.get("rsi_lower", 30)),
            rsi_upper=float(cfg.get("rsi_upper", 65)),
            breakout_lookback=int(cfg.get("breakout_lookback", 20)),
            sl_pct=float(cfg.get("sl_pct", 1.0)) / 100.0,
            tp_rr=float(cfg.get("tp_rr", 1.5)),
        )

    _notify_new_trades(state, cfg, result)

    state["last_update"] = _now_iso()
    state["metrics"] = {
        "virtual_balance": float(result.get("final_usdt", common["initial_usdt"])),
        "return_pct": float(result.get("return_pct", 0.0)),
        "trades": int(result.get("total_trades", 0)),
        "liquidations": int(result.get("liquidation_count", 0)),
    }
    state["result"] = result
    save_state(state, path)
    return state
