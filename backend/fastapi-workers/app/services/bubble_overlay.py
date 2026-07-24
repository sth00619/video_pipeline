"""Deterministic Korean speech-bubble overlays rendered after image generation."""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from app.services.text_style import draw_entertainment_text


_FONT_PATHS = (
    "/app/assets/fonts/Jalnan2TTF.ttf",
    "/app/assets/fonts/GmarketSansTTFBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
    "DejaVuSans-Bold.ttf",
)
_STYLES = {"round", "burst", "warning", "positive", "cloud", "shout"}


def _font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_PATHS:
        if os.path.exists(path) or "/" not in path:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    """Wrap Korean without relying on spaces; never truncate a message."""
    text = " ".join(str(text or "").strip().split())
    if not text:
        return []
    lines: list[str] = []
    line = ""
    for char in text:
        proposal = line + char
        if line and draw.textlength(proposal, font=font) > max_width:
            lines.append(line.rstrip())
            line = char.lstrip()
        else:
            line = proposal
    if line:
        lines.append(line.rstrip())
    return lines


def _intersects(left: int, top: int, right: int, bottom: int, region: tuple[int, int, int, int]) -> int:
    x1, y1, x2, y2 = region
    return max(0, min(right, x2) - max(left, x1)) * max(0, min(bottom, y2) - max(top, y1))


def _normalised_regions(regions: Iterable[dict | tuple | list] | None, canvas: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    result: list[tuple[int, int, int, int]] = []
    for raw in regions or []:
        if isinstance(raw, dict):
            x, y, width, height = raw.get("x", 0), raw.get("y", 0), raw.get("width", 0), raw.get("height", 0)
        else:
            x, y, width, height = raw
        if max(abs(float(x)), abs(float(y)), abs(float(width)), abs(float(height))) <= 1.001:
            x, y, width, height = x * canvas[0], y * canvas[1], width * canvas[0], height * canvas[1]
        result.append((round(x), round(y), round(x + width), round(y + height)))
    return result


def _burst_polygon(bounds: tuple[int, int, int, int], points: int = 16) -> list[tuple[float, float]]:
    left, top, right, bottom = bounds
    cx, cy = (left + right) / 2, (top + bottom) / 2
    rx, ry = (right - left) / 2, (bottom - top) / 2
    result = []
    for index in range(points * 2):
        theta = -math.pi / 2 + index * math.pi / points
        factor = 1.16 if index % 2 == 0 else .89
        result.append((cx + math.cos(theta) * rx * factor, cy + math.sin(theta) * ry * factor))
    return result


def _draw_cloud(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], fill, outline, width: int) -> None:
    left, top, right, bottom = bounds
    radius = max(18, (right - left) // 9)
    centers = ((left + radius, top + radius * 2), (left + radius * 3, top + radius), (left + radius * 5, top + radius * 1.5), (right - radius * 2, top + radius * 1.2), (right - radius, top + radius * 2.4))
    draw.rounded_rectangle(bounds, radius=radius * 2, fill=fill, outline=outline, width=width)
    for cx, cy in centers:
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=fill, outline=outline, width=width)


def _gradient(size: tuple[int, int], top: tuple[int, int, int, int], bottom: tuple[int, int, int, int]) -> Image.Image:
    result = Image.new("RGBA", size)
    draw = ImageDraw.Draw(result)
    height = max(1, size[1] - 1)
    for y in range(size[1]):
        factor = y / height
        color = tuple(round(a + (b - a) * factor) for a, b in zip(top, bottom))
        draw.line((0, y, size[0], y), fill=color)
    return result


