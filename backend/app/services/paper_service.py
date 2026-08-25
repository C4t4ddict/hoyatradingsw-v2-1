from paper_live import load_state as load_paper_state, start_session as start_paper_session, pause_session as pause_paper_session, reset_session as reset_paper_session, stop_background_worker, get_audit_payload as get_paper_audit_payload, get_strategy_payload, get_ledger_events
from market_intel import get_market_brief
from backend.app.services.ml_signal_service import build_signal_summary


def get_paper_payload():
    state = load_paper_state()
    latest_event = ((get_market_brief(force_refresh=False).get('top') or [{}])[0])
    ml_signal = build_signal_summary(latest_event, get_market_brief(force_refresh=False), regime=state.get('market_regime')) if latest_event else {}
    return {
        'running': state.get('running'),
        'paused': state.get('paused'),
        'metrics': state.get('metrics'),
        'result': state.get('result'),
        'config': state.get('config'),
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
    cfg = {
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
    if overrides:
        cfg.update(overrides)
    return start_paper_session(cfg)


def pause_paper():
    return pause_paper_session()


def reset_paper():
    return reset_paper_session()


def update_paper_config(overrides: dict = None):
    state = load_paper_state()
    current_cfg = (state or {}).get('config') or {
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
    if overrides:
        current_cfg.update(overrides)
    stop_background_worker()
    return start_paper_session(current_cfg)


def get_paper_audit():
    return get_paper_audit_payload()


def get_paper_strategy():
    return get_strategy_payload()


def get_paper_events(limit: int = 200):
    return get_ledger_events(limit=limit)
