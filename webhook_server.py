import os
import json
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv

from risk import RiskConfig, calc_position_size_usdt, calc_tp_price
from exchange import get_exchange, place_market_order, fetch_account_status, fetch_pnl_snapshot
from profiles import resolve_profile
from performance import log_trade, read_events, summarize
from risk_guard import GuardConfig, can_trade, apply_trade_result
from notifier import maybe_alert
from idempotency import has_signal, save_signal
from strategy_store import (
    get_strategy_params,
    get_strategy_version,
    list_strategy_versions,
    set_latest_from_version,
    get_portfolio_weights,
    save_portfolio_weights,
    set_strategy_tag,
    get_strategy_tag,
    set_strategy_lock,
    get_strategy_lock,
)
from market_intel import get_market_brief, fetch_items
from ml_dataset import append_events, load_events, enrich_with_price_labels
from predict_model import predict_event

load_dotenv()

app = FastAPI(title="Pine Webhook Trader")

with open("config.example.yaml", "r", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)

risk_cfg = RiskConfig(**CFG["risk"])
strategy_flags = CFG["strategies"]

trade_cfg = CFG.get("trade", {})
allowed_spot = set(trade_cfg.get("allowed_symbols_spot", trade_cfg.get("allowed_symbols", ["BTC/USDT", "ETH/USDT"])))
allowed_futures = set(trade_cfg.get("allowed_symbols_futures", ["BTC/USDT:USDT", "ETH/USDT:USDT"]))

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "")
WEBHOOK_MIN_EXPECTED_RETURN_PCT = float(os.getenv("WEBHOOK_MIN_EXPECTED_RETURN_PCT", "-999"))
WEBHOOK_MAX_ALLOWED_MDD_PCT = float(os.getenv("WEBHOOK_MAX_ALLOWED_MDD_PCT", "999"))
WEBHOOK_AUTO_SELECT_VERSION = os.getenv("WEBHOOK_AUTO_SELECT_VERSION", "false").lower() == "true"
WEBHOOK_LIVE_ALLOWED_TAGS = [t.strip() for t in os.getenv("WEBHOOK_LIVE_ALLOWED_TAGS", "stable").split(",") if t.strip()]
WEBHOOK_TEST_TAG_FORCE_DRY_RUN = os.getenv("WEBHOOK_TEST_TAG_FORCE_DRY_RUN", "true").lower() == "true"
TRADING_WINDOW_UTC = os.getenv("TRADING_WINDOW_UTC", "00:00-23:59")
VOL_PAUSE_ENABLED = os.getenv("VOL_PAUSE_ENABLED", "false").lower() == "true"
VOL_LOOKBACK_CANDLES = int(os.getenv("VOL_LOOKBACK_CANDLES", "12"))
VOL_SPIKE_THRESHOLD_PCT = float(os.getenv("VOL_SPIKE_THRESHOLD_PCT", "3.0"))
MARKET_INTEL_FILTER_ENABLED = os.getenv("MARKET_INTEL_FILTER_ENABLED", "true").lower() == "true"
MARKET_INTEL_MIN_SCORE = float(os.getenv("MARKET_INTEL_MIN_SCORE", "-1.5"))
MARKET_INTEL_BLOCK_BEARISH = os.getenv("MARKET_INTEL_BLOCK_BEARISH", "true").lower() == "true"
MARKET_INTEL_SIZE_UP_BULLISH = float(os.getenv("MARKET_INTEL_SIZE_UP_BULLISH", "1.15"))
MARKET_INTEL_SIZE_DOWN_BEARISH = float(os.getenv("MARKET_INTEL_SIZE_DOWN_BEARISH", "0.65"))
MARKET_INTEL_AUTO_REFRESH_SEC = int(os.getenv("MARKET_INTEL_AUTO_REFRESH_SEC", "300"))
ML_FILTER_ENABLED = os.getenv("ML_FILTER_ENABLED", "true").lower() == "true"
ML_MIN_UP_PROBA_4H = float(os.getenv("ML_MIN_UP_PROBA_4H", "0.52"))
ML_BLOCK_LOW_CONFIDENCE = os.getenv("ML_BLOCK_LOW_CONFIDENCE", "true").lower() == "true"
ML_WEIGHT_1H = float(os.getenv("ML_WEIGHT_1H", "0.2"))
ML_WEIGHT_4H = float(os.getenv("ML_WEIGHT_4H", "0.5"))
ML_WEIGHT_24H = float(os.getenv("ML_WEIGHT_24H", "0.3"))
ML_MIN_COMPOSITE_SCORE = float(os.getenv("ML_MIN_COMPOSITE_SCORE", "0.54"))
ML_MIN_SHORT_CONFIRM = float(os.getenv("ML_MIN_SHORT_CONFIRM", "0.50"))


