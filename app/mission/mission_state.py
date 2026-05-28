from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.config.constants import MissionRuntimeState


@dataclass(slots=True)
class MissionContext:
    runtime_state: MissionRuntimeState = MissionRuntimeState.IDLE
    websocket_connected: bool = False
    vehicle_connected: bool = False
    mission_active: bool = False
    publisher_running: bool = False
    history_id: int | None = None
    last_state_change: datetime | None = None
