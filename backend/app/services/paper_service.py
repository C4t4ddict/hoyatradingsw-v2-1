from paper_live import load_state as load_paper_state, start_session as start_paper_session, pause_session as pause_paper_session, reset_session as reset_paper_session


def get_paper_payload():
    state = load_paper_state()
    return {'running': state.get('running'), 'paused': state.get('paused'), 'metrics': state.get('metrics'), 'result': state.get('result'), 'config': state.get('config')}


def start_paper():
    cfg = {'market_type': 'futures', 'symbol': 'BTC/USDT:USDT', 'timeframe': '15m', 'strategy': 'ensemble_regime', 'initial_usdt': 1000.0, 'position_mode': 'both', 'leverage': 1.0}
    return start_paper_session(cfg)


def pause_paper():
    return pause_paper_session()


def reset_paper():
    return reset_paper_session()
