"""Deterministic Korean thumbnail typography.

Headline copy is rendered as layout data rather than an image-model prompt.  It
keeps the visual language consistent and, importantly, fails loudly when the
licensed display face is unavailable instead of silently falling back to a
different font.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field


Tone = Literal["white", "yellow", "red"]
TONE_RGB = {"white": (255, 255, 255), "yellow": (255, 214, 0), "red": (255, 59, 48)}


class FontProfileNotFoundError(RuntimeError):
    code = "TYPOGRAPHY_PROFILE_NOT_FOUND"


class HeadlineOverflowError(ValueError):
    code = "HEADLINE_OVERFLOW"


class Span(BaseModel):
    text: str = Field(min_length=1, max_length=32)
    tone: Tone = "white"
    scale: float = Field(default=1.0, ge=.88, le=1.22)


class HeadlineLineV3(BaseModel):
    """One display line, represented by independently coloured text spans."""

    spans: list[Span] = Field(min_length=1, max_length=4)

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)


class TypographyProfile(BaseModel):
    id: Literal["black_han_sans_v1"] = "black_han_sans_v1"
    family: str = "Black Han Sans"
    safe_margin_px: int = 32
    max_stroke_ratio: float = .055
    letter_spacing_em: float = -.02
    line_gap_ratio: float = .10
    min_font_px: int = 64

    @property
    def font_path(self) -> Path:
        # .../thumbnail/v2 -> app/assets/fonts
        return Path(__file__).resolve().parents[3] / "assets" / "fonts" / "BlackHanSans-Regular.ttf"

    def require_font(self) -> Path:
        path = self.font_path
        if not path.is_file():
            raise FontProfileNotFoundError(
                f"{self.code}: licensed Black Han Sans asset is missing at {path}"
            )
        return path

    @property
    def code(self) -> str:
        return "TYPOGRAPHY_PROFILE_NOT_FOUND"


BLACK_HAN_PROFILE = TypographyProfile()


@dataclass(frozen=True)
class TextMetrics:
    fill_ratios: tuple[float, ...]
    scale_ratios: tuple[float, ...]
    font_px: int
    canvas_width: int
    text_safe_bottom: bool
    profile_id: str

    @property
    def copy_fill(self) -> float:
        return max(self.fill_ratios, default=0.0)

    @property
    def minimum_fill(self) -> float:
        return min(self.fill_ratios, default=0.0)

    @property
    def minimum_scale(self) -> float:
        return min(self.scale_ratios, default=1.0)

    @property
    def mobile_font_px(self) -> float:
        return round(self.font_px * 320 / max(1, self.canvas_width), 2)


def load_display_font(size: int, profile: TypographyProfile = BLACK_HAN_PROFILE):
    return ImageFont.truetype(str(profile.require_font()), max(1, size))


def _line_image(line: HeadlineLineV3, font_px: int, profile: TypographyProfile) -> Image.Image:
    """Draw a line at its real alpha bounding box; no horizontal distortion."""
    fonts = [load_display_font(round(font_px * span.scale), profile) for span in line.spans]
    ascents = [font.getmetrics()[0] for font in fonts]
    descents = [font.getmetrics()[1] for font in fonts]
    stroke = max(2, min(round(font_px * profile.max_stroke_ratio), round(font_px * .065)))
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    widths = [
        probe.textlength(span.text, font=font) + max(0, len(span.text) - 1) * round(font.size * profile.letter_spacing_em)
        for span, font in zip(line.spans, fonts)
    ]
    shadow = max(3, round(font_px * .032))
    width = round(sum(widths) + stroke * 4 + shadow * 2)
    height = max(ascents) + max(descents) + stroke * 4 + shadow * 2
    image = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x = stroke * 2
    baseline = stroke * 2 + max(ascents)
    for span, font, ascent, text_width in zip(line.spans, fonts, ascents, widths):
        y = baseline - ascent
        character_x = x
        tracking = round(font.size * profile.letter_spacing_em)
        for char in span.text:
            draw.text(
                (character_x + shadow, y + shadow), char, font=font,
                fill=(0, 0, 0, 205), stroke_width=stroke + 1, stroke_fill=(0, 0, 0, 205),
            )
            draw.text(
                (character_x, y), char, font=font, fill=TONE_RGB[span.tone] + (255,),
                stroke_width=stroke, stroke_fill=(0, 0, 0, 255),
            )
            character_x += probe.textlength(char, font=font) + tracking
        x += text_width
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    return image.crop(bbox) if bbox else image


def _coerce_line(raw) -> HeadlineLineV3:
    if isinstance(raw, HeadlineLineV3):
        return raw
    # Backward-compatible input: old API sent ``text`` and ``tone`` per line.
    spans = getattr(raw, "spans", None)
    if spans:
        return HeadlineLineV3(spans=spans)
    return HeadlineLineV3(spans=[Span(text=raw.text, tone=getattr(raw, "tone", "white"))])


def render_headline(canvas: Image.Image, headline: list, zone, profile: TypographyProfile = BLACK_HAN_PROFILE) -> TextMetrics:
    profile.require_font()
    lines = [_coerce_line(line) for line in headline]
    available_width = zone.width - zone.pad * 2
    available_height = zone.height - zone.pad * 2
    # Use a bounded search. Actual alpha dimensions (not nominal font size)
    # decide whether the full multi-line shelf is safe.
    font_px = min(int(available_height / max(1, len(lines) * .92)), int(available_width / 2.3))
    min_px = profile.min_font_px
    rendered: list[Image.Image] = []
    while font_px >= min_px:
        rendered = [_line_image(line, font_px, profile) for line in lines]
        total_h = sum(item.height for item in rendered) + max(4, round(max(item.height for item in rendered) * profile.line_gap_ratio)) * (len(rendered) - 1)
        if total_h <= available_height and all(item.width <= available_width for item in rendered):
            break
        font_px -= 4
    else:
        raise HeadlineOverflowError("HEADLINE_OVERFLOW: planner must shorten a headline line")

    gap = max(4, round(max(item.height for item in rendered) * profile.line_gap_ratio))
    total_h = sum(item.height for item in rendered) + gap * (len(rendered) - 1)
    y = zone.top + zone.pad + max(0, (available_height - total_h) // 2)
    fills: list[float] = []
    scales: list[float] = []
    for line_image in rendered:
        x = zone.left + zone.pad
        canvas.alpha_composite(line_image, (x, y))
        fills.append(line_image.width / max(1, available_width))
        scales.append(1.0)
        y += line_image.height + gap
    return TextMetrics(
        tuple(fills), tuple(scales), font_px, canvas.width,
        text_safe_bottom=y - gap <= canvas.height - profile.safe_margin_px,
        profile_id=profile.id,
    )
