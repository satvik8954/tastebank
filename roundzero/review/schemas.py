"""Review data model.

`ReviewOutput` is what the model must produce (validated). `Review` is what the app shows:
every flag resolved to real client quotes with author, project and date.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..memory.banks import OBSERVATION_TOPICS

Severity = Literal["high", "medium", "low"]


def _lower(v):
    return v.lower().strip() if isinstance(v, str) else v


def _ids(v) -> list[str]:
    """Accept ["F1","O2"], "F1, O2" or ["[F1]"] from the model."""
    if isinstance(v, str):
        v = v.replace(";", ",").split(",")
    return [str(x).strip().strip("[]") for x in (v or []) if str(x).strip()]


class Flag(BaseModel):
    severity: Severity
    topic: str
    issue: str
    suggestion: str
    evidence: list[str] = Field(default_factory=list)  # evidence ids like "F3", "O1"
    directive: str | None = None  # name of a directive, when the flag comes from a hard rule

    @field_validator("severity", mode="before")
    @classmethod
    def _lower(cls, v):
        return _lower(v)

    @field_validator("evidence", mode="before")
    @classmethod
    def _ids(cls, v):
        return _ids(v)

    @field_validator("directive", mode="before")
    @classmethod
    def _empty_directive(cls, v):
        return v or None


class ReviewOutput(BaseModel):
    verdict: Literal["ready_for_client", "needs_changes"]
    summary: str
    flags: list[Flag] = Field(default_factory=list)


# Hand-written (no $ref/$defs) so it works as a Hindsight reflect response_schema and in prompts.
REVIEW_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["ready_for_client", "needs_changes"]},
        "summary": {"type": "string", "description": "One or two sentences for the designer."},
        "flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "topic": {"type": "string", "enum": list(OBSERVATION_TOPICS)},
                    "issue": {"type": "string", "description": "What in THIS draft the client would object to."},
                    "suggestion": {"type": "string", "description": "Concrete fix."},
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Evidence ids (e.g. F12, O3) from the provided list that justify this flag.",
                    },
                    "directive": {
                        "type": "string",
                        "description": "Name of the directive this flag enforces, if any; otherwise empty.",
                    },
                },
                "required": ["severity", "topic", "issue", "suggestion", "evidence"],
            },
        },
    },
    "required": ["verdict", "summary", "flags"],
}


class Citation(BaseModel):
    """One real client statement, as shown on a flag card."""

    document_id: str
    quote: str
    author: str
    role: str
    date: str
    project_name: str | None = None
    round: str | None = None
    kind: str = "feedback"


class Evidence(BaseModel):
    id: str  # F# = client statement, O# = taste-profile observation
    kind: Literal["feedback", "observation"]
    text: str  # what memory holds (extracted fact(s) or observation text)
    citation: Citation | None = None
    source_ids: list[str] = Field(default_factory=list)  # O#: the F# it is built from

    def render(self) -> str:
        if self.citation:
            c = self.citation
            where = f'"{c.project_name}" round {c.round}' if c.project_name else c.kind
            return f'[{self.id}] {c.date} · {c.author} ({c.role}) · {where}: "{c.quote}"'
        src = f" (built from {', '.join(self.source_ids)})" if self.source_ids else ""
        return f"[{self.id}] taste-profile observation{src}: {self.text}"


class FlagCheck(BaseModel):
    """Verifier's decision on one proposed flag."""

    index: int
    keep: bool
    severity: Severity
    evidence: list[str] = Field(default_factory=list)
    reason: str = ""
    failed: str | None = None  # which criterion failed: "a" | "b" | "c" | "d"

    @field_validator("severity", "failed", mode="before")
    @classmethod
    def _lower(cls, v):
        return _lower(v) or None if isinstance(v, str) else v

    @field_validator("evidence", mode="before")
    @classmethod
    def _ids(cls, v):
        return _ids(v)


class Verification(BaseModel):
    checks: list[FlagCheck]


class DiscardedFlag(BaseModel):
    flag: Flag
    reason: str


class ResolvedFlag(Flag):
    citations: list[Citation] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)


class Review(BaseModel):
    client_id: str
    bank_id: str | None
    memory: bool
    engine: str
    verdict: str
    summary: str
    flags: list[ResolvedFlag]
    discarded: list[DiscardedFlag] = Field(default_factory=list)  # proposed but not grounded
    evidence: list[Evidence] = Field(default_factory=list)
    memories_consulted: int = 0
    timings: dict[str, float] = Field(default_factory=dict)  # seconds per stage
    elapsed_s: float = 0.0

    @property
    def blocking(self) -> list[ResolvedFlag]:
        return [f for f in self.flags if f.severity in ("high", "medium")]
