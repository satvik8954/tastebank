"""Live taste-change demo: Crunchd rebrands from muted pastels to loud colour.

    python scripts/demo_rebrand.py            # live: retain the rebrand into rz-crunchd (~2 min)
    python scripts/demo_rebrand.py --fallback # no writes: before vs after [Colour] observations
    python scripts/demo_rebrand.py --fallback --topic ""   # ...all topics
    python scripts/demo_rebrand.py --reset    # restore rz-crunchd from rz-crunchd-before

Live mode snapshots the taste profile, retains the rebrand-phase feedback (brief + three
projects) in order, waits for consolidation, then prints which observations were UPDATED
(with their previous versions), CREATED or REMOVED.
"""

from __future__ import annotations

import argparse
import itertools
import sys
import textwrap
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roundzero.config import bank_id  # noqa: E402
from roundzero.data import get_client, memory_items  # noqa: E402
from roundzero.memory.client import (  # noqa: E402
    _http,
    delete_bank_if_exists,
    hindsight,
    wait_for_operation,
    wait_until_idle,
)
from roundzero.memory.retain import retain_item  # noqa: E402

CLIENT = "crunchd"


def observations(bank: str) -> dict[str, object]:
    return {m.id: m for m in hindsight().list_memories(bank_id=bank, type="observation", limit=200).items}


def history(bank: str, memory_id: str) -> list[dict]:
    with _http() as http:
        return http.get(f"/v1/default/banks/{bank}/memories/{memory_id}/history").json()


def wrap(text: str, prefix: str) -> str:
    return textwrap.fill(text, width=110, initial_indent=prefix, subsequent_indent=" " * len(prefix))


def show_changes(bank: str, before: dict[str, object], after: dict[str, object]) -> None:
    updated = [m for i, m in after.items() if i in before and before[i].text != m.text]
    created = [m for i, m in after.items() if i not in before]
    removed = [m for i, m in before.items() if i not in after]

    print(f"\n=== UPDATED ({len(updated)}): same observation, history preserved")
    for m in updated:
        print(wrap(m.text, f"  [proof {before[m.id].proof_count} -> {m.proof_count}] NOW: "))
        for change in history(bank, m.id):
            print(wrap(change.get("previous_text") or "", "      was: "))
        print()
    print(f"=== CREATED ({len(created)})")
    for m in created:
        print(wrap(m.text, f"  [proof {m.proof_count}] "))
    print(f"\n=== REMOVED ({len(removed)})")
    for m in removed:
        print(wrap(m.text, "  "))


def reset() -> None:
    main_bank, snapshot = bank_id(CLIENT), bank_id(CLIENT, "before")
    t0 = time.monotonic()
    delete_bank_if_exists(main_bank)
    op_id = hindsight().clone_bank(snapshot, main_bank)
    wait_for_operation(snapshot, op_id)
    wait_until_idle(main_bank, label=f"restoring {main_bank}")
    print(f"{main_bank} restored from {snapshot}: {len(observations(main_bank))} observations "
          f"in {time.monotonic() - t0:.0f}s")


def live() -> None:
    bank = bank_id(CLIENT)
    items = memory_items(get_client(CLIENT), {"rebrand"})
    already = hindsight().list_memories(bank_id=bank, type="world", search_query="Rebrand reveal post", limit=1)
    if already.total:
        sys.exit(f"{bank} already contains the rebrand. Run with --reset first.")
    before = observations(bank)
    print(f"{bank}: {len(before)} observations before the rebrand\n")

    # Timing: is this stage-safe? retain() is synchronous (fact extraction); consolidation
    # into observations runs afterwards as a background operation.
    timings: list[tuple[str, float, float]] = []  # (step, retain seconds, consolidation seconds)
    t_start = time.monotonic()
    for group, group_items in itertools.groupby(items, key=lambda i: i.project_id or i.document_id):
        t0 = time.monotonic()
        for item in group_items:
            print(wrap(f"{item.metadata['author']}: \"{item.metadata['quote']}\"", f"  retain [{item.metadata['date']}] "))
            retain_item(bank, item)
        t1 = time.monotonic()
        wait_until_idle(bank, label=f"consolidating {group}")
        timings.append((group, t1 - t0, time.monotonic() - t1))
    total = time.monotonic() - t_start

    show_changes(bank, before, observations(bank))

    print("\n=== TIMING (retain -> consolidation done)")
    for step, t_ret, t_con in timings:
        print(f"  {step:<18} retain {t_ret:5.1f}s   consolidation {t_con:5.1f}s")
    print(f"  {'TOTAL':<18} {total:.1f}s  ({sum(t for _, t, _ in timings):.1f}s retain, "
          f"{sum(t for _, _, t in timings):.1f}s consolidation)")


def fallback(topic: str | None) -> None:
    """Side-by-side of the pre-seeded banks. Consolidation sometimes replaces a reversed
    observation instead of updating it, so the before bank is shown explicitly rather than
    relying only on the history API."""
    before_bank, after_bank = bank_id(CLIENT, "before"), bank_id(CLIENT, "after")
    tag = f"[{topic}]" if topic else ""
    before = [m for m in observations(before_bank).values() if m.text.startswith(tag)]
    after = [m for m in observations(after_bank).values() if m.text.startswith(tag)]
    print(f"Pre-seeded {before_bank} -> {after_bank} (no writes){f', topic {tag}' if tag else ''}")

    print(f"\n=== BEFORE the rebrand ({before_bank})")
    for m in sorted(before, key=lambda m: -(m.proof_count or 0)):
        print(wrap(m.text, f"  [proof {m.proof_count}] "))
    print(f"\n=== AFTER the rebrand ({after_bank}), with history")
    for m in sorted(after, key=lambda m: -(m.proof_count or 0)):
        print(wrap(m.text, f"  [proof {m.proof_count}] "))
        for change in history(after_bank, m.id):
            print(wrap(change.get("previous_text") or "", "      was: "))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--reset", action="store_true")
    mode.add_argument("--fallback", action="store_true")
    parser.add_argument("--topic", default="Colour", help="fallback: observation topic to compare ('' for all)")
    args = parser.parse_args()
    if args.reset:
        reset()
    elif args.fallback:
        fallback(args.topic or None)
    else:
        live()


if __name__ == "__main__":
    main()
