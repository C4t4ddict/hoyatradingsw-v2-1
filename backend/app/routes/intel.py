from fastapi import APIRouter
from app.services.intel_service import get_intel_payload
router = APIRouter()
@router.get('/api/intel')
def api_intel():
    return get_intel_payload()
