"""Licensed deterministic display typography for factual cartoon surfaces."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


FONT_ROOT = Path(__file__).resolve().parents[2] / "assets" / "fonts"
DISPLAY_FONT = FONT_ROOT / "BlackHanSans-Regular.ttf"
DISPLAY_LICENSE = FONT_ROOT / "LICENSES" / "BlackHanSans-OFL-1.1.txt"


@dataclass(frozen=True)
class TextRole:
    minimum_px: int
    outer_stroke_px: int
    inner_stroke_px: int


TEXT_ROLES = {
    "hero": TextRole(66, 7, 3),
    "title": TextRole(44, 5, 2),
    "support": TextRole(30, 3, 1),
}


def ensure_display_font_license() -> Path:
    """Return the reviewed font or fail closed instead of using host fonts."""
    if not DISPLAY_FONT.is_file() or not DISPLAY_LICENSE.is_file():
        raise RuntimeError("licensed display font bundle is incomplete")
    return DISPLAY_FONT


def display_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ensure_display_font_license()), max(1, size))


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, stroke: int) -> int:
    box = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    return box[2] - box[0]


def draw_display_text(
    image: Image.Image,
    position: tuple[int, int],
    text: str,
    *,
    role: str,
    fill: str,
    accent_spans: Iterable[tuple[int, int, str]] = (),
    align: str = "left",
    scale: float = 1.0,
    stroke_scale: float = 1.0,
) -> tuple[int, int, int, int]:
    """Draw double-outlined display text, with optional exact character spans.

    Span geometry uses the same font metrics as the base string.  This keeps
    an emphasized word attached to its sentence through perspective warping,
    rather than treating it as an independent UI label.
    """
    spec = TEXT_ROLES[role]
    scale = max(1.0, float(scale))
    stroke_scale = max(1.0, float(stroke_scale))
    font = display_font(round(spec.minimum_px * scale))
    draw = ImageDraw.Draw(image)
    outer = "#071A3A"
    inner = "#FFF4D6"
    outer_stroke = max(1, round(spec.outer_stroke_px * scale * stroke_scale))
    inner_stroke = max(1, round(spec.inner_stroke_px * scale * stroke_scale))
    width = _text_width(draw, text, font, outer_stroke)
    x, y = position
    if align == "center":
        x -= width // 2
    elif align == "right":
        x -= width
    draw.text((x, y), text, font=font, fill=fill, stroke_width=outer_stroke, stroke_fill=outer)
    draw.text((x, y), text, font=font, fill=fill, stroke_width=inner_stroke, stroke_fill=inner)
    for start, end, color in accent_spans:
        if not (0 <= start < end <= len(text)):
            continue
        prefix = text[:start]
        token = text[start:end]
        token_x = x + int(draw.textlength(prefix, font=font))
        draw.text((token_x, y), token, font=font, fill=color, stroke_width=outer_stroke, stroke_fill=outer)
        draw.text((token_x, y), token, font=font, fill=color, stroke_width=inner_stroke, stroke_fill=inner)
    box = draw.textbbox((x, y), text, font=font, stroke_width=outer_stroke)
    return tuple(int(value) for value in box)
