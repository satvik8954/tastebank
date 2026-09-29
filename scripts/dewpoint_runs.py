"""Repeated live runs of the Dewpoint memory-ON review, archived for an honest catch rate.

    python scripts/dewpoint_runs.py --runs 3          # live runs, archived to data/eval/dewpoint/
    python scripts/dewpoint_runs.py --score           # score every archived run
    python scripts/dewpoint_runs.py --promote <file>  # make an archived run the stage recording

Scoring matches each planted issue against the flags' topic + issue text (not the fix text,
which often mentions things the flag isn't about). Matches are printed for manual checking.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roundzero.config import DATA_DIR, bank_id  # noqa: E402
from roundzero.review.replay import recording_path, run_review  # noqa: E402

IMAGE = DATA_DIR / "drafts" / "dewpoint_hydra-mist_v1.png"
PROJECT, FMT = "Hydra Mist launch post", "instagram_post"
ARCHIVE = DATA_DIR / "eval" / "dewpoint"

# planted issue -> (topic filter or None, regex on the flag's issue text)
PLANTED = {
    "ice-blue / clinical palette": ("colour", r"blue|icy|ice|cool|clinical|palette|warm"),
    '"Heals" + "in 3 days"': (None, r"heal"),
    '"anti-aging"': (None, r"anti.?aging"),
    "before/after split": (None, r"before.{0,3}after"),
    '"Clinically proven" uncited': (None, r"clinically|uncited|citation|substantiat"),
    "front-on bottle": (None, r"front|three.quarter|angle"),
    "no ingredient percentages": (None, r"percent"),
    "gradient fills": (None, r"gradient"),
}


def score(review: dict) -> dict[str, str | None]:
    hits: dict[str, str | None] = {}
    for item, (topic, pattern) in PLANTED.items():
        hit = None
        for f in review["flags"]:
            if topic and f["topic"].lower() != topic:
                continue
            if topic == "colour" and re.search(r"gradient", f["issue"], re.I):
                continue  # the gradient flag is also [Colour]; don't count it as the palette
            if re.search(pattern, f["issue"], re.I):
                hit = f"[{f['severity']}] {f['issue'][:90]}"
                break
        hits[item] = hit
    return hits


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=0)
    p.add_argument("--score", action="store_true")
    p.add_argument("--promote")
    args = p.parse_args()
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    rec = recording_path(IMAGE, PROJECT, FMT, True, bank_id("dewpoint"))

    for n in range(args.runs):
        if n:
            time.sleep(30)  # Groq free tier headroom
        r = run_review("dewpoint", IMAGE, PROJECT, FMT, memory=True, bank_id=bank_id("dewpoint"), mode="live")
        dest = ARCHIVE / f"run-{time.strftime('%Y%m%dT%H%M%S')}.json"
        shutil.copy(rec, dest)
        print(f"run {n + 1}: {r.elapsed_s}s, {len(r.flags)} flags -> {dest.name}")

    if args.promote:
        shutil.copy(ARCHIVE / args.promote, rec)
        print(f"stage recording <- {args.promote}")

    if args.score or args.runs:
        files = sorted(ARCHIVE.glob("run-*.json"))
        totals = {k: 0 for k in PLANTED}
        for f in files:
            data = json.loads(f.read_text(encoding="utf-8"))
            hits = score(data["review"])
            print(f"\n{f.name} (reviewer {data.get('reviewer_version')}): {sum(1 for h in hits.values() if h)}/{len(PLANTED)}")
            for item, hit in hits.items():
                totals[item] += bool(hit)
                print(f"  {'✓' if hit else '✗'} {item:32} {hit or ''}")
        print(f"\nCatch rate over {len(files)} archived runs:")
        for item, n_hit in totals.items():
            print(f"  {item:32} {n_hit}/{len(files)}")


if __name__ == "__main__":
    main()
