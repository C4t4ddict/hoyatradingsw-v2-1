from fastapi import APIRouter
from app.services.overview_service import get_overview_payload
router = APIRouter()
@router.get('/api/overview')
def api_overview():
    return get_overview_payload()
