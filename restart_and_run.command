#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "[info] HoyaTradingSW v2.1 restart_and_run.command"

COMPOSE_FILE=""
for f in docker-compose.yml docker-compose.yaml compose.yml compose.yaml; do
  if [ -f "$f" ]; then
    COMPOSE_FILE="$f"
    break
  fi
done

if [ -n "$COMPOSE_FILE" ]; then
  echo "[docker] restarting docker compose using $COMPOSE_FILE"
  docker compose -f "$COMPOSE_FILE" down
  docker compose -f "$COMPOSE_FILE" up -d --build
else
  echo "[docker] no docker compose file found in project root. skipping docker restart."
fi

if [ ! -d ".venv" ]; then
  echo "[setup] creating .venv"
  python3 -m venv .venv
fi

source .venv/bin/activate

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "[setup] created .env from .env.example"
fi

if [ -f requirements.txt ]; then
  echo "[setup] installing python requirements"
  pip install -r requirements.txt
fi

if [ -f frontend/package.json ]; then
  echo "[setup] installing frontend packages"
  cd frontend
  npm install
  cd ..
fi

echo "[run] starting backend API on :8010"
osascript <<EOF
 tell application "Terminal"
   do script "cd \"$(pwd)\" && source .venv/bin/activate && python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010"
   activate
 end tell
EOF

sleep 3

if [ -f frontend/package.json ]; then
  echo "[run] starting frontend on :3001"
  osascript <<EOF
 tell application "Terminal"
   do script "cd \"$(pwd)/frontend\" && npm run dev"
   activate
 end tell
EOF
fi

echo "[done] backend: http://127.0.0.1:8010"
echo "[done] frontend: http://127.0.0.1:3001"
echo "Press Enter to close this launcher window."
read
