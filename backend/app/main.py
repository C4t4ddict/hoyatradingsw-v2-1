from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from webhook_server import app as legacy_app, health, account_status
from market_intel import get_market_brief
from paper_live import load_state as load_paper_state, start_session as start_paper_session, pause_session as pause_paper_session, reset_session as reset_paper_session
from performance import read_events, summarize
from predict_model import predict_event

app = FastAPI(title='HoyaTradingSW v2.1 API')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.mount('/legacy', legacy_app)

@app.get('/healthz')
def healthz():
    return {'ok': True, 'message': 'v2.1 backend alive'}

@app.get('/api/overview')
def api_overview():
    events = read_events()
    summary = summarize(events)
    brief = get_market_brief(force_refresh=False)
    latest_event = (brief.get('top') or [{}])[0] if brief.get('top') else {}
    ml = predict_event(latest_event) if latest_event else {}
    return {
        'summary': summary,
        'market_brief': brief,
        'ml_pred': ml,
    }

@app.get('/api/paper')
def api_paper():
    return load_paper_state()

@app.get('/api/account')
def api_account(market_type: str = 'futures'):
    return account_status(market_type=market_type)

@app.get('/api/intel')
def api_intel():
    brief = get_market_brief(force_refresh=True)
    latest_event = (brief.get('top') or [{}])[0] if brief.get('top') else {}
    ml = predict_event(latest_event) if latest_event else {}
    return {'market_brief': brief, 'latest_event': latest_event, 'ml_pred': ml}

@app.get('/api/risk')
def api_risk():
    h = health()
    return {'risk_guard': h.get('risk_guard'), 'execution_policy': h.get('execution_policy')}


@app.post("/api/paper/start")
def api_paper_start():
    cfg = {"market_type": "futures", "symbol": "BTC/USDT:USDT", "timeframe": "15m", "strategy": "ensemble_regime", "initial_usdt": 1000.0, "position_mode": "both", "leverage": 1.0}
    return start_paper_session(cfg)

@app.post("/api/paper/pause")
def api_paper_pause():
    return pause_paper_session()

@app.post("/api/paper/reset")
def api_paper_reset():
    return reset_paper_session()
