from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Backoff:
    initial_seconds: float
    maximum_seconds: float
    multiplier: float = 2.0

    def __post_init__(self) -> None:
        self._current = self.initial_seconds

    def sleep(self) -> None:
        time.sleep(self._current)
        self._current = min(self.maximum_seconds, self._current * self.multiplier)

    def reset(self) -> None:
        self._current = self.initial_seconds
