import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from webhook_server import app as legacy_app
from backend.app.routes.overview import router as overview_router
from backend.app.routes.paper import router as paper_router
from backend.app.routes.account import router as account_router
from backend.app.routes.risk import router as risk_router
from backend.app.routes.intel import router as intel_router
from backend.app.routes.strategies import router as strategies_router
from backend.app.routes.signals import router as signals_router
from backend.app.routes.operations import router as operations_router
from backend.app.routes.security import router as security_router
from backend.app.routes.backtests import router as backtests_router
from backend.app.routes.runtime import router as runtime_router

def _configured_values(name):
    return [value.strip() for value in os.getenv(name, '').split(',') if value.strip() and '*' not in value]


app = FastAPI(title='HoyaTradingSW v2.1 API', docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://127.0.0.1:3001', 'http://localhost:3001', *_configured_values('HOYA_WEB_ORIGINS')],
    allow_methods=['GET', 'POST', 'DELETE'],
    allow_headers=['Content-Type', 'X-Settings-Token', 'X-Webhook-Token'],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', *_configured_values('HOYA_WEB_HOSTS')])


@app.middleware('http')
async def protect_api_responses(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
    return response


app.mount('/legacy', legacy_app)
app.include_router(overview_router)
app.include_router(paper_router)
app.include_router(account_router)
app.include_router(risk_router)
app.include_router(intel_router)
app.include_router(strategies_router)
app.include_router(signals_router)
app.include_router(operations_router)
app.include_router(security_router)
app.include_router(backtests_router)
app.include_router(runtime_router)

@app.get('/healthz')
def healthz():
    return {'ok': True, 'message': 'v2.1 backend alive'}
