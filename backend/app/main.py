from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from webhook_server import app as legacy_app

app = FastAPI(title='HoyaTradingSW v2.1 API')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.mount('/legacy', legacy_app)

@app.get('/healthz')
def healthz():
    return {'ok': True, 'message': 'v2.1 backend alive'}
