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
    box = draw.textbbox((0, 0), headline, font=font, stroke_width=max(3, size // 11))
    x, y = int(width * 0.04), int(height * 0.035)
    # A solid panel avoids putting synthetic typography on a busy background.
    pad = int(size * 0.26)
    draw.rounded_rectangle((x - pad, y - pad, x + (box[2]-box[0]) + pad, y + (box[3]-box[1]) + pad), radius=pad, fill=(255, 255, 255, 238), outline=(*color, 255), width=max(4, size // 13))
    draw.text((x, y), headline, font=font, fill=(30, 25, 20, 255), stroke_width=1, stroke_fill=(255, 255, 255, 255))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output_path, quality=95)
    return output_path
