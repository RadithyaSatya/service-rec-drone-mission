#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PID_DIR="${PID_DIR:-$ROOT_DIR/run}"
APP_PID_FILE="$PID_DIR/app.pid"

if [[ ! -f "$APP_PID_FILE" ]]; then
  echo "Native app is not running"
  exit 0
fi

app_pid="$(cat "$APP_PID_FILE")"
if kill -0 "$app_pid" >/dev/null 2>&1; then
  kill -TERM "$app_pid"
  echo "Sent SIGTERM to native app PID $app_pid"
else
  echo "Stale PID file found for PID $app_pid"
fi

rm -f "$APP_PID_FILE"
