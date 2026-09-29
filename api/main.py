"""Round Zero HTTP API (FastAPI).

    uvicorn api.main:app --reload --port 8000

Hindsight's Python SDK is synchronous and runs its own event loop internally, so every
endpoint that touches Hindsight is a plain `def` (FastAPI runs those in a threadpool). The
review stream runs the reviewer in a worker thread and relays its progress events to the
browser as server-sent events (SSE).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Literal

import yaml
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from hindsight_client_api.exceptions import ApiException

from roundzero.config import DATA_DIR, bank_id, settings
from roundzero.data import load_clients
from roundzero.feedback import FeedbackIn, log_feedback, project_rounds
from roundzero.memory.banks import OBSERVATION_TOPICS
from roundzero.memory.client import _http, hindsight, list_operations
from roundzero.review.replay import RecordingMissing, default_mode, has_recording, run_review

DRAFTS_DIR = DATA_DIR / "drafts"
UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Round Zero", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/files/drafts", StaticFiles(directory=DRAFTS_DIR), name="drafts")
app.mount("/files/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


# --- clients & memory ---------------------------------------------------------------------

def _banks_for(client) -> list[dict]:
    banks = [{"id": bank_id(client.id), "label": "Current memory"}]
    if "rebrand" in client.phases:
        banks += [
            {"id": bank_id(client.id, "before"), "label": "Before rebrand (Jun 2026)"},
            {"id": bank_id(client.id, "after"), "label": "After rebrand"},
        ]
    return banks


@app.get("/api/config")
def config() -> dict:
    return {"review_mode": default_mode(), "hindsight_url": settings.hindsight_url, "topics": list(OBSERVATION_TOPICS)}


@app.get("/api/clients")
def clients() -> list[dict]:
    return [
        {
            "id": c.id,
            "name": c.name,
            "industry": c.industry,
            "contacts": [x.model_dump() for x in c.contacts],
            "brand": c.brand,
            "brand_after_rebrand": c.brand_after_rebrand,
            "banks": _banks_for(c),
        }
        for c in load_clients().values()
    ]


@app.get("/api/clients/{client_id}/projects")
def projects(client_id: str) -> list[dict]:
    if client_id not in load_clients():
        raise HTTPException(404, "unknown client")
    return project_rounds(client_id)


_TOPIC = re.compile(r"^\[(\w+)\]\s*")


@app.get("/api/banks/{bank}/profile")
def taste_profile(bank: str) -> dict:
    """The client's taste profile = Hindsight observations, grouped by topic, with proof counts."""
    try:
        items = hindsight().list_memories(bank_id=bank, type="observation", limit=200).items
    except ApiException as exc:
        raise HTTPException(exc.status or 502, f"Hindsight: {exc.reason}") from exc
    groups: dict[str, list[dict]] = {t: [] for t in OBSERVATION_TOPICS}
    for m in sorted(items, key=lambda m: -(m.proof_count or 0)):
        match = _TOPIC.match(m.text)
        topic = match.group(1).capitalize() if match else "Other"
        groups.setdefault(topic, []).append(
            {
                "id": m.id,
                "text": _TOPIC.sub("", m.text),
                "proof_count": m.proof_count or 0,
                "sources": len(m.source_memory_ids or []),
                "updated_at": str(m.updated_at or m.mentioned_at or ""),
            }
        )
    return {"bank": bank, "total": len(items), "topics": {k: v for k, v in groups.items() if v}}


@app.get("/api/banks/{bank}/observations/{memory_id}/history")
def observation_history(bank: str, memory_id: str) -> list[dict]:
    with _http() as http:
        resp = http.get(f"/v1/default/banks/{bank}/memories/{memory_id}/history")
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text[:300])
    return [
        {
            "previous_text": _TOPIC.sub("", h.get("previous_text") or ""),
            "changed_at": h.get("changed_at"),
            "source_facts": [f.get("text") for f in h.get("source_facts") or []],
        }
        for h in resp.json()
    ]


