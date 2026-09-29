"""(Re)create the sandbox bank used for live feedback-logging demos.

    python scripts/reset_sandbox.py                     # rz-crunchd-sandbox <- clone of rz-crunchd
    python scripts/reset_sandbox.py --from rz-crunchd-before

The sandbox is a server-side clone (no LLM calls, a few seconds), so logging feedback in the
UI never touches the demo banks. Resetting also drops locally logged feedback for the
sandbox, so the revision-rounds chart returns to the seeded history.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roundzero.config import bank_id  # noqa: E402
from roundzero.feedback import LOG_PATH  # noqa: E402
from roundzero.memory.client import delete_bank_if_exists, hindsight, wait_for_operation, wait_until_idle  # noqa: E402

CLIENT = "crunchd"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from", dest="source", default=bank_id(CLIENT))
    args = p.parse_args()
    sandbox = bank_id(CLIENT, "sandbox")

    t0 = time.monotonic()
    delete_bank_if_exists(sandbox)
    op_id = hindsight().clone_bank(args.source, sandbox)
    wait_for_operation(args.source, op_id)
    wait_until_idle(sandbox, label=f"cloning {args.source} -> {sandbox}")
    n_obs = hindsight().list_memories(bank_id=sandbox, type="observation", limit=1).total

    dropped = 0
    if LOG_PATH.exists():
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
        keep = [ln for ln in lines if ln.strip() and json.loads(ln).get("bank_id") != sandbox]
        dropped = len(lines) - len(keep)
        LOG_PATH.write_text("".join(f"{ln}\n" for ln in keep), encoding="utf-8")

    print(f"{sandbox} <- {args.source}: {n_obs} observations, {dropped} logged feedback entries cleared, "
          f"{time.monotonic() - t0:.0f}s")


if __name__ == "__main__":
    main()
