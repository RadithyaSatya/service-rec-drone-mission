#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

curl -fsS http://127.0.0.1:9997/v3/paths/list >/dev/null
curl -fsS http://127.0.0.1:9998/metrics >/dev/null
python -m app.streaming.healthcheck
