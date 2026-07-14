"""Render Korean headline graphics deterministically, never through an image model."""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

COLORS = {"positive": (232, 90, 40), "negative": (30, 60, 200), "alert": (200, 20, 20), "neutral": (20, 120, 60)}
FONT_CANDIDATES = ("/app/assets/fonts/BlackHanSans-Regular.ttf", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def add_headline(image_path: str, output_path: str, headline: str, mood: str = "neutral") -> str:
    image = Image.open(image_path).convert("RGBA")
    if not headline:
        image.convert("RGB").save(output_path, quality=95)
        return output_path
    width, height = image.size
    size = max(38, int(height * 0.105))
    font = _font(size)
    draw = ImageDraw.Draw(image)
    color = COLORS.get(mood, COLORS["neutral"])
    x, y = int(width * 0.04), int(height * 0.035)
    # Keep the illustration unobstructed: show the headline directly on the
    # image instead of placing it inside a white card/panel.  A soft shadow
    # and dark outline preserve readability over both bright and dark scenes.
    shadow_offset = max(2, size // 24)
    stroke_width = max(3, size // 14)
    draw.text(
        (x + shadow_offset, y + shadow_offset), headline, font=font,
        fill=(0, 0, 0, 150), stroke_width=stroke_width, stroke_fill=(0, 0, 0, 150),
    )
    draw.text(
        (x, y), headline, font=font, fill=(*color, 255),
        stroke_width=stroke_width, stroke_fill=(18, 22, 32, 255),
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output_path, quality=95)
    return output_path
