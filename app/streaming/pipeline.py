from __future__ import annotations

import threading
import time
from urllib.parse import urlparse, urlunparse

import requests

from app.config.constants import MissionRuntimeState, StreamProfile
from app.config.settings import Settings
from app.mission.mission_events import MISSION_START_EVENTS, MISSION_STOP_EVENTS
from app.mission.state_machine import MissionStateMachine
from app.streaming.ffmpeg_manager import FFmpegManager
from app.streaming.mediamtx_manager import MediaMTXManager
from app.streaming.recorder import Recorder
from app.telemetry.models import MissionEvent, VehicleState
from app.utils.logger import get_logger

LOGGER = get_logger(__name__)


class StreamingController:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._state = MissionStateMachine()
        self._mediamtx = MediaMTXManager(settings)
        self._recorder = Recorder(settings)
        self._lock = threading.RLock()
        self._running = False
        self._drone_id: str | None = None
        self._publisher: FFmpegManager | None = None

    @property
    def drone_id(self) -> str:
        if not self._drone_id:
            raise RuntimeError("drone id not resolved yet")
        return self._drone_id

    def start(self) -> None:
        self._settings.ensure_runtime_dirs()
        self._drone_id = self._resolve_drone_id()
        self._publisher = FFmpegManager(self._settings, self._drone_id)
        self._mediamtx.start()
        self._running = True
        LOGGER.info(
            "streaming controller started",
            extra={
                "context": {
                    "drone_id": self._drone_id,
                    "publish_url": self._settings.mediamtx_publish_url(self._drone_id),
                    "hls_url": self._settings.mediamtx_hls_url(self._drone_id),
                }
            },
        )

    def stop(self) -> None:
        with self._lock:
            self._running = False
            if self._publisher:
                self._publisher.stop()
            self._state.update_publisher(False)
            self._recorder.stop_session()
            self._mediamtx.stop()
            self._state.clear_mission()
            self._state.update_websocket(False)

    def on_websocket_status(self, connected: bool) -> None:
        self._state.update_websocket(connected)
        self._reconcile()

    def on_vehicle_state(self, payload: VehicleState) -> None:
        LOGGER.info(
            "vehicle state received",
            extra={
                "context": {
                    "connected": payload.connected,
                    "in_mission": payload.in_mission,
                    "armed": payload.armed,
                    "mode": payload.mode,
                }
            },
        )
        self._state.update_vehicle(payload.connected, payload.in_mission)
        if payload.in_mission and self._recorder.active_history_id() is None:
            history_id = self._fetch_active_history_id()
            if history_id is not None:
                self._state.update_history(history_id)
                time.sleep(self._settings.mission_start_grace_seconds)
                self._recorder.start_session(self.drone_id, history_id)
        if not payload.in_mission:
            self._close_recording_if_needed()
        self._reconcile()

    def on_mission_event(self, event: MissionEvent) -> None:
        LOGGER.info(
            "mission event received",
            extra={
                "context": {
                    "event": event.event,
                    "history_id": event.history_id,
                    "message": event.message,
                }
            },
        )
        if event.history_id is not None:
            self._state.update_history(event.history_id)
        if event.event in MISSION_START_EVENTS and event.history_id is not None:
            self._state.update_vehicle(True, True)
            self._recorder.start_session(self.drone_id, event.history_id)
        if event.event in MISSION_STOP_EVENTS:
            self._state.clear_mission()
            self._close_recording_if_needed()
        self._reconcile()

    def current_state(self) -> MissionRuntimeState:
        return self._state.snapshot().runtime_state

    def _reconcile(self) -> None:
        with self._lock:
            if not self._running or self._publisher is None:
                return

            self._mediamtx.ensure_running()
            snapshot = self._state.snapshot()
            if snapshot.runtime_state == MissionRuntimeState.DISCONNECTED:
                self._publisher.stop()
                self._state.update_publisher(False)
                return

            profile = StreamProfile.MISSION if snapshot.mission_active else StreamProfile.IDLE
            if profile == StreamProfile.IDLE and not self._settings.idle_stream_enabled:
                self._publisher.stop()
                self._state.update_publisher(False)
                return
            self._publisher.ensure_profile(profile)
            self._state.update_publisher(self._publisher.is_running())

    def _close_recording_if_needed(self) -> None:
        finalized_dir = self._recorder.stop_session()
        if finalized_dir is not None:
            LOGGER.info("mission archive prepared", extra={"context": {"path": str(finalized_dir)}})

    def _resolve_drone_id(self) -> str:
        try:
            response = requests.get(
                f"{self._settings.base_url}/device-context",
                headers=self._settings.headers,
                timeout=self._settings.http_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            drone_id = data.get("resolved_uav_id")
            if drone_id is None:
                raise RuntimeError(f"resolved_uav_id missing in response: {data}")
            return str(drone_id)
        except Exception as exc:
            LOGGER.warning(
                "device context unavailable, using subscribe_uav_id fallback",
                extra={"context": {"error": str(exc), "fallback_uav_id": self._settings.subscribe_uav_id}},
            )
            return str(self._settings.subscribe_uav_id)

    def _fetch_active_history_id(self) -> int | None:
        try:
            response = requests.get(
                f"{self._settings.base_url}/mission/current",
                headers=self._settings.headers,
                timeout=self._settings.http_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("has_active_mission"):
                return None
            history_id = data.get("mission_history_id") or data.get("history_id")
            return int(history_id) if history_id is not None else None
        except Exception as exc:
            LOGGER.warning("failed to fetch active mission", extra={"context": {"error": str(exc)}})
            return None


def build_ws_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "", "", "", ""))
