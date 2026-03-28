import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict

STORE_PATH = os.getenv("IDEMPOTENCY_STORE_PATH", "data/idempotency_store.json")
TTL_HOURS = int(os.getenv("IDEMPOTENCY_TTL_HOURS", "48"))


def _ensure_parent(path: str):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cutoff_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=TTL_HOURS)).isoformat()


def load_store(path: str = STORE_PATH) -> Dict[str, str]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_store(store: Dict[str, str], path: str = STORE_PATH):
    _ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def cleanup_expired(store: Dict[str, str]) -> Dict[str, str]:
    cutoff = _cutoff_iso()
    clean = {}
    for k, v in store.items():
        if isinstance(v, str) and v >= cutoff:
            clean[k] = v
    return clean


def has_signal(signal_id: str) -> bool:
    if not signal_id:
        return False
    store = cleanup_expired(load_store())
    save_store(store)
    return signal_id in store


def save_signal(signal_id: str):
    if not signal_id:
        return
    store = cleanup_expired(load_store())
    store[signal_id] = _now_iso()
    save_store(store)