def _draw_style(overlay: Image.Image, bounds: tuple[int, int, int, int], style: str) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    draw = ImageDraw.Draw(overlay)
    style = style if style in _STYLES else "round"
    outline = (24, 24, 28, 255)
    fill = (255, 255, 255, 255)
    stroke = max(4, round(overlay.width * .0025))
    if style == "burst":
        draw.polygon(_burst_polygon(bounds), fill=(255, 253, 240, 255), outline=outline)
        draw.line(_burst_polygon(bounds) + [_burst_polygon(bounds)[0]], fill=outline, width=stroke, joint="curve")
    elif style == "warning":
        draw.rounded_rectangle(bounds, radius=26, fill=fill, outline=(230, 0, 35, 255), width=stroke + 4)
        outline = (230, 0, 35, 255)
    elif style == "positive":
        mask = Image.new("L", overlay.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(bounds, radius=32, fill=255)
        overlay.paste(_gradient(overlay.size, (255, 245, 109, 255), (189, 240, 123, 255)), (0, 0), mask)
        draw = ImageDraw.Draw(overlay)
        draw.rounded_rectangle(bounds, radius=32, outline=outline, width=stroke)
    elif style == "cloud":
        _draw_cloud(draw, bounds, fill, outline, stroke)
    elif style == "shout":
        draw.rounded_rectangle(bounds, radius=20, fill=(255, 234, 65, 255), outline=(15, 15, 15, 255), width=stroke + 4)
        outline = (15, 15, 15, 255)
    else:
        draw.rounded_rectangle(bounds, radius=32, fill=fill, outline=outline, width=stroke)
    return fill, outline


def render_speech_bubble_overlay(
    text: str,
    *,
    canvas_size: tuple[int, int] = (1920, 1080),
    character_side: str = "right",
    style: str = "round",
    avoid_regions: Iterable[dict | tuple | list] | None = None,
    subtitle_safe_area_pct: float = 21,
    font_max_px: int = 96,
    font_min_px: int = 60,
) -> Image.Image | None:
    """Return a collision-avoiding transparent bubble or ``None`` if unsafe.

    All lettering is drawn here, not in a Gemini/Kling prompt.  The result is
    deterministic for identical inputs and safe to cache by scene fingerprint.
    """
    if not str(text or "").strip():
        return Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    overlay = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    max_width = round(canvas_size[0] * .36)
    font = None; lines: list[str] = []
    for size in range(max(font_min_px, font_max_px), font_min_px - 1, -2):
        candidate = _font(size)
        wrapped = _wrap(text, draw, candidate, max_width)
        if 1 <= len(wrapped) <= 2:
            font, lines = candidate, wrapped
            break
    if font is None:
        return None
    rendered = "\n".join(lines)
    text_box = draw.multiline_textbbox((0, 0), rendered, font=font, spacing=10, align="center", stroke_width=0)
    text_w, text_h = text_box[2] - text_box[0], text_box[3] - text_box[1]
    padding_x, padding_y = round(canvas_size[0] * .025), round(canvas_size[1] * .026)
    box_w, box_h = text_w + padding_x * 2, text_h + padding_y * 2
    safe_bottom = round(canvas_size[1] * (1 - max(0, min(subtitle_safe_area_pct, 45)) / 100))
    x_left = round(canvas_size[0] * .06); x_right = canvas_size[0] - box_w - x_left
    y_top = round(canvas_size[1] * .07); y_mid = round(canvas_size[1] * .28)
    preferred = [x_left, x_right] if character_side == "right" else [x_right, x_left]
    candidates = [(x, y) for y in (y_top, y_mid) for x in preferred] + [((canvas_size[0] - box_w) // 2, y_top)]
    regions = _normalised_regions(avoid_regions, canvas_size)
    best: tuple[int, int, int] | None = None
    for x, y in candidates:
        bounds = (x, y, x + box_w, y + box_h)
        if x < 0 or y < 0 or bounds[2] > canvas_size[0] or bounds[3] > safe_bottom:
            continue
        overlap = sum(_intersects(*bounds, region) for region in regions)
        candidate = (overlap, x, y)
        if best is None or candidate < best:
            best = candidate
    if best is None or best[0] > box_w * box_h * .15:
        return None
    _, x, y = best
    bounds = (x, y, x + box_w, y + box_h)
    _, outline = _draw_style(overlay, bounds, style)
    draw = ImageDraw.Draw(overlay)
    tail_y = min(safe_bottom - 2, bounds[3] + round(canvas_size[1] * .026))
    if x < canvas_size[0] // 2:
        tail = [(bounds[2] - padding_x * 1.5, bounds[3] - 2), (bounds[2] + padding_x * .3, tail_y), (bounds[2] - padding_x * .3, bounds[3] - 2)]
    else:
        tail = [(bounds[0] + padding_x * 1.5, bounds[3] - 2), (bounds[0] - padding_x * .3, tail_y), (bounds[0] + padding_x * .3, bounds[3] - 2)]
    draw.polygon(tail, fill=(255, 255, 255, 255), outline=outline)
    center = ((bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2)
    text_fill = (20, 20, 24, 255)
    text_stroke = 0
    if style == "shout":
        # The multi-line version retains the same three-layer treatment per
        # line, centred as one block.
        line_height = max(1, text_h // len(lines))
        first_y = center[1] - ((len(lines) - 1) * line_height // 2)
        for line_index, line in enumerate(lines):
            draw_entertainment_text(overlay, (center[0], first_y + line_index * line_height), line, font)
    else:
        draw.multiline_text(center, rendered, fill=text_fill, font=font, anchor="mm", align="center", spacing=10, stroke_width=text_stroke, stroke_fill=text_fill)
    return overlay


def write_speech_bubble_overlay(
    output_path: str,
    text: str,
    *,
    character_side: str = "right",
    style: str = "round",
    avoid_regions: Iterable[dict | tuple | list] | None = None,
    subtitle_safe_area_pct: float = 21,
    font_max_px: int = 96,
    font_min_px: int = 60,
) -> bool:
    """Write an FFmpeg-ready PNG and report whether a safe overlay exists."""
    if not text:
        return False
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        overlay = render_speech_bubble_overlay(
            text,
            character_side=character_side,
            style=style,
            avoid_regions=avoid_regions,
            subtitle_safe_area_pct=subtitle_safe_area_pct,
            font_max_px=font_max_px,
            font_min_px=font_min_px,
        )
        if overlay is None:
            return False
        overlay.save(output_path, "PNG")
        return Path(output_path).exists() and Path(output_path).stat().st_size > 500
    except OSError:
        return False
