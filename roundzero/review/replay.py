"""Full-review record/replay: the stage fallback.

Every successful live review is recorded (the Review plus its progress events with their
original timing) under data/recordings/, which is committed to the repo. Modes:

  live    run the real pipeline (Hindsight + Groq) and record it          [default]
  replay  play back the recording, events re-emitted at their original pace
  auto    run live; if anything fails, play back the recording instead

Choose with RZ_REVIEW_MODE, or per request from the API/UI (`mode=`). Recordings are keyed
by reviewer version, memory on/off, bank, image content, project and format, so a changed
draft or a different bank never replays a stale review.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ..config import DATA_DIR
from .progress import Emit, ReviewEvent
from .reviewer import review_with_memory, review_without_memory
from .schemas import Review

log = logging.getLogger(__name__)

# The reviewer is frozen for the demo. Bump only on a deliberate behaviour change; that
# invalidates recordings, which must then be re-recorded (scripts/final_check.py).
REVIEWER_VERSION = "1.0"
RECORDINGS_DIR = DATA_DIR / "recordings"

Mode = Literal["live", "replay", "auto"]


class RecordingMissing(LookupError):
    pass


def default_mode() -> Mode:
    mode = os.getenv("RZ_REVIEW_MODE", "live").lower()
    return mode if mode in ("live", "replay", "auto") else "live"  # type: ignore[return-value]


def recording_path(image: str | Path, project: str, fmt: str, memory: bool, bank_id: str | None) -> Path:
    image_sha = hashlib.sha1(Path(image).read_bytes()).hexdigest()
    key = f"{REVIEWER_VERSION}|{'on' if memory else 'off'}|{bank_id or '-'}|{image_sha}|{project}|{fmt}"
    stem = f"{Path(image).stem}__{'on-' + bank_id if memory else 'off'}"
    return RECORDINGS_DIR / f"{stem}__{hashlib.sha1(key.encode()).hexdigest()[:10]}.json"


def has_recording(image: str | Path, project: str, fmt: str, memory: bool, bank_id: str | None) -> bool:
    return recording_path(image, project, fmt, memory, bank_id).exists()


def run_review(
    client_id: str,
    image: str | Path,
    project: str,
    fmt: str,
    *,
    memory: bool,
    bank_id: str | None = None,
    emit: Emit | None = None,
    mode: Mode | None = None,
    replay_speed: float = 1.0,
) -> Review:
    mode = mode or default_mode()
    path = recording_path(image, project, fmt, memory, bank_id)

    if mode == "replay":
        return _replay(path, emit, replay_speed)

    events: list[ReviewEvent] = []

    def record(e: ReviewEvent) -> None:
        events.append(e)
        if emit:
            emit(e)

    try:
        if memory:
            review = review_with_memory(client_id, bank_id, image, project, fmt, emit=record)
        else:
            review = review_without_memory(client_id, image, project, fmt, emit=record)
    except Exception as exc:
        if mode == "auto" and path.exists():
            log.warning("live review failed (%s); replaying recording", exc)
            if emit:
                emit(ReviewEvent(stage="error", status="progress", message="Live review failed; showing the recorded review", t=0))
            return _replay(path, emit, replay_speed)
        raise

    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "reviewer_version": REVIEWER_VERSION,
                "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "review": review.model_dump(mode="json"),
                "events": [e.model_dump(mode="json") for e in events],
            },
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return review


def _replay(path: Path, emit: Emit | None, speed: float) -> Review:
    if not path.exists():
        raise RecordingMissing(f"No recording at {path.name}; run it live once to record it")
    data = json.loads(path.read_text(encoding="utf-8"))
    last_t = 0.0
    for raw in data["events"]:
        event = ReviewEvent.model_validate(raw)
        if speed > 0:
            time.sleep(max(0.0, event.t - last_t) / speed)
        last_t = event.t
        if emit:
            emit(event)
    review = Review.model_validate(data["review"])
    return review.model_copy(update={"source": "replay", "recorded_at": data.get("recorded_at")})
