import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from strategy_governance import StrategyRegistry


router = APIRouter()


def _registry() -> StrategyRegistry:
    return StrategyRegistry(os.getenv("STRATEGY_REGISTRY_PATH", "data/strategy_registry.sqlite3"))


class StrategyRegistration(BaseModel):
    name: str
    version: str
    parameters: Dict[str, Any]
    dataset_as_of: str
    code_sha: str


class StrategyTransition(BaseModel):
    target_stage: str
    metrics: Dict[str, Any]
    evidence: Dict[str, Any]
    manual_approved: bool = False
    approved_by: Optional[str] = None


@router.get('/api/strategies')
def list_strategies():
    return {"strategies": _registry().list()}


@router.post('/api/strategies')
def register_strategy(body: StrategyRegistration):
    try:
        return _registry().register(**body.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/api/strategies/{strategy_id}')
def get_strategy(strategy_id: str):
    try:
        registry = _registry()
        return {"strategy": registry.get(strategy_id), "history": registry.history(strategy_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="strategy not found") from exc


@router.post('/api/strategies/{strategy_id}/transition')
def transition_strategy(strategy_id: str, body: StrategyTransition):
    try:
        return _registry().request_transition(strategy_id, **body.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="strategy not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/api/strategies/{strategy_id}/demote')
def demote_strategy(strategy_id: str, metrics: Dict[str, Any]):
    try:
        return _registry().auto_demote(strategy_id, metrics)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="strategy not found") from exc
