from fastapi import APIRouter
from app.services.paper_service import get_paper_payload, start_paper, pause_paper, reset_paper
router = APIRouter()
@router.get('/api/paper')
def api_paper(): return get_paper_payload()
@router.post('/api/paper/start')
def api_paper_start(): return start_paper()
@router.post('/api/paper/pause')
def api_paper_pause(): return pause_paper()
@router.post('/api/paper/reset')
def api_paper_reset(): return reset_paper()
