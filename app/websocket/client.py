from __future__ import annotations

import json
import threading
import time

import requests
import websocket

from app.config.settings import Settings
from app.streaming.pipeline import StreamingController, build_ws_base_url
from app.utils.logger import get_logger
from app.websocket.handlers import TelemetryMessageRouter
from app.websocket.reconnect import default_backoff

LOGGER = get_logger(__name__)


class TelemetryWebSocketClient:
    def __init__(self, settings: Settings, controller: StreamingController) -> None:
        self._settings = settings
        self._controller = controller
        self._router = TelemetryMessageRouter(controller)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="telemetry-ws", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _run(self) -> None:
        backoff = default_backoff()
        while not self._stop_event.is_set():
            ws = None
            try:
                ws_url = self._build_ws_url()
                LOGGER.info("connecting websocket", extra={"context": {"url": ws_url}})
                ws = websocket.create_connection(ws_url, timeout=self._settings.ws_timeout_seconds)
                ws.settimeout(self._settings.ws_timeout_seconds)
                self._controller.on_websocket_status(True)
                self._subscribe(ws)
                backoff.reset()
                last_ping = time.monotonic()
                while not self._stop_event.is_set():
                    try:
                        message = ws.recv()
                        if message:
                            self._router.handle(message)
                    except websocket.WebSocketTimeoutException:
                        if time.monotonic() - last_ping >= self._settings.ws_heartbeat_seconds:
                            ws.ping()
                            last_ping = time.monotonic()
            except Exception as exc:
                self._controller.on_websocket_status(False)
                LOGGER.warning("websocket loop error", extra={"context": {"error": str(exc)}})
                backoff.sleep()
            finally:
                self._controller.on_websocket_status(False)
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass

    def _build_ws_url(self) -> str:
        token = self._request_ws_token()
        return f"{build_ws_base_url(self._settings.base_url)}/ws/telemetry?token={token}"

    def _request_ws_token(self) -> str:
        response = requests.post(
            f"{self._settings.base_url}/auth/ws-token",
            headers=self._settings.headers,
            timeout=self._settings.http_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        token = (
            data.get("token")
            or data.get("ws_token")
            or data.get("access_token")
            or data.get("data", {}).get("token")
        )
        if not token:
            raise RuntimeError(f"ws token missing in response: {json.dumps(data)}")
        return token

    def _subscribe(self, ws: websocket.WebSocket) -> None:
        payload = {"type": "subscribe", "uav_ids": [self._settings.subscribe_uav_id]}
        ws.send(json.dumps(payload))
