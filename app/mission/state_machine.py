from __future__ import annotations

import threading
from dataclasses import asdict

from app.config.constants import MissionRuntimeState
from app.mission.mission_state import MissionContext
from app.utils.logger import get_logger
from app.utils.time import utcnow

LOGGER = get_logger(__name__)


class MissionStateMachine:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._context = MissionContext(last_state_change=utcnow())

    def snapshot(self) -> MissionContext:
        with self._lock:
            return MissionContext(**asdict(self._context))

    def update_websocket(self, connected: bool) -> MissionContext:
        with self._lock:
            self._context.websocket_connected = connected
            self._recompute_locked()
            return self.snapshot()

    def update_vehicle(self, connected: bool, in_mission: bool) -> MissionContext:
        with self._lock:
            self._context.vehicle_connected = connected
            self._context.mission_active = in_mission
            self._recompute_locked()
            return self.snapshot()

    def update_publisher(self, running: bool) -> MissionContext:
        with self._lock:
            self._context.publisher_running = running
            self._recompute_locked()
            return self.snapshot()

    def update_history(self, history_id: int | None) -> MissionContext:
        with self._lock:
            self._context.history_id = history_id
            return self.snapshot()

    def clear_mission(self) -> MissionContext:
        with self._lock:
            self._context.mission_active = False
            self._context.history_id = None
            self._recompute_locked()
            return self.snapshot()

    def _recompute_locked(self) -> None:
        previous = self._context.runtime_state
        if not self._context.websocket_connected or not self._context.vehicle_connected:
            current = MissionRuntimeState.DISCONNECTED
        elif self._context.mission_active and self._context.publisher_running:
            current = MissionRuntimeState.RECORDING
        elif self._context.publisher_running:
            current = MissionRuntimeState.STREAMING
        else:
            current = MissionRuntimeState.CONNECTED

        if previous != current:
            self._context.runtime_state = current
            self._context.last_state_change = utcnow()
            LOGGER.info(
                "mission state changed",
                extra={"context": {"from": previous.value, "to": current.value}},
            )
