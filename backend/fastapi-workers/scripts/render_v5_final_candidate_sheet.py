#!/usr/bin/env python3
"""V5 최종 후보 8씬(보정본 포함)을 한 장의 검토 시트로 렌더링한다."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "benchmark"
CELL = (480, 270)
MARGIN = 24
LABEL_HEIGHT = 30
SCENES = (
    ("01 port / right", "gemini_pro_strict_textless_v5_identity_continuity_01_port", "bench_01_port.png"),
    ("02 retail / left", "gemini_pro_strict_textless_v5_composition_8_scene_v3", "bench_02_retail.png"),
    ("03 classroom / right", "gemini_pro_strict_textless_v5_composition_8_scene_v3", "bench_03_classroom.png"),
    ("04 classroom / left", "gemini_pro_strict_textless_v5_composition_8_scene_v3", "bench_04_classroom2.png"),
    ("05 weather / right", "gemini_pro_strict_textless_v5_composition_8_scene_v3", "bench_05_weather.png"),
    ("06 split / center", "gemini_pro_strict_textless_v5_composition_8_scene_v3", "bench_06_split.png"),
    ("07 trade / left", "gemini_pro_strict_textless_v5_identity_continuity_07_trade", "bench_07_trade.png"),
    ("08 data lab / center", "gemini_pro_strict_textless_v5_composition_8_scene_v3", "bench_08_datalab.png"),
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
    columns = 2
    rows = 4
    sheet = Image.new("RGB", (MARGIN + columns * (CELL[0] + MARGIN), MARGIN + rows * (CELL[1] + LABEL_HEIGHT + MARGIN)), "#101827")
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    for index, (label, run_id, filename) in enumerate(SCENES):
        source = OUT / run_id / filename
        col, row = index % columns, index // columns
        x = MARGIN + col * (CELL[0] + MARGIN)
        y = MARGIN + row * (CELL[1] + LABEL_HEIGHT + MARGIN)
        sheet.paste(_fit(source), (x, y))
        draw.rectangle((x, y, x + CELL[0] - 1, y + CELL[1] - 1), outline="#42d6ff", width=2)
        draw.text((x, y + CELL[1] + 5), label, font=font, fill="#eef8ff")
    target = OUT / "v5_final_candidate_8_scene_review_sheet.png"
    sheet.save(target, quality=95)
    print(target)


if __name__ == "__main__":
    main()