@app.get("/api/banks/{bank}/operations")
def operations(bank: str) -> dict:
    active = [op for s in ("pending", "processing") for op in list_operations(bank, status=s)]
    return {"active": len(active), "types": sorted({op.get("task_type") or "?" for op in active})}


@app.post("/api/feedback")
def feedback(fb: FeedbackIn, bank: str | None = None) -> dict:
    target = bank or bank_id(fb.client_id)
    item = log_feedback(fb, target)
    return {"bank": target, "document_id": item.document_id, "project_id": item.project_id}


# --- drafts --------------------------------------------------------------------------------

def _manifest() -> list[dict]:
    return yaml.safe_load((DRAFTS_DIR / "drafts.yaml").read_text(encoding="utf-8"))


@app.get("/api/drafts")
def drafts() -> list[dict]:
    out = []
    for d in _manifest():
        out.append({**{k: d[k] for k in ("file", "client", "project", "format")}, "url": f"/files/drafts/{d['file']}",
                    "notes": d.get("notes"), "planted": d.get("planted") or []})
    for meta in sorted(UPLOADS_DIR.glob("*.json")):
        out.append(json.loads(meta.read_text(encoding="utf-8")))
    return out


@app.post("/api/drafts")
async def upload_draft(
    file: UploadFile = File(...),
    client: str = Form(...),
    project: str = Form(...),
    format: str = Form("instagram_post"),
) -> dict:
    if client not in load_clients():
        raise HTTPException(400, "unknown client")
    data = await file.read()
    if not data or len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "empty or too large (15 MB max)")
    suffix = Path(file.filename or "draft.png").suffix.lower() or ".png"
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, "png, jpg or webp only")
    name = f"{hashlib.sha1(data).hexdigest()[:12]}{suffix}"
    (UPLOADS_DIR / name).write_bytes(data)
    meta = {"file": name, "client": client, "project": project, "format": format,
            "url": f"/files/uploads/{name}", "notes": None, "planted": [], "uploaded": True}
    (UPLOADS_DIR / f"{name}.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


def _draft_path(file: str) -> Path:
    for base in (DRAFTS_DIR, UPLOADS_DIR):
        p = (base / file).resolve()
        if p.parent == base.resolve() and p.is_file():
            return p
    raise HTTPException(404, "draft not found")


# --- review (SSE) --------------------------------------------------------------------------

def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/api/review/stream")
async def review_stream(
    file: str,
    client: str,
    project: str,
    format: str = "instagram_post",
    memory: bool = True,
    bank: str | None = None,
    mode: Literal["live", "replay", "auto"] | None = None,
    speed: float = Query(1.0, gt=0, le=20),
) -> StreamingResponse:
    """Stream a review: `progress` events while it runs, then one `result` (or `error`)."""
    if client not in load_clients():
        raise HTTPException(404, "unknown client")
    image = _draft_path(file)
    target_bank = (bank or bank_id(client)) if memory else None
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

    def push(kind: str, payload: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, (kind, payload))

    def worker() -> None:
        try:
            review = run_review(
                client, image, project, format, memory=memory, bank_id=target_bank,
                mode=mode, replay_speed=speed,
                emit=lambda e: push("progress", e.model_dump(mode="json")),
            )
            push("result", review.model_dump(mode="json"))
        except RecordingMissing as exc:
            push("error", {"message": str(exc), "kind": "recording_missing"})
        except Exception as exc:  # noqa: BLE001 - report any failure to the browser
            push("error", {"message": f"{type(exc).__name__}: {exc}"[:500], "kind": "review_failed"})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=worker, daemon=True).start()

    async def events():
        yield _sse("start", {"memory": memory, "bank": target_bank, "mode": mode or default_mode(),
                             "has_recording": has_recording(image, project, format, memory, target_bank)})
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"  # stops proxies closing a quiet stream during reflect
                continue
            if item is None:
                break
            yield _sse(*item)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
