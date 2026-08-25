import os

from paper_live import BACKUP_DIR, backup_ledger, export_ledger_csv, load_state as load_paper_state, start_session as start_paper_session, pause_session as pause_paper_session, reset_session as reset_paper_session, restore_ledger, stop_background_worker, get_audit_payload as get_paper_audit_payload, get_strategy_payload, get_ledger_events
from market_intel import get_market_brief
from backend.app.services.ml_signal_service import build_signal_summary


DEFAULT_PAPER_CONFIG = {
    'market_type': 'spot',
    'symbol': 'BTC/ETH/SOL',
    'timeframe': '4h',
    'strategy': 'vol_target_momentum',
    'initial_usdt': 1000.0,
    'position_mode': 'long_cash',
    'leverage': 1.0,
    'mode': 'vol_target_momentum',
    'live_refresh_sec': 60,
    'fee_pct': 0.0005,
    'slippage_pct': 0.0005,
    'target_volatility': 0.20,
}


def _safe_paper_config(overrides: dict = None):
    config = dict(DEFAULT_PAPER_CONFIG)
    requested = overrides or {}
    config['initial_usdt'] = min(1_000_000.0, max(100.0, float(requested.get('initial_usdt', config['initial_usdt']))))
    config['target_volatility'] = min(0.25, max(0.01, float(requested.get('target_volatility', config['target_volatility']))))
    config['live_refresh_sec'] = min(3600, max(15, int(requested.get('live_refresh_sec', config['live_refresh_sec']))))
    config['fee_pct'] = min(0.02, max(0.0, float(requested.get('fee_pct', config['fee_pct']))))
    config['slippage_pct'] = min(0.02, max(0.0, float(requested.get('slippage_pct', config['slippage_pct']))))
    return config


def get_paper_payload():
    state = load_paper_state()
    brief = get_market_brief(force_refresh=False)
    latest_event = ((brief.get('top') or [{}])[0])
    ml_signal = build_signal_summary(latest_event, brief, regime=state.get('market_regime')) if latest_event else {}
    return {
        'running': state.get('running'),
        'paused': state.get('paused'),
        'metrics': state.get('metrics'),
        'result': state.get('result'),
        'config': _safe_paper_config(state.get('config')),
        'ml_signal': ml_signal,
        'executed_strategy': state.get('executed_strategy'),
        'executed_timeframe': state.get('executed_timeframe'),
        'executed_position_mode': state.get('executed_position_mode'),
        'fallback_mode': state.get('fallback_mode'),
        'paper_note': (state.get('result') or {}).get('note'),
        'strategy_decision': state.get('strategy_decision'),
        'risk_status': state.get('risk_status'),
        'order_events': state.get('order_events') or [],
        'pending_orders': ((state.get('event_engine') or {}).get('pending_orders') or []),
        'market_regime': state.get('market_regime'),
    }


def start_paper(overrides: dict = None):
    stop_background_worker()
    cfg = _safe_paper_config(overrides)
    return start_paper_session(cfg)


def pause_paper():
    return pause_paper_session()


def reset_paper():
    return reset_paper_session()


def update_paper_config(overrides: dict = None):
    state = load_paper_state()
    requested = {**((state or {}).get('config') or {}), **(overrides or {})}
    current_cfg = _safe_paper_config(requested)
    stop_background_worker()
    return start_paper_session(current_cfg)


def get_paper_audit():
    return get_paper_audit_payload()


def get_paper_strategy():
    return get_strategy_payload()


def get_paper_events(limit: int = 200):
    return get_ledger_events(limit=limit)


def create_ledger_backup():
    return backup_ledger()


def create_ledger_export():
    return export_ledger_csv()


def restore_ledger_backup(backup_name: str):
    safe_name = os.path.basename(backup_name)
    if safe_name != backup_name or not safe_name.endswith(".sqlite3"):
        raise ValueError("invalid backup name")
    return restore_ledger(os.path.join(BACKUP_DIR, safe_name))