def _market_kind(v: Optional[str]) -> str:
    mv = (v or "spot").lower().strip()
    if mv in ["future", "futures", "swap", "usdm", "perp"]:
        return "futures"
    return "spot"


def _guard_cfg(mt: str) -> GuardConfig:
    base_loss = float(os.getenv("DAILY_LOSS_LIMIT_USDT", "30"))
    base_streak = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))

    if mt == "futures":
        loss = float(os.getenv("DAILY_LOSS_LIMIT_USDT_FUTURES", str(base_loss)))
        streak = int(os.getenv("MAX_CONSECUTIVE_LOSSES_FUTURES", str(base_streak)))
    else:
        loss = float(os.getenv("DAILY_LOSS_LIMIT_USDT_SPOT", str(base_loss)))
        streak = int(os.getenv("MAX_CONSECUTIVE_LOSSES_SPOT", str(base_streak)))

    return GuardConfig(daily_loss_limit_usdt=loss, max_consecutive_losses=streak)


def _guard_state_path(mt: str) -> str:
    if mt == "futures":
        return os.getenv("RISK_STATE_PATH_FUTURES", "data/risk_state_futures.json")
    return os.getenv("RISK_STATE_PATH_SPOT", "data/risk_state_spot.json")


def _max_concurrent_positions(mt: str) -> int:
    if mt == "futures":
        return int(os.getenv("MAX_CONCURRENT_POSITIONS_FUTURES", str(trade_cfg.get("max_concurrent_positions_futures", 3))))
    return int(os.getenv("MAX_CONCURRENT_POSITIONS_SPOT", str(trade_cfg.get("max_concurrent_positions_spot", 5))))


