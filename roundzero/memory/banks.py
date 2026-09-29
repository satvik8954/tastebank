"""Per-client memory bank setup: mission, retain/observation/reflect missions,
disposition, and directives. Safe to re-run: create_bank is an upsert (PUT) and
directives are replaced wholesale.
"""

from __future__ import annotations

from ..config import AGENCY_NAME
from ..data import Client, Directive
from .client import hindsight

# Shape what Hindsight extracts at retain() time.
RETAIN_MISSION = (
    "Extract the client's design preferences, dislikes, rules and approvals: colours (keep hex "
    "values), typography, layout and composition, imagery and photography, copy tone and exact "
    "wording, and legal/compliance requirements. Record who said it, their role, the project "
    "name and the date. Note when a new statement contradicts or reverses an earlier one. "
    "Ignore scheduling and pleasantries."
)

# Shape the auto-consolidated observations, i.e. the client's taste profile.
OBSERVATION_TOPICS = ("Colour", "Typography", "Layout", "Imagery", "Copy", "Compliance")

OBSERVATIONS_MISSION = (
    "Observations are this client's taste profile: reusable rules for future design drafts, "
    "each backed by the client feedback that supports it. Each observation covers exactly ONE "
    "topic and starts with that topic in square brackets: "
    + ", ".join(f"[{t}]" for t in OBSERVATION_TOPICS)
    + ". Never combine topics; e.g. a colour palette rule and a copy-wording rule are separate "
    "observations. Within a topic, keep distinct rules separate rather than one catch-all. "
    "When newer feedback reverses an older preference (for example after a rebrand), UPDATE "
    "the existing observation in place rather than deleting it and creating a new one: state "
    "the CURRENT rule first, then what it replaced and since when. Rules that the new feedback "
    "does not contradict must survive unchanged. Record disagreements between client "
    "stakeholders and how they were resolved. Do not create observations that only describe a "
    "single draft, round or approval; use those as evidence for the rule they support."
)

REFLECT_MISSION = (
    f"You review design drafts for {AGENCY_NAME} before they are sent to this client. Predict "
    "the feedback the client would give. Every issue must be grounded in specific past client "
    "feedback; cite it. Apply the client's CURRENT preferences; older, superseded preferences "
    "must not be raised as issues."
)

# Directives applied to every client bank (hard rules for reflect()).
GLOBAL_DIRECTIVES = [
    Directive(
        name="Evidence required",
        content=(
            "Only raise an issue if retrieved client feedback supports it, or a directive "
            "requires it. Never invent client preferences."
        ),
        priority=20,
    ),
    Directive(
        name="Most recent direction wins",
        content=(
            "When client feedback conflicts over time, the most recent statement wins. Mention "
            "the older, conflicting feedback only as context, never as a requirement."
        ),
        priority=20,
    ),
]


def configure_bank(client: Client, bank_id: str) -> None:
    hs = hindsight()
    d = client.bank.disposition
    hs.create_bank(
        bank_id=bank_id,
        name=f"{client.name} (Round Zero)",
        mission=client.bank.mission,
        disposition_skepticism=d.get("skepticism"),
        disposition_literalism=d.get("literalism"),
        disposition_empathy=d.get("empathy"),
        retain_mission=RETAIN_MISSION,
        observations_mission=OBSERVATIONS_MISSION,
        reflect_mission=REFLECT_MISSION,
        enable_observations=True,
    )
    hs.update_bank_config(bank_id, enable_auto_consolidation=True)
    sync_directives(bank_id, GLOBAL_DIRECTIVES + client.bank.directives)


def sync_directives(bank_id: str, directives: list[Directive]) -> None:
    hs = hindsight()
    for existing in hs.list_directives(bank_id=bank_id, limit=200).items:
        hs.delete_directive(bank_id=bank_id, directive_id=existing.id)
    for d in directives:
        hs.create_directive(bank_id=bank_id, name=d.name, content=d.content, priority=d.priority)
