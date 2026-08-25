from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.app.services.paper_service import create_ledger_backup, create_ledger_export, get_paper_payload, start_paper, pause_paper, reset_paper, restore_ledger_backup, update_paper_config, get_paper_audit, get_paper_strategy, get_paper_events
from backend.app.routes.security import _authorize_settings

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
    target_volatility: Optional[float] = None
    slippage_pct: Optional[float] = None


class LedgerRestoreRequest(BaseModel):
    backup_name: str

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


@router.get('/api/paper/strategy')
def api_paper_strategy():
    return get_paper_strategy()


@router.get('/api/paper/events')
def api_paper_events(limit: int = 200):
    return get_paper_events(limit=limit)


@router.post('/api/paper/ledger/backup')
def api_paper_ledger_backup(x_settings_token: Optional[str] = Header(default=None)):
    _authorize_settings(x_settings_token)
    return create_ledger_backup()


@router.post('/api/paper/ledger/export')
def api_paper_ledger_export(x_settings_token: Optional[str] = Header(default=None)):
    _authorize_settings(x_settings_token)
    return create_ledger_export()


@router.post('/api/paper/ledger/restore')
def api_paper_ledger_restore(body: LedgerRestoreRequest, x_settings_token: Optional[str] = Header(default=None)):
    _authorize_settings(x_settings_token)
    try:
        return restore_ledger_backup(body.backup_name)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
