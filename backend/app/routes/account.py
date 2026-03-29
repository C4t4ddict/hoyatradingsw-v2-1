from fastapi import APIRouter
from app.services.account_service import get_account_payload
router = APIRouter()
@router.get('/api/account')
def api_account(market_type: str = 'futures'):
    return get_account_payload(market_type)
