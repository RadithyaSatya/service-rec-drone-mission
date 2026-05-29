#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  set -a
  source .env
  set +a
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is not installed or not in PATH"
  echo "install ffmpeg first, then rerun ./scripts/start.sh"
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  echo "creating local virtualenv in .venv"
  python3 -m venv .venv
fi

VENV_PY=".venv/bin/python"
VENV_PIP=".venv/bin/pip"

if ! "$VENV_PY" -c "import fastapi, uvicorn, requests, websocket" >/dev/null 2>&1; then
  echo "installing python dependencies from requirements.txt"
  "$VENV_PIP" install -r requirements.txt
fi

mkdir -p records hls logs run
touch logs/app.log logs/ffmpeg.stdout.log logs/ffmpeg.stderr.log
touch logs/service.stdout.log logs/service.stderr.log

echo "starting service in foreground"
echo "press Ctrl+C to stop"

exec "$VENV_PY" app.py
