import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

WALLET_HISTORY_PATH = os.getenv("WALLET_HISTORY_PATH", "data/wallet_history.jsonl")


def _ensure_parent(path: str):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def append_wallet_snapshot(market_type: str, usdt_total: float, usdt_free: float = None, usdt_used: float = None, path: str = WALLET_HISTORY_PATH):
    _ensure_parent(path)
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "market_type": market_type,
        "usdt_total": usdt_total,
        "usdt_free": usdt_free,
        "usdt_used": usdt_used,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_wallet_history(path: str = WALLET_HISTORY_PATH) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []

    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows
