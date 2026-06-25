from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from backend.app.services.paper_service import get_paper_payload, start_paper, pause_paper, reset_paper, update_paper_config, get_paper_audit

router = APIRouter()

class PaperStartRequest(BaseModel):
    market_type: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    strategy: Optional[str] = None
    initial_usdt: Optional[float] = None
    position_mode: Optional[str] = None
    leverage: Optional[float] = None
    mode: Optional[str] = None
    live_refresh_sec: Optional[int] = None

@router.get('/api/paper')
def api_paper():
    return get_paper_payload()

@router.post('/api/paper/start')
def api_paper_start(body: PaperStartRequest = None):
    cfg = body.model_dump(exclude_none=True) if body else None
    return start_paper(cfg)

@router.post('/api/paper/pause')
def api_paper_pause():
    return pause_paper()

@router.post('/api/paper/reset')
def api_paper_reset():
    return reset_paper()

@router.post('/api/paper/config')
def api_paper_config(body: PaperStartRequest = None):
    cfg = body.model_dump(exclude_none=True) if body else {}
    return update_paper_config(cfg)


@router.get('/api/paper/audit')
def api_paper_audit():
    return get_paper_audit()
