#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p logs

touch \
  logs/app.log \
  logs/ffmpeg.stdout.log \
  logs/ffmpeg.stderr.log \
  logs/health.json

tail -n "${TAIL_LINES:-100}" -f \
  logs/app.log \
  logs/ffmpeg.stdout.log \
  logs/ffmpeg.stderr.log
