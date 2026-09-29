"""Review one draft from the command line.

    python scripts/review_draft.py data/drafts/crunchd_maple-chipotle_pastel.png --bank rz-crunchd-after
    python scripts/review_draft.py data/drafts/dewpoint_hydra-mist_v1.png --no-memory

Client, project and format come from data/drafts/drafts.yaml when the file is listed there.
"""

from __future__ import annotations

import argparse
import logging
import sys
import textwrap
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roundzero.config import DATA_DIR, bank_id  # noqa: E402
from roundzero.review.reviewer import review_with_memory, review_without_memory  # noqa: E402
from roundzero.review.schemas import Review  # noqa: E402


def draft_info(image: Path) -> dict:
    manifest = yaml.safe_load((DATA_DIR / "drafts" / "drafts.yaml").read_text(encoding="utf-8"))
    return next((d for d in manifest if d["file"] == image.name), {})


def print_review(r: Review) -> None:
    label = f"memory ON · {r.bank_id}" if r.memory else "memory OFF"
    print(f"\n=== {label} · engine={r.engine} · {r.elapsed_s}s · verdict: {r.verdict.upper()}")
    print(textwrap.fill(r.summary, 110, initial_indent="  ", subsequent_indent="  "))
    if r.memory:
        print(f"  evidence: {sum(e.kind == 'feedback' for e in r.evidence)} client quotes, "
              f"{sum(e.kind == 'observation' for e in r.evidence)} observations; reflect consulted {r.memories_consulted} memories")
    for f in r.flags:
        print(f"\n  [{f.severity.upper()}] [{f.topic}] {f.issue}")
        print(textwrap.fill(f"fix: {f.suggestion}", 110, initial_indent="     ", subsequent_indent="          "))
        if f.directive:
            print(f"     directive: {f.directive}")
        for c in f.citations:
            where = f'{c.project_name}, round {c.round}' if c.project_name else c.kind
            quote = c.quote if len(c.quote) <= 220 else c.quote[:217].rstrip() + "…"
            print(textwrap.fill(f'"{quote}" ({c.author}, {c.role} · {where} · {c.date})', 110,
                                initial_indent="     > ", subsequent_indent="       "))
    for d in r.discarded:
        print(f"\n  (discarded) [{d.flag.topic}] {d.flag.issue[:90]}")
        print(textwrap.fill(f"why: {d.reason}", 110, initial_indent="     ", subsequent_indent="          "))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--client")
    parser.add_argument("--bank", help="defaults to the client's main bank")
    parser.add_argument("--no-memory", action="store_true")
    parser.add_argument("--project")
    parser.add_argument("--format")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="  %(levelname)s %(message)s")

    info = draft_info(args.image)
    client = args.client or info.get("client") or sys.exit("--client is required for drafts not in drafts.yaml")
    project = args.project or info.get("project", args.image.stem)
    fmt = args.format or info.get("format", "instagram_post")

    if args.no_memory:
        print_review(review_without_memory(client, args.image, project, fmt))
    else:
        print_review(review_with_memory(client, args.bank or bank_id(client), args.image, project, fmt))


if __name__ == "__main__":
    main()
