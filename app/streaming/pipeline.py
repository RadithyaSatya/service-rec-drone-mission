from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests

from app.config.constants import MissionRuntimeState, StreamProfile
from app.config.settings import Settings
from app.mission.mission_events import MISSION_START_EVENTS, MISSION_STOP_EVENTS
from app.streaming.ffmpeg_manager import FFmpegManager
from app.telemetry.models import MissionEvent, VehicleState
from app.utils.logger import get_logger
from app.utils.time import format_utc_path, utcnow

LOGGER = get_logger(__name__)


class StreamingController:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.RLock()
        self._running = False
        self._drone_id: str | None = None
        self._publisher: FFmpegManager | None = None
        self._ws_connected = False
        self._vehicle_connected = False
        self._mission_active = False
        self._publisher_running = False
        self._history_id: int | None = None
        self._record_path: Path | None = None
        self._record_started_at_epoch: float | None = None
        self._runtime_state = MissionRuntimeState.IDLE
        self._stream_ready: bool | None = None

    @property
    def drone_id(self) -> str:
        if not self._drone_id:
            raise RuntimeError("drone id not resolved yet")
        return self._drone_id

    def start(self) -> None:
        self._settings.ensure_runtime_dirs()
        self._drone_id = self._resolve_drone_id()
        self._publisher = FFmpegManager(self._settings, self._drone_id)
        self._running = True
        LOGGER.info(
            "streaming controller started",
            extra={
                "context": {
                    "drone_id": self._drone_id,
                    "base_url": self._settings.resolved_base_url,
                    "source_url": self._settings.resolved_rtsp_url,
                    "hls_url": self.hls_url(),
                    "player_url": self._settings.player_url,
                }
            },
        )

    def stop(self) -> None:
        with self._lock:
            self._running = False
            if self._publisher:
                self._publisher.stop()
            self._publisher_running = False
            self._stop_recording()
            self._mission_active = False
            self._history_id = None
            self._ws_connected = False
            self._vehicle_connected = False
            self._set_runtime_state()
            self._set_stream_ready(False, reason="controller-stopped")

    def on_websocket_status(self, connected: bool) -> None:
        self._ws_connected = connected
        self._set_runtime_state()
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
        self._vehicle_connected = payload.connected
        if payload.in_mission and not self._mission_active:
            time.sleep(self._settings.mission_start_grace_seconds)
            self._start_recording(self._history_id)
        if not payload.in_mission:
            self._stop_recording()
            self._history_id = None
        self._mission_active = payload.in_mission
        self._set_runtime_state()
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
            self._history_id = event.history_id
        if event.event in MISSION_START_EVENTS:
            self._vehicle_connected = True
            self._mission_active = True
            self._start_recording(event.history_id)
        if event.event in MISSION_STOP_EVENTS:
            self._mission_active = False
            self._stop_recording()
            self._history_id = None
        self._set_runtime_state()
        self._reconcile()

    def current_state(self) -> MissionRuntimeState:
        return self._runtime_state

    def hls_url(self) -> str:
        return self._settings.hls_playlist_url(self.drone_id)

    def hls_path(self) -> Path:
        return self._settings.hls_playlist_path(self.drone_id)

    def tick(self) -> None:
        self._reconcile()

    def _reconcile(self) -> None:
        with self._lock:
            if not self._running or self._publisher is None:
                return

            if not self._ws_connected or not self._vehicle_connected:
                self._publisher.stop()
                self._publisher_running = False
                self._set_runtime_state()
                self._set_stream_ready(False, reason="vehicle-disconnected")
                return

            profile = StreamProfile.MISSION if self._mission_active else StreamProfile.IDLE
            if profile == StreamProfile.IDLE and not self._settings.idle_stream_enabled:
                self._publisher.stop()
                self._publisher_running = False
                self._set_runtime_state()
                self._set_stream_ready(False, reason="idle-stream-disabled")
                return
            self._publisher.ensure_profile(
                profile,
                None if self._record_path is None else str(self._record_path),
            )
            self._publisher_running = self._publisher.is_running()
            self._set_runtime_state()
            if not self._publisher_running:
                self._set_stream_ready(False, reason="publisher-not-running")
                return
            self._set_stream_ready(True, profile=profile)

    def _resolve_drone_id(self) -> str:
        try:
            response = requests.get(
                f"{self._settings.resolved_base_url}/device-context",
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

    def _set_stream_ready(self, ready: bool, profile: StreamProfile | None = None, reason: str | None = None) -> None:
        if self._stream_ready == ready:
            return
        self._stream_ready = ready
        context = {
            "ready": ready,
            "hls_url": self.hls_url(),
            "player_url": self._settings.player_url,
        }
        if profile is not None:
            context["profile"] = profile.value
        if reason is not None:
            context["reason"] = reason
        LOGGER.info("stream status changed", extra={"context": context})

    def _start_recording(self, history_id: int | None) -> None:
        if self._record_path is not None:
            return
        effective_history_id = history_id if history_id is not None else int(utcnow().timestamp())
        self._history_id = effective_history_id
        output_path = self._mission_file(self.drone_id, effective_history_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._record_path = output_path
        self._record_started_at_epoch = utcnow().timestamp()
        LOGGER.info(
            "recording session started",
            extra={"context": {"history_id": effective_history_id, "output_path": str(output_path)}},
        )

    def _stop_recording(self) -> None:
        if self._record_path is None:
            return
        finished_at = utcnow().timestamp()
        manifest = {
            "history_id": self._history_id,
            "drone_id": self.drone_id,
            "output_file": self._record_path.name,
            "started_at_epoch": self._record_started_at_epoch,
            "finished_at_epoch": finished_at,
        }
        self._record_path.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        LOGGER.info("mission recording prepared", extra={"context": {"path": str(self._record_path)}})
        self._record_path = None
        self._record_started_at_epoch = None

    def _mission_file(self, drone_id: str, history_id: int) -> Path:
        now = utcnow()
        year, month, _ = format_utc_path(now)
        mission_dir = Path(self._settings.records_dir) / f"drone_{drone_id}" / year / month
        return mission_dir / f"mission_{history_id}.mp4"

    def _set_runtime_state(self) -> None:
        previous = self._runtime_state
        if not self._ws_connected or not self._vehicle_connected:
            current = MissionRuntimeState.DISCONNECTED
        elif self._mission_active and self._publisher_running:
            current = MissionRuntimeState.RECORDING
        elif self._publisher_running:
            current = MissionRuntimeState.STREAMING
        else:
            current = MissionRuntimeState.CONNECTED
        if current != previous:
            self._runtime_state = current
            LOGGER.info("mission state changed", extra={"context": {"from": previous.value, "to": current.value}})


def build_ws_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "", "", "", ""))
