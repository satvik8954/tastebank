"""Seed one Hindsight memory bank per client from data/clients/*.yaml.

    python scripts/seed.py                       # all clients
    python scripts/seed.py --client crunchd --reset
    python scripts/seed.py --consolidate end     # faster, less realistic observation history

What it does, per client:
  1. Upsert the bank: mission, retain/observations/reflect missions, disposition, directives.
  2. retain() every piece of past feedback in chronological order, backdated with its real
     timestamp and tagged client/project/phase. Each quote is its own document, so evidence
     can be traced back to the exact quote.
  3. Poll the Operations API until extraction + consolidation have finished. With the
     default `--consolidate project` this happens after every project, so observations
     evolve in order and keep a real history, rather than being built in one pass at the end.

For clients with a rebrand phase (Crunchd):
  - `rz-crunchd`         main bank, pre-rebrand history only. The live demo retains the
                         rebrand into this bank (scripts/demo_rebrand.py).
  - `rz-crunchd-before`  snapshot of the above, used to reset between rehearsals.
  - `rz-crunchd-after`   fallback: pre-seeded with the rebrand already consolidated.
"""

from __future__ import annotations

import argparse
import itertools
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hindsight_client_api.exceptions import ApiException  # noqa: E402

from roundzero.config import bank_id, settings  # noqa: E402
from roundzero.data import Client, MemoryItem, load_clients, memory_items  # noqa: E402
from roundzero.memory.banks import configure_bank  # noqa: E402
from roundzero.memory.client import (  # noqa: E402
    delete_bank_if_exists,
    failed_operations,
    hindsight,
    wait_for_operation,
    wait_until_idle,
)
from roundzero.memory.retain import retain_item  # noqa: E402


def retain_all(bank: str, items: list[MemoryItem], consolidate: str) -> None:
    """Retain oldest-first. Waits for consolidation after each project (or once at the end)."""
    groups = itertools.groupby(items, key=lambda i: i.project_id or i.document_id)
    done = 0
    for group_key, group in groups:
        group = list(group)
        for item in group:
            retain_item(bank, item)
            done += 1
        print(f"  [{done:>3}/{len(items)}] retained {group_key} ({len(group)} item(s), {group[0].timestamp:%Y-%m-%d})")
        if consolidate == "project":
            wait_until_idle(bank, label=f"consolidating {group_key}")
    wait_until_idle(bank, label="final consolidation")


def memory_count(bank: str, kind: str | None = None) -> int:
    try:
        return hindsight().list_memories(bank_id=bank, type=kind, limit=1).total
    except ApiException as exc:
        if exc.status == 404:
            return 0
        raise


def clone(src: str, dst: str) -> bool:
    """Server-side bank clone (no LLM calls). Returns False if unsupported on this server."""
    delete_bank_if_exists(dst)
    try:
        op_id = hindsight().clone_bank(src, dst)
    except ApiException as exc:
        print(f"  clone {src} -> {dst} unavailable ({exc.status}); falling back to re-seeding")
        return False
    wait_for_operation(src, op_id)
    wait_until_idle(dst, label=f"clone {dst}")
    return True


def seed_client(client: Client, *, reset: bool, consolidate: str, force: bool) -> None:
    main = bank_id(client.id)
    print(f"\n== {client.name} -> {main}")
    if reset:
        variants = [None] + (["before", "after"] if "rebrand" in client.phases else [])
        for b in (bank_id(client.id, v) for v in variants):
            if delete_bank_if_exists(b):
                print(f"  deleted {b}")

    if memory_count(main) and not force:
        print(f"  {main} already has memories; skipping retain (use --reset or --force)")
    else:
        configure_bank(client, main)
        print("  bank configured (mission, directives, disposition)")
        retain_all(main, memory_items(client, {"base"}), consolidate)

    if "rebrand" not in client.phases:
        return

    before, after = bank_id(client.id, "before"), bank_id(client.id, "after")
    print(f"  snapshot {main} -> {before} (reset point for the live rebrand demo)")
    clone(main, before)

    print(f"  building fallback {after} (rebrand already consolidated)")
    if not clone(main, after):
        configure_bank(client, after)
        retain_all(after, memory_items(client, {"base"}), consolidate)
    retain_all(after, memory_items(client, {"rebrand"}), consolidate)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    clients = load_clients()
    parser.add_argument("--client", action="append", choices=sorted(clients), help="seed only these clients")
    parser.add_argument("--reset", action="store_true", help="delete the client's banks first")
    parser.add_argument("--force", action="store_true", help="retain even if the bank already has memories")
    parser.add_argument(
        "--consolidate",
        choices=["project", "end"],
        default="project",
        help="wait for consolidation after each project (realistic history) or only at the end (faster)",
    )
    args = parser.parse_args()

    print(f"Hindsight: {settings.hindsight_url}  prefix: {settings.bank_prefix}")
    t0 = time.monotonic()
    for cid in args.client or sorted(clients):
        seed_client(clients[cid], reset=args.reset, consolidate=args.consolidate, force=args.force)

    print("\n== Summary")
    for cid in args.client or sorted(clients):
        variants = [None] + (["before", "after"] if "rebrand" in clients[cid].phases else [])
        for v in variants:
            b = bank_id(cid, v)
            failed = failed_operations(b)
            print(
                f"  {b:<24} facts={memory_count(b, 'world') + memory_count(b, 'experience'):>4}"
                f"  observations={memory_count(b, 'observation'):>3}"
                + (f"  FAILED ops={len(failed)}" if failed else "")
            )
    print(f"Done in {time.monotonic() - t0:.0f}s")


if __name__ == "__main__":
    main()
