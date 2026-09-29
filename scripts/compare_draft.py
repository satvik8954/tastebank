"""Memory ON vs OFF on the same draft (the core demo comparison).

    python scripts/compare_draft.py data/drafts/crunchd_maple-chipotle_pastel.png --bank rz-crunchd-after
    python scripts/compare_draft.py data/drafts/dewpoint_hydra-mist_v1.png

Both sides get the identical draft description (cached extraction); only memory differs.
Prints each review, then the drafts.yaml planted issues for a manual catch-rate read.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from review_draft import draft_info, print_event, print_review  # noqa: E402

from roundzero.config import bank_id  # noqa: E402
from roundzero.review.reviewer import review_with_memory, review_without_memory  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--bank", help="memory bank for the ON side (default: client's main bank)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="  %(levelname)s %(message)s")

    info = draft_info(args.image)
    if not info:
        sys.exit(f"{args.image.name} is not in data/drafts/drafts.yaml")
    client, project, fmt = info["client"], info["project"], info["format"]

    off = review_without_memory(client, args.image, project, fmt)
    print("memory ON progress:")
    on = review_with_memory(client, args.bank or bank_id(client), args.image, project, fmt, emit=print_event)
    print_review(off)
    print_review(on)

    print("\n=== PLANTED ISSUES (drafts.yaml, for scoring; never shown to the model)")
    for p in info.get("planted") or ["(none: control draft)"]:
        print(f"  - {p}")


if __name__ == "__main__":
    main()
