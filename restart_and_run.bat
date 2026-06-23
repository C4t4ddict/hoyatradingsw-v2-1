@echo off
setlocal
cd /d %~dp0

echo [info] HoyaTradingSW v2.1 restart_and_run.bat

set "COMPOSE_FILE="
if exist docker-compose.yml set "COMPOSE_FILE=docker-compose.yml"
if exist docker-compose.yaml set "COMPOSE_FILE=docker-compose.yaml"
if exist compose.yml set "COMPOSE_FILE=compose.yml"
if exist compose.yaml set "COMPOSE_FILE=compose.yaml"

if defined COMPOSE_FILE (
  echo [docker] restarting docker compose using %COMPOSE_FILE%
  docker compose -f %COMPOSE_FILE% down
  docker compose -f %COMPOSE_FILE% up -d --build
) else (
  echo [docker] no docker compose file found in project root. skipping docker restart.
)

if not exist .venv (
  echo [setup] creating .venv
  py -3 -m venv .venv
)

call .venv\Scripts\activate

if not exist .env (
  if exist .env.example (
    copy .env.example .env >nul
    echo [setup] created .env from .env.example
  )
)

if exist requirements.txt (
  echo [setup] installing python requirements
  pip install -r requirements.txt
)

if exist frontend\package.json (
  echo [setup] installing frontend packages
  cd frontend
  call npm install
  cd ..
)

echo [run] starting backend API on :8010
start "HoyaTradingSW-v2.1-API" cmd /k "cd /d %~dp0 && call .venv\Scripts\activate && python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010"

timeout /t 3 >nul

if exist frontend\package.json (
  echo [run] starting frontend on :3001
  start "HoyaTradingSW-v2.1-Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
)

echo [done] backend: http://127.0.0.1:8010
echo [done] frontend: http://127.0.0.1:3001
pause
