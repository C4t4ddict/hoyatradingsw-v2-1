import os
from typing import Any, Dict, List

import ccxt


def _normalize_market_type(market_type: str) -> str:
    if not market_type:
        return os.getenv("BINANCE_DEFAULT_TYPE", "spot").lower()
    mt = market_type.lower().strip()
    if mt in ["future", "futures", "swap", "usdm", "perp", "perpetual"]:
        return "swap"
    return "spot"


def get_exchange(read_only: bool = False, market_type: str = ""):
    ex_name = os.getenv("EXCHANGE", "binance")
    key = os.getenv("API_KEY", "")
    secret = os.getenv("API_SECRET", "")

    ex_class = getattr(ccxt, ex_name)
    default_type = _normalize_market_type(market_type)

    config = {
        "enableRateLimit": True,
        "timeout": int(os.getenv("CCXT_TIMEOUT_MS", "20000")),
        "options": {
            "defaultType": default_type,
            "warnOnFetchOpenOrdersWithoutSymbol": False,
        },
    }

    if not read_only:
        config["apiKey"] = key
        config["secret"] = secret

    ex = ex_class(config)

    # read_only(백테스트/시세조회)는 메인넷 공개 OHLCV를 사용해 타임아웃을 줄인다.
    use_testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"
    if use_testnet and (not read_only) and hasattr(ex, "set_sandbox_mode"):
        ex.set_sandbox_mode(True)

    return ex


def place_market_order(exchange, symbol: str, side: str, amount: float, dry_run: bool = True):
    if dry_run:
        return {"dry_run": True, "symbol": symbol, "side": side, "amount": amount}
    return exchange.create_order(symbol, "market", side, amount)


def fetch_account_status(exchange) -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "balance": None,
        "positions": [],
        "open_orders": [],
    }

    try:
        bal = exchange.fetch_balance()
        usdt_total = None
        usdt_free = None
        usdt_used = None

        if isinstance(bal, dict):
            usdt_obj = bal.get("USDT") or {}
            usdt_total = usdt_obj.get("total")
            usdt_free = usdt_obj.get("free")
            usdt_used = usdt_obj.get("used")

            if usdt_total is None:
                usdt_total = bal.get("total", {}).get("USDT")
            if usdt_free is None:
                usdt_free = bal.get("free", {}).get("USDT")
            if usdt_used is None:
                usdt_used = bal.get("used", {}).get("USDT")

        status["balance"] = {
            "usdt_total": usdt_total,
            "usdt_free": usdt_free,
            "usdt_used": usdt_used,
        }
    except Exception as e:
        status["balance_error"] = str(e)

    try:
        if hasattr(exchange, "fetch_positions"):
            positions = exchange.fetch_positions()
            keep: List[Dict[str, Any]] = []
            for p in positions:
                contracts = p.get("contracts")
                if contracts in [None, 0, 0.0]:
                    continue
                keep.append({
                    "symbol": p.get("symbol"),
                    "side": p.get("side"),
                    "contracts": contracts,
                    "entryPrice": p.get("entryPrice"),
                    "markPrice": p.get("markPrice"),
                    "unrealizedPnl": p.get("unrealizedPnl"),
                })
            status["positions"] = keep
    except Exception as e:
        status["positions_error"] = str(e)

    try:
        open_orders = exchange.fetch_open_orders()
        status["open_orders"] = [{
            "symbol": o.get("symbol"),
            "side": o.get("side"),
            "type": o.get("type"),
            "amount": o.get("amount"),
            "price": o.get("price"),
            "status": o.get("status"),
        } for o in open_orders]
    except Exception as e:
        status["open_orders_error"] = str(e)

    return status


def fetch_pnl_snapshot(exchange) -> Dict[str, Any]:
    realized = 0.0
    unrealized = 0.0

    try:
        if hasattr(exchange, "fetch_positions"):
            positions = exchange.fetch_positions()
            for p in positions:
                v = p.get("unrealizedPnl")
                if isinstance(v, (int, float)):
                    unrealized += float(v)
    except Exception:
        pass

    try:
        if hasattr(exchange, "fetch_my_trades"):
            trades = exchange.fetch_my_trades(limit=200)
            for t in trades:
                info = t.get("info") if isinstance(t, dict) else None
                if not isinstance(info, dict):
                    continue
                rp = info.get("realizedPnl")
                if rp is None:
                    rp = info.get("realizedProfit")
                try:
                    if rp is not None:
                        realized += float(rp)
                except Exception:
                    continue
    except Exception:
        pass

    return {
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
    }
