"""Reusable post-production Korean text treatments.

This module intentionally accepts already validated screen strings.  It is not
used to place text inside image-generation prompts.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


def draw_entertainment_text(
    image: Image.Image,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    *,
    anchor: str = "mm",
    fill: tuple[int, int, int, int] = (255, 236, 65, 255),
    white_stroke: int = 5,
    outer_stroke: int = 11,
) -> None:
    """Draw the three-layer variety-show treatment deterministically.

    Pillow does not provide a portable glyph gradient mask for every Korean
    font build, so the preset keeps a high-contrast solid fill while retaining
    the requested white middle border and dark brown outer border.
    """
    draw = ImageDraw.Draw(image)
    outer = (62, 35, 25, 255)
    draw.text(xy, text, font=font, anchor=anchor, fill=fill, stroke_width=outer_stroke, stroke_fill=outer)
    draw.text(xy, text, font=font, anchor=anchor, fill=fill, stroke_width=white_stroke, stroke_fill=(255, 255, 255, 255))

