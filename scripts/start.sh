#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p records hls logs
touch logs/app.log logs/ffmpeg.stdout.log logs/ffmpeg.stderr.log logs/health.json
bash scripts/compose.sh -f docker/docker-compose.yml up --build -d
