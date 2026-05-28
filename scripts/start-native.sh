#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PID_DIR="${PID_DIR:-$ROOT_DIR/run}"
APP_PID_FILE="$PID_DIR/app.pid"
REQUIREMENTS_FILE="$ROOT_DIR/requirements.txt"

mkdir -p "$PID_DIR" records hls logs

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

check_python_requirements() {
  local output

  output="$("$PYTHON_BIN" - "$REQUIREMENTS_FILE" <<'PY'
import pathlib
import subprocess
import sys

requirements_file = pathlib.Path(sys.argv[1])
if not requirements_file.exists():
    sys.exit(0)

missing = []
for raw_line in requirements_file.read_text().splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    requirement = line.split("==", 1)[0].strip()
    result = subprocess.run(
        [sys.executable, "-m", "pip", "show", requirement],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        missing.append(requirement)

for requirement in missing:
    print(requirement)
PY
)"

  if [[ -n "$output" ]]; then
    printf '%s\n' "$output"
  fi
}

has_internet_for_pip() {
  "$PYTHON_BIN" - <<'PY'
import socket
import sys

hosts = [
    ("pypi.org", 443),
    ("files.pythonhosted.org", 443),
]

for host, port in hosts:
    try:
        with socket.create_connection((host, port), timeout=2):
            sys.exit(0)
    except OSError:
        continue

sys.exit(1)
PY
}

ensure_python_dependencies() {
  if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
    return
  fi

  local missing_requirements
  missing_requirements="$(check_python_requirements)"

  if [[ -z "$missing_requirements" ]]; then
    echo "Python dependencies already installed"
    return
  fi

  echo "Missing Python dependencies detected:"
  printf '%s\n' "$missing_requirements"

  if ! has_internet_for_pip; then
    echo "No internet connection detected, skipping dependency install"
    return
  fi

  echo "Internet detected, installing Python dependencies"
  if ! "$PYTHON_BIN" -m pip install -r "$REQUIREMENTS_FILE"; then
    echo "Dependency install failed, continuing startup without blocking" >&2
  fi
}

require_command "$PYTHON_BIN"
require_command ffmpeg
require_command mediamtx
ensure_python_dependencies

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
