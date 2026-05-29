from __future__ import annotations

import os
import signal
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from app.utils.logger import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class ProcessSpec:
    name: str
    command: list[str]
    stdout_path: str | None = None
    stderr_path: str | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None


class ManagedProcess:
    def __init__(self, spec: ProcessSpec) -> None:
        self._spec = spec
        self._lock = threading.RLock()
        self._process: subprocess.Popen[bytes] | None = None
        self._stdout_handle = None
        self._stderr_handle = None

    @property
    def pid(self) -> int | None:
        with self._lock:
            return None if self._process is None else self._process.pid

    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def exit_code(self) -> int | None:
        with self._lock:
            return None if self._process is None else self._process.poll()

    def start(self) -> None:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return

            self._open_logs()
            LOGGER.info(
                "starting process",
                extra={"context": {"process": self._spec.name, "command": self._spec.command}},
            )
            self._process = subprocess.Popen(
                self._spec.command,
                cwd=self._spec.cwd,
                env=self._merged_env(),
                stdout=self._stdout_handle or subprocess.DEVNULL,
                stderr=self._stderr_handle or subprocess.DEVNULL,
                preexec_fn=os.setsid if os.name != "nt" else None,
            )

    def stop(self, kill_after_seconds: float = 10.0) -> None:
        with self._lock:
            process = self._process
            self._process = None
        if process is None:
            self._close_logs()
            return

        LOGGER.info("stopping process", extra={"context": {"process": self._spec.name, "pid": process.pid}})
        try:
            if process.poll() is not None:
                return
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    return
            else:
                process.terminate()
            process.wait(timeout=kill_after_seconds)
        except subprocess.TimeoutExpired:
            LOGGER.warning(
                "forcing process kill",
                extra={"context": {"process": self._spec.name, "pid": process.pid}},
            )
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    return
            else:
                process.kill()
            process.wait(timeout=5)
        finally:
            self._close_logs()

    def poll(self) -> int | None:
        with self._lock:
            return None if self._process is None else self._process.poll()

    def _open_logs(self) -> None:
        self._close_logs()
        if self._spec.stdout_path:
            Path(self._spec.stdout_path).parent.mkdir(parents=True, exist_ok=True)
            self._stdout_handle = open(self._spec.stdout_path, "ab")
        if self._spec.stderr_path:
            Path(self._spec.stderr_path).parent.mkdir(parents=True, exist_ok=True)
            self._stderr_handle = open(self._spec.stderr_path, "ab")

    def _close_logs(self) -> None:
        for handle_name in ("_stdout_handle", "_stderr_handle"):
            handle = getattr(self, handle_name)
            if handle is not None:
                handle.close()
                setattr(self, handle_name, None)

    def _merged_env(self) -> dict[str, str]:
        merged = os.environ.copy()
        if self._spec.env:
            merged.update(self._spec.env)
        return merged
