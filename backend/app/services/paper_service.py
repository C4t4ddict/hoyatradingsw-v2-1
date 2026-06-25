from paper_live import load_state as load_paper_state, start_session as start_paper_session, pause_session as pause_paper_session, reset_session as reset_paper_session, stop_background_worker, get_audit_payload as get_paper_audit_payload
from market_intel import get_market_brief
from backend.app.services.ml_signal_service import build_signal_summary


def get_paper_payload():
    state = load_paper_state()
    latest_event = ((get_market_brief(force_refresh=False).get('top') or [{}])[0])
    ml_signal = build_signal_summary(latest_event, get_market_brief(force_refresh=False)) if latest_event else {}
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
        'paper_note': (state.get('result') or {}).get('note')
    }


def start_paper(overrides: dict = None):
    stop_background_worker()
    cfg = {
        'market_type': 'futures',
        'symbol': 'BTC/USDT:USDT',
        'timeframe': '15m',
        'strategy': 'ensemble_regime',
        'initial_usdt': 1000.0,
        'position_mode': 'both',
        'leverage': 10.0,
        'mode': 'ml_signal',
        'live_refresh_sec': 10,
        'fee_pct': 0.0005,
        'funding_rate_per_8h': 0.0001,
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
        'market_type': 'futures',
        'symbol': 'BTC/USDT:USDT',
        'timeframe': '15m',
        'strategy': 'ensemble_regime',
        'initial_usdt': 1000.0,
        'position_mode': 'both',
        'leverage': 10.0,
        'mode': 'ml_signal',
        'live_refresh_sec': 10,
        'fee_pct': 0.0005,
        'funding_rate_per_8h': 0.0001,
    }
    if overrides:
        current_cfg.update(overrides)
    stop_background_worker()
    return start_paper_session(current_cfg)


def get_paper_audit():
    return get_paper_audit_payload()
