"""Render the demo drafts (data/drafts/templates/*.html) to PNG with Playwright.

    python -m playwright install chromium   # once
    python scripts/make_drafts.py

Each template declares its canvas with <meta name="rz-size" content="1080x1080">.
Output: data/drafts/<template-name>.png
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "data" / "drafts" / "templates"
OUT = ROOT / "data" / "drafts"


def canvas_size(html: str) -> tuple[int, int]:
    m = re.search(r'name="rz-size" content="(\d+)x(\d+)"', html)
    return (int(m.group(1)), int(m.group(2))) if m else (1080, 1080)


def main() -> None:
    only = set(sys.argv[1:])
    templates = [t for t in sorted(TEMPLATES.glob("*.html")) if not only or t.stem in only]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for tpl in templates:
            width, height = canvas_size(tpl.read_text(encoding="utf-8"))
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            page.goto(tpl.as_uri(), wait_until="networkidle")  # wait for Google Fonts
            page.evaluate("document.fonts.ready")
            out = OUT / f"{tpl.stem}.png"
            page.screenshot(path=str(out), full_page=False)
            page.close()
            print(f"  {out.relative_to(ROOT)}  ({width}x{height})")
        browser.close()


if __name__ == "__main__":
    main()
