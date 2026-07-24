"""Pillow-only timeline and bullet cards; all highlight geometry is known."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from app.models.article_evidence import NormalizedBBox
from app.services.annotate import rect
from ..article_scene import ScenePNGs
from ..frame_spec import FRAME_16_9, SafeAreas, subtitle_zone
from .schemas import BulletListCardSpec, TimelineCardSpec


class CardOverflowError(ValueError):
    code = "CARD_OVERFLOW"


class InfographicUnverifiedError(ValueError):
    code = "INFOGRAPHIC_UNVERIFIED"


@dataclass(frozen=True)
class TimelineStyle:
    bg: str = "#F7F4EF"
    date_color: str = "#111111"
    line_color: str = "#D96B2B"
    text_color: str = "#111111"
    accent_red: str = "#E5241D"
    date_font_px: int = 72
    body_font_px: int = 58
    line_gap: float = 1.22


def _font(size: int):
    for path in ("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", "/app/assets/fonts/NanumGothicBold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _union(items: Iterable[NormalizedBBox]) -> NormalizedBBox | None:
    values = list(items)
    if not values:
        return None
    left, top = min(v.x for v in values), min(v.y for v in values)
    right, bottom = max(v.x + v.width for v in values), max(v.y + v.height for v in values)
    return NormalizedBBox(x=left, y=top, width=right-left, height=bottom-top)


class InfographicRenderer:
    def _assert_refs(self, refs: Iterable[str], verified_facts: list[dict] | None) -> None:
        if not list(refs):
            raise InfographicUnverifiedError("INFOGRAPHIC_UNVERIFIED: source_refs required")
        available = {f"facts[{i}]" for i, _ in enumerate(verified_facts or [])}
        if available and any(ref not in available for ref in refs):
            raise InfographicUnverifiedError("INFOGRAPHIC_UNVERIFIED: unknown source_ref")

    def timeline(self, spec: TimelineCardSpec, verified_facts: list[dict] | None = None, size: tuple[int, int] = FRAME_16_9) -> ScenePNGs:
        for entry in spec.entries:
            self._assert_refs(entry.source_refs, verified_facts)
        width, height = size
        image = Image.new("RGB", size, "#F7F4EF")
        draw = ImageDraw.Draw(image)
        style = TimelineStyle()
        date_font, body_font = _font(style.date_font_px), _font(style.body_font_px)
        left, rail, text_x = int(width*.055), int(width*.27), int(width*.31)
        y, bottom = int(height*.10), subtitle_zone(height)[0] - 38
        draw.line((rail, y, rail, bottom), fill=style.line_color, width=10)
        emphasis: list[NormalizedBBox] = []
        for entry in spec.entries:
            draw.ellipse((rail-15, y+18, rail+15, y+48), fill=style.line_color)
            draw.text((left, y), entry.date_label, font=date_font, fill=style.date_color)
            line_y = y
            for index, text in enumerate(entry.lines):
                draw.text((text_x, line_y), text, font=body_font, fill=style.text_color)
                box = draw.textbbox((text_x, line_y), text, font=body_font)
                if entry.emphasis_line_range and entry.emphasis_line_range[0] <= index <= entry.emphasis_line_range[1]:
                    emphasis.append(NormalizedBBox(x=box[0]/width, y=box[1]/height, width=(box[2]-box[0])/width, height=(box[3]-box[1])/height))
                line_y += int(style.body_font_px * style.line_gap)
            y = line_y + int(height*.045)
            if y > bottom:
                raise CardOverflowError("CARD_OVERFLOW: timeline does not fit subtitle-safe frame")
        plain = image.copy()
        emphasized = image.copy()
        group = _union(emphasis)
        if group:
            rect(emphasized, group, color=style.accent_red, stroke_width=9)
        return ScenePNGs(plain=plain, emphasized=emphasized)

    def bullet_list(self, spec: BulletListCardSpec, verified_facts: list[dict] | None = None, size: tuple[int, int] = FRAME_16_9) -> ScenePNGs:
        self._assert_refs(spec.source_refs, verified_facts)
        width, height = size
        image = Image.new("RGB", size, "#F7F4EF")
        draw = ImageDraw.Draw(image)
        title_font, body_font = _font(76), _font(62)
        draw.text((int(width*.07), int(height*.10)), spec.title, font=title_font, fill="#111111")
        y, bottom = int(height*.27), subtitle_zone(height)[0] - 38
        selected: NormalizedBBox | None = None
        for index, text in enumerate(spec.bullets):
            draw.ellipse((int(width*.08), y+23, int(width*.10), y+43), fill="#D96B2B")
            draw.text((int(width*.13), y), text, font=body_font, fill="#111111")
            box = draw.textbbox((int(width*.13), y), text, font=body_font)
            if index == spec.emphasis_index:
                selected = NormalizedBBox(x=box[0]/width, y=box[1]/height, width=(box[2]-box[0])/width, height=(box[3]-box[1])/height)
            y += int(height*.115)
            if y > bottom:
                raise CardOverflowError("CARD_OVERFLOW: bullet list does not fit subtitle-safe frame")
        plain, emphasized = image.copy(), image.copy()
        if selected:
            rect(emphasized, selected, color="#E5241D", stroke_width=9)
        return ScenePNGs(plain=plain, emphasized=emphasized)
