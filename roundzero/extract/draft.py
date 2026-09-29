"""Full draft analysis = measured palette + vision attributes, cached per image content.

Caching makes demo runs repeatable and free: the same PNG always yields the same
description, so ON/OFF and before/after comparisons differ only in memory.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel

from ..config import DATA_DIR
from .palette import Palette, extract_palette
from .vision import VisionAttributes, extract_vision

CACHE_DIR = DATA_DIR / "generated" / "extract"
# Bump when the vision prompt/schema changes so cached extractions are redone.
EXTRACT_VERSION = 4


class DraftAnalysis(BaseModel):
    image_sha1: str
    palette: Palette
    vision: VisionAttributes

    def describe(self) -> str:
        v = self.vision
        other = " / ".join(f'"{t}"' for t in v.copy_text) or "none"
        packaging = " / ".join(f'"{t}"' for t in v.packaging_text) or "none"
        return "\n".join(
            [
                f"COLOUR (measured from pixels): {self.palette.summary()}",
                f"LAYOUT: {v.layout} Main subject: {v.subject_position}.",
                f"TYPOGRAPHY: {v.typeface_style}. Headline case: {v.headline_case}.",
                f'HEADLINE (verbatim): "{v.headline}". Other design copy: {other}. '
                f"Amount of design copy: {v.text_amount}.",
                f"TEXT PRINTED ON THE PRODUCT/PACKAGING (part of the product, not design copy): {packaging}.",
                f"EMOJI: {' '.join(v.emoji) if v.emoji else 'none'}. Punctuation: {v.punctuation_notes or 'nothing notable'}.",
                f"IMAGERY: {v.imagery}",
                f"LOGO: {v.logo or 'not visible'}",
                f"EFFECTS: {', '.join(v.effects) if v.effects else 'none'}",
                f"TONE: {v.tone}",
            ]
        )


def cache_path(path: str | Path) -> Path:
    sha = hashlib.sha1(Path(path).read_bytes()).hexdigest()
    return CACHE_DIR / f"{sha}.v{EXTRACT_VERSION}.json"


def analyse_draft(path: str | Path, *, refresh: bool = False) -> DraftAnalysis:
    path = Path(path)
    sha = hashlib.sha1(path.read_bytes()).hexdigest()
    cached = cache_path(path)
    if cached.exists() and not refresh:
        try:
            return DraftAnalysis.model_validate_json(cached.read_text(encoding="utf-8"))
        except ValueError:
            pass  # cache from an older schema: re-extract
    analysis = DraftAnalysis(image_sha1=sha, palette=extract_palette(path), vision=extract_vision(path))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")
    return analysis
