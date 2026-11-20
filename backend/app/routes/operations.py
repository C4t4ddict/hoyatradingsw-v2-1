from typing import Optional

from fastapi import APIRouter, Depends, Header

from backend.app.services.operations_service import get_daily_report, get_operations_payload, send_daily_report
from backend.app.routes.security import _authorize_settings, require_local_operator, require_operator


router = APIRouter()


@router.get('/api/operations', dependencies=[Depends(require_local_operator)])
def api_operations():
    return get_operations_payload()


@router.get('/api/operations/daily-report', dependencies=[Depends(require_operator)])
def api_operations_daily_report():
    return get_daily_report()


@router.post('/api/operations/daily-report/send')
def api_operations_send_daily_report(x_settings_token: Optional[str] = Header(default=None)):
    _authorize_settings(x_settings_token)
    return send_daily_report()
