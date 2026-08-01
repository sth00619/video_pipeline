#!/usr/bin/env python3
"""V5 장식형 정보 장면 8종을 한 장의 사람 검토용 시트로 만든다."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "benchmark"
CELL = (480, 270)
MARGIN = 24
LABEL_HEIGHT = 30
SCENES = (
    ("01 port", "gemini_pro_diegetic_v5_bench_01_port", "bench_01_port.png"),
    ("02 retail", "gemini_pro_diegetic_v5_retail_solo_v2", "bench_02_retail.png"),
    ("03 classroom", "gemini_pro_diegetic_v5_bench_03_classroom", "bench_03_classroom.png"),
    ("04 classroom", "gemini_pro_diegetic_v5_bench_04_classroom2", "bench_04_classroom2.png"),
    ("05 weather", "gemini_pro_diegetic_v5_bench_05_weather", "bench_05_weather.png"),
    ("06 split", "gemini_pro_diegetic_v5_bench_06_split", "bench_06_split.png"),
    ("07 trade", "gemini_pro_diegetic_v5_bench_07_trade", "bench_07_trade.png"),
    ("08 data lab", "gemini_pro_diegetic_v5_bench_08_datalab_v2", "bench_08_datalab.png"),
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
    columns = 2
    rows = (len(SCENES) + columns - 1) // columns
    width = MARGIN + columns * (CELL[0] + MARGIN)
    height = MARGIN + rows * (CELL[1] + LABEL_HEIGHT + MARGIN)
    sheet = Image.new("RGB", (width, height), "#101827")
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    for index, (label, directory, filename) in enumerate(SCENES):
        source = OUT / directory / filename
        if not source.exists():
            raise FileNotFoundError(f"검토 시트 원본이 없습니다: {source}")
        col, row = index % columns, index // columns
        x = MARGIN + col * (CELL[0] + MARGIN)
        y = MARGIN + row * (CELL[1] + LABEL_HEIGHT + MARGIN)
        sheet.paste(_fit(source), (x, y))
        draw.rectangle((x, y, x + CELL[0] - 1, y + CELL[1] - 1), outline="#42d6ff", width=2)
        draw.text((x, y + CELL[1] + 5), label, font=font, fill="#eef8ff")
    target = OUT / "v5_diegetic_information_8_scene_contact_sheet.png"
    sheet.save(target, quality=95)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
