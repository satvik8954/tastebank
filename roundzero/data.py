"""Synthetic client data (data/clients/*.yaml) and its conversion to Hindsight memories.

Each client quote becomes ONE memory with its own document_id, so any fact Hindsight
extracts from it (and any observation built on that fact) can be traced back to the exact
quote, author, project and date. That is what the review UI shows as evidence.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import cache
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from .config import CLIENTS_DIR

Phase = Literal["base", "rebrand"]


class Contact(BaseModel):
    name: str
    role: str


class Feedback(BaseModel):
    by: str
    quote: str


class Round(BaseModel):
    date: date
    draft: str
    approved: bool = False
    feedback: list[Feedback]


class Project(BaseModel):
    id: str
    name: str
    format: str
    brief: str
    phase: Phase = "base"
    reviewed_with_round_zero: bool = False
    rounds: list[Round]

    @property
    def revision_rounds(self) -> int:
        return len(self.rounds)

    @property
    def started(self) -> date:
        return self.rounds[0].date


class Event(BaseModel):
    id: str
    date: datetime
    by: str
    kind: str = "brief"
    phase: Phase = "base"
    text: str


class Directive(BaseModel):
    name: str
    content: str
    priority: int = 0


class BankConfig(BaseModel):
    mission: str
    disposition: dict[str, int]
    directives: list[Directive] = Field(default_factory=list)


class Client(BaseModel):
    id: str
    name: str
    industry: str
    contacts: list[Contact]
    brand: dict
    brand_after_rebrand: dict | None = None
    bank: BankConfig
    events: list[Event] = Field(default_factory=list)
    projects: list[Project]

    def role_of(self, person: str) -> str:
        return next((c.role for c in self.contacts if c.name == person), "client")

    @property
    def phases(self) -> list[Phase]:
        seen = {p.phase for p in self.projects} | {e.phase for e in self.events}
        return [p for p in ("base", "rebrand") if p in seen]


class MemoryItem(BaseModel):
    """One retain() call. `document_id` doubles as the citation key."""

    document_id: str
    client_id: str
    project_id: str | None
    phase: Phase
    timestamp: datetime
    content: str
    context: str
    tags: list[str]
    metadata: dict[str, str]

    @property
    def observation_scopes(self) -> list[list[str]]:
        # Hindsight's default ("combined") consolidates only among memories with the exact
        # same tag set, which would silo every project. All of a client's feedback must feed
        # one taste profile, so observations are scoped to the client tag alone. Project and
        # phase tags stay on the facts for recall filtering.
        return [[f"client:{self.client_id}"]]


@cache
def load_clients() -> dict[str, Client]:
    clients = {}
    for path in sorted(CLIENTS_DIR.glob("*.yaml")):
        client = Client.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        clients[client.id] = client
    return clients


def get_client(client_id: str) -> Client:
    try:
        return load_clients()[client_id]
    except KeyError:
        raise KeyError(f"Unknown client '{client_id}'. Known: {', '.join(load_clients())}") from None


def memory_items(client: Client, phases: set[Phase] | None = None) -> list[MemoryItem]:
    """All memories for a client, oldest first. Retain in this order."""
    items: list[MemoryItem] = []

    for ev in client.events:
        items.append(
            MemoryItem(
                document_id=ev.id,
                client_id=client.id,
                project_id=None,
                phase=ev.phase,
                timestamp=ev.date,
                content=ev.text,
                context=f"{ev.kind} from {client.name}",
                tags=[f"client:{client.id}", f"phase:{ev.phase}", f"kind:{ev.kind}"],
                metadata={
                    "kind": ev.kind,
                    "author": ev.by,
                    "role": client.role_of(ev.by),
                    "date": ev.date.date().isoformat(),
                    "quote": ev.text,
                },
            )
        )

    for proj in client.projects:
        n_rounds = len(proj.rounds)
        for r_idx, rnd in enumerate(proj.rounds, start=1):
            for f_idx, fb in enumerate(rnd.feedback):
                role = client.role_of(fb.by)
                # Feedback lands mid-afternoon, a few minutes apart, so ordering is stable.
                ts = datetime.combine(rnd.date, time(14, 0)) + timedelta(minutes=7 * f_idx)
                outcome = f"\nOutcome: approved at round {r_idx} of {n_rounds}." if rnd.approved else ""
                content = (
                    f"[{rnd.date.isoformat()}] {fb.by} ({role}, {client.name}) gave feedback on "
                    f'round {r_idx} of the project "{proj.name}" ({proj.format.replace("_", " ")}).\n'
                    f"Draft shown: {rnd.draft.strip()}\n"
                    f'Feedback: "{fb.quote.strip()}"{outcome}'
                )
                items.append(
                    MemoryItem(
                        document_id=f"{proj.id}-r{r_idx}-{f_idx}",
                        client_id=client.id,
                        project_id=proj.id,
                        phase=proj.phase,
                        timestamp=ts,
                        content=content,
                        context=f"client feedback on a design draft for {client.name}",
                        tags=[
                            f"client:{client.id}",
                            f"project:{proj.id}",
                            f"phase:{proj.phase}",
                            "kind:feedback",
                        ],
                        metadata={
                            "kind": "feedback",
                            "project_id": proj.id,
                            "project_name": proj.name,
                            "round": str(r_idx),
                            "author": fb.by,
                            "role": role,
                            "date": rnd.date.isoformat(),
                            "quote": fb.quote.strip(),
                            "approved": str(rnd.approved).lower(),
                        },
                    )
                )

    if phases is not None:
        items = [i for i in items if i.phase in phases]
    return sorted(items, key=lambda i: i.timestamp)


def citation_index() -> dict[str, MemoryItem]:
    """document_id -> source item, across all clients. Used to render evidence cards."""
    return {
        item.document_id: item
        for client in load_clients().values()
        for item in memory_items(client)
    }
