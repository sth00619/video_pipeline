"""Resolution-independent, deterministic editorial annotations."""
from __future__ import annotations

import math
import os
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFont

from app.models.article_evidence import EvidenceAnnotation, NormalizedBBox


DEFAULT_RED = "#E60023"
_FONT_CANDIDATES = (
    "/app/assets/fonts/GmarketSansTTFBold.ttf",
    "/app/assets/fonts/Jalnan2TTF.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
    "DejaVuSans-Bold.ttf",
)


def _font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path) or "/" not in path:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _bbox(value: NormalizedBBox | list[float] | tuple[float, float, float, float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    bbox = value if isinstance(value, NormalizedBBox) else NormalizedBBox.from_list(value)
    width, height = size
    return (
        round(bbox.x * width),
        round(bbox.y * height),
        round((bbox.x + bbox.width) * width),
        round((bbox.y + bbox.height) * height),
    )


def underline(
    layer: Image.Image,
    bbox_list: Iterable[NormalizedBBox | list[float]],
    color: str = DEFAULT_RED,
    stroke_width: int = 5,
    jitter_seed: int | None = None,
    offset: int = 0,
) -> None:
    """Underline each DOM Range rect; no random jitter is used by default."""
    draw = ImageDraw.Draw(layer)
    width, height = layer.size
    for item in bbox_list:
        left, top, right, bottom = _bbox(item, (width, height))
        y = min(height - 1, max(top + 1, bottom + int(offset)))
        draw.line((left, y, right, y), fill=color, width=stroke_width, joint="curve")


def ellipse(layer: Image.Image, bbox: NormalizedBBox | list[float], color: str = DEFAULT_RED, stroke_width: int = 10) -> None:
    ImageDraw.Draw(layer).ellipse(_bbox(bbox, layer.size), outline=color, width=stroke_width)


def rect(layer: Image.Image, bbox: NormalizedBBox | list[float], color: str = DEFAULT_RED, stroke_width: int = 8, rounded: bool = False) -> None:
    box = _bbox(bbox, layer.size)
    draw = ImageDraw.Draw(layer)
    if rounded:
        draw.rounded_rectangle(box, radius=max(stroke_width * 2, 12), outline=color, width=stroke_width)
    else:
        draw.rectangle(box, outline=color, width=stroke_width)


def dashed_ellipse(layer: Image.Image, bbox: NormalizedBBox | list[float], color: str = DEFAULT_RED, stroke_width: int = 10, dash_deg: int = 14, gap_deg: int = 10) -> None:
    draw = ImageDraw.Draw(layer)
    box = _bbox(bbox, layer.size)
    angle = 0
    while angle < 360:
        draw.arc(box, angle, min(360, angle + dash_deg), fill=color, width=stroke_width)
        angle += dash_deg + gap_deg


def arrow(layer: Image.Image, from_xy: tuple[float, float], to_xy: tuple[float, float], color: str = DEFAULT_RED, stroke_width: int = 8) -> None:
    draw = ImageDraw.Draw(layer)
    width, height = layer.size
    start = (round(from_xy[0] * width), round(from_xy[1] * height))
    end = (round(to_xy[0] * width), round(to_xy[1] * height))
    draw.line((start, end), fill=color, width=stroke_width)
    theta = math.atan2(end[1] - start[1], end[0] - start[0])
    head = max(22, stroke_width * 3)
    left = (end[0] - head * math.cos(theta - math.pi / 6), end[1] - head * math.sin(theta - math.pi / 6))
    right = (end[0] - head * math.cos(theta + math.pi / 6), end[1] - head * math.sin(theta + math.pi / 6))
    draw.polygon([end, left, right], fill=color)


def highlighter(layer: Image.Image, bbox: NormalizedBBox | list[float], color: str = "#FFE146", alpha: float = 0.35) -> None:
    left, top, right, bottom = _bbox(bbox, layer.size)
    rgb = color.lstrip("#")
    fill = tuple(int(rgb[i:i + 2], 16) for i in (0, 2, 4)) + (round(max(0, min(alpha, 1)) * 255),)
    ImageDraw.Draw(layer, "RGBA").rounded_rectangle((left, top, right, bottom), radius=8, fill=fill)


def highlight_multiply(base: Image.Image, bboxes: Iterable[NormalizedBBox | list[float]], color: str = "#39E65A", pad_x: int = 6, pad_y: int = 4) -> Image.Image:
    """Apply a crisp editorial highlighter without washing out black glyphs."""
    layer = Image.new("RGB", base.size, "white")
    draw = ImageDraw.Draw(layer)
    for item in bboxes:
        left, top, right, bottom = _bbox(item, base.size)
        draw.rounded_rectangle((left - pad_x, top - pad_y, right + pad_x, bottom + pad_y), radius=max(4, (bottom - top) // 3), fill=color)
    return ImageChops.multiply(base.convert("RGB"), layer)


def callout_block(layer: Image.Image, text: str, anchor: tuple[float, float], style: str = "red_block") -> None:
    """Draw a fixed-label red block for already verified screen text."""
    if style != "red_block":
        raise ValueError(f"unsupported callout style: {style}")
    draw = ImageDraw.Draw(layer)
    width, height = layer.size
    font = _font(max(28, round(width * 0.038)))
    max_width = round(width * 0.42)
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words or [text]:
        proposal = f"{current} {word}".strip()
        if current and draw.textlength(proposal, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = proposal
    if current:
        lines.append(current)
    lines = lines[:3]
    rendered = "\n".join(lines)
    bbox = draw.multiline_textbbox((0, 0), rendered, font=font, spacing=8, stroke_width=0)
    padding_x, padding_y = round(width * 0.014), round(height * 0.014)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = min(max(round(anchor[0] * width), 0), width - text_w - padding_x * 2)
    y = min(max(round(anchor[1] * height), 0), height - text_h - padding_y * 2)
    draw.rectangle((x, y, x + text_w + padding_x * 2, y + text_h + padding_y * 2), fill=(230, 0, 35, 255))
    draw.multiline_text((x + padding_x, y + padding_y - bbox[1]), rendered, font=font, fill="white", spacing=8, stroke_width=1, stroke_fill="white")


def render_annotations(canvas_size: tuple[int, int], annotations: Iterable[EvidenceAnnotation | dict], supersample: int = 4) -> Image.Image:
    """Render all primitives to a transparent layer with deterministic AA."""
    if supersample < 1:
        raise ValueError("supersample must be at least one")
    high_size = (canvas_size[0] * supersample, canvas_size[1] * supersample)
    layer = Image.new("RGBA", high_size, (0, 0, 0, 0))
    for raw in annotations:
        item = raw if isinstance(raw, EvidenceAnnotation) else EvidenceAnnotation.model_validate(raw)
        width = item.stroke_width * supersample
        if item.type == "underline":
            underline(layer, item.bboxes or [item.bbox], item.color, width)
        elif item.type == "ellipse":
            ellipse(layer, item.bbox, item.color, width)
        elif item.type == "rect":
            rect(layer, item.bbox, item.color, width)
        elif item.type == "dashed_ellipse":
            dashed_ellipse(layer, item.bbox, item.color, width)
        elif item.type == "arrow":
            arrow(layer, item.from_xy, item.to_xy, item.color, width)
        elif item.type == "highlighter":
            highlighter(layer, item.bbox, item.color)
    return layer.resize(canvas_size, Image.Resampling.LANCZOS) if supersample > 1 else layer