def _symbol_limit_map(mt: str):
    cfg_key = "symbol_limits_futures" if mt == "futures" else "symbol_limits_spot"
    env_key = "SYMBOL_LIMITS_FUTURES_JSON" if mt == "futures" else "SYMBOL_LIMITS_SPOT_JSON"

    limits = trade_cfg.get(cfg_key, {}) or {}
    raw = os.getenv(env_key, "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                limits.update(parsed)
        except Exception:
            pass
    return limits


def _symbol_concurrent_limit(mt: str, symbol: str) -> Optional[int]:
    limits = _symbol_limit_map(mt)
    v = limits.get(symbol)
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        return None


class Signal(BaseModel):
    strategy: str
    symbol: str
    side: str
    price: float
    stop_loss: Optional[float] = None
    risk_profile: Optional[str] = "safe"
    signal_id: Optional[str] = None
    market_type: Optional[str] = "spot"
    timeframe: Optional[str] = None
    strategy_version: Optional[int] = None
    strategy_tag: Optional[str] = None

    @field_validator("side")
    @classmethod
    def validate_side(cls, v):
        lv = v.lower()
        if lv not in ["buy", "sell"]:
            raise ValueError("side must be buy or sell")
        return lv

    @field_validator("market_type")
    @classmethod
    def validate_market_type(cls, v):
        return _market_kind(v)


class TradeResult(BaseModel):
    strategy: str = "unknown"
    symbol: str
    realized_pnl: float
    note: Optional[str] = None
    market_type: Optional[str] = "spot"


class FuturesConfigRequest(BaseModel):
    symbol: str
    leverage: int = 3
    margin_mode: str = "isolated"  # isolated | cross

    @field_validator("margin_mode")
    @classmethod
    def validate_margin_mode(cls, v):
        lv = v.lower().strip()
        if lv not in ["isolated", "cross"]:
            raise ValueError("margin_mode must be isolated or cross")
        return lv


class FuturesPositionModeRequest(BaseModel):
    hedged: bool = False  # False=one-way, True=hedge mode


class StrategyVersionActivateRequest(BaseModel):
    symbol: str
    timeframe: str
    strategy: str
    version_index: int


class PortfolioWeightRequest(BaseModel):
    symbol: str
    timeframe: str
    ema: float
    rsi: float
    breakout: float


class StrategyTagRequest(BaseModel):
    symbol: str
    timeframe: str
    strategy: str
    tag: str
    version_index: int


class StrategyLockRequest(BaseModel):
    symbol: str
    timeframe: str
    strategy: str
    locked: bool = True
    reason: str = ""


class StrategyPromoteRequest(BaseModel):
    symbol: str
    timeframe: str
    strategy: str
    from_tag: str = "test"
    to_tag: str = "stable"


def _get_allowed_symbols(market_type: str):
    return allowed_futures if market_type == "futures" else allowed_spot


def _get_exchange(market_type: str, read_only: bool = False):
    mt = "swap" if market_type == "futures" else "spot"
    return get_exchange(read_only=read_only, market_type=mt)


def _active_exposure_count(market_type: str) -> int:
    ex = _get_exchange(market_type, read_only=False)
    status = fetch_account_status(ex)

    if market_type == "futures":
        if status.get("positions_error"):
            raise RuntimeError(status["positions_error"])
        return len(status.get("positions") or [])

    if status.get("open_orders_error"):
        raise RuntimeError(status["open_orders_error"])
    return len(status.get("open_orders") or [])


def _active_exposure_count_by_symbol(market_type: str, symbol: str) -> int:
    ex = _get_exchange(market_type, read_only=False)
    status = fetch_account_status(ex)

    if market_type == "futures":
        if status.get("positions_error"):
            raise RuntimeError(status["positions_error"])
        positions = status.get("positions") or []
        return len([p for p in positions if p.get("symbol") == symbol])

    if status.get("open_orders_error"):
        raise RuntimeError(status["open_orders_error"])
    orders = status.get("open_orders") or []
    return len([o for o in orders if o.get("symbol") == symbol])


def _pick_best_version(symbol: str, timeframe: str, strategy: str):
    versions = list_strategy_versions(symbol, timeframe, strategy)
    if not versions:
        return None, None

    candidates = []
    for idx, v in enumerate(versions):
        if not isinstance(v, dict):
            continue
        r = v.get("return_pct")
        mdd = v.get("max_drawdown_pct")
        if isinstance(r, (int, float)) and r < WEBHOOK_MIN_EXPECTED_RETURN_PCT:
            continue
        if isinstance(mdd, (int, float)) and mdd > WEBHOOK_MAX_ALLOWED_MDD_PCT:
            continue
        candidates.append((idx, v))

    if not candidates:
        return None, None

    candidates.sort(key=lambda x: x[1].get("return_pct", -999999), reverse=True)
    return candidates[0]


def _is_within_trading_window() -> bool:
    try:
        s, e = TRADING_WINDOW_UTC.split("-")
        sh, sm = [int(x) for x in s.split(":")]
        eh, em = [int(x) for x in e.split(":")]
    except Exception:
        return True

    now = datetime.now(timezone.utc)
    cur = now.hour * 60 + now.minute
    start = sh * 60 + sm
    end = eh * 60 + em

    if start <= end:
        return start <= cur <= end
    return cur >= start or cur <= end


def _volatility_spike(exchange, symbol: str, timeframe: str) -> Optional[float]:
    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=max(5, VOL_LOOKBACK_CANDLES))
        if not candles:
            return None
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]
        last_close = candles[-1][4]
        if not last_close:
            return None
        spike_pct = ((max(highs) - min(lows)) / last_close) * 100.0
        return spike_pct
    except Exception:
        return None


def _market_intel_worker():
    while True:
        try:
            get_market_brief(force_refresh=True)
            items = fetch_items(per_source=8)
            append_events(items)

            # BTC 1h 캔들 기준으로 이벤트 후 1h/4h/24h 반응 라벨링 시도
            try:
                ex = get_exchange(read_only=True, market_type="swap")
                candles = ex.fetch_ohlcv("BTC/USDT:USDT", timeframe="1h", limit=500)
                enrich_with_price_labels(load_events(), candles)
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(max(60, MARKET_INTEL_AUTO_REFRESH_SEC))


@app.on_event("startup")
def startup_background_tasks():
    if MARKET_INTEL_FILTER_ENABLED:
        th = threading.Thread(target=_market_intel_worker, daemon=True)
        th.start()


