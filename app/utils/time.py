from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def format_utc_path(dt: datetime) -> tuple[str, str, str]:
    return dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")
