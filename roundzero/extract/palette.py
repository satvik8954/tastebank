"""Colour facts measured from pixels, never guessed by a model.

The vision model is unreliable on colour (it called the peach Crunchd draft "white"), so
palette, background colour and grain/noise texture come from here.
"""

from __future__ import annotations

import colorsys
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageStat
from pydantic import BaseModel

HUES = [  # (upper bound in degrees, name)
    (15, "red"), (40, "orange"), (50, "amber"), (66, "yellow"), (90, "lime"), (150, "green"),
    (185, "teal"), (210, "cyan"), (250, "blue"), (280, "indigo"), (320, "purple"), (345, "pink"), (360, "red"),
]


class Swatch(BaseModel):
    hex: str
    share: float  # fraction of pixels
    description: str
    saturation: float  # chroma, 0..1
    lightness: float


class Palette(BaseModel):
    swatches: list[Swatch]
    background: Swatch
    overall: str  # e.g. "muted / pastel, light"
    mean_saturation: float
    grain_detected: bool
    noise_level: float

    def summary(self) -> str:
        sw = "; ".join(f"{s.hex} {s.description} ({s.share:.0%})" for s in self.swatches)
        grain = "film grain / noise texture detected" if self.grain_detected else "no grain texture (clean, flat)"
        return (
            f"Background: {self.background.hex} ({self.background.description}). "
            f"Dominant colours: {sw}. Overall palette: {self.overall}. Texture: {grain}."
        )


def describe(rgb: tuple[int, int, int]) -> tuple[str, float, float]:
    """Name a colour. Uses chroma (max-min), not HLS saturation: HLS calls pale peach
    "saturated", which is perceptually backwards."""
    r, g, b = (c / 255 for c in rgb)
    h, l, _ = colorsys.rgb_to_hls(r, g, b)
    chroma = max(r, g, b) - min(r, g, b)
    if l < 0.1:
        return "near-black", chroma, l
    if l > 0.85 and 0.03 < chroma < 0.12:
        # Tinted whites matter to clients: ice-blue reads "clinical", cream reads "warm".
        cool = 150 <= h * 360 <= 280
        return ("cool off-white (icy blue tint)" if cool else "warm off-white (cream tint)"), chroma, l
    if l > 0.94 and chroma <= 0.03:
        return "near-white", chroma, l
    if chroma < 0.08:
        return ("light grey" if l > 0.6 else "dark grey" if l < 0.35 else "grey"), chroma, l
    hue = next(name for bound, name in HUES if h * 360 <= bound)
    if chroma > 0.6:
        tone = "vivid/neon"
    elif chroma > 0.4:
        tone = "saturated"
    elif l > 0.68:
        tone = "pastel"
    else:
        tone = "muted"
    shade = "light " if l > 0.75 else "dark " if l < 0.3 else ""
    return f"{tone} {shade}{hue}".strip(), chroma, l


def _hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb[:3])


def _swatch(rgb, share) -> Swatch:
    desc, s, l = describe(tuple(rgb[:3]))
    return Swatch(hex=_hex(rgb), share=round(share, 3), description=desc, saturation=round(s, 2), lightness=round(l, 2))


def _dist(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def extract_palette(path: str | Path, n_colors: int = 16, max_swatches: int = 6) -> Palette:
    img = Image.open(path).convert("RGB")
    small = img.copy()
    small.thumbnail((256, 256))

    # Octree keeps small vivid areas distinct (median-cut averages them into mud); then
    # merge near-duplicates such as gradient steps and anti-aliasing.
    quant = small.quantize(colors=n_colors, method=Image.Quantize.FASTOCTREE)
    pal = quant.getpalette()
    clusters: list[list] = []  # [rgb, count]
    for count, idx in sorted(quant.getcolors(), reverse=True):
        rgb = tuple(pal[idx * 3 : idx * 3 + 3])
        near = next((c for c in clusters if _dist(c[0], rgb) < 40), None)
        if near:
            near[1] += count
        else:
            clusters.append([rgb, count])
    total = sum(c for _, c in clusters)
    clusters.sort(key=lambda c: -c[1])
    swatches = [_swatch(rgb, c / total) for rgb, c in clusters if c / total >= 0.015][:max_swatches]

    # Background = most common colour along the border.
    w, h = small.size
    border = [small.getpixel((x, y)) for x in range(w) for y in (0, 1, h - 2, h - 1)]
    border += [small.getpixel((x, y)) for y in range(h) for x in (0, 1, w - 2, w - 1)]
    bg_rgb = max(set(border), key=border.count) if len(set(border)) < len(border) / 3 else _mean(border)
    background = _swatch(bg_rgb, 1.0)

    # Character of the chromatic colours (ignore black/white/grey), plus the background tone.
    chromatic = [
        s for s in swatches
        if not s.description.startswith(("near-", "grey", "light grey", "dark grey", "cool off-white", "warm off-white"))
    ]
    weight = max(sum(s.share for s in chromatic), 1e-6)
    mean_sat = sum(s.saturation * s.share for s in chromatic) / weight if chromatic else 0.0
    vivid = sum(s.share for s in chromatic if s.saturation > 0.6)
    if not chromatic:
        overall = "neutral / monochrome"
    elif vivid / weight > 0.4 or mean_sat > 0.55:
        overall = "bold, high-saturation / neon"
    elif mean_sat < 0.35:
        overall = "muted / pastel" if background.lightness > 0.6 else "muted, deep"
    else:
        overall = "moderately saturated"
    overall += ", dark background" if background.lightness < 0.25 else ", light background" if background.lightness > 0.7 else ""

    noise = _noise_level(img)
    return Palette(
        swatches=swatches,
        background=background,
        overall=overall,
        mean_saturation=round(mean_sat, 2),
        grain_detected=noise > GRAIN_THRESHOLD,
        noise_level=round(noise, 2),
    )


def _mean(pixels):
    n = len(pixels)
    return tuple(sum(p[i] for p in pixels) // n for i in range(3))


GRAIN_THRESHOLD = 0.6


def _noise_level(img: Image.Image, block: int = 24) -> float:
    """Pixel-level noise on the FLAT parts of the image.

    High-frequency energy = |image - lightly blurred image|, averaged per block. Text and
    edges make some blocks noisy, so take the 25th percentile: grain overlays raise every
    flat block, clean flat or gradient designs stay near zero.
    """
    gray = img.convert("L")
    diff = ImageChops.difference(gray, gray.filter(ImageFilter.GaussianBlur(1.2)))
    w, h = diff.size
    means = sorted(
        ImageStat.Stat(diff.crop((x, y, x + block, y + block))).mean[0]
        for x in range(0, w - block + 1, block)
        for y in range(0, h - block + 1, block)
    )
    return means[len(means) // 4] if means else 0.0