@app.get("/health")
def health():
    return {
        "ok": True,
        "dry_run": DRY_RUN,
        "strategies": strategy_flags,
        "allowed_symbols": {
            "spot": sorted(list(allowed_spot)),
            "futures": sorted(list(allowed_futures)),
        },
        "risk_guard": {
            "spot": _guard_cfg("spot").__dict__,
            "futures": _guard_cfg("futures").__dict__,
        },
        "max_concurrent_positions": {
            "spot": _max_concurrent_positions("spot"),
            "futures": _max_concurrent_positions("futures"),
        },
        "symbol_limits": {
            "spot": _symbol_limit_map("spot"),
            "futures": _symbol_limit_map("futures"),
        },
        "execution_policy": {
            "live_allowed_tags": WEBHOOK_LIVE_ALLOWED_TAGS,
            "test_tag_force_dry_run": WEBHOOK_TEST_TAG_FORCE_DRY_RUN,
            "auto_select_version": WEBHOOK_AUTO_SELECT_VERSION,
            "trading_window_utc": TRADING_WINDOW_UTC,
            "vol_pause_enabled": VOL_PAUSE_ENABLED,
            "vol_lookback_candles": VOL_LOOKBACK_CANDLES,
            "vol_spike_threshold_pct": VOL_SPIKE_THRESHOLD_PCT,
            "market_intel_filter_enabled": MARKET_INTEL_FILTER_ENABLED,
            "market_intel_min_score": MARKET_INTEL_MIN_SCORE,
            "market_intel_block_bearish": MARKET_INTEL_BLOCK_BEARISH,
            "market_intel_size_up_bullish": MARKET_INTEL_SIZE_UP_BULLISH,
            "market_intel_size_down_bearish": MARKET_INTEL_SIZE_DOWN_BEARISH,
            "market_intel_auto_refresh_sec": MARKET_INTEL_AUTO_REFRESH_SEC,
            "ml_filter_enabled": ML_FILTER_ENABLED,
            "ml_min_up_proba_4h": ML_MIN_UP_PROBA_4H,
            "ml_block_low_confidence": ML_BLOCK_LOW_CONFIDENCE,
            "ml_weight_1h": ML_WEIGHT_1H,
            "ml_weight_4h": ML_WEIGHT_4H,
            "ml_weight_24h": ML_WEIGHT_24H,
            "ml_min_composite_score": ML_MIN_COMPOSITE_SCORE,
            "ml_min_short_confirm": ML_MIN_SHORT_CONFIRM,
        },
    }


