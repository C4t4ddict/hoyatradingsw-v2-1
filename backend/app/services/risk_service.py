import os

from live_controls import get_live_control_store
from webhook_server import health

def get_risk_payload():
    h = health()
    guards = h.get('risk_guard') or {}
    limits = h.get('max_concurrent_positions') or {}
    spot = guards.get('spot') or {}
    futures = guards.get('futures') or {}
    return {
        'risk_guard': {
            'spot': {
                'enabled': True,
                'daily_loss_limit_usdt': spot.get('daily_loss_limit_usdt'),
                'max_consecutive_losses': spot.get('max_consecutive_losses'),
                'max_open_positions': limits.get('spot'),
                'allow_short': False,
                'max_leverage': 1,
            },
            'futures': {
                'enabled': True,
                'daily_loss_limit_usdt': futures.get('daily_loss_limit_usdt'),
                'max_consecutive_losses': futures.get('max_consecutive_losses'),
                'max_open_positions': limits.get('futures'),
                'allow_short': True,
                'max_leverage': int(os.getenv('MAX_LIVE_LEVERAGE', '5')),
            },
        },
        'execution_policy': {
            **(h.get('execution_policy') or {}),
            'dry_run': h.get('dry_run'),
            'live_control': get_live_control_store().status(),
        },
    }
