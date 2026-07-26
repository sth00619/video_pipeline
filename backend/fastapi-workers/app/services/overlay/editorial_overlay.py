"""Channel-owned overlay grammar rendered after image/video generation.

Every readable Korean string and financial number passes through this module.
It intentionally contains no provider call and returns geometry for provenance
and collision QA.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pydantic import BaseModel, Field, model_validator

from .style_profile import ChannelOverlayStyle, load_channel_overlay_style


OverlayKind = Literal[
    "speech", "shout", "burst", "cloud", "caption_chip", "article_callout",
    "badge", "title_card", "date_stamp", "chalk_note", "metaphor_label",
]

_WATERMARK = {"x": .78, "y": .0, "width": .22, "height": .12}
_SUBTITLE = {"x": .0, "y": .79, "width": 1.0, "height": .21}


class OverlaySlot(BaseModel):
    kind: OverlayKind
    text: str = Field(min_length=1, max_length=48)
    claim_type: Literal["reaction", "derived_hook", "verbatim_fact"] = "reaction"
    source_refs: list[str] = Field(default_factory=list)
    anchor: Literal["upper_left", "upper_right", "subject_gaze", "subject_hand", "target", "lower_left"] = "upper_left"
    target_bbox: tuple[float, float, float, float] | None = None
    text_style: Literal["solid", "outline", "gradient"] = "solid"
    tone: Literal["neutral", "danger", "benefit", "warning"] = "neutral"
    max_area_ratio: float = Field(default=.18, ge=.04, le=.18)
    spans: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_contract(self):
        if self.claim_type != "reaction" and not self.source_refs:
            raise ValueError("grounded overlay requires source_refs")
        if self.kind in {"cloud", "metaphor_label", "article_callout", "chalk_note"} and not self.target_bbox:
            raise ValueError("target-bound overlay requires target_bbox")
        if self.text_style == "gradient" and not (self.kind == "burst" and self.claim_type == "derived_hook"):
            raise ValueError("gradient is reserved for question burst overlays")
        return self


@dataclass
class OverlayRenderResult:
    image: Image.Image
    bbox: dict[str, int]
    style: str
    skipped_reason: str | None = None


def _font(size: int, style: ChannelOverlayStyle, kind: OverlayKind | None = None) -> ImageFont.FreeTypeFont:
    path = style.font_chalk if kind == "chalk_note" else style.font_display
    if path.is_file():
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _normalised_regions(regions: Iterable[dict] | None, size: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    result = []
    for region in regions or []:
        x, y, w, h = (float(region.get(key, 0)) for key in ("x", "y", "width", "height"))
        if max(abs(x), abs(y), abs(w), abs(h)) <= 1.001:
            x, y, w, h = x * size[0], y * size[1], w * size[0], h * size[1]
        result.append((round(x), round(y), round(x + w), round(y + h)))
    return result


def _intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _burst(bounds: tuple[int, int, int, int]) -> list[tuple[float, float]]:
    left, top, right, bottom = bounds; cx, cy = (left + right) / 2, (top + bottom) / 2
    rx, ry = (right - left) / 2, (bottom - top) / 2
    points = []
    for index in range(24):
        angle = -math.pi / 2 + index * math.pi / 12
        factor = 1.14 if index % 2 == 0 else .88
        points.append((cx + math.cos(angle) * rx * factor, cy + math.sin(angle) * ry * factor))
    return points


def _text_gradient(size: tuple[int, int], top=(255, 210, 48, 255), bottom=(255, 210, 48, 255)) -> Image.Image:
    image = Image.new("RGBA", size)
    draw = ImageDraw.Draw(image)
    height = max(1, size[1] - 1)
    for y in range(size[1]):
        t = y / height
        draw.line((0, y, size[0], y), fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return image


def _wrap_copy(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str | None:
    """Fit editorial copy to one or two intentional display lines.

    Korean hooks often have few spaces, so word wrapping alone is not enough.
    This keeps a large readable display face instead of silently shrinking a
    long phrase into an unreadable single line.
    """
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    raw_lines = [part.strip() for part in str(text).splitlines() if part.strip()]
    if len(raw_lines) > 2:
        return None
    if raw_lines and all(probe.textlength(line, font=font) <= max_width for line in raw_lines):
        return "\n".join(raw_lines)
    source = " ".join(raw_lines) if raw_lines else str(text).strip()
    words = source.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and probe.textlength(candidate, font=font) > max_width:
            lines.append(current); current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) <= 2 and lines:
        return "\n".join(lines)
    # One unbroken Korean phrase: split by glyph while preserving at most two
    # lines.  If it still does not fit, the caller tries the next font size.
    chars = list(source.replace(" ", ""))
    lines = []; current = ""
    for char in chars:
        candidate = current + char
        if current and probe.textlength(candidate, font=font) > max_width:
            lines.append(current); current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines) if 1 <= len(lines) <= 2 else None


def _fit_text(text: str, max_width: int, start: int, style: ChannelOverlayStyle, kind: OverlayKind) -> tuple[ImageFont.FreeTypeFont, str, tuple[int, int, int, int]]:
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for size in range(start, 23, -2):
        font = _font(size, style, kind)
        rendered = _wrap_copy(text, font, max_width)
        if not rendered:
            continue
        bbox = probe.multiline_textbbox((0, 0), rendered, font=font, spacing=max(6, size // 9), stroke_width=max(1, round(size * style.text_outline_ratio)))
        if bbox[2] - bbox[0] <= max_width:
            return font, rendered, bbox
    font = _font(24, style, kind)
    rendered = _wrap_copy(text, font, max_width) or str(text)
    return font, rendered, probe.multiline_textbbox((0, 0), rendered, font=font, spacing=6, stroke_width=2)


def _hex_rgba(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


def _draw_shape(layer: Image.Image, kind: OverlayKind, bounds: tuple[int, int, int, int], tone: str, style: ChannelOverlayStyle) -> tuple[int, int, int, int]:
    draw = ImageDraw.Draw(layer); outline = (16, 16, 24, 255)
    fill = {
        "danger": _hex_rgba(style.danger_color, 250),
        "benefit": _hex_rgba(style.benefit_color, 250),
        "warning": _hex_rgba(style.neutral_color, 250),
    }.get(tone, _hex_rgba(style.neutral_color, 250))
    width = max(5, round(layer.width * style.bubble_outline_ratio))
    # Chalk belongs directly on an authored board surface. A white card behind
    # it defeats the diegetic "background explanation" grammar and obscures
    # the cartoon scene, so only the chalk glyphs are rendered below.
    if kind == "chalk_note":
        return outline
    # Spoken reactions and question bursts are intentionally high-contrast
    # white shapes with coloured lettering. A red or yellow filled bubble
    # competes with the cartoon background and weakens the text hierarchy.
    if kind in {"speech", "shout", "burst", "cloud"}:
        fill = _hex_rgba(style.neutral_color, 250)
    elif kind in {"caption_chip", "title_card", "date_stamp"}:
        fill = (0, 0, 0, 238)
        outline = (0, 0, 0, 255)
    if kind == "burst":
        polygon = _burst(bounds); draw.polygon(polygon, fill=fill, outline=outline)
        draw.line(polygon + [polygon[0]], fill=outline, width=width, joint="curve")
    elif kind == "speech":
        left, top, right, bottom = bounds; radius = max(22, (right - left) // 12)
        # Tail points from the bubble toward the mascot occupying the opposite
        # side of the information surface.
        if (left + right) / 2 < layer.width / 2:
            tail = [(right - radius * 2, bottom - 2), (right - radius // 2, bottom + radius), (right - radius * 4, bottom - 2)]
        else:
            tail = [(left + radius * 2, bottom - 2), (left + radius // 2, bottom + radius), (left + radius * 4, bottom - 2)]
        draw.polygon(tail, fill=fill, outline=outline)
        draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline, width=width)
    elif kind == "cloud":
        left, top, right, bottom = bounds; radius = max(15, (right - left) // 10)
        draw.rounded_rectangle(bounds, radius=radius * 2, fill=fill, outline=outline, width=width)
        for cx, cy in ((left + radius, top + radius * 1.6), ((left + right) // 2, top + radius), (right - radius, top + radius * 1.5)):
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=fill, outline=outline, width=width)
    else:
        radius = 10 if kind in {"caption_chip", "date_stamp", "badge"} else 28
        draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline, width=width)
    return outline


def render_editorial_overlay(
    slot: OverlaySlot | dict,
    *,
    canvas_size: tuple[int, int] = (1920, 1080),
    subject_regions: Iterable[dict] | None = None,
    copy_regions: Iterable[dict] | None = None,
    watermark_region: dict | None = None,
    subtitle_region: dict | None = None,
    style_profile: str | None = None,
) -> OverlayRenderResult | None:
    """Render one collision-aware overlay, returning its exact pixel bounds."""
    contract = slot if isinstance(slot, OverlaySlot) else OverlaySlot.model_validate(slot)
    style = load_channel_overlay_style(style_profile)
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0)); draw = ImageDraw.Draw(layer)
    max_width = int(canvas_size[0] * (.46 if contract.kind == "title_card" else (style.speech_max_width_ratio if contract.kind in {"speech", "shout", "burst", "cloud"} else style.card_max_width_ratio)))
    font, rendered, text_bbox = _fit_text(contract.text, max_width, max(46, round(canvas_size[1] * style.display_font_ratio)), style, contract.kind)
    text_w, text_h = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
    pad_x, pad_y = round(canvas_size[0] * .022), round(canvas_size[1] * .02)
    width, height = text_w + pad_x * 2, text_h + pad_y * 2
    protected = _normalised_regions(subject_regions, canvas_size) + _normalised_regions(copy_regions, canvas_size)
    protected += _normalised_regions([watermark_region or _WATERMARK, subtitle_region or _SUBTITLE], canvas_size)
    if contract.target_bbox:
        x, y, w, h = contract.target_bbox
        if max(abs(x), abs(y), abs(w), abs(h)) <= 1.001:
            x, y, w, h = x * canvas_size[0], y * canvas_size[1], w * canvas_size[0], h * canvas_size[1]
        target = (round(x), round(y), round(x + w), round(y + h))
        if contract.kind == "chalk_note":
            candidates = [(target[0] + pad_x, target[1] + pad_y)]
        else:
            candidates = [(target[0], max(16, target[1] - height - 22)), (target[2] - width, target[3] + 22)]
    else:
        candidates = [(round(canvas_size[0] * .05), round(canvas_size[1] * .055)), (canvas_size[0] - width - round(canvas_size[0] * .05), round(canvas_size[1] * .15))]
    if contract.anchor in {"upper_right", "subject_gaze"}:
        candidates.reverse()
    best = None
    for x, y in candidates:
        bounds = (x, y, x + width, y + height)
        if bounds[0] < 0 or bounds[1] < 0 or bounds[2] > canvas_size[0] or bounds[3] > int(canvas_size[1] * .79):
            continue
        overlap = sum(_intersects(bounds, other) for other in protected)
        item = (overlap, bounds)
        if best is None or item[0] < best[0]: best = item
    if not best or best[0] > width * height * .15:
        return OverlayRenderResult(layer, {}, contract.kind, "protected_region_collision")
    bounds = best[1]; outline = _draw_shape(layer, contract.kind, bounds, contract.tone, style)
    position = (bounds[0] + pad_x, bounds[1] + pad_y - text_bbox[1])
    if contract.kind == "chalk_note":
        mask = Image.new("L", canvas_size, 0); md = ImageDraw.Draw(mask)
        md.multiline_text(position, rendered, font=font, fill=220, spacing=max(6, font.size // 9), stroke_width=1)
        mask = mask.filter(ImageFilter.GaussianBlur(.35)); chalk = Image.new("RGBA", canvas_size, (245, 245, 228, 0)); chalk.putalpha(mask)
        layer.alpha_composite(chalk)
    elif contract.text_style == "gradient":
        mask = Image.new("L", canvas_size, 0); md = ImageDraw.Draw(mask)
        md.multiline_text(position, rendered, font=font, fill=255, spacing=max(6, font.size // 9), stroke_width=max(3, round(font.size * style.text_outline_ratio)), stroke_fill=255)
        gradient = _text_gradient(canvas_size)
        gradient.putalpha(mask)
        layer.alpha_composite(gradient)
        draw.multiline_text(position, rendered, font=font, fill=(0, 0, 0, 0), spacing=max(6, font.size // 9), stroke_width=max(4, round(font.size * style.text_outline_ratio * 1.15)), stroke_fill=outline)
    else:
        fill = (
            _hex_rgba(style.benefit_color)
            if contract.kind in {"speech", "shout", "burst"}
            else ((255, 255, 255, 255) if contract.kind in {"caption_chip", "title_card", "date_stamp"} else (22, 22, 28, 255))
        )
        strong_outline = contract.kind in {"speech", "shout", "burst", "cloud", "caption_chip"}
        draw.multiline_text(
            position, rendered, font=font, fill=fill, spacing=max(6, font.size // 9),
            stroke_width=max(1, round(font.size * style.text_outline_ratio)) if strong_outline else max(1, font.size // 42),
            stroke_fill=outline if strong_outline or contract.text_style == "outline" else fill,
        )
    return OverlayRenderResult(layer, {"x": bounds[0], "y": bounds[1], "width": width, "height": height}, contract.kind)
