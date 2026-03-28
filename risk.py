from dataclasses import dataclass

@dataclass
class RiskConfig:
    account_usdt: float
    risk_per_trade: float
    max_position_usdt: float
    min_order_usdt: float
    target_rr: float
    default_stop_loss_pct: float


def calc_position_size_usdt(cfg: RiskConfig, entry_price: float, stop_price: float) -> float:
    risk_capital = cfg.account_usdt * cfg.risk_per_trade
    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return 0.0

    qty = risk_capital / stop_distance
    position_usdt = qty * entry_price
    position_usdt = min(position_usdt, cfg.max_position_usdt)

    if position_usdt < cfg.min_order_usdt:
        return 0.0
    return position_usdt


def calc_tp_price(entry_price: float, stop_price: float, side: str, rr: float) -> float:
    risk = abs(entry_price - stop_price)
    if side.lower() == "buy":
        return entry_price + risk * rr
    return entry_price - risk * rr
