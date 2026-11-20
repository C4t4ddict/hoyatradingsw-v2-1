from typing import Optional

from fastapi import APIRouter, Header
from backend.app.services.account_service import get_account_payload
router = APIRouter()
@router.get('/api/account')
def api_account(market_type: str = 'futures', x_webhook_token: Optional[str] = Header(default=None)):
    return get_account_payload(market_type, x_webhook_token)
