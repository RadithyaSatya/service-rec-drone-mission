from __future__ import annotations

import json
from typing import Any

from app.telemetry.models import MissionEvent, TelemetryEnvelope, VehicleState


def parse_message(raw_message: str) -> TelemetryEnvelope | None:
    try:
        data = json.loads(raw_message)
    except json.JSONDecodeError:
        return None

    message_type = data.get("type")
    if message_type not in (None, "publish"):
        return None

    return TelemetryEnvelope(
        uav_id=data.get("uav_id"),
        kind=data.get("kind"),
        metric=data.get("metric"),
        payload=_as_dict(data.get("payload")),
    )


def parse_vehicle_state(payload: dict[str, Any]) -> VehicleState:
    return VehicleState(
        connected=bool(payload.get("connected")),
        armed=_optional_bool(payload.get("armed")),
        mode=payload.get("mode"),
        landed_state=payload.get("landed_state"),
        in_mission=bool(payload.get("in_mission")),
        flight_speed=_optional_float(payload.get("flight_speed")),
    )


def parse_mission_event(payload: dict[str, Any]) -> MissionEvent:
    history_id = payload.get("history_id")
    return MissionEvent(
        event=payload.get("event"),
        history_id=int(history_id) if history_id is not None else None,
        message=payload.get("message"),
        schedule_time=payload.get("schedule_time"),
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
