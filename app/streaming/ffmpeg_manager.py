from __future__ import annotations

import threading

from app.config.constants import StreamProfile, VideoCodec
from app.config.settings import Settings
from app.utils.logger import get_logger
from app.utils.process import ManagedProcess, ProcessSpec

LOGGER = get_logger(__name__)


class FFmpegManager:
    def __init__(self, settings: Settings, drone_id: str) -> None:
        self._settings = settings
        self._drone_id = drone_id
        self._lock = threading.RLock()
        self._profile: StreamProfile | None = None
        self._publish_url: str | None = None
        self._process: ManagedProcess | None = None

    def ensure_profile(self, profile: StreamProfile) -> None:
        publish_url = self._settings.mediamtx_publish_url(self._drone_id)
        with self._lock:
            should_restart = (
                self._process is None
                or not self._process.is_running()
                or self._profile != profile
                or self._publish_url != publish_url
            )
            if not should_restart:
                return

            self._stop_locked()
            spec = ProcessSpec(
                name="ffmpeg-publisher",
                command=self._build_command(publish_url),
                stdout_path=f"{self._settings.logs_dir}/ffmpeg.stdout.log",
                stderr_path=f"{self._settings.logs_dir}/ffmpeg.stderr.log",
            )
            self._process = ManagedProcess(spec)
            self._process.start()
            self._profile = profile
            self._publish_url = publish_url

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.is_running()

    def exit_code(self) -> int | None:
        with self._lock:
            return None if self._process is None else self._process.exit_code()

    def _stop_locked(self) -> None:
        if self._process is not None:
            self._process.stop()
        self._process = None
        self._profile = None
        self._publish_url = None

    def _build_command(self, publish_url: str) -> list[str]:
        command = [self._settings.ffmpeg_binary, "-hide_banner", "-loglevel", self._settings.ffmpeg_loglevel]
        command.extend(self._build_input_args())
        command.extend(self._build_video_args())
        command.extend(
            [
                "-an",
                "-f",
                "rtsp",
                "-rtsp_transport",
                self._settings.ffmpeg_transport,
                publish_url,
            ]
        )
        return command

    def _build_input_args(self) -> list[str]:
        return [
            "-rtsp_transport",
            self._settings.ffmpeg_transport,
            "-rw_timeout",
            "5000000",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-i",
            self._settings.rtsp_url,
        ]

    def _build_video_args(self) -> list[str]:
        if self._settings.ffmpeg_codec == VideoCodec.COPY:
            return ["-map", "0:v:0", "-c:v", "copy"]

        return [
            "-map",
            "0:v:0",
            "-vf",
            "format=yuv420p",
            "-c:v",
            "libx264",
            "-profile:v",
            self._settings.ffmpeg_profile,
            "-level:v",
            self._settings.ffmpeg_level,
            "-preset",
            self._settings.ffmpeg_preset,
            "-tune",
            self._settings.ffmpeg_tune,
            "-g",
            str(self._settings.ffmpeg_gop),
            "-keyint_min",
            str(self._settings.ffmpeg_gop),
            "-sc_threshold",
            "0",
            "-bf",
            "0",
            "-b:v",
            self._settings.ffmpeg_bitrate,
            "-maxrate",
            self._settings.ffmpeg_maxrate,
            "-bufsize",
            self._settings.ffmpeg_bufsize,
        ]
