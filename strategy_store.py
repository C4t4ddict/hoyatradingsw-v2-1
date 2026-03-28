import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, List

STORE_PATH = os.getenv("STRATEGY_STORE_PATH", "data/strategy_params.json")


def _ensure_parent(path: str):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_store(path: str = STORE_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_store(data: Dict[str, Any], path: str = STORE_PATH):
    _ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _key(symbol: str, timeframe: str, strategy: str) -> str:
    return f"{symbol}|{timeframe}|{strategy}"


def save_strategy_params(symbol: str, timeframe: str, strategy: str, params: Dict[str, Any], path: str = STORE_PATH):
    store = load_store(path)
    key = _key(symbol, timeframe, strategy)

    record = store.get(key)
    if not isinstance(record, dict):
        record = {"latest": {}, "versions": []}

    payload = {**params, "saved_at": _now_iso()}
    versions = record.get("versions") if isinstance(record.get("versions"), list) else []
    versions.append(payload)

    # 최신 50개 버전만 유지
    if len(versions) > 50:
        versions = versions[-50:]

    record["latest"] = payload
    record["versions"] = versions
    store[key] = record
    save_store(store, path)


def get_strategy_params(symbol: str, timeframe: str, strategy: str, path: str = STORE_PATH) -> Dict[str, Any]:
    store = load_store(path)
    key = _key(symbol, timeframe, strategy)
    record = store.get(key)

    # backward compatibility (old plain dict)
    if isinstance(record, dict) and "latest" not in record:
        return record

    if isinstance(record, dict):
        latest = record.get("latest")
        if isinstance(latest, dict):
            return latest
    return {}


def list_strategy_versions(symbol: str, timeframe: str, strategy: str, path: str = STORE_PATH) -> List[Dict[str, Any]]:
    store = load_store(path)
    key = _key(symbol, timeframe, strategy)
    record = store.get(key)
    if isinstance(record, dict) and isinstance(record.get("versions"), list):
        return record.get("versions", [])
    return []


def get_strategy_version(symbol: str, timeframe: str, strategy: str, version_index: int, path: str = STORE_PATH) -> Dict[str, Any]:
    versions = list_strategy_versions(symbol, timeframe, strategy, path)
    if not versions:
        return {}
    if version_index < 0 or version_index >= len(versions):
        return {}
    v = versions[version_index]
    return v if isinstance(v, dict) else {}


def set_latest_from_version(symbol: str, timeframe: str, strategy: str, version_index: int, path: str = STORE_PATH) -> bool:
    store = load_store(path)
    key = _key(symbol, timeframe, strategy)
    record = store.get(key)
    if not isinstance(record, dict):
        return False
    versions = record.get("versions")
    if not isinstance(versions, list) or version_index < 0 or version_index >= len(versions):
        return False

    selected = versions[version_index]
    if not isinstance(selected, dict):
        return False

    record["latest"] = {**selected, "activated_at": _now_iso(), "version_index": version_index}
    store[key] = record
    save_store(store, path)
    return True


def set_strategy_tag(symbol: str, timeframe: str, strategy: str, tag: str, version_index: int, path: str = STORE_PATH) -> bool:
    store = load_store(path)
    key = _key(symbol, timeframe, strategy)
    record = store.get(key)
    if not isinstance(record, dict):
        return False

    versions = record.get("versions")
    if not isinstance(versions, list) or version_index < 0 or version_index >= len(versions):
        return False

    tags = record.get("tags")
    if not isinstance(tags, dict):
        tags = {}

    tags[tag] = {
        "version_index": version_index,
        "updated_at": _now_iso(),
    }
    record["tags"] = tags
    store[key] = record
    save_store(store, path)
    return True


def get_strategy_tag(symbol: str, timeframe: str, strategy: str, tag: str, path: str = STORE_PATH) -> Dict[str, Any]:
    store = load_store(path)
    key = _key(symbol, timeframe, strategy)
    record = store.get(key)
    if not isinstance(record, dict):
        return {}

    tags = record.get("tags")
    if not isinstance(tags, dict):
        return {}

    v = tags.get(tag)
    return v if isinstance(v, dict) else {}


def set_strategy_lock(symbol: str, timeframe: str, strategy: str, locked: bool, reason: str = "", path: str = STORE_PATH) -> bool:
    store = load_store(path)
    key = _key(symbol, timeframe, strategy)
    record = store.get(key)
    if not isinstance(record, dict):
        return False

    record["lock"] = {
        "locked": bool(locked),
        "reason": reason,
        "updated_at": _now_iso(),
    }
    store[key] = record
    save_store(store, path)
    return True


def get_strategy_lock(symbol: str, timeframe: str, strategy: str, path: str = STORE_PATH) -> Dict[str, Any]:
    store = load_store(path)
    key = _key(symbol, timeframe, strategy)
    record = store.get(key)
    if not isinstance(record, dict):
        return {"locked": False}

    lock = record.get("lock")
    if isinstance(lock, dict):
        return lock
    return {"locked": False}



def save_portfolio_weights(symbol: str, timeframe: str, weights: Dict[str, float], path: str = STORE_PATH):
    store = load_store(path)
    bucket = store.get("__portfolio_weights__")
    if not isinstance(bucket, dict):
        bucket = {}

    key = f"{symbol}|{timeframe}"
    bucket[key] = {**weights, "saved_at": _now_iso()}
    store["__portfolio_weights__"] = bucket
    save_store(store, path)


def get_portfolio_weights(symbol: str, timeframe: str, path: str = STORE_PATH) -> Dict[str, Any]:
    store = load_store(path)
    bucket = store.get("__portfolio_weights__")
    if not isinstance(bucket, dict):
        return {}
    key = f"{symbol}|{timeframe}"
    v = bucket.get(key)
    return v if isinstance(v, dict) else {}


def save_named_preset(symbol: str, timeframe: str, strategy: str, preset_name: str, params: Dict[str, Any], path: str = STORE_PATH):
    if not preset_name.strip():
        return
    store = load_store(path)
    key = _key(symbol, timeframe, strategy)

    record = store.get(key)
    if not isinstance(record, dict):
        record = {"latest": {}, "versions": [], "presets": {}}

    presets = record.get("presets")
    if not isinstance(presets, dict):
        presets = {}

    presets[preset_name.strip()] = {**params, "saved_at": _now_iso()}
    record["presets"] = presets
    store[key] = record
    save_store(store, path)


def list_named_presets(symbol: str, timeframe: str, strategy: str, path: str = STORE_PATH) -> Dict[str, Dict[str, Any]]:
    store = load_store(path)
    key = _key(symbol, timeframe, strategy)
    record = store.get(key)
    if not isinstance(record, dict):
        return {}
    presets = record.get("presets")
    if isinstance(presets, dict):
        return presets
    return {}


def get_named_preset(symbol: str, timeframe: str, strategy: str, preset_name: str, path: str = STORE_PATH) -> Dict[str, Any]:
    presets = list_named_presets(symbol, timeframe, strategy, path)
    v = presets.get(preset_name)
    return v if isinstance(v, dict) else {}
