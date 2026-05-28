from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "context") and isinstance(record.context, dict):
            payload.update(record.context)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(level: str, app_log_path: str | None = None) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(JsonFormatter())

    handlers: list[logging.Handler] = [stdout_handler]
    if app_log_path:
        Path(app_log_path).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(app_log_path, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        handlers.append(file_handler)

    root.handlers[:] = handlers


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
