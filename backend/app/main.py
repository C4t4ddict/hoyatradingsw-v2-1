from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from webhook_server import app as legacy_app
from backend.app.routes.overview import router as overview_router
from backend.app.routes.paper import router as paper_router
from backend.app.routes.account import router as account_router
from backend.app.routes.risk import router as risk_router
from backend.app.routes.intel import router as intel_router

app = FastAPI(title='HoyaTradingSW v2.1 API')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.mount('/legacy', legacy_app)
app.include_router(overview_router)
app.include_router(paper_router)
app.include_router(account_router)
app.include_router(risk_router)
app.include_router(intel_router)

@app.get('/healthz')
def healthz():
    return {'ok': True, 'message': 'v2.1 backend alive'}
