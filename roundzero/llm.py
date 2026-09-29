"""Groq chat completions returning validated Pydantic objects.

gpt-oss / qwen models on Groq occasionally return malformed JSON or JSON that doesn't match
the schema (and occasionally fail tool/JSON generation server-side with a 400). Every call:
  1. asks for JSON mode,
  2. validates against the Pydantic model,
  3. on failure, retries with the validation error fed back (repair prompt),
  4. after `attempts` failures on the primary model, tries the fallback model once.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(RuntimeError):
    pass


def _post(payload: dict, timeout: float = 120.0) -> dict:
    if not settings.groq_api_key:
        raise LLMError("GROQ_API_KEY is not set")
    for attempt in range(3):  # transport-level retries (429 / 5xx)
        try:
            resp = httpx.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json=payload,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise LLMError(f"Groq timed out after {timeout:.0f}s") from exc
        if resp.status_code in (429, 500, 502, 503) and attempt < 2:
            wait = float(resp.headers.get("retry-after", 2 * (attempt + 1)))
            log.warning(
                "Groq %s on %s; waiting %.1fs (tokens remaining: %s)",
                resp.status_code, payload.get("model"), wait, resp.headers.get("x-ratelimit-remaining-tokens"),
            )
            time.sleep(wait)
            continue
        if resp.status_code >= 400:
            raise LLMError(f"Groq {resp.status_code}: {resp.text[:500]}")
        return resp.json()
    raise LLMError("unreachable")


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in response")
    return json.loads(text[start : end + 1])


def complete_json(
    messages: list[dict],
    schema: type[T],
    *,
    model: str | None = None,
    attempts: int = 3,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    timeout: float = 120.0,
) -> T:
    models = [model or settings.llm_model]
    if model is None and settings.llm_fallback_model not in models:
        models.append(settings.llm_fallback_model)

    last_error: Exception | None = None
    for m_idx, m in enumerate(models):
        convo = list(messages)
        for attempt in range(attempts if m_idx == 0 else 1):
            try:
                data = _post(
                    {
                        "model": m,
                        "messages": convo,
                        "response_format": {"type": "json_object"},
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "seed": 7,  # best-effort determinism for repeatable demos
                    },
                    timeout=timeout,
                )
                content = data["choices"][0]["message"].get("content") or ""
                return schema.model_validate(_extract_json(content))
            except (ValidationError, ValueError, KeyError) as exc:
                last_error = exc
                log.warning("LLM %s attempt %d invalid output: %s", m, attempt + 1, str(exc)[:300])
                convo = messages + [
                    {"role": "assistant", "content": content if "content" in locals() else ""},
                    {
                        "role": "user",
                        "content": f"That response was invalid: {str(exc)[:800]}\n"
                        "Reply again with ONLY a JSON object that matches the requested schema.",
                    },
                ]
            except LLMError as exc:  # e.g. Groq 400 "failed to generate JSON"
                last_error = exc
                log.warning("LLM %s attempt %d failed: %s", m, attempt + 1, str(exc)[:300])
    raise LLMError(f"All LLM attempts failed: {last_error}")