@app.get("/account/status")
def account_status(market_type: str = "spot", x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")

    mt = _market_kind(market_type)
    ex = _get_exchange(mt, read_only=False)
    status = fetch_account_status(ex)
    pnl = fetch_pnl_snapshot(ex)
    guard = can_trade(_guard_cfg(mt), path=_guard_state_path(mt))
    return {"ok": True, "market_type": mt, **status, **pnl, "risk_guard": guard["state"]}


@app.get("/strategy/params")
def strategy_params(symbol: str, timeframe: str, strategy: str, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")

    latest = get_strategy_params(symbol, timeframe, strategy)
    versions = list_strategy_versions(symbol, timeframe, strategy)
    return {
        "ok": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": strategy,
        "latest": latest,
        "version_count": len(versions),
        "versions": versions[-10:],
    }


@app.post("/strategy/activate-version")
def strategy_activate_version(req: StrategyVersionActivateRequest, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")

    ok = set_latest_from_version(req.symbol, req.timeframe, req.strategy, req.version_index)
    if not ok:
        raise HTTPException(400, "failed to activate version")
    latest = get_strategy_params(req.symbol, req.timeframe, req.strategy)
    return {"ok": True, "activated": req.version_index, "latest": latest}


@app.get("/strategy/versions/compare")
def strategy_versions_compare(symbol: str, timeframe: str, strategy: str, limit: int = 10, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")

    versions = list_strategy_versions(symbol, timeframe, strategy)
    rows = []
    for idx, v in enumerate(versions):
        if not isinstance(v, dict):
            continue
        rows.append({
            "version_index": idx,
            "saved_at": v.get("saved_at"),
            "return_pct": v.get("return_pct"),
            "win_rate": v.get("win_rate"),
            "profit_factor": v.get("profit_factor"),
            "max_drawdown_pct": v.get("max_drawdown_pct"),
        })

    rows = sorted(rows, key=lambda r: (r.get("return_pct") if isinstance(r.get("return_pct"), (int, float)) else -999999), reverse=True)
    return {"ok": True, "symbol": symbol, "timeframe": timeframe, "strategy": strategy, "rows": rows[:max(1, min(limit, 50))]}


@app.post("/strategy/tag")
def strategy_tag(req: StrategyTagRequest, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")

    ok = set_strategy_tag(req.symbol, req.timeframe, req.strategy, req.tag, req.version_index)
    if not ok:
        raise HTTPException(400, "failed to set strategy tag")
    return {"ok": True, "tag": req.tag, "version_index": req.version_index}


@app.get("/strategy/tag")
def strategy_tag_get(symbol: str, timeframe: str, strategy: str, tag: str, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")
    data = get_strategy_tag(symbol, timeframe, strategy, tag)
    return {"ok": True, "symbol": symbol, "timeframe": timeframe, "strategy": strategy, "tag": tag, "data": data}


@app.post("/strategy/promote")
def strategy_promote(req: StrategyPromoteRequest, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")

    src = get_strategy_tag(req.symbol, req.timeframe, req.strategy, req.from_tag)
    idx = src.get("version_index") if isinstance(src, dict) else None
    if not isinstance(idx, int):
        raise HTTPException(400, f"from_tag not found: {req.from_tag}")

    ok = set_strategy_tag(req.symbol, req.timeframe, req.strategy, req.to_tag, idx)
    if not ok:
        raise HTTPException(400, "failed to promote tag")

    return {"ok": True, "from_tag": req.from_tag, "to_tag": req.to_tag, "version_index": idx}


@app.post("/strategy/lock")
def strategy_lock(req: StrategyLockRequest, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")

    ok = set_strategy_lock(req.symbol, req.timeframe, req.strategy, req.locked, req.reason)
    if not ok:
        raise HTTPException(400, "failed to set strategy lock")
    return {"ok": True, "locked": req.locked}


@app.get("/strategy/lock")
def strategy_lock_get(symbol: str, timeframe: str, strategy: str, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")
    data = get_strategy_lock(symbol, timeframe, strategy)
    return {"ok": True, "symbol": symbol, "timeframe": timeframe, "strategy": strategy, "lock": data}


@app.get("/portfolio/weights")
def portfolio_weights(symbol: str, timeframe: str, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")
    data = get_portfolio_weights(symbol, timeframe)
    return {"ok": True, "symbol": symbol, "timeframe": timeframe, "weights": data}


@app.post("/portfolio/weights")
def portfolio_weights_save(req: PortfolioWeightRequest, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")

    total = req.ema + req.rsi + req.breakout
    if total <= 0:
        raise HTTPException(400, "sum of weights must be > 0")

    save_portfolio_weights(req.symbol, req.timeframe, {"ema": req.ema, "rsi": req.rsi, "breakout": req.breakout})
    return {"ok": True, "symbol": req.symbol, "timeframe": req.timeframe}


@app.post("/futures/configure")
def futures_configure(req: FuturesConfigRequest, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")

    if DRY_RUN:
        return {
            "ok": True,
            "dry_run": True,
            "configured": {
                "symbol": req.symbol,
                "leverage": req.leverage,
                "margin_mode": req.margin_mode,
            },
        }

    ex = _get_exchange("futures", read_only=False)
    results = {"symbol": req.symbol, "leverage": req.leverage, "margin_mode": req.margin_mode}

    try:
        if hasattr(ex, "set_margin_mode"):
            results["set_margin_mode"] = ex.set_margin_mode(req.margin_mode, req.symbol)
    except Exception as e:
        results["set_margin_mode_error"] = str(e)

    try:
        if hasattr(ex, "set_leverage"):
            results["set_leverage"] = ex.set_leverage(req.leverage, req.symbol)
    except Exception as e:
        results["set_leverage_error"] = str(e)

    return {"ok": True, **results}


@app.post("/futures/position-mode")
def futures_position_mode(req: FuturesPositionModeRequest, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")

    if DRY_RUN:
        return {"ok": True, "dry_run": True, "position_mode": "hedge" if req.hedged else "one-way"}

    ex = _get_exchange("futures", read_only=False)
    result = {"position_mode": "hedge" if req.hedged else "one-way"}

    try:
        if hasattr(ex, "set_position_mode"):
            result["set_position_mode"] = ex.set_position_mode(req.hedged)
        else:
            raise RuntimeError("exchange does not support set_position_mode")
    except Exception as e:
        result["set_position_mode_error"] = str(e)

    return {"ok": True, **result}


@app.post("/trade/result")
def trade_result(result: TradeResult, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")

    mt = _market_kind(result.market_type)
    state = apply_trade_result(result.realized_pnl, _guard_cfg(mt), path=_guard_state_path(mt))

    log_trade({
        "type": "trade_result",
        "strategy": result.strategy,
        "symbol": result.symbol,
        "market_type": mt,
        "realized_pnl": result.realized_pnl,
        "unrealized_pnl": 0.0,
        "note": result.note,
        "balance_usdt": risk_cfg.account_usdt + state.get("daily_realized_pnl", 0.0),
    })

    if state.get("halted"):
        maybe_alert(f"리스크 가드 발동({mt}) - 신규 진입 중지", state.get("reason"))

    return {"ok": True, "market_type": mt, "risk_guard": state}


@app.post("/report/daily")
def report_daily(x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")

    events = read_events()
    s = summarize(events)
    guard_spot = can_trade(_guard_cfg("spot"), path=_guard_state_path("spot"))["state"]
    guard_fut = can_trade(_guard_cfg("futures"), path=_guard_state_path("futures"))["state"]

    msg = (
        f"일일 리포트\n"
        f"- 누적 수익률: {s.get('return_pct', 0.0):.2f}%\n"
        f"- 실현손익: {s.get('realized_pnl', 0.0):.2f} USDT\n"
        f"- 미실현손익: {s.get('unrealized_pnl', 0.0):.2f} USDT\n"
        f"- 총 체결: {s.get('total_trades', 0)}\n"
        f"- Spot 가드: {'중지' if guard_spot.get('halted') else '정상'}\n"
        f"- Futures 가드: {'중지' if guard_fut.get('halted') else '정상'}"
    )
    maybe_alert("HoyaTradingSW", msg)
    return {"ok": True, "summary": s, "risk_guard": {"spot": guard_spot, "futures": guard_fut}, "message": msg}


@app.post("/webhook")
def webhook(signal: Signal, x_webhook_token: Optional[str] = Header(default=None)):
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(401, "invalid webhook token")

    mt = _market_kind(signal.market_type)

    guard = can_trade(_guard_cfg(mt), path=_guard_state_path(mt))
    if not guard["allowed"]:
        return {"ignored": True, "reason": f"risk guard halted({mt}): {guard['state'].get('reason')}"}

    if signal.signal_id and has_signal(signal.signal_id):
        return {"ignored": True, "reason": "duplicate signal_id"}

    allowed_symbols = _get_allowed_symbols(mt)
    if signal.symbol not in allowed_symbols:
        raise HTTPException(400, f"symbol not allowed for {mt}: {signal.symbol}")

    if mt == "spot" and signal.side == "sell":
        return {"ignored": True, "reason": "spot mode is long-only; short/sell entries are futures-only"}

    if not strategy_flags.get(signal.strategy, False):
        return {"ignored": True, "reason": f"strategy {signal.strategy} is OFF"}

    if not DRY_RUN:
        try:
            active_count = _active_exposure_count(mt)
            limit = _max_concurrent_positions(mt)
            if active_count >= limit:
                return {"ignored": True, "reason": f"max concurrent limit reached({mt}): {active_count}/{limit}"}

            symbol_limit = _symbol_concurrent_limit(mt, signal.symbol)
            if symbol_limit is not None:
                symbol_active = _active_exposure_count_by_symbol(mt, signal.symbol)
                if symbol_active >= symbol_limit:
                    return {"ignored": True, "reason": f"symbol concurrent limit reached({signal.symbol}): {symbol_active}/{symbol_limit}"}
        except Exception as e:
            maybe_alert("포지션 제한 체크 실패", f"{mt} {str(e)}")
            return {"ignored": True, "reason": f"cannot verify concurrent positions: {str(e)}"}

    profile_name, profile = resolve_profile(signal.risk_profile)

    tf = signal.timeframe or trade_cfg.get("timeframe", "5m")
    lock_state = get_strategy_lock(signal.symbol, tf, signal.strategy)
    if bool(lock_state.get("locked", False)):
        return {"ignored": True, "reason": f"strategy locked: {lock_state.get('reason', '')}"}

    if not _is_within_trading_window():
        return {"ignored": True, "reason": f"outside trading window UTC({TRADING_WINDOW_UTC})"}

    if VOL_PAUSE_ENABLED:
        ex_vol = _get_exchange(mt, read_only=True)
        spike = _volatility_spike(ex_vol, signal.symbol, tf)
        if isinstance(spike, (int, float)) and spike >= VOL_SPIKE_THRESHOLD_PCT:
            maybe_alert("변동성 급등으로 진입 중지", f"{signal.symbol} {tf} spike={spike:.2f}%")
            return {"ignored": True, "reason": f"volatility spike {spike:.2f}% >= {VOL_SPIKE_THRESHOLD_PCT:.2f}%"}

    intel = {"score": 0.0, "bias": "neutral", "top": []}
    if MARKET_INTEL_FILTER_ENABLED:
        intel = get_market_brief(force_refresh=False)
        intel_score = float(intel.get("score", 0.0))
        intel_bias = str(intel.get("bias", "neutral"))
        if intel_score < MARKET_INTEL_MIN_SCORE:
            return {"ignored": True, "reason": f"market intel score too low: {intel_score:.2f} < {MARKET_INTEL_MIN_SCORE:.2f}"}
        if MARKET_INTEL_BLOCK_BEARISH and intel_bias == "bearish" and signal.side == "buy":
            return {"ignored": True, "reason": "market intel bearish: buy entry paused"}

    ml_pred = {}
    ml_composite = 0.0
    latest_event = (intel.get("top") or [{}])[0] if intel.get("top") else {}
    if ML_FILTER_ENABLED and latest_event:
        ml_pred = predict_event(latest_event)
        p5 = ml_pred.get("label_up_5m", {})
        p15 = ml_pred.get("label_up_15m", {})
        p1 = ml_pred.get("label_up_1h", {})
        p4 = ml_pred.get("label_up_4h", {})
        p24 = ml_pred.get("label_up_24h", {})

        up5 = float((p5.get("proba") or [0.0, 0.0])[1] if p5.get("ok") and len(p5.get("proba") or []) > 1 else 0.0)
        up15 = float((p15.get("proba") or [0.0, 0.0])[1] if p15.get("ok") and len(p15.get("proba") or []) > 1 else 0.0)
        up1 = float((p1.get("proba") or [0.0, 0.0])[1] if p1.get("ok") and len(p1.get("proba") or []) > 1 else 0.0)
        up4 = float((p4.get("proba") or [0.0, 0.0])[1] if p4.get("ok") and len(p4.get("proba") or []) > 1 else 0.0)
        up24 = float((p24.get("proba") or [0.0, 0.0])[1] if p24.get("ok") and len(p24.get("proba") or []) > 1 else 0.0)

        total_w = max(0.0001, ML_WEIGHT_1H + ML_WEIGHT_4H + ML_WEIGHT_24H)
        ml_composite = ((up1 * ML_WEIGHT_1H) + (up4 * ML_WEIGHT_4H) + (up24 * ML_WEIGHT_24H)) / total_w
        ml_short_confirm = (up5 + up15) / 2.0

        if ML_BLOCK_LOW_CONFIDENCE and signal.side == "buy":
            if up4 < ML_MIN_UP_PROBA_4H:
                return {"ignored": True, "reason": f"ml up probability too low: {up4:.2f} < {ML_MIN_UP_PROBA_4H:.2f}"}
            if ml_composite < ML_MIN_COMPOSITE_SCORE:
                return {"ignored": True, "reason": f"ml composite score too low: {ml_composite:.2f} < {ML_MIN_COMPOSITE_SCORE:.2f}"}
            if ml_short_confirm < ML_MIN_SHORT_CONFIRM:
                return {"ignored": True, "reason": f"ml short confirm too low: {ml_short_confirm:.2f} < {ML_MIN_SHORT_CONFIRM:.2f}"}

    effective_cfg = RiskConfig(
        account_usdt=risk_cfg.account_usdt,
        risk_per_trade=profile["risk_per_trade"],
        max_position_usdt=risk_cfg.max_position_usdt * profile["max_position_multiplier"],
        min_order_usdt=risk_cfg.min_order_usdt,
        target_rr=profile["target_rr"],
        default_stop_loss_pct=profile["default_stop_loss_pct"],
    )

    applied_version = signal.strategy_version
    if signal.strategy_version is not None:
        saved_params = get_strategy_version(signal.symbol, tf, signal.strategy, signal.strategy_version)
    elif signal.strategy_tag:
        tag_data = get_strategy_tag(signal.symbol, tf, signal.strategy, signal.strategy_tag)
        idx = tag_data.get("version_index") if isinstance(tag_data, dict) else None
        if isinstance(idx, int):
            saved_params = get_strategy_version(signal.symbol, tf, signal.strategy, idx)
            applied_version = idx
        else:
            saved_params = get_strategy_params(signal.symbol, tf, signal.strategy)
    else:
        if WEBHOOK_AUTO_SELECT_VERSION:
            idx, best = _pick_best_version(signal.symbol, tf, signal.strategy)
            if best is not None:
                saved_params = best
                applied_version = idx
            else:
                saved_params = get_strategy_params(signal.symbol, tf, signal.strategy)
        else:
            saved_params = get_strategy_params(signal.symbol, tf, signal.strategy)

    sl_pct = float(saved_params.get("sl_pct", effective_cfg.default_stop_loss_pct))
    tp_rr = float(saved_params.get("tp_rr", effective_cfg.target_rr))

    expected_ret = saved_params.get("return_pct")
    expected_mdd = saved_params.get("max_drawdown_pct")
    if isinstance(expected_ret, (int, float)) and expected_ret < WEBHOOK_MIN_EXPECTED_RETURN_PCT:
        return {"ignored": True, "reason": f"expected return below threshold: {expected_ret:.2f}% < {WEBHOOK_MIN_EXPECTED_RETURN_PCT:.2f}%"}
    if isinstance(expected_mdd, (int, float)) and expected_mdd > WEBHOOK_MAX_ALLOWED_MDD_PCT:
        return {"ignored": True, "reason": f"expected MDD above threshold: {expected_mdd:.2f}% > {WEBHOOK_MAX_ALLOWED_MDD_PCT:.2f}%"}

    sl = signal.stop_loss or (
        signal.price * (1 - sl_pct)
        if signal.side == "buy"
        else signal.price * (1 + sl_pct)
    )

    position_usdt = calc_position_size_usdt(effective_cfg, signal.price, sl)
    if position_usdt <= 0:
        return {"ignored": True, "reason": "position too small or invalid risk"}

    # v2: 시장 인텔리전스 점수 기반 포지션 크기 가감
    intel_bias = str(intel.get("bias", "neutral"))
    if MARKET_INTEL_FILTER_ENABLED:
        if intel_bias == "bullish" and signal.side == "buy":
            position_usdt *= max(0.5, min(1.5, MARKET_INTEL_SIZE_UP_BULLISH))
        elif intel_bias == "bearish":
            position_usdt *= max(0.2, min(1.0, MARKET_INTEL_SIZE_DOWN_BEARISH))

    # ML 예측 확률 기반 추가 가감
    if ML_FILTER_ENABLED and ml_pred:
        if signal.side == "buy":
            if ml_composite >= 0.68:
                position_usdt *= 1.15
            elif ml_composite >= 0.60:
                position_usdt *= 1.05
            elif ml_composite < 0.54:
                position_usdt *= 0.70

    # 최종 상한/하한 재적용
    position_usdt = max(effective_cfg.min_order_usdt, min(position_usdt, effective_cfg.max_position_usdt))
    qty = position_usdt / signal.price
    tp = calc_tp_price(signal.price, sl, signal.side, tp_rr)
    risk_amount = abs(signal.price - sl) * qty

    # 태그 기반 실행 정책
    effective_dry_run = DRY_RUN
    if not DRY_RUN:
        if WEBHOOK_LIVE_ALLOWED_TAGS:
            if not signal.strategy_tag or signal.strategy_tag not in WEBHOOK_LIVE_ALLOWED_TAGS:
                return {"ignored": True, "reason": f"live order requires allowed strategy_tag in {WEBHOOK_LIVE_ALLOWED_TAGS}"}
        if WEBHOOK_TEST_TAG_FORCE_DRY_RUN and signal.strategy_tag in ["test", "paper"]:
            effective_dry_run = True

    ex = _get_exchange(mt, read_only=False)
    try:
        order = place_market_order(ex, signal.symbol, signal.side, qty, dry_run=effective_dry_run)
    except Exception as e:
        maybe_alert("주문 실패", f"{mt} {signal.symbol} {signal.side} / {str(e)}")
        raise HTTPException(500, f"order failed: {str(e)}")

    if signal.signal_id:
        save_signal(signal.signal_id)

    log_trade({
        "type": "order",
        "symbol": signal.symbol,
        "side": signal.side,
        "risk_profile": profile_name,
        "strategy": signal.strategy,
        "signal_id": signal.signal_id,
        "market_type": mt,
        "timeframe": tf,
        "strategy_version": applied_version,
        "entry_price": signal.price,
        "stop_loss": sl,
        "take_profit": tp,
        "applied_sl_pct": sl_pct,
        "applied_tp_rr": tp_rr,
        "qty": qty,
        "risk_amount_usdt": risk_amount,
        "order": order,
        "balance_usdt": effective_cfg.account_usdt,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
    })

    return {
        "accepted": True,
        "order": order,
        "market_type": mt,
        "risk_profile": profile_name,
        "execution": {
            "effective_dry_run": effective_dry_run,
            "live_allowed_tags": WEBHOOK_LIVE_ALLOWED_TAGS,
        },
        "applied_params": {
            "timeframe": tf,
            "strategy_version": applied_version,
            "strategy_tag": signal.strategy_tag,
            "sl_pct": sl_pct,
            "tp_rr": tp_rr,
            "market_intel_bias": intel.get("bias", "neutral"),
            "market_intel_score": intel.get("score", 0.0),
            "ml_pred": ml_pred,
            "ml_composite_score": ml_composite,
            "ml_short_confirm": ml_short_confirm if 'ml_short_confirm' in locals() else 0.0,
        },
        "risk": {
            "entry": signal.price,
            "stop_loss": sl,
            "take_profit": tp,
            "position_usdt": position_usdt,
            "qty": qty,
            "risk_amount_usdt": risk_amount,
        },
    }
