"""Hindsight client factory plus Operations API helpers.

The Python SDK wraps memory/bank calls, but not the Operations API, so waiting for
background work (fact extraction, observation consolidation, bank clones) goes through
REST directly: GET /v1/default/banks/{bank_id}/operations.
"""

from __future__ import annotations

import atexit
import sys
import time
from functools import cache

import httpx
from hindsight_client import Hindsight
from hindsight_client_api.exceptions import ApiException

from ..config import settings

ACTIVE_STATUSES = ("pending", "processing")


@cache
def hindsight() -> Hindsight:
    client = Hindsight(base_url=settings.hindsight_url, api_key=settings.hindsight_api_key, timeout=300.0)
    atexit.register(client.close)  # otherwise aiohttp warns about an unclosed session
    return client


def _http() -> httpx.Client:
    headers = {"Authorization": f"Bearer {settings.hindsight_api_key}"} if settings.hindsight_api_key else {}
    return httpx.Client(base_url=settings.hindsight_url, headers=headers, timeout=30.0)


def delete_bank_if_exists(bank_id: str) -> bool:
    try:
        hindsight().delete_bank(bank_id)
        return True
    except ApiException as exc:
        if exc.status == 404:
            return False
        raise


def list_operations(bank_id: str, status: str | None = None, op_type: str | None = None, limit: int = 100) -> list[dict]:
    params = {"limit": limit, "exclude_parents": "false"}
    if status:
        params["status"] = status
    if op_type:
        params["type"] = op_type
    with _http() as http:
        resp = http.get(f"/v1/default/banks/{bank_id}/operations", params=params)
        resp.raise_for_status()
        return resp.json().get("operations", [])


def get_operation(bank_id: str, operation_id: str) -> dict:
    with _http() as http:
        resp = http.get(f"/v1/default/banks/{bank_id}/operations/{operation_id}")
        resp.raise_for_status()
        return resp.json()


def wait_until_idle(bank_id: str, *, timeout: float = 1200, poll: float = 2.0, label: str = "") -> None:
    """Block until the bank has no pending/processing operations (retain + consolidation).

    Consolidation is queued right after a retain returns, so we require two consecutive
    empty polls before declaring the bank idle.
    """
    deadline = time.monotonic() + timeout
    empty_polls = 0
    started = time.monotonic()
    while True:
        active = [op for s in ACTIVE_STATUSES for op in list_operations(bank_id, status=s)]
        if not active:
            empty_polls += 1
            if empty_polls >= 2:
                if label:
                    _status(f"{label}: idle after {time.monotonic() - started:.0f}s", done=True)
                return
        else:
            empty_polls = 0
            # Keep this short: a line wider than the terminal wraps and breaks the \r overwrite.
            _status(f"{label}: {len(active)} op(s) running, {time.monotonic() - started:.0f}s")
        if time.monotonic() > deadline:
            raise TimeoutError(f"{bank_id}: operations still running after {timeout:.0f}s")
        time.sleep(poll)


def wait_for_operation(bank_id: str, operation_id: str, *, timeout: float = 600, poll: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        op = get_operation(bank_id, operation_id)
        if op.get("status") not in ACTIVE_STATUSES:
            if op.get("status") != "completed":
                raise RuntimeError(f"Operation {operation_id} on {bank_id} ended as {op.get('status')}: {op.get('error_message')}")
            return op
        if time.monotonic() > deadline:
            raise TimeoutError(f"Operation {operation_id} on {bank_id} still {op.get('status')} after {timeout:.0f}s")
        time.sleep(poll)


def failed_operations(bank_id: str) -> list[dict]:
    return list_operations(bank_id, status="failed")


_last_status_len = 0


def _status(msg: str, done: bool = False) -> None:
    # Pad with spaces instead of ANSI erase codes: PowerShell/conhost may not honour them.
    global _last_status_len
    line = "    " + msg
    sys.stdout.write("\r" + line.ljust(_last_status_len) + ("\n" if done else ""))
    sys.stdout.flush()
    _last_status_len = 0 if done else len(line)
