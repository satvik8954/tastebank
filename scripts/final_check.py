"""Final pre-freeze check, in demo order. Runs every demo review LIVE and records it, so the
recordings in data/recordings/ double as the stage fallback (RZ_REVIEW_MODE=replay).

    python scripts/final_check.py

Asserts the demo-critical verdicts and prints flags beside the planted issues for scoring.
Spaced out to stay inside Groq's free-tier 8k tokens/min.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from review_draft import draft_info  # noqa: E402

from roundzero.config import DATA_DIR, bank_id  # noqa: E402
from roundzero.review.replay import run_review  # noqa: E402

DRAFTS = DATA_DIR / "drafts"
PAUSE = 20  # seconds between reviews (rate-limit headroom)

# (image, bank for ON or None for OFF, expectation)
PLAN = [
    ("dewpoint_hydra-mist_v1.png", None, "record"),
    ("dewpoint_hydra-mist_v1.png", bank_id("dewpoint"), "needs_changes"),
    ("crunchd_maple-chipotle_pastel.png", None, "record"),
    ("crunchd_maple-chipotle_pastel.png", bank_id("crunchd", "before"), "ready"),
    ("crunchd_maple-chipotle_pastel.png", bank_id("crunchd", "after"), "flag_rebrand"),
    ("hale-whitford_estate-tax-alert_v1.png", None, "record"),
    ("hale-whitford_estate-tax-alert_v1.png", bank_id("hale-whitford"), "needs_changes"),
    ("hale-whitford_estate-tax-alert_v2.png", None, "record"),
    ("hale-whitford_estate-tax-alert_v2.png", bank_id("hale-whitford"), "ready"),
]


def main() -> None:
    failures = []
    for n, (name, bank, expect) in enumerate(PLAN, start=1):
        if n > 1:
            time.sleep(PAUSE)
        info = draft_info(DRAFTS / name)
        r = run_review(info["client"], DRAFTS / name, info["project"], info["format"],
                       memory=bank is not None, bank_id=bank, mode="live")
        label = f"ON {bank}" if bank else "OFF"
        print(f"\n[{n}/{len(PLAN)}] {name} · {label} · {r.elapsed_s}s · {r.engine} · {r.verdict}")
        for f in r.flags:
            cite = f" <- {f.citations[0].author} {f.citations[0].date}" if f.citations else ""
            print(f"    [{f.severity}] [{f.topic}] {f.issue[:110]}{cite}")
        for d in r.discarded:
            print(f"    (discarded) {d.flag.issue[:80]} | {d.reason[:80]}")
        if bank and expect != "record" and info.get("planted"):
            print("    planted: " + " | ".join(info["planted"]))

        ok = {
            "record": True,
            "needs_changes": r.verdict == "needs_changes",
            "ready": not r.blocking,
            "flag_rebrand": any(c.date >= "2026-06-02" for f in r.blocking for c in f.citations),
        }[expect]
        if not ok:
            failures.append(f"{name} {label}: expected {expect}, got {r.verdict}")

    print("\n=== RESULT: " + ("PASS" if not failures else "FAIL\n  " + "\n  ".join(failures)))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
