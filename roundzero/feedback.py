"""Log a client's real feedback: retain() it into their bank (step 4 of the core loop).

Built exactly like seeded feedback (same metadata, tags and client-scoped observations), so
new feedback is cited and consolidated the same way. Also appended to a local log that feeds
the revision-rounds chart.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timezone

from pydantic import BaseModel, Field

from .config import DATA_DIR
from .data import MemoryItem, get_client, load_clients
from .memory.retain import retain_item

LOG_PATH = DATA_DIR / "logged" / "feedback.jsonl"


class FeedbackIn(BaseModel):
    client_id: str
    project_name: str
    author: str
    quote: str = Field(min_length=3)
    round: int = Field(ge=1)
    date: date
    approved: bool = False
    draft_summary: str = ""
    reviewed_with_round_zero: bool = True


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def project_id_for(client_id: str, project_name: str) -> str:
    client = get_client(client_id)
    existing = next((p.id for p in client.projects if p.name.lower() == project_name.lower()), None)
    return existing or f"{client_id[:2]}-{_slug(project_name)}"


def log_feedback(fb: FeedbackIn, bank_id: str) -> MemoryItem:
    client = get_client(fb.client_id)
    pid = project_id_for(fb.client_id, fb.project_name)
    role = client.role_of(fb.author)
    existing = [e for e in logged_feedback() if e["project_id"] == pid and e["round"] == fb.round]
    doc_id = f"{pid}-r{fb.round}-{len(existing)}-live"
    outcome = f"\nOutcome: approved at round {fb.round}." if fb.approved else ""
    item = MemoryItem(
        document_id=doc_id,
        client_id=client.id,
        project_id=pid,
        phase="base",
        timestamp=datetime.combine(fb.date, time(14, 0)),
        content=(
            f"[{fb.date.isoformat()}] {fb.author} ({role}, {client.name}) gave feedback on round {fb.round} "
            f'of the project "{fb.project_name}".\n'
            + (f"Draft shown: {fb.draft_summary.strip()}\n" if fb.draft_summary.strip() else "")
            + f'Feedback: "{fb.quote.strip()}"{outcome}'
        ),
        context=f"client feedback on a design draft for {client.name}",
        tags=[f"client:{client.id}", f"project:{pid}", "phase:live", "kind:feedback"],
        metadata={
            "kind": "feedback",
            "project_id": pid,
            "project_name": fb.project_name,
            "round": str(fb.round),
            "author": fb.author,
            "role": role,
            "date": fb.date.isoformat(),
            "quote": fb.quote.strip(),
            "approved": str(fb.approved).lower(),
        },
    )
    retain_item(bank_id, item)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**fb.model_dump(mode="json"), "project_id": pid, "bank_id": bank_id,
                            "document_id": doc_id, "logged_at": datetime.now(timezone.utc).isoformat()}) + "\n")
    return item


def logged_feedback() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    return [json.loads(line) for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def project_rounds(client_id: str) -> list[dict]:
    """Revision rounds per project, oldest first: seeded history plus live-logged feedback."""
    client = load_clients()[client_id]
    rows = {
        p.id: {
            "project_id": p.id,
            "name": p.name,
            "format": p.format,
            "phase": p.phase,
            "started": p.started.isoformat(),
            "rounds": p.revision_rounds,
            "approved": p.rounds[-1].approved,
            "reviewed_with_round_zero": p.reviewed_with_round_zero,
            "source": "history",
        }
        for p in client.projects
    }
    for e in logged_feedback():
        if e["client_id"] != client_id:
            continue
        row = rows.setdefault(
            e["project_id"],
            {
                "project_id": e["project_id"], "name": e["project_name"], "format": "", "phase": "live",
                "started": e["date"], "rounds": 0, "approved": False,
                "reviewed_with_round_zero": e["reviewed_with_round_zero"], "source": "logged",
            },
        )
        row["rounds"] = max(row["rounds"], e["round"])
        row["approved"] = row["approved"] or e["approved"]
        row["started"] = min(row["started"], e["date"])
    return sorted(rows.values(), key=lambda r: r["started"])
