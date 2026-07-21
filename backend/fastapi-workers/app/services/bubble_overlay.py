"""Deterministic, transparent speech-bubble overlays for final video frames."""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "DejaVuSans.ttf"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def render_speech_bubble_overlay(
    text: str,
    *,
    canvas_size: tuple[int, int] = (1920, 1080),
    character_side: str = "right",
) -> Image.Image:
    """Return a transparent RGBA canvas containing one legible speech bubble.

    The graphic is generated after image-to-video, so exact Korean text is
    never supplied to a generative model or recompressed into a still image.
    """
    overlay = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    if not text:
        return overlay

    draw = ImageDraw.Draw(overlay)
    font = _font(34)
    max_width = int(canvas_size[0] * 0.28)
    words = str(text).strip().split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if line and draw.textlength(candidate, font=font) > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    rendered_text = "\n".join(lines[:3])

    left, top, right, bottom = draw.multiline_textbbox((0, 0), rendered_text, font=font, spacing=6)
    text_w, text_h = right - left, bottom - top
    padding_x, padding_y = 28, 20
    box_w, box_h = text_w + padding_x * 2, text_h + padding_y * 2
    bubble_x = int(canvas_size[0] * (0.24 if character_side == "left" else 0.58))
    bubble_y = int(canvas_size[1] * 0.19)
    bounds = (
        bubble_x - box_w // 2,
        bubble_y - box_h // 2,
        bubble_x + box_w // 2,
        bubble_y + box_h // 2,
    )
    draw.rounded_rectangle(bounds, radius=18, fill=(255, 255, 255, 255), outline=(20, 24, 28, 255), width=4)
    b_left, _, b_right, b_bottom = bounds
    if character_side == "left":
        tail = [(b_left + 34, b_bottom - 2), (b_left - 18, b_bottom + 28), (b_left + 12, b_bottom - 2)]
    else:
        tail = [(b_right - 34, b_bottom - 2), (b_right + 18, b_bottom + 28), (b_right - 12, b_bottom - 2)]
    draw.polygon(tail, fill=(255, 255, 255, 255), outline=(20, 24, 28, 255))
    draw.multiline_text((bubble_x, bubble_y), rendered_text, fill=(30, 30, 30, 255), font=font, anchor="mm", align="center", spacing=6)
    return overlay


def write_speech_bubble_overlay(output_path: str, text: str, *, character_side: str = "right") -> bool:
    """Write an FFmpeg-ready transparent PNG and report whether it is usable."""
    if not text:
        return False
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        render_speech_bubble_overlay(text, character_side=character_side).save(output_path, "PNG")
        return Path(output_path).exists() and Path(output_path).stat().st_size > 500
    except OSError:
        return False
