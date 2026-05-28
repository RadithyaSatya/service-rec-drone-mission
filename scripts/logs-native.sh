#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p logs

touch \
  logs/app.stdout.log \
  logs/app.stderr.log \
  logs/mediamtx.stdout.log \
  logs/mediamtx.stderr.log \
  logs/ffmpeg.stdout.log \
  logs/ffmpeg.stderr.log

tail -n "${TAIL_LINES:-100}" -f \
  logs/app.stdout.log \
  logs/app.stderr.log \
  logs/mediamtx.stdout.log \
  logs/mediamtx.stderr.log \
  logs/ffmpeg.stdout.log \
  logs/ffmpeg.stderr.log
