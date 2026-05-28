from __future__ import annotations

import json
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path

from app.config.settings import Settings
from app.utils.logger import get_logger
from app.utils.time import format_utc_path, utcnow

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class RecordingSession:
    history_id: int
    drone_id: str
    path_name: str
    started_at_epoch: float


class Recorder:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.RLock()
        self._active: RecordingSession | None = None

    def start_session(self, drone_id: str, history_id: int) -> None:
        with self._lock:
            if self._active and self._active.history_id == history_id:
                return
            self._active = RecordingSession(
                history_id=history_id,
                drone_id=drone_id,
                path_name=self._settings.stream_name_template.format(drone_id=drone_id).lstrip("/"),
                started_at_epoch=utcnow().timestamp(),
            )
            LOGGER.info(
                "recording session started",
                extra={"context": {"history_id": history_id, "drone_id": drone_id}},
            )

    def stop_session(self) -> Path | None:
        with self._lock:
            session = self._active
            self._active = None
        if session is None:
            return None
        finished_at = utcnow()
        target_dir = self._mission_dir(session.drone_id, session.history_id, finished_at)
        target_dir.mkdir(parents=True, exist_ok=True)
        self._materialize_segments(session, finished_at.timestamp(), target_dir)
        self._write_manifest(session, target_dir, finished_at.timestamp())
        LOGGER.info(
            "recording session finalized",
            extra={"context": {"history_id": session.history_id, "target_dir": str(target_dir)}},
        )
        return target_dir

    def active_history_id(self) -> int | None:
        with self._lock:
            return None if self._active is None else self._active.history_id

    def _materialize_segments(self, session: RecordingSession, end_epoch: float, target_dir: Path) -> None:
        source_root = Path(self._settings.raw_records_dir) / session.path_name
        if not source_root.exists():
            LOGGER.warning("raw recording path not found", extra={"context": {"path": str(source_root)}})
            return

        start_epoch = session.started_at_epoch - self._settings.record_segment_grace_seconds
        end_epoch = end_epoch + self._settings.record_segment_grace_seconds
        for source in sorted(source_root.rglob("*.mp4")):
            stat = source.stat()
            if stat.st_mtime < start_epoch or stat.st_mtime > end_epoch:
                continue
            target = target_dir / source.name
            if target.exists():
                continue
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)

    def _write_manifest(self, session: RecordingSession, target_dir: Path, end_epoch: float) -> None:
        manifest = {
            "history_id": session.history_id,
            "drone_id": session.drone_id,
            "path_name": session.path_name,
            "started_at_epoch": session.started_at_epoch,
            "finished_at_epoch": end_epoch,
        }
        (target_dir / "mission.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _mission_dir(self, drone_id: str, history_id: int, finished_at) -> Path:
        year, month, _ = format_utc_path(finished_at)
        return Path(self._settings.records_dir) / f"drone_{drone_id}" / year / month / f"mission_{history_id}"
