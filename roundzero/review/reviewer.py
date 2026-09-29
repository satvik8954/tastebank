"""Pre-client review of a design draft.

Memory ON  (engine "hindsight-reflect"):
  1. recall() per draft aspect -> numbered, dated evidence of real client quotes (evidence.py)
  2. reflect() on the client's bank with that evidence as context and a response_schema.
     reflect applies the bank's mission, directives and disposition and can search the
     bank itself; our schema forces every flag to cite evidence ids.
  3. Verify (Groq, temperature 0): each proposed flag is checked against the draft and the
     dated evidence: is the problem really there, does it contradict a specific client
     instruction, is that instruction still current, does it apply to this kind of asset?
     The verifier also fills in evidence ids reflect left out. Rejected flags are kept in
     `discarded` with a reason.
  4. Resolve ids to real quotes (author, project, date); drop anything still unbacked.
  If reflect fails or returns invalid output twice, the same prompt + evidence goes to Groq.

Memory OFF (engine "groq-no-memory"): same draft description, same schema, only the client's
name and industry. This is what a reviewer without Hindsight would say.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from pydantic import ValidationError

from ..config import DATA_DIR
from ..data import Client, get_client
from ..extract.draft import DraftAnalysis, analyse_draft, cache_path
from ..llm import LLMError, complete_json
from ..memory.banks import GLOBAL_DIRECTIVES
from ..memory.client import hindsight
from .evidence import gather_evidence
from .progress import Emit, Progress
from .schemas import (
    REVIEW_JSON_SCHEMA,
    DiscardedFlag,
    Evidence,
    Flag,
    ResolvedFlag,
    Review,
    ReviewOutput,
    Verification,
)

log = logging.getLogger(__name__)

RULES = """Rules:
- Only raise an issue that the evidence above supports, or that a directive requires. Cite the
  evidence ids for every issue. Never invent client preferences.
- Apply the client's CURRENT preferences. When evidence conflicts, the most recent dated
  statement wins; older, superseded preferences are NOT issues.
- Something the client has explicitly approved before is not an issue unless newer feedback
  reversed it.
- Judge only what is actually in the draft description. Do NOT flag a preference the draft
  already satisfies (e.g. the rule is "product off-center" and the product is off-center).
  When unsure whether the draft violates a rule, do not flag it.
- Text printed on the product packaging is part of the product, not on-image copy.
- severity: high = the client would reject the draft; medium = they would ask for a change;
  low = polish. Use high or medium ONLY when the draft directly contradicts a specific
  instruction the client gave. Extrapolations and general improvement ideas are low at most.
- Musings, open questions and passing remarks ("something to talk about") are not rules.
- A rule stated for a specific medium or format (e.g. photography styling, out-of-home posters,
  carousels) applies only to that medium or format.
