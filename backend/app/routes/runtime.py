import time
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.app.routes.security import _authorize_settings
from runtime_data import BAR_MS, RuntimeStore, SYMBOLS
from runtime_evaluation import EvaluationStore

router = APIRouter()


class RuntimeControl(BaseModel):
    action: Literal['pause', 'resume', 'retry']


@router.get('/api/runtime')
def runtime_status():
    store = EvaluationStore()
    return {**store.status(), 'campaigns': store.campaigns(), 'signals': store.signal_status()}


@router.get('/api/runtime/candles')
def runtime_candles(symbol: str = 'BTC/USDT'):
    if symbol not in SYMBOLS:
        raise HTTPException(422, '차트에서 지원하지 않는 종목입니다.')
    now_ms = int(time.time() * 1000)
    rows = RuntimeStore().candles(symbol, now_ms=now_ms, limit=540)
    last_completed_open = now_ms // BAR_MS * BAR_MS - BAR_MS
    return {'symbol': symbol, 'interval_ms': BAR_MS, 'rows': rows,
            'stale': not rows or rows[-1][0] < last_completed_open}


@router.post('/api/runtime/control')
def runtime_control(body: RuntimeControl, x_settings_token: Optional[str] = Header(default=None)):
    _authorize_settings(x_settings_token)
    store = EvaluationStore()
    store.control(body.action)
    return store.status()


@router.post('/api/paper/resume')
def paper_resume(x_settings_token: Optional[str] = Header(default=None)):
    _authorize_settings(x_settings_token)
    from paper_live import load_state, resume_session
    state = load_state()
    if not state.get('session_id'):
        raise HTTPException(409, '재개할 세션이 없습니다. 모의투자 화면에서 시작하세요.')
    if any(not row['ready'] for row in EvaluationStore().status()['market']):
        raise HTTPException(409, '공개 시세 수집 완료 후 재개하세요.')
    return resume_session()
