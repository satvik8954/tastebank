"""Print a bank's taste profile: observations by proof count, optionally with history.

    python scripts/inspect_bank.py rz-crunchd-after
    python scripts/inspect_bank.py rz-crunchd-after --history --grep neon
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roundzero.memory.client import _http, hindsight  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bank")
    parser.add_argument("--grep", help="only observations containing this text")
    parser.add_argument("--history", action="store_true", help="show how each observation changed")
    args = parser.parse_args()

    items = hindsight().list_memories(bank_id=args.bank, type="observation", limit=200).items
    if args.grep:
        items = [m for m in items if args.grep.lower() in m.text.lower()]
    items.sort(key=lambda m: -(m.proof_count or 0))
    print(f"{args.bank}: {len(items)} observation(s)\n")

    with _http() as http:
        for m in items:
            print(f"[proof {m.proof_count}] {m.text}")
            if args.history:
                history = http.get(f"/v1/default/banks/{args.bank}/memories/{m.id}/history").json()
                # Newest change first; `changed_at` is consolidation wall-clock time, so omit it.
                for change in history:
                    print(textwrap.indent(f"previously: {change.get('previous_text')}", "      "))
            print()


if __name__ == "__main__":
    main()
