from fastapi import APIRouter

from backend.app.services.operations_service import get_daily_report, get_operations_payload, send_daily_report


router = APIRouter()


@router.get('/api/operations')
def api_operations():
    return get_operations_payload()


@router.get('/api/operations/daily-report')
def api_operations_daily_report():
    return get_daily_report()


@router.post('/api/operations/daily-report/send')
def api_operations_send_daily_report():
    return send_daily_report()