- If nothing in the draft conflicts with current preferences or directives, return verdict
  "ready_for_client" with an empty flags list."""


def _draft_block(project: str, fmt: str, analysis: DraftAnalysis) -> str:
    return f'DRAFT: "{project}" ({fmt.replace("_", " ")})\n{analysis.describe()}'


def _memory_prompt(client: Client, project: str, fmt: str, analysis: DraftAnalysis, evidence: list[Evidence]) -> tuple[str, str]:
    query = (
        f"Review this design draft for {client.name} before it is sent to them, and predict the "
        f"feedback they would give.\n\n{_draft_block(project, fmt, analysis)}\n\n{RULES}"
    )
    context = (
        "EVIDENCE: what this client has actually said, retrieved from memory, oldest first. "
        "Cite by id.\n" + "\n".join(e.render() for e in evidence)
    )
    return query, context


def _schema_instructions() -> str:
    return "Respond with a JSON object matching this JSON Schema:\n" + json.dumps(REVIEW_JSON_SCHEMA)


REFLECT_CACHE = DATA_DIR / "generated" / "reflect"


def _reflect(bank_id: str, query: str, context: str) -> tuple[ReviewOutput, int]:
    """reflect() with a record/replay cache. Every successful output is recorded; with
    RZ_REPLAY_REFLECT=1 a recorded output for the same bank + prompt is replayed, so
    downstream changes (verifier, resolver, UI) can be tested without Cloud reflect calls."""
    key = hashlib.sha1(f"{bank_id}\n{query}\n{context}".encode()).hexdigest()
    cached = REFLECT_CACHE / f"{key}.json"
    if os.getenv("RZ_REPLAY_REFLECT") == "1" and cached.exists():
        data = json.loads(cached.read_text(encoding="utf-8"))
        return ReviewOutput.model_validate(data["output"]), data["consulted"]
    output, consulted = _reflect_live(bank_id, query, context)
    REFLECT_CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps({"output": output.model_dump(), "consulted": consulted}, indent=2), encoding="utf-8")
    return output, consulted


def _reflect_live(bank_id: str, query: str, context: str) -> tuple[ReviewOutput, int]:
    last: Exception | None = None
    for attempt in range(2):
        resp = hindsight().reflect(
            bank_id=bank_id,
            query=query,
            context=context,
            budget="mid",
            response_schema=REVIEW_JSON_SCHEMA,
            include_facts=True,
            apply_all_directives=True,
        )
        try:
            if resp.structured_output is None:
                raise ValueError(f"no structured_output ({resp.structured_output_error})")
            consulted = len(resp.based_on.memories or []) if resp.based_on else 0
            return ReviewOutput.model_validate(resp.structured_output), consulted
        except (ValidationError, ValueError) as exc:
            last = exc
            log.warning("reflect attempt %d invalid: %s", attempt + 1, str(exc)[:300])
    raise LLMError(f"reflect returned invalid output twice: {last}")


VERIFY_PROMPT = """You are the verification step of a design pre-review. A reviewer proposed the
flags below for a draft. Check each flag strictly against the draft description and the dated
client evidence. Keep a flag ONLY if all of these hold:
 (a) the problem is actually present in the draft as described (not a misreading);
 (b) at least one evidence item is a specific client instruction the draft contradicts, or a
     listed directive requires it;
 (c) that instruction is not superseded by LATER-dated evidence (the newest statement wins);
 (d) the instruction applies to this kind of asset. Rules about a MEDIUM'S OWN PROPERTIES
     apply only to that medium, even if an observation phrases them generally: photo grading,
     retouching, lighting and film looks apply only to photography, never to a vector
     illustration; out-of-home legibility rules apply only to posters/OOH. Everything else
     (brand palette, typography, layout, product depiction, wording, claims, compliance)
     applies to ALL assets, even if first given on one project.
For kept flags: set `evidence` to the ids that justify it (fill them in if the reviewer left
them out) and set severity: high = client would reject, medium = would ask for a change,
low = polish. For discarded flags give a short reason and the letter of the criterion that
failed.

