from fastapi import APIRouter
from backend.app.services.risk_service import get_risk_payload
router = APIRouter()
@router.get('/api/risk')
def api_risk():
    return get_risk_payload()
