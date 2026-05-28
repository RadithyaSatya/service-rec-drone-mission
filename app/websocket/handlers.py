from __future__ import annotations

from app.streaming.pipeline import StreamingController
from app.telemetry.parser import parse_message, parse_mission_event, parse_vehicle_state
from app.utils.logger import get_logger

LOGGER = get_logger(__name__)


class TelemetryMessageRouter:
    def __init__(self, controller: StreamingController) -> None:
        self._controller = controller

    def handle(self, raw_message: str) -> None:
        envelope = parse_message(raw_message)
        if envelope is None:
            LOGGER.debug("ignoring non-publish websocket payload")
            return

        if envelope.metric == "vehicle_state":
            self._controller.on_vehicle_state(parse_vehicle_state(envelope.payload))
            return

        if envelope.metric == "mission_event":
            self._controller.on_mission_event(parse_mission_event(envelope.payload))
