#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "[setup] creating .venv"
  python3 -m venv .venv
fi

source .venv/bin/activate

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "[setup] created .env from .env.example"
fi

echo "[setup] installing requirements"
pip install -r requirements.txt

echo "[run] starting API server on :8010"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010 > /tmp/hoyatradingsw_server.log 2>&1 &
SERVER_PID=$!

cleanup() {
  echo "[stop] stopping server (pid=$SERVER_PID)"
  kill "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

sleep 2

echo "[run] starting dashboard on :8501"
streamlit run dashboard.py --server.port 8501
