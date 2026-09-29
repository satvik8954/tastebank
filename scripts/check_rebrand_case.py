"""Acceptance check for the headline demo case (hits Hindsight Cloud + Groq).

The pastel Maple Chipotle draft must:
  - PASS against rz-crunchd-before (no high/medium flags), and
  - be FLAGGED against rz-crunchd-after, with a flag citing actual rebrand-era client
    feedback (dated 2026-06-02 or later) by quote and date.

    python scripts/check_rebrand_case.py [--runs 3]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from review_draft import print_review  # noqa: E402

from roundzero.config import DATA_DIR, bank_id  # noqa: E402
from roundzero.review.reviewer import review_with_memory  # noqa: E402

IMAGE = DATA_DIR / "drafts" / "crunchd_maple-chipotle_pastel.png"
PROJECT, FMT = "Fall flavour: Maple Chipotle", "instagram_post"
REBRAND_DATE = "2026-06-02"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1, help="repeat to check stability")
    args = parser.parse_args()

    failures = []
    for run in range(1, args.runs + 1):
        print(f"\n################ run {run}/{args.runs}")
        before = review_with_memory("crunchd", bank_id("crunchd", "before"), IMAGE, PROJECT, FMT)
        print_review(before)
        if before.blocking:
            failures.append(f"run {run}: BEFORE bank raised {len(before.blocking)} high/medium flag(s)")

        after = review_with_memory("crunchd", bank_id("crunchd", "after"), IMAGE, PROJECT, FMT)
        print_review(after)
        rebrand_cited = [
            f for f in after.blocking if any(c.date >= REBRAND_DATE for c in f.citations)
        ]
        if not rebrand_cited:
            failures.append(f"run {run}: AFTER bank has no high/medium flag citing feedback dated >= {REBRAND_DATE}")

    print("\n################ RESULT")
    if failures:
        print("FAIL\n  " + "\n  ".join(failures))
        sys.exit(1)
    print(f"PASS ({args.runs} run(s)): passes before the rebrand, flagged after it with rebrand quotes cited")


if __name__ == "__main__":
    main()
