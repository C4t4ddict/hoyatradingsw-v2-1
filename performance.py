import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List

PERF_LOG = os.getenv("PERF_LOG", "data/performance_log.jsonl")


def _ensure_parent(path: str):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def log_trade(event: Dict[str, Any], path: str = PERF_LOG):
    _ensure_parent(path)
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_events(path: str = PERF_LOG) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def summarize(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not events:
        return {
            "total_trades": 0,
            "start_balance": None,
            "latest_balance": None,
            "return_pct": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
        }

    balances = [e.get("balance_usdt") for e in events if isinstance(e.get("balance_usdt"), (int, float))]
    start_balance = balances[0] if balances else None
    latest_balance = balances[-1] if balances else None

    if start_balance and latest_balance:
        ret = ((latest_balance - start_balance) / start_balance) * 100.0
    else:
        ret = 0.0

    realized_pnl = 0.0
    unrealized_pnl = 0.0
    for e in events:
        if isinstance(e.get("realized_pnl"), (int, float)):
            realized_pnl += float(e["realized_pnl"])
        if isinstance(e.get("unrealized_pnl"), (int, float)):
            unrealized_pnl += float(e["unrealized_pnl"])

    return {
        "total_trades": len([e for e in events if e.get("type") == "order"]),
        "start_balance": start_balance,
        "latest_balance": latest_balance,
        "return_pct": ret,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
    }


def strategy_breakdown(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bucket: Dict[str, Dict[str, Any]] = {}

    for e in events:
        strategy = e.get("strategy") or "unknown"
        if strategy not in bucket:
            bucket[strategy] = {
                "strategy": strategy,
                "orders": 0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
            }

        if e.get("type") == "order":
            bucket[strategy]["orders"] += 1

        if isinstance(e.get("realized_pnl"), (int, float)):
            bucket[strategy]["realized_pnl"] += float(e["realized_pnl"])

        if isinstance(e.get("unrealized_pnl"), (int, float)):
            bucket[strategy]["unrealized_pnl"] += float(e["unrealized_pnl"])

    return sorted(bucket.values(), key=lambda x: x["orders"], reverse=True)
