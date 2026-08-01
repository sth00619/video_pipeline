#!/usr/bin/env python3
"""V5 보정 전후의 항만·무역 장면을 비교 시트로 렌더링한다."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "benchmark"
CELL = (640, 360)
MARGIN = 28
HEADER = 36
ROWS = (
    ("01 port: continuity", "bench_01_port.png", "gemini_pro_strict_textless_v5_identity_continuity_01_port"),
    ("07 trade: mascot identity", "bench_07_trade.png", "gemini_pro_strict_textless_v5_identity_continuity_07_trade"),
)


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf"):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _fit(path: Path) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGB")
    image.thumbnail(CELL, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", CELL, "#0e1726")
    canvas.paste(image, ((CELL[0] - image.width) // 2, (CELL[1] - image.height) // 2))
    return canvas


def main() -> None:
    width = MARGIN * 3 + CELL[0] * 2
    height = MARGIN * 2 + HEADER + len(ROWS) * (CELL[1] + HEADER + MARGIN)
    sheet = Image.new("RGB", (width, height), "#101827")
    draw = ImageDraw.Draw(sheet)
    font = _font(19)
    small = _font(16)
    for column, label in enumerate(("before", "after: fixed contract")):
        x = MARGIN + column * (CELL[0] + MARGIN)
        draw.text((x, MARGIN), label, font=font, fill="#eef8ff")
    original_dir = OUT / "gemini_pro_strict_textless_v5_composition_8_scene_v3"
    for row, (label, filename, replacement_dir) in enumerate(ROWS):
        y = MARGIN + HEADER + row * (CELL[1] + HEADER + MARGIN)
        draw.text((MARGIN, y), label, font=small, fill="#a9c3d8")
        image_y = y + HEADER
        for column, path in enumerate((original_dir / filename, OUT / replacement_dir / filename)):
            x = MARGIN + column * (CELL[0] + MARGIN)
            sheet.paste(_fit(path), (x, image_y))
            draw.rectangle((x, image_y, x + CELL[0] - 1, image_y + CELL[1] - 1), outline="#42d6ff", width=2)
    target = OUT / "v5_identity_continuity_before_after.png"
    sheet.save(target, quality=95)
    print(target)


if __name__ == "__main__":
    main()
