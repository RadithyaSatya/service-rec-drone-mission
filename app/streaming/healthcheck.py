from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from app.config.settings import load_settings


@dataclass(slots=True)
class HealthSnapshot:
    mediamtx_api_ok: bool
    metrics_ok: bool


def collect_health() -> HealthSnapshot:
    settings = load_settings()
    api_ok = _reachable(f"{settings.mediamtx_api_url}/v3/paths/list", settings.http_timeout_seconds)
    metrics_ok = _reachable(settings.mediamtx_metrics_url, settings.http_timeout_seconds)
    return HealthSnapshot(mediamtx_api_ok=api_ok, metrics_ok=metrics_ok)


def write_health_file() -> int:
    settings = load_settings()
    health = collect_health()
    Path(settings.healthcheck_path).write_text(json.dumps(asdict(health), indent=2), encoding="utf-8")
    return 0 if health.mediamtx_api_ok else 1


def _reachable(url: str, timeout: int) -> bool:
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False


if __name__ == "__main__":
    raise SystemExit(write_health_file())
