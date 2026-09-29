"""Layout / typography / copy / imagery via the Groq vision model (qwen/qwen3.8-27b).

Colours are deliberately NOT asked for; they come from palette.py.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ..config import settings
from ..llm import complete_json


class VisionAttributes(BaseModel):
    layout: str = Field(description="Composition: where things sit, whitespace, alignment, symmetry")
    subject_position: str = Field("", description="Where the main product/subject sits (centered, off-center left/right...)")
    typeface_style: str = Field(description="serif / sans-serif / rounded sans / condensed / script / handwritten; weights")
    headline_case: str = Field(description="lowercase / sentence case / title case / ALL CAPS / mixed")
    headline: str = Field("", description="The main headline, verbatim")
    copy_text: list[str] = Field(
        default_factory=list,
        description="All OTHER copy set on the design (subheads, body, tags, CTAs, handles), verbatim, reading order",
    )
    packaging_text: list[str] = Field(
        default_factory=list,
        description="Text that is part of a product/packaging/logo illustration, not design copy",
    )
    text_amount: str = Field("", description="Design copy only (excluding packaging): one line / a few lines / lots of text")
    emoji: list[str] = Field(default_factory=list)
    punctuation_notes: str = Field("", description="Exclamation marks, all-caps words, etc.")
    imagery: str = Field(description="Photos/illustrations/icons: what they show, style, crop, retouching, angle")
    logo: str = Field("", description="Logo presence and position")
    effects: list[str] = Field(default_factory=list, description="Gradients, shadows, textures, photo grading, stickers")
    tone: str = Field(description="Overall tone in a few words")

    @field_validator("copy_text", "packaging_text", "emoji", "effects", mode="before")
    @classmethod
    def _str_to_list(cls, v):
        # The model sometimes returns "a, b, c" for list fields; accept it rather than
        # spending a repair round-trip.
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v


PROMPT = """You are a senior art director cataloguing a design draft for a pre-client review.
Describe ONLY what is visibly in the image, precisely and neutrally. Do not judge it and do
not describe colours (colours are measured separately). The image is ONE single design canvas
exactly as it will be published: not a mockup, not a presentation board, no detail crops.

Return a JSON object with exactly these keys:
- layout: composition, alignment, whitespace, symmetry
- subject_position: where the main product/subject sits. Judge by where the subject's CENTRE
  point falls: "left third", "centre" or "right third", then add detail (tilt, cropping)
- typeface_style: serif / sans-serif / rounded sans / condensed / script / handwritten, plus weight
- headline_case: lowercase / sentence case / title case / ALL CAPS / mixed
- headline: the main headline, verbatim (join its lines with spaces)
- copy_text: list of all OTHER copy set on the design (subheads, body copy, tags/badges, CTAs,
  handles), verbatim, in reading order. Do NOT include text printed on a product, package or logo.
- packaging_text: list of text that is part of a product/packaging/logo illustration
- text_amount: amount of design copy excluding packaging text: one line / a few lines / lots of text
- emoji: list of emoji characters present (empty list if none)
- punctuation_notes: exclamation marks, all-caps words, notable punctuation
- imagery: start with the medium: "photography" or "vector illustration" (or both). Then what
  it shows, crop, retouching, product angle (front-on / three-quarter)
- logo: presence and position (e.g. top-left, bottom-right)
- effects: list of gradients, shadows, textures, stickers, photo grading, split-screen comparisons
- tone: overall tone in a few words"""


def _data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def extract_vision(path: str | Path) -> VisionAttributes:
    path = Path(path)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": _data_url(path)}},
            ],
        }
    ]
    # Vision has no fallback model on Groq, so pass model explicitly (skips text fallback).
    return complete_json(messages, VisionAttributes, model=settings.vision_model, temperature=0.0)
