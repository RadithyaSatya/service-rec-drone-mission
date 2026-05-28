#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PID_DIR="${PID_DIR:-$ROOT_DIR/run}"
APP_PID_FILE="$PID_DIR/app.pid"

mkdir -p "$PID_DIR" records hls logs

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

require_command "$PYTHON_BIN"
require_command ffmpeg
require_command mediamtx

if [[ -f "$APP_PID_FILE" ]]; then
  existing_pid="$(cat "$APP_PID_FILE")"
  if kill -0 "$existing_pid" >/dev/null 2>&1; then
    echo "Native app already running with PID $existing_pid" >&2
    exit 1
  fi
  rm -f "$APP_PID_FILE"
fi

nohup env MEDIAMTX_MANAGED=true "$PYTHON_BIN" -m app.main \
  >>"$ROOT_DIR/logs/app.stdout.log" \
  2>>"$ROOT_DIR/logs/app.stderr.log" &

app_pid="$!"
echo "$app_pid" >"$APP_PID_FILE"
echo "Native app started with PID $app_pid"
