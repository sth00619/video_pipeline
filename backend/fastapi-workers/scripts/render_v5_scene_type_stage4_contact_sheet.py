#!/usr/bin/env python3
"""V5 씬 타입 3씬 실제 생성 결과를 사람 검토용 contact sheet로 만든다."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
GENERATED_ROOT = ROOT / "out/v5_pilot/kospi_july_2026/generated_backgrounds"
CELL = (640, 360)
MARGIN = 24
LABEL_HEIGHT = 58
SCENES = (
    ("01 · graph · data_lab", "kospi_july_01.png"),
    ("02 · graph · trade_calculator", "kospi_july_02.png"),
    ("03 · metric · risk_control_room", "kospi_july_03.png"),
)


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf"):
        if Path(candidate).is_file():
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
    parser = argparse.ArgumentParser(description="V5 3씬 contact sheet 생성")
    parser.add_argument("--run-id", default="kospi_july_2026_scene_type_stage4")
    parser.add_argument("--output-name", default="scene_type_stage4_contact_sheet.png")
    args = parser.parse_args()
    out_dir = GENERATED_ROOT / args.run_id
    columns = 2
    rows = 2
    sheet = Image.new(
        "RGB",
        (MARGIN + columns * (CELL[0] + MARGIN), MARGIN + rows * (CELL[1] + LABEL_HEIGHT + MARGIN)),
        "#101827",
    )
    draw = ImageDraw.Draw(sheet)
    font = _font(19)
    for index, (label, filename) in enumerate(SCENES):
        source = out_dir / filename
        if not source.is_file():
            raise FileNotFoundError(f"생성 이미지를 찾을 수 없습니다: {source}")
        col, row = index % columns, index // columns
        x = MARGIN + col * (CELL[0] + MARGIN)
        y = MARGIN + row * (CELL[1] + LABEL_HEIGHT + MARGIN)
        sheet.paste(_fit(source), (x, y))
        draw.rectangle((x, y, x + CELL[0] - 1, y + CELL[1] - 1), outline="#42d6ff", width=2)
        draw.text((x, y + CELL[1] + 12), label, font=font, fill="#eef8ff")
    target = out_dir / args.output_name
    sheet.save(target, quality=95)
    print(target)


if __name__ == "__main__":
    main()
