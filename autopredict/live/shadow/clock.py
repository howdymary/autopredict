"""Injectable UTC clocks for live polling and deterministic replay."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from .contracts import utc_text


class ShadowClock(Protocol):
    def now(self) -> datetime: ...


class SystemUTCClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class ReplayClock:
    def __init__(self, initial: datetime) -> None:
        utc_text(initial)
        self._now = initial

    def now(self) -> datetime:
        return self._now

    def advance_to(self, value: datetime) -> None:
        utc_text(value)
        if value < self._now:
            raise ValueError("replay clock cannot move backwards")
        self._now = value