Return JSON: {"checks": [{"index": <flag index>, "keep": true|false, "severity": "high|medium|low",
"evidence": ["F1", ...], "reason": "...", "failed": "a|b|c|d or empty"}]} with one entry per flag."""

# Medium/format scoping (criterion d) is only honoured for these topics. Brand palette, type,
# wording, claims and compliance rules hold for every asset, and the verifier model has
# proven unreliable at respecting that from the prompt alone.
SCOPE_LIMITABLE_TOPICS = {"imagery", "layout"}


def _verify(
    output: ReviewOutput, draft: str, evidence: list[Evidence], directives: str
) -> tuple[list[Flag], list[DiscardedFlag]]:
    """Ground every proposed flag (Groq, temperature 0). Also repairs missing evidence ids,
    which reflect sometimes omits even though the schema asks for them."""
    if not output.flags:
        return [], []
    flags_block = "\n".join(
        f"[{i}] ({f.severity}) [{f.topic}] {f.issue} | proposed evidence: {', '.join(f.evidence) or 'none'}"
        f"{f' | directive: {f.directive}' if f.directive else ''}"
        for i, f in enumerate(output.flags)
    )
    result = complete_json(
        [
            {"role": "system", "content": VERIFY_PROMPT},
            {
                "role": "user",
                "content": f"{draft}\n\nDIRECTIVES (hard rules):\n{directives}\n\nEVIDENCE (oldest first):\n"
                + "\n".join(e.render() for e in evidence)
                + f"\n\nPROPOSED FLAGS:\n{flags_block}",
            },
        ],
        Verification,
        temperature=0.0,
        attempts=1,  # stage safety: one try on the primary, then the fast fallback model
        timeout=12.0,
    )
    checks = {c.index: c for c in result.checks}
    kept, discarded = [], []
    for i, flag in enumerate(output.flags):
        c = checks.get(i)
        if c is None:  # verifier skipped it: keep as proposed rather than silently lose it
            kept.append(flag)
        elif c.keep:
            kept.append(flag.model_copy(update={"severity": c.severity, "evidence": c.evidence or flag.evidence}))
        elif c.failed == "d" and flag.topic.lower() not in SCOPE_LIMITABLE_TOPICS:
            log.info("overriding scope discard for [%s] %s", flag.topic, flag.issue)
            kept.append(flag.model_copy(update={"evidence": c.evidence or flag.evidence}))
        else:
            discarded.append(DiscardedFlag(flag=flag, reason=c.reason or "not grounded"))
    return kept, discarded


def _resolve(
    flags: list[Flag], evidence: list[Evidence], directive_names: set[str]
) -> tuple[list[ResolvedFlag], list[DiscardedFlag]]:
    by_id = {e.id: e for e in evidence}
    kept, dropped = [], []
    for flag in flags:
        ids = [i for i in flag.evidence if i in by_id]
        directive = flag.directive if flag.directive and flag.directive.lower() in directive_names else None
        citations = [by_id[i].citation for i in ids if by_id[i].citation]
        obs = [by_id[i].text for i in ids if not by_id[i].citation]
        if not citations:
            # Cited only observations: show their most recent substantive supporting quotes
            # (skip bare approvals like "approved.").
            for i in ids:
                srcs = [by_id[s].citation for s in by_id[i].source_ids if s in by_id and by_id[s].citation]
                srcs = [c for c in srcs if len(c.quote) >= 25]
                citations.extend(sorted(srcs, key=lambda c: c.date)[-2:])
        substantive = [c for c in citations if len(c.quote) >= 25]
        if substantive:  # a bare "approved." adds nothing next to a real instruction
            citations = substantive
        seen, unique = set(), []
        for c in sorted(citations, key=lambda c: c.date, reverse=True):  # newest first on the card
            if c.document_id not in seen:
                seen.add(c.document_id)
                unique.append(c)
        if not unique and not directive:
            dropped.append(DiscardedFlag(flag=flag, reason="no resolvable client quote or directive"))
            continue
        kept.append(ResolvedFlag(**{**flag.model_dump(), "evidence": ids, "directive": directive}, citations=unique, observations=obs))
    order = {"high": 0, "medium": 1, "low": 2}
    kept.sort(key=lambda f: order[f.severity])
    return kept, dropped


def _analyse(image: str | Path, progress: Progress) -> DraftAnalysis:
    cached = cache_path(image).exists()
    progress.event("extract", "start", "Reading the draft: measuring colours, reading layout and copy…", cached=cached)
    with progress.timed("extract"):
        analysis = analyse_draft(image)
    progress.event(
        "extract",
        "done",
        f"Palette: {analysis.palette.overall}; background {analysis.palette.background.hex}"
        + ("; grain texture detected" if analysis.palette.grain_detected else ""),
        cached=cached,
        palette=[s.hex for s in analysis.palette.swatches],
        headline=analysis.vision.headline,
    )
    return analysis


def review_with_memory(
    client_id: str, bank_id: str, image: str | Path, project: str, fmt: str, emit: Emit | None = None
) -> Review:
    progress = Progress(emit)
    client = get_client(client_id)
    analysis = _analyse(image, progress)
    evidence = gather_evidence(bank_id, analysis, progress=progress)
    query, context = _memory_prompt(client, project, fmt, analysis, evidence)
    all_directives = GLOBAL_DIRECTIVES + client.bank.directives
    directive_names = {d.name.lower() for d in all_directives}
    directives = "\n".join(f"- {d.name}: {d.content}" for d in all_directives)

    progress.event(
        "reflect",
        "start",
        f"Hindsight reflect: reasoning over {client.name}'s memory with {len(all_directives)} directives…",
        directives=[d.name for d in all_directives],
    )
    try:
        with progress.timed("reflect"):
            output, consulted = _reflect(bank_id, query, context)
        engine = "hindsight-reflect"
    except Exception as exc:  # noqa: BLE001 - any reflect failure falls back to Groq
        log.warning("reflect failed, falling back to Groq: %s", exc)
        progress.event("reflect", "progress", "reflect unavailable; falling back to Groq over the same evidence")
        with progress.timed("reflect"):
            output = complete_json(
                [
                    {"role": "system", "content": f"{client.bank.mission}\n\nDirectives (hard rules):\n{directives}\n\n{_schema_instructions()}"},
                    {"role": "user", "content": f"{query}\n\n{context}"},
                ],
                ReviewOutput,
            )
        consulted, engine = 0, "groq-fallback-with-memory"
    progress.event(
        "reflect",
        "done",
        f"{len(output.flags)} potential issue(s) proposed after consulting {consulted} memories",
        proposed=[f"[{f.topic}] {f.issue}" for f in output.flags],
        consulted=consulted,
    )

    progress.event("verify", "start", f"Checking {len(output.flags)} issue(s) against the dated evidence…")
    try:
        with progress.timed("verify"):
            verified, discarded = _verify(output, _draft_block(project, fmt, analysis), evidence, directives)
        engine += "+verified"
    except LLMError as exc:  # verification is a safety net; never lose the review over it
        log.warning("verification failed, using unverified flags: %s", exc)
        verified, discarded = output.flags, []
    flags, unresolved = _resolve(verified, evidence, directive_names)
    discarded += unresolved
    progress.event(
        "verify",
        "done",
        f"{len(flags)} issue(s) confirmed with client quotes, {len(discarded)} discarded",
        discarded=[{"issue": d.flag.issue, "reason": d.reason} for d in discarded],
    )
    verdict = "needs_changes" if any(f.severity in ("high", "medium") for f in flags) else "ready_for_client"
    review = Review(
        client_id=client_id,
        bank_id=bank_id,
        memory=True,
        engine=engine,
        verdict=verdict,
        summary=output.summary,
        flags=flags,
        discarded=discarded,
        evidence=evidence,
        memories_consulted=consulted,
        elapsed_s=round(progress.elapsed(), 1),
        timings=progress.timings,
    )
    progress.event("done", "done", f"Verdict: {verdict.replace('_', ' ')}", verdict=verdict)
    return review


def review_without_memory(
    client_id: str, image: str | Path, project: str, fmt: str, emit: Emit | None = None
) -> Review:
    progress = Progress(emit)
    client = get_client(client_id)
    analysis = _analyse(image, progress)
    progress.event("reflect", "start", "Reviewing with general design judgement only (no client memory)…")
    prompt = (
        f"You are a senior designer at a creative agency reviewing a draft before it goes to the "
        f"client {client.name} ({client.industry}). You have no history with this client; use "
        f"general design judgement to predict the feedback they would give.\n\n"
        f"{_draft_block(project, fmt, analysis)}\n\n"
        "severity: high = client would reject; medium = would ask for a change; low = polish. "
        "Leave evidence as an empty list."
    )
    with progress.timed("reflect"):
        output = complete_json(
            [{"role": "system", "content": _schema_instructions()}, {"role": "user", "content": prompt}],
            ReviewOutput,
        )
    # Without memory there are no directives or evidence; drop any the model invents
    # (it otherwise makes up names like "BrandPalette").
    flags = [ResolvedFlag(**{**f.model_dump(), "directive": None, "evidence": []}) for f in output.flags]
    review = Review(
        client_id=client_id,
        bank_id=None,
        memory=False,
        engine="groq-no-memory",
        verdict=output.verdict,
        summary=output.summary,
        flags=flags,
        elapsed_s=round(progress.elapsed(), 1),
        timings=progress.timings,
    )
    progress.event("done", "done", f"Verdict: {output.verdict.replace('_', ' ')}", verdict=output.verdict)
    return review
