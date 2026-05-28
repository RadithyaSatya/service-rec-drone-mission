from __future__ import annotations

from app.utils.retry import Backoff


def default_backoff() -> Backoff:
    return Backoff(initial_seconds=1, maximum_seconds=10)
