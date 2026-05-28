from __future__ import annotations

from enum import Enum


class MissionRuntimeState(str, Enum):
    IDLE = "IDLE"
    CONNECTED = "CONNECTED"
    STREAMING = "STREAMING"
    RECORDING = "RECORDING"
    DISCONNECTED = "DISCONNECTED"


class VideoCodec(str, Enum):
    COPY = "copy"
    LIBX264 = "libx264"


class StreamProfile(str, Enum):
    IDLE = "idle"
    MISSION = "mission"
