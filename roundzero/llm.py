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


class RateLimited(LLMError):
    """Groq 429 with a long retry-after. Each model has its own token bucket (free tier:
    8k tokens/min), so the caller should try the next model instead of sleeping."""

    def __init__(self, model: str, wait: float):
        super().__init__(f"{model} rate-limited for {wait:.0f}s")
        self.wait = wait


MAX_INLINE_WAIT = 3.0  # sleep through short 429s; longer ones switch model


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
            if resp.status_code == 429 and wait > MAX_INLINE_WAIT:
                log.warning("Groq 429 on %s (retry-after %.0fs); trying another model", payload.get("model"), wait)
                raise RateLimited(payload.get("model", "?"), wait)
            log.warning("Groq %s on %s; waiting %.1fs", resp.status_code, payload.get("model"), wait)
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
    return_usage: bool = False,
):
    """Returns the validated object, or (object, usage) when return_usage=True; usage is
    Groq's token usage for the successful call plus the model that produced it."""
    models = [model or settings.llm_model]
    if model is None and settings.llm_fallback_model not in models:
        models.append(settings.llm_fallback_model)

    last_error: Exception | None = None
    limited: dict[str, float] = {}  # model -> retry-after, for models that hit a 429
    # Each model gets its turn; if every model is rate-limited, wait for the soonest and
    # give that one a final try.
    schedule = [(m, attempts if i == 0 else 1) for i, m in enumerate(models)]
    for pass_no in range(2):
        if pass_no == 1:
            if not limited or len(limited) < len(models):
                break
            m, wait = min(limited.items(), key=lambda kv: kv[1])
            log.warning("all models rate-limited; waiting %.0fs for %s", wait, m)
            time.sleep(wait)
            schedule = [(m, 1)]
        result = _try_models(schedule, messages, schema, temperature, max_tokens, timeout, return_usage, limited)
        if not isinstance(result, Exception):
            return result
        last_error = result
    raise LLMError(f"All LLM attempts failed: {last_error}")


def _try_models(schedule, messages, schema, temperature, max_tokens, timeout, return_usage, limited):
    """One pass over (model, attempts). Returns the result, or the last exception."""
    last_error: Exception = LLMError("no attempts made")
    for m, n_attempts in schedule:
        convo = list(messages)
        content = ""
        for attempt in range(n_attempts):
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
                result = schema.model_validate(_extract_json(content))
                if return_usage:
                    return result, {**(data.get("usage") or {}), "model": m}
                return result
            except (ValidationError, ValueError, KeyError) as exc:
                last_error = exc
                log.warning("LLM %s attempt %d invalid output: %s", m, attempt + 1, str(exc)[:300])
                convo = messages + [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": f"That response was invalid: {str(exc)[:800]}\n"
                        "Reply again with ONLY a JSON object that matches the requested schema.",
                    },
                ]
            except RateLimited as exc:
                last_error = exc
                limited[m] = exc.wait
                break  # next model
            except LLMError as exc:  # e.g. Groq 400 "failed to generate JSON"
                last_error = exc
                log.warning("LLM %s attempt %d failed: %s", m, attempt + 1, str(exc)[:300])
    return last_error
