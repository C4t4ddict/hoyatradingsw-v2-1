import os
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from signal_quality import SignalQualityStore, analyze_market_regime
from ml_readiness import get_hybrid_ml_readiness


router = APIRouter()


def _store() -> SignalQualityStore:
    return SignalQualityStore(os.getenv("SIGNAL_QUALITY_PATH", "data/signal_quality.sqlite3"))


class SignalOutcome(BaseModel):
    signal_type: str
    horizon: str
    predicted_probability: float
    actual: int
    signed_score: float
    forward_return: float
    source: Optional[str] = None
    occurred_at: Optional[str] = None
    observation_id: Optional[str] = None


class MarketRegimeRequest(BaseModel):
    closes: list[float]
    volumes: Optional[list[float]] = None
    funding_rate: float = 0.0
    alt_returns: Optional[list[float]] = None
    as_of_index: Optional[int] = None


@router.get('/api/signals/quality')
def get_signal_quality():
    store = _store()
    return {
        "intel": store.summary("intel"),
        "ml": store.summary("ml"),
        "pattern": store.summary("pattern"),
        "intel_by_horizon": store.horizon_summaries("intel"),
        "ml_by_horizon": store.horizon_summaries("ml"),
        "pattern_by_horizon": store.horizon_summaries("pattern"),
        "sources": store.source_reliability(),
    }


@router.get('/api/ml/readiness')
def get_model_readiness():
    return get_hybrid_ml_readiness()


@router.post('/api/signals/outcomes')
def record_signal_outcome(body: SignalOutcome):
    store = _store()
    written = store.record(**body.model_dump())
    return {"written": written, "quality": store.summary(body.signal_type)}


@router.post('/api/signals/regime')
def classify_regime(body: MarketRegimeRequest):
    return analyze_market_regime(**body.model_dump())
