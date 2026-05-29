from __future__ import annotations

import os
import threading
from pathlib import Path

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
        self._record_path: str | None = None
        self._process: ManagedProcess | None = None

    def ensure_profile(self, profile: StreamProfile, record_path: str | None = None) -> None:
        with self._lock:
            restart_reason = self._restart_reason(profile, record_path)
            should_restart = (
                self._process is None
                or not self._process.is_running()
                or self._profile != profile
                or self._record_path != record_path
            )
            if not should_restart:
                return

            self._stop_locked()
            self._clear_hls_outputs()
            command = self._build_command(profile, record_path)
            spec = ProcessSpec(
                name="ffmpeg-publisher",
                command=command,
                stdout_path=f"{self._settings.logs_dir}/ffmpeg.stdout.log",
                stderr_path=f"{self._settings.logs_dir}/ffmpeg.stderr.log",
            )
            self._process = ManagedProcess(spec)
            self._process.start()
            self._profile = profile
            self._record_path = record_path
            LOGGER.info(
                "ffmpeg streaming started",
                extra={
                    "context": {
                        "profile": profile.value,
                        "drone_id": self._drone_id,
                        "source_url": self._settings.resolved_rtsp_url,
                        "hls_path": str(self._settings.hls_playlist_path(self._drone_id)),
                        "record_path": record_path,
                        "restart_reason": restart_reason,
                    }
                },
            )

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
            LOGGER.info(
                "ffmpeg publish stopping",
                extra={"context": {"profile": None if self._profile is None else self._profile.value}},
            )
            self._process.stop()
        self._process = None
        self._profile = None
        self._record_path = None

    def _restart_reason(self, profile: StreamProfile, record_path: str | None) -> str:
        if self._process is None:
            return "initial-start"
        if not self._process.is_running():
            return "process-exited"
        if self._profile != profile:
            return f"profile-changed:{self._profile.value if self._profile else 'none'}->{profile.value}"
        if self._record_path != record_path:
            return "record-path-changed"
        return "unchanged"

    def _build_command(self, profile: StreamProfile, record_path: str | None) -> list[str]:
        command = [self._settings.ffmpeg_binary, "-hide_banner", "-loglevel", self._settings.ffmpeg_loglevel]
        command.extend(self._build_input_args())
        command.extend(self._build_video_args())
        command.extend(["-an"])
        if profile == StreamProfile.MISSION and record_path:
            command.extend(self._build_mission_outputs(record_path))
        else:
            command.extend(self._build_hls_output_args())
        return command

    def _build_input_args(self) -> list[str]:
        return [
            "-rtsp_transport",
            self._settings.ffmpeg_transport,
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-i",
            self._settings.resolved_rtsp_url,
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

    def _build_hls_output_args(self) -> list[str]:
        hls_dir = self._settings.hls_output_dir(self._drone_id)
        return [
            "-f",
            "hls",
            "-hls_time",
            str(self._settings.hls_time_seconds),
            "-hls_list_size",
            str(self._settings.hls_list_size),
            "-hls_delete_threshold",
            str(self._settings.hls_delete_threshold),
            "-hls_flags",
            "delete_segments+append_list+omit_endlist+program_date_time+independent_segments",
            "-hls_segment_filename",
            str(hls_dir / "segment_%06d.ts"),
            str(self._settings.hls_playlist_path(self._drone_id)),
        ]

    def _build_mission_outputs(self, record_path: str) -> list[str]:
        hls_args = self._build_hls_output_args()
        hls_target = hls_args[-1]
        hls_segment_pattern = hls_args[-2]
        return [
            "-f",
            "tee",
            (
                "[f=hls"
                f":hls_time={self._settings.hls_time_seconds}"
                f":hls_list_size={self._settings.hls_list_size}"
                f":hls_delete_threshold={self._settings.hls_delete_threshold}"
                ":hls_flags=delete_segments+append_list+omit_endlist+program_date_time+independent_segments"
                f":hls_segment_filename={hls_segment_pattern}]"
                f"{hls_target}"
                f"|[f=mp4:movflags=+faststart]{record_path}"
            ),
        ]

    def _clear_hls_outputs(self) -> None:
        hls_dir = self._settings.hls_output_dir(self._drone_id)
        hls_dir.mkdir(parents=True, exist_ok=True)
        for path in hls_dir.iterdir():
            if path.is_file() and path.suffix in {".m3u8", ".ts", ".tmp"}:
                try:
                    path.unlink()
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    LOGGER.warning(
                        "failed to remove stale hls artifact",
                        extra={"context": {"path": str(path), "error": str(exc)}},
                    )
        playlist = self._settings.hls_playlist_path(self._drone_id)
        if not playlist.exists():
            playlist.touch()
            if os.name != "nt":
                playlist.chmod(0o644)
