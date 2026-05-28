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

    mediamtx_host: str = os.getenv("MEDIAMTX_HOST", "127.0.0.1")
    mediamtx_rtsp_port: int = _int("MEDIAMTX_RTSP_PORT", 8554)
    mediamtx_hls_port: int = _int("MEDIAMTX_HLS_PORT", 8888)
    mediamtx_webrtc_port: int = _int("MEDIAMTX_WEBRTC_PORT", 8889)
    mediamtx_api_port: int = _int("MEDIAMTX_API_PORT", 9997)
    mediamtx_metrics_port: int = _int("MEDIAMTX_METRICS_PORT", 9998)
    mediamtx_managed: bool = _bool("MEDIAMTX_MANAGED", False)
    mediamtx_binary: str = os.getenv("MEDIAMTX_BIN", "mediamtx")
    mediamtx_config_path: str = os.getenv("MEDIAMTX_CONFIG_PATH", "./app/config/mediamtx.yml")
    mediamtx_ready_timeout_seconds: int = _int("MEDIAMTX_READY_TIMEOUT_SECONDS", 30)
    mediamtx_restart_delay_seconds: int = _int("MEDIAMTX_RESTART_DELAY_SECONDS", 3)

    ffmpeg_binary: str = os.getenv("FFMPEG_BIN", "ffmpeg")
    ffprobe_binary: str = os.getenv("FFPROBE_BIN", "ffprobe")
    rtsp_url: str = os.getenv("RTSP_URL", "rtsp://192.168.144.25:8554/main.264")
    stream_name_template: str = os.getenv("STREAM_NAME_TEMPLATE", "uav/{drone_id}/live")
    ffmpeg_codec: VideoCodec = VideoCodec(os.getenv("FFMPEG_CODEC", "copy"))
    ffmpeg_bitrate: str = os.getenv("FFMPEG_BITRATE", "2500k")
    ffmpeg_maxrate: str = os.getenv("FFMPEG_MAXRATE", "3000k")
    ffmpeg_bufsize: str = os.getenv("FFMPEG_BUFSIZE", "5000k")
    ffmpeg_preset: str = os.getenv("FFMPEG_PRESET", "veryfast")
    ffmpeg_tune: str = os.getenv("FFMPEG_TUNE", "zerolatency")
    ffmpeg_gop: int = _int("FFMPEG_GOP", 30)
    ffmpeg_profile: str = os.getenv("FFMPEG_PROFILE", "baseline")
    ffmpeg_level: str = os.getenv("FFMPEG_LEVEL", "3.1")
    ffmpeg_transport: str = os.getenv("FFMPEG_RTSP_TRANSPORT", "tcp")
    ffmpeg_loglevel: str = os.getenv("FFMPEG_LOGLEVEL", "warning")
    publisher_restart_backoff_seconds: int = _int("FORWARD_RESTART_DELAY_SECONDS", 5)
    idle_stream_enabled: bool = _bool("IDLE_STREAM_ENABLED", True)
    mission_start_grace_seconds: float = _float("MISSION_START_GRACE_SECONDS", 1.0)

    records_dir: str = os.getenv("RECORDS_DIR", "./records")
    raw_records_dir: str = os.getenv("RAW_RECORDS_DIR", "./records/_raw")
    hls_dir: str = os.getenv("HLS_DIR", "./hls")
    logs_dir: str = os.getenv("LOGS_DIR", "./logs")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    healthcheck_path: str = os.getenv("HEALTHCHECK_PATH", "./logs/health.json")
    record_segment_grace_seconds: int = _int("RECORD_SEGMENT_GRACE_SECONDS", 3)

    docker_compose_project: str = os.getenv("COMPOSE_PROJECT_NAME", "uav-streaming-system")
    supported_platforms: tuple[str, ...] = field(
        default=("macos", "linux", "raspberry-pi"), init=False
    )

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Device-Token": self.token}

    @property
    def mediamtx_api_url(self) -> str:
        return f"http://{self.mediamtx_host}:{self.mediamtx_api_port}"

    @property
    def mediamtx_metrics_url(self) -> str:
        return f"http://{self.mediamtx_host}:{self.mediamtx_metrics_port}/metrics"

    def mediamtx_publish_url(self, drone_id: str) -> str:
        path = self.stream_name_template.format(drone_id=drone_id).lstrip("/")
        return f"rtsp://{self.mediamtx_host}:{self.mediamtx_rtsp_port}/{path}"

    def mediamtx_hls_url(self, drone_id: str) -> str:
        path = self.stream_name_template.format(drone_id=drone_id).lstrip("/")
        return f"http://{self.mediamtx_host}:{self.mediamtx_hls_port}/{path}/index.m3u8"

    def mediamtx_webrtc_url(self, drone_id: str) -> str:
        path = self.stream_name_template.format(drone_id=drone_id).lstrip("/")
        return f"http://{self.mediamtx_host}:{self.mediamtx_webrtc_port}/{path}/whep"

    def ensure_runtime_dirs(self) -> None:
        for value in (self.records_dir, self.raw_records_dir, self.hls_dir, self.logs_dir):
            Path(value).mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    return Settings()
