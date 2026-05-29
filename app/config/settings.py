from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from app.config.constants import VideoCodec


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def _float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "uav-streaming-system")
    base_url: str = os.getenv("BASE_URL", "http://127.0.0.1:8081")
    token: str = os.getenv("TOKEN", "uav-local-dev-token")
    subscribe_uav_id: int = _int("SUBSCRIBE_UAV_ID", 1)

    ws_timeout_seconds: int = _int("WS_TIMEOUT_SECONDS", 15)
    ws_reconnect_delay_seconds: int = _int("WS_RECONNECT_DELAY_SECONDS", 5)
    ws_heartbeat_seconds: int = _int("WS_HEARTBEAT_SECONDS", 10)
    http_timeout_seconds: int = _int("HTTP_TIMEOUT_SECONDS", 10)
    startup_source_settle_seconds: float = _float("START_DELAY_SECONDS", 1.5)

    ffmpeg_binary: str = os.getenv("FFMPEG_BIN", "ffmpeg")
    ffprobe_binary: str = os.getenv("FFPROBE_BIN", "ffprobe")
    rtsp_url: str = os.getenv("RTSP_URL", "rtsp://192.168.144.25:8554/main.264")
    ffmpeg_codec: VideoCodec = VideoCodec(os.getenv("FFMPEG_CODEC", "copy"))
    ffmpeg_bitrate: str = os.getenv("FFMPEG_BITRATE", "2500k")
    ffmpeg_maxrate: str = os.getenv("FFMPEG_MAXRATE", "3000k")
    ffmpeg_bufsize: str = os.getenv("FFMPEG_BUFSIZE", "5000k")
    ffmpeg_preset: str = os.getenv("FFMPEG_PRESET", "ultrafast")
    ffmpeg_tune: str = os.getenv("FFMPEG_TUNE", "zerolatency")
    ffmpeg_gop: int = _int("FFMPEG_GOP", 30)
    ffmpeg_profile: str = os.getenv("FFMPEG_PROFILE", "baseline")
    ffmpeg_level: str = os.getenv("FFMPEG_LEVEL", "3.1")
    ffmpeg_transport: str = os.getenv("FFMPEG_RTSP_TRANSPORT", "tcp")
    ffmpeg_loglevel: str = os.getenv("FFMPEG_LOGLEVEL", "warning")
    publisher_restart_backoff_seconds: int = _int("FFMPEG_RESTART_DELAY_SECONDS", 5)
    idle_stream_enabled: bool = _bool("IDLE_STREAM_ENABLED", True)
    mission_start_grace_seconds: float = _float("MISSION_START_GRACE_SECONDS", 1.0)
    hls_time_seconds: int = _int("HLS_TIME_SECONDS", 1)
    hls_list_size: int = _int("HLS_LIST_SIZE", 4)
    hls_delete_threshold: int = _int("HLS_DELETE_THRESHOLD", 1)
    server_host: str = os.getenv("SERVER_HOST", "0.0.0.0")
    server_port: int = _int("SERVER_PORT", 8088)
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8088")

    records_dir: str = os.getenv("RECORDS_DIR", "./records")
    hls_dir: str = os.getenv("HLS_DIR", "./hls")
    logs_dir: str = os.getenv("LOGS_DIR", "./logs")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    app_log_path: str = os.getenv("APP_LOG_PATH", "./logs/app.log")

    supported_platforms: tuple[str, ...] = field(
        default=("macos", "linux", "raspberry-pi"), init=False
    )

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Device-Token": self.token}

    @property
    def resolved_base_url(self) -> str:
        return self.base_url

    @property
    def resolved_rtsp_url(self) -> str:
        return self.rtsp_url

    def hls_output_dir(self, drone_id: str) -> Path:
        return Path(self.hls_dir) / "uav" / str(drone_id)

    def hls_playlist_path(self, drone_id: str) -> Path:
        return self.hls_output_dir(drone_id) / "index.m3u8"

    def hls_playlist_url(self, drone_id: str) -> str:
        return f"{self.public_base_url.rstrip('/')}/hls/uav/{drone_id}/index.m3u8"

    @property
    def player_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/player"

    def ensure_runtime_dirs(self) -> None:
        for value in (self.records_dir, self.hls_dir, self.logs_dir):
            Path(value).mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    return Settings()
