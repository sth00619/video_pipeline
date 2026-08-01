#!/usr/bin/env python3
"""V5 오염 수정 재검증용 참조·결과 검토 시트를 만든다. 외부 API 호출은 없다."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
CELL = (480, 270)
MARGIN = 24
LABEL_HEIGHT = 30
SOURCES = (
    ("reference · character", OUT / "references" / "character_reference_v4_identity_clean.png"),
    ("reference · style", OUT / "references" / "style_reference_v4_medium_clean.png"),
    ("reference · layout review only", OUT / "references" / "layout_reference_v2_textless.png"),
    ("08 data lab · strict textless", OUT / "benchmark" / "gemini_pro_strict_textless_v5_revalidation_08_datalab" / "bench_08_datalab.png"),
    ("03 classroom · strict textless", OUT / "benchmark" / "gemini_pro_strict_textless_v5_revalidation_03_classroom" / "bench_03_classroom.png"),
    ("06 split · strict textless", OUT / "benchmark" / "gemini_pro_strict_textless_v5_revalidation_06_split" / "bench_06_split.png"),
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
    rows = (len(SOURCES) + columns - 1) // columns
    width = MARGIN + columns * (CELL[0] + MARGIN)
    height = MARGIN + rows * (CELL[1] + LABEL_HEIGHT + MARGIN)
    sheet = Image.new("RGB", (width, height), "#101827")
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    for index, (label, source) in enumerate(SOURCES):
        if not source.is_file():
            raise FileNotFoundError(f"검토 원본이 없습니다: {source}")
        col, row = index % columns, index // columns
        x = MARGIN + col * (CELL[0] + MARGIN)
        y = MARGIN + row * (CELL[1] + LABEL_HEIGHT + MARGIN)
        sheet.paste(_fit(source), (x, y))
        draw.rectangle((x, y, x + CELL[0] - 1, y + CELL[1] - 1), outline="#42d6ff", width=2)
        draw.text((x, y + CELL[1] + 5), label, font=font, fill="#eef8ff")
    target = OUT / "benchmark" / "v5_strict_textless_revalidation_review_sheet.png"
    sheet.save(target, quality=95)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
