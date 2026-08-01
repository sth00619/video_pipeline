#!/usr/bin/env python3
"""V5 8씬 결과를 검토 시트로 렌더링한다."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "benchmark"
CELL = (480, 270)
MARGIN = 24
LABEL_HEIGHT = 30
SCENES = (
    ("01 port / right", "bench_01_port.png"),
    ("02 retail / left", "bench_02_retail.png"),
    ("03 classroom / right", "bench_03_classroom.png"),
    ("04 classroom / left", "bench_04_classroom2.png"),
    ("05 weather / right", "bench_05_weather.png"),
    ("06 split / center", "bench_06_split.png"),
    ("07 trade / left", "bench_07_trade.png"),
    ("08 data lab / center", "bench_08_datalab.png"),
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


def main() -> int:
    parser = argparse.ArgumentParser(description="V5 8씬 검토 시트 생성")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-name", default="v5_composition_8_scene_review_sheet.png")
    args = parser.parse_args()
    run_dir = OUT / args.run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"결과 폴더가 없습니다: {run_dir}")

    columns = 2
    rows = (len(SCENES) + columns - 1) // columns
    width = MARGIN + columns * (CELL[0] + MARGIN)
    height = MARGIN + rows * (CELL[1] + LABEL_HEIGHT + MARGIN)
    sheet = Image.new("RGB", (width, height), "#101827")
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    for index, (label, filename) in enumerate(SCENES):
        source = run_dir / filename
        col, row = index % columns, index // columns
        x = MARGIN + col * (CELL[0] + MARGIN)
        y = MARGIN + row * (CELL[1] + LABEL_HEIGHT + MARGIN)
        if source.is_file():
            sheet.paste(_fit(source), (x, y))
            border = "#42d6ff"
        else:
            draw.rectangle((x, y, x + CELL[0], y + CELL[1]), fill="#351d28")
            draw.text((x + 22, y + CELL[1] // 2 - 14), "NO IMAGE", font=font, fill="#ffb5b5")
            border = "#ff6b6b"
        draw.rectangle((x, y, x + CELL[0] - 1, y + CELL[1] - 1), outline=border, width=2)
        draw.text((x, y + CELL[1] + 5), label, font=font, fill="#eef8ff")
    target = OUT / args.output_name
    sheet.save(target, quality=95)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
