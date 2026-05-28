from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TelemetryEnvelope:
    uav_id: int | None
    kind: str | None
    metric: str | None
    payload: dict[str, Any]


@dataclass(slots=True)
class VehicleState:
    connected: bool
    armed: bool | None
    mode: str | None
    landed_state: str | None
    in_mission: bool
    flight_speed: float | None


@dataclass(slots=True)
class MissionEvent:
    event: str | None
    history_id: int | None
    message: str | None
    schedule_time: str | None
