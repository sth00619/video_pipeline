"""Compatibility exports for the v2 display typography module."""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageFont
from .brief import ThumbnailBriefV2
from .typography import (
    BLACK_HAN_PROFILE,
    HeadlineOverflowError,
    TextMetrics,
    load_display_font,
    render_headline,
)


@dataclass(frozen=True)
class Zone:
    left: int
    top: int
    width: int
    height: int
    pad: int


def _font(size: int):
    """Bubble/badge type uses the same licensed profile as headlines."""
    return load_display_font(size, BLACK_HAN_PROFILE)


def draw(canvas: Image.Image, brief: ThumbnailBriefV2, zone: Zone) -> TextMetrics:
    return render_headline(canvas, brief.headline, zone, BLACK_HAN_PROFILE)
