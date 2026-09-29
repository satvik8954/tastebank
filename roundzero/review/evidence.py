"""Turn Hindsight recall() results into a numbered, dated evidence list.

One recall per aspect of the draft (colour, typography, layout/imagery, copy) so a draft
with many issues still surfaces evidence for each. Facts carry the metadata we attached at
retain() time (quote, author, project, date), so every F# resolves to an exact client quote.
Observations (O#) point to their source facts, which are added as F# too.
"""

from __future__ import annotations

from ..extract.draft import DraftAnalysis
from ..memory.client import hindsight
from .schemas import Citation, Evidence

MAX_FEEDBACK = 36
MAX_OBSERVATIONS = 12


def aspect_queries(analysis: DraftAnalysis) -> dict[str, str]:
    v = analysis.vision
    return {
        "colour": f"colour palette and background colours: {analysis.palette.summary()}",
        "typography": f"typography, typeface and headline case: {v.typeface_style}; {v.headline_case}",
        "layout_imagery": f"layout, product placement, imagery and effects: {v.layout} {v.imagery} {', '.join(v.effects)}",
        "copy": f"copy wording, tone, claims, emoji and punctuation: {v.headline} / {' / '.join(v.copy_text)} {v.punctuation_notes}",
    }


def _citation(result) -> Citation | None:
    md = result.metadata or {}
    if not md.get("quote") or not result.document_id:
        return None
    return Citation(
        document_id=result.document_id,
        quote=md["quote"],
        author=md.get("author", "client"),
        role=md.get("role", ""),
        date=md.get("date", ""),
        project_name=md.get("project_name"),
        round=md.get("round"),
        kind=md.get("kind", "feedback"),
    )


def gather_evidence(bank_id: str, analysis: DraftAnalysis, budget: str = "mid") -> list[Evidence]:
    hs = hindsight()
    facts_by_doc: dict[str, tuple[Citation, list[str]]] = {}
    observations: dict[str, tuple[str, list[str]]] = {}  # obs id -> (text, source document ids)

    def add_fact(res) -> str | None:
        cit = _citation(res)
        if not cit:
            return None
        entry = facts_by_doc.setdefault(cit.document_id, (cit, []))
        if res.text not in entry[1]:
            entry[1].append(res.text)
        return cit.document_id

    for query in aspect_queries(analysis).values():
        resp = hs.recall(
            bank_id=bank_id,
            query=query,
            types=["observation", "world", "experience"],
            budget=budget,
            max_tokens=2048,
            include_source_facts=True,
            max_source_facts_tokens=2048,
        )
        source_facts = resp.source_facts or {}
        for res in resp.results:
            if res.type == "observation":
                docs = []
                for sid in res.source_fact_ids or []:
                    sf = source_facts.get(sid)
                    if sf is not None and (doc := add_fact(sf)):
                        docs.append(doc)
                prev = observations.get(res.id)
                observations[res.id] = (res.text, sorted(set(docs) | set(prev[1] if prev else [])))
            else:
                add_fact(res)

    # Oldest first, so recency is visible to the reviewer; number after sorting.
    ordered = sorted(facts_by_doc.values(), key=lambda e: (e[0].date, e[0].document_id))
    if len(ordered) > MAX_FEEDBACK:  # keep the most recent when trimming
        ordered = ordered[-MAX_FEEDBACK:]
    evidence: list[Evidence] = []
    doc_to_id: dict[str, str] = {}
    for i, (cit, texts) in enumerate(ordered, start=1):
        eid = f"F{i}"
        doc_to_id[cit.document_id] = eid
        evidence.append(Evidence(id=eid, kind="feedback", text=" | ".join(texts), citation=cit))
    for i, (text, docs) in enumerate(list(observations.values())[:MAX_OBSERVATIONS], start=1):
        evidence.append(
            Evidence(id=f"O{i}", kind="observation", text=text, source_ids=[doc_to_id[d] for d in docs if d in doc_to_id])
        )
    return evidence
