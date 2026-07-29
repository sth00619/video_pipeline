#!/usr/bin/env python3
"""P1 벤치마크의 두 모델 결과를 비용 없이 한 장의 비교 시트로 렌더링한다."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "benchmark"
SCENE_IDS = [
    "bench_01_port",
    "bench_02_retail",
    "bench_03_classroom",
    "bench_04_classroom2",
    "bench_05_weather",
    "bench_06_split",
    "bench_07_trade",
    "bench_08_datalab",
]
CELL = (480, 270)
HEADER_HEIGHT = 48
ROW_GAP = 28
MARGIN = 28


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    """환경별 글꼴 차이에도 비교 라벨이 보이도록 순차적으로 찾는다."""
    candidates = (
        ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf"]
        if bold
        else ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"]
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _fit(path: Path) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGB")
    image.thumbnail(CELL, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", CELL, "#0f1720")
    offset = ((CELL[0] - image.width) // 2, (CELL[1] - image.height) // 2)
    canvas.paste(image, offset)
    return canvas


def main() -> None:
    width = MARGIN * 3 + CELL[0] * 2
    height = MARGIN * 2 + HEADER_HEIGHT + len(SCENE_IDS) * (CELL[1] + ROW_GAP) - ROW_GAP
    sheet = Image.new("RGB", (width, height), "#111827")
    draw = ImageDraw.Draw(sheet)
    header_font = _font(22, bold=True)
    label_font = _font(16, bold=True)
    detail_font = _font(13)
    columns = [
        (OUT / "bfl_klein", "BFL FLUX.2 KLEIN 9B — draft lane", "#d28a31"),
        (OUT / "gemini_pro", "GEMINI 3 PRO IMAGE — final candidate", "#65c4e8"),
    ]

    for column_index, (_, title, color) in enumerate(columns):
        x = MARGIN + column_index * (CELL[0] + MARGIN)
        draw.rounded_rectangle((x, MARGIN, x + CELL[0], MARGIN + HEADER_HEIGHT), radius=8, fill=color)
        draw.text((x + 12, MARGIN + 13), title, fill="#071018", font=header_font)

    for row, scene_id in enumerate(SCENE_IDS):
        y = MARGIN + HEADER_HEIGHT + row * (CELL[1] + ROW_GAP)
        draw.text((4, y + 5), f"{row + 1:02d}", fill="#a6b4c6", font=label_font)
        for column_index, (directory, _, color) in enumerate(columns):
            x = MARGIN + column_index * (CELL[0] + MARGIN)
            image_path = directory / f"{scene_id}.png"
            sheet.paste(_fit(image_path), (x, y))
            draw.rectangle((x, y, x + CELL[0] - 1, y + CELL[1] - 1), outline=color, width=2)
            draw.rectangle((x, y + CELL[1] - 24, x + 152, y + CELL[1]), fill="#080d13")
            draw.text((x + 8, y + CELL[1] - 19), scene_id.replace("bench_", ""), fill="#e5edf7", font=detail_font)

    target = OUT / "v5_p1_klein_vs_gemini_contact_sheet.png"
    sheet.save(target, quality=95)
    print(target)


if __name__ == "__main__":
    main()
