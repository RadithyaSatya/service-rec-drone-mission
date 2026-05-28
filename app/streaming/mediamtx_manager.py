from __future__ import annotations

import time
from pathlib import Path

import requests

from app.config.settings import Settings
from app.utils.logger import get_logger
from app.utils.process import ManagedProcess, ProcessSpec

LOGGER = get_logger(__name__)


class MediaMTXManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._process = ManagedProcess(
            ProcessSpec(
                name="mediamtx",
                command=[
                    settings.mediamtx_binary,
                    settings.mediamtx_config_path,
                ],
                stdout_path=f"{settings.logs_dir}/mediamtx.stdout.log",
                stderr_path=f"{settings.logs_dir}/mediamtx.stderr.log",
            )
        )

    def start(self) -> None:
        if self._settings.mediamtx_managed:
            Path(self._settings.mediamtx_config_path).parent.mkdir(parents=True, exist_ok=True)
            self._process.start()
        self.wait_until_ready()

    def stop(self) -> None:
        if self._settings.mediamtx_managed:
            self._process.stop()

    def wait_until_ready(self) -> None:
        deadline = time.time() + self._settings.mediamtx_ready_timeout_seconds
        last_error: Exception | None = None
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            try:
                if self.is_healthy():
                    LOGGER.info("mediamtx ready", extra={"context": {"attempt": attempt}})
                    return
            except Exception as exc:  # pragma: no cover - startup probe
                last_error = exc
                LOGGER.info(
                    "mediamtx healthcheck retry",
                    extra={"context": {"attempt": attempt, "error": str(exc)}},
                )
            time.sleep(1)
        raise RuntimeError(f"MediaMTX did not become ready: {last_error}")

    def is_healthy(self) -> bool:
        response = requests.get(
            f"{self._settings.mediamtx_api_url}/v3/paths/list",
            timeout=self._settings.http_timeout_seconds,
        )
        response.raise_for_status()
        return True

    def ensure_running(self) -> None:
        if self._settings.mediamtx_managed and not self._process.is_running():
            LOGGER.warning("mediamtx process exited, restarting")
            time.sleep(self._settings.mediamtx_restart_delay_seconds)
            self._process.start()
        self.wait_until_ready()

    def is_publish_ready(self, path_name: str) -> bool:
        response = requests.get(
            f"{self._settings.mediamtx_api_url}/v3/paths/list",
            timeout=self._settings.http_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("items", []):
            if item.get("name") != path_name:
                continue
            return bool(item.get("sourceReady"))
        return False
