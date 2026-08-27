from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.services.backtest_service import run_backtest_analysis


router = APIRouter()


class BacktestRequest(BaseModel):
    asset: Literal["BTC", "ETH", "SOL"] = "BTC"
    market_type: Literal["spot", "futures"] = "spot"
    timeframe: Literal["15m", "1h", "4h"] = "4h"
    start_date: date
    end_date: date
    strategy: Literal[
        "ema_cross",
        "rsi_reversion",
        "breakout_20",
        "trend_continuation_system",
        "volatility_breakout_atr",
    ] = "ema_cross"
    position_mode: Literal["long", "short", "both"] = "long"
    initial_usdt: float = Field(default=1000.0, ge=100.0, le=1_000_000.0)
    fee_pct: float = Field(default=0.0005, ge=0.0, le=0.02)
    slippage_pct: float = Field(default=0.0005, ge=0.0, le=0.02)
    leverage: float = Field(default=1.0, ge=1.0, le=5.0)


@router.post("/api/backtests/run")
def run_backtest_endpoint(body: BacktestRequest):
    if body.market_type == "spot" and body.position_mode != "long":
        raise HTTPException(status_code=422, detail="현물 백테스트는 매수 방향만 지원합니다.")
    if body.market_type == "spot" and body.leverage != 1.0:
        raise HTTPException(status_code=422, detail="현물 백테스트 레버리지는 1배여야 합니다.")
    try:
        return run_backtest_analysis(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"공개 시세 조회 또는 백테스트 실행에 실패했습니다: {type(exc).__name__}") from exc
