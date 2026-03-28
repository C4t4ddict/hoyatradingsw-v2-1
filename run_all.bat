@echo off
cd /d %~dp0

if not exist .venv (
  echo [setup] creating .venv
  py -3 -m venv .venv
)

call .venv\Scripts\activate

if not exist .env (
  copy .env.example .env >nul
  echo [setup] created .env from .env.example
)

echo [setup] installing requirements
pip install -r requirements.txt

echo [run] starting API server on :8000
start "HoyaTradingSW-API" cmd /k "call .venv\Scripts\activate && python main.py"

timeout /t 2 >nul

echo [run] starting dashboard on :8501
start "HoyaTradingSW-Dashboard" cmd /k "call .venv\Scripts\activate && streamlit run dashboard.py --server.port 8501"

echo Done. Open http://127.0.0.1:8501
pause
