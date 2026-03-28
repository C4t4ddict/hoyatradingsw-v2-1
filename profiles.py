RISK_PROFILES = {
    "safe": {
        "label": "안전",
        "risk_per_trade": 0.005,
        "max_position_multiplier": 0.6,
        "default_stop_loss_pct": 0.008,
        "target_rr": 1.3,
    },
    "aggressive": {
        "label": "공격",
        "risk_per_trade": 0.02,
        "max_position_multiplier": 1.5,
        "default_stop_loss_pct": 0.015,
        "target_rr": 2.0,
    },
}


def resolve_profile(name: str):
    if not name:
        return "safe", RISK_PROFILES["safe"]
    key = name.strip().lower()
    if key not in RISK_PROFILES:
        return "safe", RISK_PROFILES["safe"]
    return key, RISK_PROFILES[key]
