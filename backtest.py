from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


def _ms(dt_str: str) -> int:
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def fetch_ohlcv(exchange, symbol: str, timeframe: str, start_iso: str, end_iso: str, limit: int = 1000) -> List[List[float]]:
    since = _ms(start_iso)
    end_ms = _ms(end_iso)
    candles = []

    while since < end_ms:
        chunk = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
        if not chunk:
            break
        candles.extend(chunk)
        last_ts = chunk[-1][0]
        if last_ts <= since:
            break
        since = last_ts + 1
        if len(chunk) < limit:
            break

    return [c for c in candles if c[0] <= end_ms]


def fetch_funding_rates(exchange, symbol: str, start_iso: str, end_iso: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Binance/ccxt funding history (무료 공개 데이터) 조회."""
    if not hasattr(exchange, "fetch_funding_rate_history"):
        return []

    start_ms = _ms(start_iso)
    end_ms = _ms(end_iso)
    since = start_ms
    out: List[Dict[str, Any]] = []

    while since < end_ms:
        try:
            chunk = exchange.fetch_funding_rate_history(symbol, since=since, limit=limit)
        except Exception:
            break

        if not chunk:
            break

        for r in chunk:
            ts = r.get("timestamp")
            fr = r.get("fundingRate")
            if isinstance(ts, int) and isinstance(fr, (int, float)) and ts <= end_ms:
                out.append({"timestamp": ts, "fundingRate": float(fr)})

        last_ts = chunk[-1].get("timestamp") if isinstance(chunk[-1], dict) else None
        if not isinstance(last_ts, int) or last_ts <= since:
            break
        since = last_ts + 1
        if len(chunk) < limit:
            break

    return out

def _ema(values, period):
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _rsi(values, period=14):
    if len(values) < period + 1:
        return [50.0 for _ in values]

    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(0.0, d))
        losses.append(max(0.0, -d))

    avg_gain = sum(gains[1:period + 1]) / period
    avg_loss = sum(losses[1:period + 1]) / period

    rsi = [50.0 for _ in values]
    for i in range(period, len(values)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 999999
        rsi[i] = 100 - (100 / (1 + rs))
    return rsi


def _bollinger(values: List[float], period: int = 20, mult: float = 2.0):
    mid = []
    upper = []
    lower = []
    for i in range(len(values)):
        if i < period - 1:
            mid.append(values[i])
            upper.append(values[i])
            lower.append(values[i])
            continue
        w = values[i - period + 1:i + 1]
        m = sum(w) / period
        var = sum((x - m) ** 2 for x in w) / period
        sd = var ** 0.5
        mid.append(m)
        upper.append(m + mult * sd)
        lower.append(m - mult * sd)
    return mid, upper, lower


def _entry_signal(strategy: str, i: int, opens: List[float], closes: List[float], highs: List[float], lows: List[float], ema_fast: List[float], ema_slow: List[float], rsi14: List[float], rsi_lower: float, breakout_lookback: int) -> bool:
    if strategy == "ema_cross":
        return ema_fast[i - 1] <= ema_slow[i - 1] and ema_fast[i] > ema_slow[i]

    if strategy == "rsi_reversion":
        return rsi14[i - 1] < rsi_lower and rsi14[i] >= rsi_lower

    if strategy == "breakout_20":
        if i < breakout_lookback + 1:
            return False
        prev_high_n = max(highs[i - breakout_lookback:i])
        return closes[i] > prev_high_n

    # TradingLab 계열 컨셉 추가
    if strategy in ["fvg_imbalance", "tlab_fvg_secret"]:
        if i < 3:
            return False
        # bullish FVG proxy: 현재 저가가 2봉 전 고가 위에 형성
        return lows[i] > highs[i - 2] and closes[i] > ema_fast[i]

    if strategy in ["orderflow_breaker", "tlab_strategy_ever_need"]:
        if i < 12:
            return False
        prev_high = max(highs[i - 10:i])
        return closes[i] > prev_high and rsi14[i] > 50

    if strategy in ["candlestick_engulf", "tlab_candlestick_filter"]:
        if i < 2:
            return False
        prev_bear = closes[i - 1] < opens[i - 1]
        bullish_engulf = closes[i] > opens[i] and closes[i] >= opens[i - 1] and opens[i] <= closes[i - 1]
        return prev_bear and bullish_engulf

    if strategy in ["supply_demand_flip", "tlab_daytrading_beginner"]:
        if i < 20:
            return False
        zone_low = min(lows[i - 20:i - 5])
        zone_high = max(highs[i - 20:i - 5])
        # 이전 공급/수요 구간 상단 돌파 후 재진입
        return closes[i] > zone_high and ema_fast[i] > ema_slow[i]


    if strategy == "dual_momentum_trend":
        if i < 30:
            return False
        mom = (closes[i] - closes[i-20]) / max(closes[i-20],1e-9)
        return mom > 0.02 and ema_fast[i] > ema_slow[i]

    if strategy == "volatility_breakout_atr":
        if i < 20:
            return False
        rng = sum((highs[j]-lows[j]) for j in range(i-14,i+1)) / 15.0
        prev_high = max(highs[i-20:i])
        return closes[i] > prev_high and (highs[i]-lows[i]) > rng*1.2

    if strategy == "donchian_vol_filter":
        if i < breakout_lookback + 1:
            return False
        up = max(highs[i-breakout_lookback:i])
        avg_range = sum((highs[j]-lows[j]) for j in range(max(1,i-20), i+1))/max(1,len(range(max(1,i-20), i+1)))
        return closes[i] > up and (highs[i]-lows[i]) > avg_range

    if strategy == "mean_reversion_zscore":
        if i < 30:
            return False
        w = closes[i-20:i+1]
        m = sum(w)/len(w)
        var = sum((x-m)**2 for x in w)/len(w)
        sd = var**0.5 if var>0 else 1e-9
        z = (closes[i]-m)/sd
        return z < -1.5 and rsi14[i] < 35

    if strategy == "rsi_failure_structure":
        if i < 10:
            return False
        prev_low = min(lows[i-5:i])
        return rsi14[i] > rsi14[i-1] and closes[i] > prev_low and ema_fast[i] > ema_slow[i]

    if strategy == "vwap_anchored_intraday":
        if i < 10:
            return False
        v = 0.0
        pv = 0.0
        for j in range(max(0,i-20), i+1):
            vol = max(0.0, (highs[j]-lows[j])) + 1e-6
            tp = (highs[j]+lows[j]+closes[j])/3.0
            pv += tp*vol
            v += vol
        vwap = pv/max(v,1e-9)
        return closes[i] > vwap and ema_fast[i] > ema_slow[i]

    if strategy == "funding_oi_reversal_pro":
        # OI 대체 프록시: 급락 후 긴 꼬리 + RSI 과매도
        body = abs(closes[i]-opens[i])
        lower_wick = min(opens[i],closes[i]) - lows[i]
        return rsi14[i] < 30 and lower_wick > body*1.5

    if strategy == "adaptive_vol_target":
        if i < 25:
            return False
        return ema_fast[i] > ema_slow[i] and rsi14[i] > 50

    return False


def _exit_signal(strategy: str, i: int, opens: List[float], closes: List[float], highs: List[float], lows: List[float], ema_fast: List[float], ema_slow: List[float], rsi14: List[float], rsi_upper: float) -> bool:
    if strategy == "ema_cross":
        return ema_fast[i - 1] >= ema_slow[i - 1] and ema_fast[i] < ema_slow[i]

    if strategy == "rsi_reversion":
        return rsi14[i] >= rsi_upper

    if strategy == "breakout_20":
        return ema_fast[i] < ema_slow[i]

    if strategy in ["fvg_imbalance", "tlab_fvg_secret"]:
        return closes[i] < ema_fast[i]

    if strategy in ["orderflow_breaker", "tlab_strategy_ever_need"]:
        return closes[i] < ema_slow[i]

    if strategy in ["candlestick_engulf", "tlab_candlestick_filter"]:
        return rsi14[i] >= 70 or closes[i] < ema_fast[i]

    if strategy in ["supply_demand_flip", "tlab_daytrading_beginner"]:
        return ema_fast[i] < ema_slow[i]


    if strategy == "dual_momentum_trend":
        return ema_fast[i] < ema_slow[i]

    if strategy == "volatility_breakout_atr":
        return ema_fast[i] < ema_slow[i]

    if strategy == "donchian_vol_filter":
        return ema_fast[i] < ema_slow[i]

    if strategy == "mean_reversion_zscore":
        return rsi14[i] >= 55

    if strategy == "rsi_failure_structure":
        return ema_fast[i] < ema_slow[i]

    if strategy == "vwap_anchored_intraday":
        return closes[i] < ema_fast[i]

    if strategy == "funding_oi_reversal_pro":
        return rsi14[i] >= 55

    if strategy == "adaptive_vol_target":
        return ema_fast[i] < ema_slow[i]

    return False


def _entry_signal_short(strategy: str, i: int, opens: List[float], closes: List[float], highs: List[float], lows: List[float], ema_fast: List[float], ema_slow: List[float], rsi14: List[float], rsi_upper: float, breakout_lookback: int) -> bool:
    if strategy == "ema_cross":
        return ema_fast[i - 1] >= ema_slow[i - 1] and ema_fast[i] < ema_slow[i]

    if strategy == "rsi_reversion":
        return rsi14[i - 1] > rsi_upper and rsi14[i] <= rsi_upper

    if strategy == "breakout_20":
        if i < breakout_lookback + 1:
            return False
        prev_low_n = min(lows[i - breakout_lookback:i])
        return closes[i] < prev_low_n

    if strategy in ["fvg_imbalance", "tlab_fvg_secret"]:
        if i < 3:
            return False
        return highs[i] < lows[i - 2] and closes[i] < ema_fast[i]

    if strategy in ["orderflow_breaker", "tlab_strategy_ever_need"]:
        if i < 12:
            return False
        prev_low = min(lows[i - 10:i])
        return closes[i] < prev_low and rsi14[i] < 50

    if strategy in ["candlestick_engulf", "tlab_candlestick_filter"]:
        if i < 2:
            return False
        prev_bull = closes[i - 1] > opens[i - 1]
        bearish_engulf = closes[i] < opens[i] and closes[i] <= opens[i - 1] and opens[i] >= closes[i - 1]
        return prev_bull and bearish_engulf

    if strategy in ["supply_demand_flip", "tlab_daytrading_beginner"]:
        if i < 20:
            return False
        zone_low = min(lows[i - 20:i - 5])
        return closes[i] < zone_low and ema_fast[i] < ema_slow[i]


    if strategy == "dual_momentum_trend":
        if i < 30:
            return False
        mom = (closes[i] - closes[i-20]) / max(closes[i-20],1e-9)
        return mom > 0.02 and ema_fast[i] > ema_slow[i]

    if strategy == "volatility_breakout_atr":
        if i < 20:
            return False
        rng = sum((highs[j]-lows[j]) for j in range(i-14,i+1)) / 15.0
        prev_high = max(highs[i-20:i])
        return closes[i] > prev_high and (highs[i]-lows[i]) > rng*1.2

    if strategy == "donchian_vol_filter":
        if i < breakout_lookback + 1:
            return False
        up = max(highs[i-breakout_lookback:i])
        avg_range = sum((highs[j]-lows[j]) for j in range(max(1,i-20), i+1))/max(1,len(range(max(1,i-20), i+1)))
        return closes[i] > up and (highs[i]-lows[i]) > avg_range

    if strategy == "mean_reversion_zscore":
        if i < 30:
            return False
        w = closes[i-20:i+1]
        m = sum(w)/len(w)
        var = sum((x-m)**2 for x in w)/len(w)
        sd = var**0.5 if var>0 else 1e-9
        z = (closes[i]-m)/sd
        return z < -1.5 and rsi14[i] < 35

    if strategy == "rsi_failure_structure":
        if i < 10:
            return False
        prev_low = min(lows[i-5:i])
        return rsi14[i] > rsi14[i-1] and closes[i] > prev_low and ema_fast[i] > ema_slow[i]

    if strategy == "vwap_anchored_intraday":
        if i < 10:
            return False
        v = 0.0
        pv = 0.0
        for j in range(max(0,i-20), i+1):
            vol = max(0.0, (highs[j]-lows[j])) + 1e-6
            tp = (highs[j]+lows[j]+closes[j])/3.0
            pv += tp*vol
            v += vol
        vwap = pv/max(v,1e-9)
        return closes[i] > vwap and ema_fast[i] > ema_slow[i]

    if strategy == "funding_oi_reversal_pro":
        # OI 대체 프록시: 급락 후 긴 꼬리 + RSI 과매도
        body = abs(closes[i]-opens[i])
        lower_wick = min(opens[i],closes[i]) - lows[i]
        return rsi14[i] < 30 and lower_wick > body*1.5

    if strategy == "adaptive_vol_target":
        if i < 25:
            return False
        return ema_fast[i] > ema_slow[i] and rsi14[i] > 50


    if strategy == "dual_momentum_trend":
        if i < 30:
            return False
        mom = (closes[i-20] - closes[i]) / max(closes[i-20],1e-9)
        return mom > 0.02 and ema_fast[i] < ema_slow[i]

    if strategy == "volatility_breakout_atr":
        if i < 20:
            return False
        rng = sum((highs[j]-lows[j]) for j in range(i-14,i+1)) / 15.0
        prev_low = min(lows[i-20:i])
        return closes[i] < prev_low and (highs[i]-lows[i]) > rng*1.2

    if strategy == "donchian_vol_filter":
        if i < breakout_lookback + 1:
            return False
        dn = min(lows[i-breakout_lookback:i])
        avg_range = sum((highs[j]-lows[j]) for j in range(max(1,i-20), i+1))/max(1,len(range(max(1,i-20), i+1)))
        return closes[i] < dn and (highs[i]-lows[i]) > avg_range

    if strategy == "mean_reversion_zscore":
        if i < 30:
            return False
        w = closes[i-20:i+1]
        m = sum(w)/len(w)
        var = sum((x-m)**2 for x in w)/len(w)
        sd = var**0.5 if var>0 else 1e-9
        z = (closes[i]-m)/sd
        return z > 1.5 and rsi14[i] > 65

    if strategy == "rsi_failure_structure":
        if i < 10:
            return False
        prev_high = max(highs[i-5:i])
        return rsi14[i] < rsi14[i-1] and closes[i] < prev_high and ema_fast[i] < ema_slow[i]

    if strategy == "vwap_anchored_intraday":
        if i < 10:
            return False
        v = 0.0
        pv = 0.0
        for j in range(max(0,i-20), i+1):
            vol = max(0.0, (highs[j]-lows[j])) + 1e-6
            tp = (highs[j]+lows[j]+closes[j])/3.0
            pv += tp*vol
            v += vol
        vwap = pv/max(v,1e-9)
        return closes[i] < vwap and ema_fast[i] < ema_slow[i]

    if strategy == "funding_oi_reversal_pro":
        body = abs(closes[i]-opens[i])
        upper_wick = highs[i] - max(opens[i],closes[i])
        return rsi14[i] > 70 and upper_wick > body*1.5

    if strategy == "adaptive_vol_target":
        if i < 25:
            return False
        return ema_fast[i] < ema_slow[i] and rsi14[i] < 50

    return False


def _exit_signal_short(strategy: str, i: int, opens: List[float], closes: List[float], highs: List[float], lows: List[float], ema_fast: List[float], ema_slow: List[float], rsi14: List[float], rsi_lower: float) -> bool:
    if strategy == "ema_cross":
        return ema_fast[i - 1] <= ema_slow[i - 1] and ema_fast[i] > ema_slow[i]

    if strategy == "rsi_reversion":
        return rsi14[i] <= rsi_lower

    if strategy == "breakout_20":
        return ema_fast[i] > ema_slow[i]

    if strategy in ["fvg_imbalance", "tlab_fvg_secret"]:
        return closes[i] > ema_fast[i]

    if strategy in ["orderflow_breaker", "tlab_strategy_ever_need"]:
        return closes[i] > ema_slow[i]

    if strategy in ["candlestick_engulf", "tlab_candlestick_filter"]:
        return rsi14[i] <= 30 or closes[i] > ema_fast[i]

    if strategy in ["supply_demand_flip", "tlab_daytrading_beginner"]:
        return ema_fast[i] > ema_slow[i]


    if strategy == "dual_momentum_trend":
        return ema_fast[i] > ema_slow[i]

    if strategy == "volatility_breakout_atr":
        return ema_fast[i] > ema_slow[i]

    if strategy == "donchian_vol_filter":
        return ema_fast[i] > ema_slow[i]

    if strategy == "mean_reversion_zscore":
        return rsi14[i] <= 45

    if strategy == "rsi_failure_structure":
        return ema_fast[i] > ema_slow[i]

    if strategy == "vwap_anchored_intraday":
        return closes[i] > ema_fast[i]

    if strategy == "funding_oi_reversal_pro":
        return rsi14[i] <= 45

    if strategy == "adaptive_vol_target":
        return ema_fast[i] > ema_slow[i]

    return False


def run_backtest(
    candles: List[List[float]],
    strategy: str = "ema_cross",
    initial_usdt: float = 1000.0,
    fee_pct: float = 0.0005,
    sl_pct: float = 0.01,
    tp_rr: float = 1.5,
    ema_fast_period: int = 20,
    ema_slow_period: int = 50,
    rsi_period: int = 14,
    rsi_lower: float = 30.0,
    rsi_upper: float = 65.0,
    breakout_lookback: int = 20,
    funding_rate_per_8h: float = 0.0,
    funding_events: Optional[List[Dict[str, Any]]] = None,
    position_mode: str = "long",
    leverage: float = 1.0,
    maintenance_margin_rate: float = 0.005,
) -> Dict[str, Any]:
    if len(candles) < 80:
        return {"error": "not enough candles", "trades": [], "equity_curve": []}

    opens = [c[1] for c in candles]
    closes = [c[4] for c in candles]
    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]
    volumes = [c[5] for c in candles]

    ema_fast = _ema(closes, ema_fast_period)
    ema_slow = _ema(closes, ema_slow_period)
    rsi14 = _rsi(closes, rsi_period)
    bb_mid, bb_upper, bb_lower = _bollinger(closes, period=20, mult=2.0)

    usdt = initial_usdt
    position = None
    trades = []
    equity = []

    allow_long = position_mode in ["long", "both"]
    allow_short = position_mode in ["short", "both"]
    lev = max(1.0, float(leverage))
    mmr = max(0.0, min(0.2, float(maintenance_margin_rate)))


    def _vol_scale(idx:int)->float:
        if idx < 20:
            return 1.0
        ranges=[(highs[j]-lows[j])/max(closes[j],1e-9) for j in range(idx-20, idx)]
        v=sum(ranges)/max(len(ranges),1)
        target=0.01
        scale=target/max(v,1e-6)
        return max(0.3,min(1.5,scale))

    for i in range(1, len(candles)):
        ts, _, high, low, close, _ = candles[i]

        if position is None:
            entered = False

            # 전략 1: 추세 지속 (Trend Continuation)
            if strategy == "trend_continuation_system":
                if allow_long:
                    cond_trend = ema_fast[i] > ema_slow[i]
                    cond_pullback = abs(close - ema_fast[i]) / max(ema_fast[i], 1e-9) <= 0.01
                    cond_rsi = 40 <= rsi14[i] <= 55
                    avg_vol = sum(volumes[max(0, i-20):i+1]) / max(1, len(volumes[max(0, i-20):i+1]))
                    cond_vol = volumes[i] >= avg_vol * 1.2
                    if cond_trend and cond_pullback and cond_rsi and cond_vol:
                        entry = close
                        sl = entry * (1 - sl_pct)
                        tp = entry * (1 + sl_pct * max(tp_rr, 3.0))
                        qty = (usdt * 0.95 * lev * (_vol_scale(i) if strategy == "adaptive_vol_target" else 1.0)) / entry
                        position = {"side": "long", "entry": entry, "sl": sl, "tp": tp, "qty": qty, "entry_ts": ts, "entry_i": i, "liq_price": entry * (1 - max(0.0005, (1.0/lev - mmr)))}
                        entered = True

                if (not entered) and allow_short:
                    cond_trend = ema_fast[i] < ema_slow[i]
                    cond_pullback = abs(close - ema_fast[i]) / max(ema_fast[i], 1e-9) <= 0.01
                    cond_rsi = 45 <= rsi14[i] <= 60
                    avg_vol = sum(volumes[max(0, i-20):i+1]) / max(1, len(volumes[max(0, i-20):i+1]))
                    cond_vol = volumes[i] >= avg_vol * 1.2
                    if cond_trend and cond_pullback and cond_rsi and cond_vol:
                        entry = close
                        sl = entry * (1 + sl_pct)
                        tp = entry * (1 - sl_pct * max(tp_rr, 3.0))
                        qty = (usdt * 0.95 * lev * (_vol_scale(i) if strategy == "adaptive_vol_target" else 1.0)) / entry
                        position = {"side": "short", "entry": entry, "sl": sl, "tp": tp, "qty": qty, "entry_ts": ts, "entry_i": i, "liq_price": entry * (1 + max(0.0005, (1.0/lev - mmr)))}
                        entered = True

            # 전략 2: 청산 사냥 역추세 (Liquidation Reversal)
            elif strategy == "liquidation_reversal_setup":
                body = abs(close - opens[i])
                lower_wick = min(opens[i], close) - lows[i]
                upper_wick = highs[i] - max(opens[i], close)
                avg_vol = sum(volumes[max(0, i-20):i+1]) / max(1, len(volumes[max(0, i-20):i+1]))
                vol_spike = volumes[i] >= avg_vol * 1.3

                if allow_long:
                    cond = close > opens[i] and close > bb_lower[i] and lows[i] < bb_lower[i] and lower_wick > body * 1.5 and rsi14[i] < 45 and vol_spike
                    if cond:
                        entry = close
                        sl = entry * (1 - min(sl_pct, 0.015))
                        tp = entry * (1 + max(0.02, sl_pct * tp_rr))
                        qty = (usdt * 0.95 * lev * (_vol_scale(i) if strategy == "adaptive_vol_target" else 1.0)) / entry
                        position = {"side": "long", "entry": entry, "sl": sl, "tp": tp, "qty": qty, "entry_ts": ts, "entry_i": i, "liq_price": entry * (1 - max(0.0005, (1.0/lev - mmr)))}
                        entered = True

                if (not entered) and allow_short:
                    cond = close < opens[i] and close < bb_upper[i] and highs[i] > bb_upper[i] and upper_wick > body * 1.5 and rsi14[i] > 55 and vol_spike
                    if cond:
                        entry = close
                        sl = entry * (1 + min(sl_pct, 0.015))
                        tp = entry * (1 - max(0.02, sl_pct * tp_rr))
                        qty = (usdt * 0.95 * lev * (_vol_scale(i) if strategy == "adaptive_vol_target" else 1.0)) / entry
                        position = {"side": "short", "entry": entry, "sl": sl, "tp": tp, "qty": qty, "entry_ts": ts, "entry_i": i, "liq_price": entry * (1 + max(0.0005, (1.0/lev - mmr)))}
                        entered = True

            else:
                if allow_long and _entry_signal(strategy, i, opens, closes, highs, lows, ema_fast, ema_slow, rsi14, rsi_lower, breakout_lookback):
                    entry = close
                    sl = entry * (1 - sl_pct)
                    tp = entry * (1 + sl_pct * tp_rr)
                    qty = (usdt * 0.95 * lev * (_vol_scale(i) if strategy == "adaptive_vol_target" else 1.0)) / entry
                    position = {
                        "side": "long",
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "qty": qty,
                        "entry_ts": ts,
                        "entry_i": i,
                        "liq_price": entry * (1 - max(0.0005, (1.0/lev - mmr))),
                    }
                    entered = True

                if (not entered) and allow_short and _entry_signal_short(strategy, i, opens, closes, highs, lows, ema_fast, ema_slow, rsi14, rsi_upper, breakout_lookback):
                    entry = close
                    sl = entry * (1 + sl_pct)
                    tp = entry * (1 - sl_pct * tp_rr)
                    qty = (usdt * 0.95 * lev * (_vol_scale(i) if strategy == "adaptive_vol_target" else 1.0)) / entry
                    position = {
                        "side": "short",
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "qty": qty,
                        "entry_ts": ts,
                        "entry_i": i,
                        "liq_price": entry * (1 + max(0.0005, (1.0/lev - mmr))),
                    }
        else:
            exit_price = None
            reason = None

            if position["side"] == "long":
                if low <= position.get("liq_price", -1):
                    exit_price = position.get("liq_price")
                    reason = "liquidation"
                elif low <= position["sl"]:
                    exit_price = position["sl"]
                    reason = "sl"
                elif high >= position["tp"]:
                    exit_price = position["tp"]
                    reason = "tp"
                elif _exit_signal(strategy, i, opens, closes, highs, lows, ema_fast, ema_slow, rsi14, rsi_upper):
                    exit_price = close
                    reason = "signal"
            else:
                if high >= position.get("liq_price", 10**18):
                    exit_price = position.get("liq_price")
                    reason = "liquidation"
                elif high >= position["sl"]:
                    exit_price = position["sl"]
                    reason = "sl"
                elif low <= position["tp"]:
                    exit_price = position["tp"]
                    reason = "tp"
                elif _exit_signal_short(strategy, i, opens, closes, highs, lows, ema_fast, ema_slow, rsi14, rsi_lower):
                    exit_price = close
                    reason = "signal"

            if exit_price is not None:
                if position["side"] == "long":
                    gross = (exit_price - position["entry"]) * position["qty"]
                else:
                    gross = (position["entry"] - exit_price) * position["qty"]
                entry_fee = (position["entry"] * position["qty"]) * fee_pct
                exit_fee = (exit_price * position["qty"]) * fee_pct
                fees = entry_fee + exit_fee

                hold_hours = max(0.0, (ts - position["entry_ts"]) / 1000.0 / 3600.0)
                funding_periods = hold_hours / 8.0
                notional = position["entry"] * position["qty"]

                if funding_events:
                    rate_sum = 0.0
                    for ev in funding_events:
                        ev_ts = ev.get("timestamp")
                        ev_rate = ev.get("fundingRate")
                        if isinstance(ev_ts, int) and isinstance(ev_rate, (int, float)) and position["entry_ts"] < ev_ts <= ts:
                            rate_sum += float(ev_rate)
                    funding_fee = notional * rate_sum
                else:
                    funding_fee = notional * funding_rate_per_8h * funding_periods

                balance_before = usdt
                pnl = gross - fees - funding_fee
                usdt += pnl
                pnl_pct = ((pnl / balance_before) * 100.0) if balance_before else 0.0
                trades.append({
                    "strategy": strategy,
                    "side": position.get("side", "long"),
                    "entry_ts": position["entry_ts"],
                    "exit_ts": ts,
                    "entry": position["entry"],
                    "exit": exit_price,
                    "gross_pnl": gross,
                    "entry_fee": entry_fee,
                    "exit_fee": exit_fee,
                    "fees": fees,
                    "funding_hours": hold_hours,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "balance_before": balance_before,
                    "balance": usdt,
                    "funding_fee": funding_fee,
                    "liq_price": position.get("liq_price"),
                    "reason": reason,
                    "entry_i": position["entry_i"],
                    "exit_i": i,
                })
                position = None

        equity.append({"ts": ts, "equity": usdt})

    wins = len([t for t in trades if t["pnl"] > 0])
    total = len(trades)
    ret_pct = ((usdt - initial_usdt) / initial_usdt) * 100.0

    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

    peak = initial_usdt
    max_dd = 0.0
    for e in equity:
        val = e["equity"]
        if val > peak:
            peak = val
        dd = ((peak - val) / peak) * 100.0 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    liquidation_count = len([t for t in trades if t.get("reason") == "liquidation"])

    return {
        "strategy": strategy,
        "initial_usdt": initial_usdt,
        "final_usdt": usdt,
        "return_pct": ret_pct,
        "trades": trades,
        "total_trades": total,
        "win_rate": (wins / total * 100.0) if total else 0.0,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_dd,
        "liquidation_count": liquidation_count,
        "equity_curve": equity,
    }


def run_ensemble_backtest(
    candles: List[List[float]],
    initial_usdt: float = 1000.0,
    position_mode: str = "both",
    leverage: float = 1.0,
    funding_rate_per_8h: float = 0.0,
    funding_events: Optional[List[Dict[str, Any]]] = None,
    trend_weight: float = 0.4,
    reversal_weight: float = 0.3,
    base_weight: float = 0.3,
    trend_spread_threshold: float = 0.01,
    reversal_rsi_low: float = 30.0,
    reversal_rsi_high: float = 70.0,
) -> Dict[str, Any]:
    """레짐 기반 혼합: 추세장=trend_continuation, 과열=liquidation_reversal, 그 외=ema_cross"""
    closes = [c[4] for c in candles]
    ema20 = _ema(closes, 20)
    ema60 = _ema(closes, 60)
    rsi14 = _rsi(closes, 14)

    trend_candles = []
    rev_candles = []
    base_candles = []

    for i, c in enumerate(candles):
        if i < 60:
            base_candles.append(c)
            continue
        spread = abs(ema20[i] - ema60[i]) / max(ema60[i], 1e-9)
        if spread >= trend_spread_threshold:
            trend_candles.append(c)
        elif rsi14[i] <= reversal_rsi_low or rsi14[i] >= reversal_rsi_high:
            rev_candles.append(c)
        else:
            base_candles.append(c)

    raw_weights = {
        "trend_continuation_system": max(0.0, trend_weight),
        "liquidation_reversal_setup": max(0.0, reversal_weight),
        "ema_cross": max(0.0, base_weight),
    }
    wsum = sum(raw_weights.values())
    if wsum <= 0:
        raw_weights = {"trend_continuation_system": 0.4, "liquidation_reversal_setup": 0.3, "ema_cross": 0.3}
        wsum = 1.0

    norm_weights = {k: v / wsum for k, v in raw_weights.items()}

    parts = []
    datasets = {
        "trend_continuation_system": trend_candles,
        "liquidation_reversal_setup": rev_candles,
        "ema_cross": base_candles,
    }

    for name, sub in datasets.items():
        if len(sub) < 80:
            continue
        r = run_backtest(
            sub,
            strategy=name,
            initial_usdt=initial_usdt,
            position_mode=position_mode,
            leverage=leverage,
            funding_rate_per_8h=funding_rate_per_8h,
            funding_events=funding_events,
        )
        parts.append((norm_weights.get(name, 0.0), r))

    if not parts:
        return {"error": "not enough candles for ensemble"}

    final_usdt = sum(w * p.get("final_usdt", initial_usdt) for w, p in parts)
    ret_pct = ((final_usdt - initial_usdt) / initial_usdt) * 100.0
    total_trades = sum(int(p.get("total_trades", 0)) for _, p in parts)
    liq = sum(int(p.get("liquidation_count", 0)) for _, p in parts)
    pf = sum(float(w) * float(p.get("profit_factor", 0.0)) for w, p in parts)
    mdd = sum(float(w) * float(p.get("max_drawdown_pct", 0.0)) for w, p in parts)

    return {
        "strategy": "ensemble_regime",
        "initial_usdt": initial_usdt,
        "final_usdt": final_usdt,
        "return_pct": ret_pct,
        "total_trades": total_trades,
        "liquidation_count": liq,
        "parts": [{"weight": w, "strategy": p.get("strategy"), "return_pct": p.get("return_pct", 0.0)} for w, p in parts],
        "win_rate": 0.0,
        "profit_factor": pf,
        "max_drawdown_pct": mdd,
        "trades": [],
        "equity_curve": [],
    }


def optimize_ensemble(
    candles: List[List[float]],
    objective: str = "balanced",
    initial_usdt: float = 1000.0,
    position_mode: str = "both",
    leverage: float = 1.0,
    funding_rate_per_8h: float = 0.0,
    funding_events: Optional[List[Dict[str, Any]]] = None,
    max_mdd_pct: float = 40.0,
    max_liquidations: int = 3,
    min_trades: int = 5,
) -> Dict[str, Any]:
    rows = []
    best = None

    weight_sets = [
        (0.5, 0.3, 0.2),
        (0.4, 0.3, 0.3),
        (0.3, 0.4, 0.3),
        (0.6, 0.2, 0.2),
        (0.2, 0.5, 0.3),
    ]
    spread_sets = [0.008, 0.01, 0.015]
    rsi_sets = [(25, 75), (30, 70), (35, 65)]

    for tw, rw, bw in weight_sets:
        for sp in spread_sets:
            for rl, rh in rsi_sets:
                r = run_ensemble_backtest(
                    candles,
                    initial_usdt=initial_usdt,
                    position_mode=position_mode,
                    leverage=leverage,
                    funding_rate_per_8h=funding_rate_per_8h,
                    funding_events=funding_events,
                    trend_weight=tw,
                    reversal_weight=rw,
                    base_weight=bw,
                    trend_spread_threshold=sp,
                    reversal_rsi_low=float(rl),
                    reversal_rsi_high=float(rh),
                )
                if r.get("error"):
                    continue

                row = {
                    "trend_weight": tw,
                    "reversal_weight": rw,
                    "base_weight": bw,
                    "trend_spread_threshold": sp,
                    "reversal_rsi_low": rl,
                    "reversal_rsi_high": rh,
                    "return_pct": float(r.get("return_pct", 0.0)),
                    "profit_factor": float(r.get("profit_factor", 0.0)),
                    "max_drawdown_pct": float(r.get("max_drawdown_pct", 0.0)),
                    "liquidation_count": int(r.get("liquidation_count", 0)),
                    "total_trades": int(r.get("total_trades", 0)),
                    "final_usdt": float(r.get("final_usdt", initial_usdt)),
                }

                if row["max_drawdown_pct"] > max_mdd_pct:
                    continue
                if row["liquidation_count"] > max_liquidations:
                    continue
                if row["total_trades"] < min_trades:
                    continue

                score = _opt_score(row, objective) - (row["liquidation_count"] * 0.5)
                row["score"] = score
                rows.append(row)

                if best is None or score > best["score"]:
                    best = row

    rows = sorted(rows, key=lambda x: x.get("score", -999999), reverse=True)
    return {"best": best, "rows": rows}


def run_simple_ema_backtest(candles: List[List[float]], initial_usdt: float = 1000.0, fee_pct: float = 0.0005, sl_pct: float = 0.01, tp_rr: float = 1.5) -> Dict[str, Any]:
    return run_backtest(
        candles,
        strategy="ema_cross",
        initial_usdt=initial_usdt,
        fee_pct=fee_pct,
        sl_pct=sl_pct,
        tp_rr=tp_rr,
    )


def _opt_score(row: Dict[str, Any], objective: str) -> float:
    ret = float(row.get("return_pct", 0.0))
    pf = float(row.get("profit_factor", 0.0))
    mdd = float(row.get("max_drawdown_pct", 0.0))

    if objective == "safe":
        return ret + (pf * 2.0) - (mdd * 1.5)
    if objective == "balanced":
        return ret + (pf * 1.0) - (mdd * 1.0)
    if objective == "aggressive":
        return ret + (pf * 0.5) - (mdd * 0.5)
    return ret


def optimize_strategy(candles: List[List[float]], strategy: str = "ema_cross", objective: str = "return") -> Dict[str, Any]:
    best = None
    rows = []

    ema_fast_candidates = [10, 20, 30]
    ema_slow_candidates = [50, 100]
    rsi_period_candidates = [10, 14]
    rsi_lower_candidates = [25, 30, 35]
    rsi_upper_candidates = [60, 65, 70]
    breakout_candidates = [20, 30, 40]

    if strategy == "ema_cross":
        for ef in ema_fast_candidates:
            for es in ema_slow_candidates:
                if ef >= es:
                    continue
                r = run_backtest(candles, strategy=strategy, ema_fast_period=ef, ema_slow_period=es)
                if r.get("error"):
                    continue
                row = {
                    "strategy": strategy,
                    "ema_fast": ef,
                    "ema_slow": es,
                    "return_pct": r.get("return_pct", 0.0),
                    "win_rate": r.get("win_rate", 0.0),
                    "total_trades": r.get("total_trades", 0),
                    "profit_factor": r.get("profit_factor", 0.0),
                    "max_drawdown_pct": r.get("max_drawdown_pct", 0.0),
                }
                rows.append(row)
                if best is None or _opt_score(row, objective) > _opt_score(best, objective):
                    best = row

    elif strategy == "rsi_reversion":
        for rp in rsi_period_candidates:
            for rl in rsi_lower_candidates:
                for ru in rsi_upper_candidates:
                    if rl >= ru:
                        continue
                    r = run_backtest(candles, strategy=strategy, rsi_period=rp, rsi_lower=rl, rsi_upper=ru)
                    if r.get("error"):
                        continue
                    row = {
                        "strategy": strategy,
                        "rsi_period": rp,
                        "rsi_lower": rl,
                        "rsi_upper": ru,
                        "return_pct": r.get("return_pct", 0.0),
                        "win_rate": r.get("win_rate", 0.0),
                        "total_trades": r.get("total_trades", 0),
                        "profit_factor": r.get("profit_factor", 0.0),
                        "max_drawdown_pct": r.get("max_drawdown_pct", 0.0),
                    }
                    rows.append(row)
                    if best is None or _opt_score(row, objective) > _opt_score(best, objective):
                        best = row

    elif strategy == "breakout_20":
        for b in breakout_candidates:
            for ef in ema_fast_candidates:
                for es in ema_slow_candidates:
                    if ef >= es:
                        continue
                    r = run_backtest(candles, strategy=strategy, breakout_lookback=b, ema_fast_period=ef, ema_slow_period=es)
                    if r.get("error"):
                        continue
                    row = {
                        "strategy": strategy,
                        "breakout_lookback": b,
                        "ema_fast": ef,
                        "ema_slow": es,
                        "return_pct": r.get("return_pct", 0.0),
                        "win_rate": r.get("win_rate", 0.0),
                        "total_trades": r.get("total_trades", 0),
                        "profit_factor": r.get("profit_factor", 0.0),
                        "max_drawdown_pct": r.get("max_drawdown_pct", 0.0),
                    }
                    rows.append(row)
                    if best is None or _opt_score(row, objective) > _opt_score(best, objective):
                        best = row

    elif strategy in ["trend_continuation_system", "liquidation_reversal_setup"]:
        sl_candidates = [0.008, 0.012, 0.015, 0.02]
        rr_candidates = [1.5, 2.0, 3.0]
        for sl in sl_candidates:
            for rr in rr_candidates:
                r = run_backtest(candles, strategy=strategy, sl_pct=sl, tp_rr=rr)
                if r.get("error"):
                    continue
                row = {
                    "strategy": strategy,
                    "sl_pct": sl,
                    "tp_rr": rr,
                    "return_pct": r.get("return_pct", 0.0),
                    "win_rate": r.get("win_rate", 0.0),
                    "total_trades": r.get("total_trades", 0),
                    "profit_factor": r.get("profit_factor", 0.0),
                    "max_drawdown_pct": r.get("max_drawdown_pct", 0.0),
                }
                rows.append(row)
                if best is None or _opt_score(row, objective) > _opt_score(best, objective):
                    best = row

    return {"best": best, "rows": rows}


def walk_forward_backtest(candles: List[List[float]], strategy: str = "ema_cross", train_ratio: float = 0.7) -> Dict[str, Any]:
    if len(candles) < 200:
        return {"error": "not enough candles for walk-forward"}

    split_idx = int(len(candles) * train_ratio)
    train = candles[:split_idx]
    test = candles[split_idx:]

    opt = optimize_strategy(train, strategy=strategy)
    best = opt.get("best")
    if not best:
        return {"error": "optimization failed"}

    kwargs = {
        "strategy": strategy,
        "ema_fast_period": best.get("ema_fast", 20),
        "ema_slow_period": best.get("ema_slow", 50),
        "rsi_period": best.get("rsi_period", 14),
        "rsi_lower": best.get("rsi_lower", 30),
        "rsi_upper": best.get("rsi_upper", 65),
        "breakout_lookback": best.get("breakout_lookback", 20),
    }

    train_result = run_backtest(train, **kwargs)
    test_result = run_backtest(test, **kwargs)

    return {
        "best_params": best,
        "train_result": {
            "return_pct": train_result.get("return_pct", 0.0),
            "win_rate": train_result.get("win_rate", 0.0),
            "total_trades": train_result.get("total_trades", 0),
        },
        "test_result": {
            "return_pct": test_result.get("return_pct", 0.0),
            "win_rate": test_result.get("win_rate", 0.0),
            "total_trades": test_result.get("total_trades", 0),
        },
    }
