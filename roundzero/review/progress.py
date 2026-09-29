"""Progress events for a running review, so the UI can show memory at work during the wait.

The reviewer calls `progress.event(...)`; whoever started the review passes an `emit`
callback (the API turns events into server-sent events; the CLI prints them). Each stage is
also timed, and the timings end up on the Review.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel, Field


class ReviewEvent(BaseModel):
    stage: str  # extract | recall | evidence | reflect | verify | done | error
    status: str  # start | progress | done
    message: str  # human-readable, shown as-is in the UI
    data: dict[str, Any] = Field(default_factory=dict)
    t: float  # seconds since the review started


Emit = Callable[[ReviewEvent], None]


class Progress:
    def __init__(self, emit: Emit | None = None):
        self._emit = emit
        self._t0 = time.monotonic()
        self.timings: dict[str, float] = {}

    def elapsed(self) -> float:
        return round(time.monotonic() - self._t0, 2)

    def event(self, stage: str, status: str, message: str, **data: Any) -> None:
        if self._emit:
            self._emit(ReviewEvent(stage=stage, status=status, message=message, data=data, t=self.elapsed()))

    @contextmanager
    def timed(self, stage: str) -> Iterator[None]:
        start = time.monotonic()
        try:
            yield
        finally:
            self.timings[stage] = round(self.timings.get(stage, 0) + time.monotonic() - start, 2)
