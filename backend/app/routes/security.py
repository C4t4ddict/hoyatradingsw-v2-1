import secrets
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from live_controls import get_live_control_store
from security import get_vault, resolve_secret


router = APIRouter()
SecretName = Literal[
    "API_KEY", "API_SECRET", "WEBHOOK_TOKEN",
    "ALERT_TELEGRAM_BOT_TOKEN", "ALERT_TELEGRAM_CHAT_ID",
    "PAPER_ALERT_TELEGRAM_BOT_TOKEN", "PAPER_ALERT_TELEGRAM_CHAT_ID",
]


def _authorize_settings(token: Optional[str]) -> None:
    expected = resolve_secret("SETTINGS_TOKEN")
    if not expected or expected == 'CHANGE_ME_SETTINGS_TOKEN':
        raise HTTPException(status_code=503, detail="SETTINGS_TOKEN is not configured")
    if not isinstance(token, str) or not secrets.compare_digest(token.encode('utf-8'), expected.encode('utf-8')):
        raise HTTPException(status_code=401, detail="invalid settings token")


def require_operator(x_settings_token: Optional[str] = Header(default=None)) -> None:
    _authorize_settings(x_settings_token)


def require_local_operator(request: Request, x_settings_token: Optional[str] = Header(default=None)) -> None:
    if request.scope.get('hoya_desktop_authenticated') is not True:
        _authorize_settings(x_settings_token)


class SecretWriteRequest(BaseModel):
    name: SecretName
    value: str = Field(min_length=1, max_length=4096)


class LiveChallengeRequest(BaseModel):
    confirmation: str


class LiveConfirmRequest(BaseModel):
    challenge_token: str
    confirmation: str
    duration_minutes: int = Field(default=240, ge=5, le=1440)


class OrderCapRequest(BaseModel):
    max_order_usdt: float = Field(gt=0)


@router.get('/api/security/status')
def api_security_status():
    return {
        "vault": get_vault().status(),
        "settings_token_configured": bool(resolve_secret("SETTINGS_TOKEN")),
        "live_control": get_live_control_store().status(),
    }


@router.post('/api/security/secrets')
def api_security_set_secret(body: SecretWriteRequest, x_settings_token: Optional[str] = Header(default=None)):
    _authorize_settings(x_settings_token)
    vault = get_vault()
    try:
        vault.set(body.name, body.value)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"stored": True, "name": body.name}


@router.delete('/api/security/secrets/{name}')
def api_security_delete_secret(name: SecretName, x_settings_token: Optional[str] = Header(default=None)):
    _authorize_settings(x_settings_token)
    return {"deleted": get_vault().delete(name), "name": name}


@router.get('/api/live/status')
def api_live_status(request: Request, x_settings_token: Optional[str] = Header(default=None)):
    store = get_live_control_store()
    history = []
    if x_settings_token or request.scope.get('hoya_desktop_authenticated') is True:
        require_local_operator(request, x_settings_token)
        history = store.history(limit=100)
    return {"control": store.status(), "history": history}


@router.post('/api/live/challenge')
def api_live_challenge(body: LiveChallengeRequest, x_settings_token: Optional[str] = Header(default=None)):
    _authorize_settings(x_settings_token)
    try:
        return get_live_control_store().request_live_challenge(body.confirmation)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/api/live/confirm')
def api_live_confirm(body: LiveConfirmRequest, x_settings_token: Optional[str] = Header(default=None)):
    _authorize_settings(x_settings_token)
    try:
        return get_live_control_store().confirm_live(
            body.challenge_token, body.confirmation, duration_minutes=body.duration_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/api/live/disable')
def api_live_disable(x_settings_token: Optional[str] = Header(default=None)):
    _authorize_settings(x_settings_token)
    return get_live_control_store().disable_live()


@router.post('/api/live/order-cap')
def api_live_order_cap(body: OrderCapRequest, x_settings_token: Optional[str] = Header(default=None)):
    _authorize_settings(x_settings_token)
    try:
        return get_live_control_store().set_order_cap(body.max_order_usdt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
