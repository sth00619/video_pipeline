"""V5 모델 비교용 contact sheet를 결정론적으로 만든다.

이미 생성된 결과만 배열한다. 이 스크립트는 이미지 API를 호출하지 않으며,
원본 이미지의 픽셀을 편집하지 않는다.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "out" / "v5_pilot" / "kospi_july_2026" / "v5_klein_vs_gemini_primary_comparison_sheet.png"

KLEIN_IMAGES = [
    ("01 port", ROOT / "out" / "benchmark" / "bfl_klein" / "bench_01_port.png"),
    ("02 retail", ROOT / "out" / "benchmark" / "bfl_klein" / "bench_02_retail.png"),
    ("03 classroom", ROOT / "out" / "benchmark" / "bfl_klein" / "bench_03_classroom.png"),
    ("04 classroom2", ROOT / "out" / "benchmark" / "bfl_klein" / "bench_04_classroom2.png"),
    ("05 weather", ROOT / "out" / "benchmark" / "bfl_klein" / "bench_05_weather.png"),
    ("06 split (legacy)", ROOT / "out" / "benchmark" / "bfl_klein" / "bench_06_split.png"),
    ("07 trade", ROOT / "out" / "benchmark" / "bfl_klein" / "bench_07_trade.png"),
    ("08 data_lab", ROOT / "out" / "benchmark" / "bfl_klein" / "bench_08_datalab.png"),
]

GEMINI_IMAGES = [
    (
        "01 data_lab | primary: holo map",
        ROOT
        / "out"
        / "v5_pilot"
        / "kospi_july_2026"
        / "generated_backgrounds"
        / "kospi_july_2026_scene_type_primary_text_v3"
        / "kospi_july_01.png",
    ),
    (
        "02 trade_calculator | primary: scale plinth",
        ROOT
        / "out"
        / "v5_pilot"
        / "kospi_july_2026"
        / "generated_backgrounds"
        / "kospi_july_2026_trade_primary_v5"
        / "kospi_july_02.png",
    ),
    (
        "03 risk_control_room | primary: gauge dial",
        ROOT
        / "out"
        / "v5_pilot"
        / "kospi_july_2026"
        / "generated_backgrounds"
        / "kospi_july_2026_risk_primary_v7"
        / "kospi_july_03.png",
    ),
]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _fit_image(path: Path, size: tuple[int, int]) -> Image.Image:
    if not path.exists():
        raise FileNotFoundError(f"비교 대상 이미지를 찾을 수 없습니다: {path}")
    source = Image.open(path).convert("RGB")
    fitted = Image.new("RGB", size, "#101827")
    source.thumbnail(size, Image.Resampling.LANCZOS)
    left = (size[0] - source.width) // 2
    top = (size[1] - source.height) // 2
    fitted.paste(source, (left, top))
    return fitted


def _draw_group(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    items: list[tuple[str, Path]],
    *,
    title: str,
    note: str,
    top: int,
    columns: int,
    cell_size: tuple[int, int],
) -> int:
    margin = 38
    gap = 20
    title_font = _font(32)
    note_font = _font(18)
    label_font = _font(18)
    draw.text((margin, top), title, font=title_font, fill="#f8fafc")
    draw.text((margin, top + 43), note, font=note_font, fill="#a9bacd")
    grid_top = top + 78
    for index, (label, path) in enumerate(items):
        row, column = divmod(index, columns)
        x = margin + column * (cell_size[0] + gap)
        y = grid_top + row * (cell_size[1] + 35)
        card = _fit_image(path, cell_size)
        canvas.paste(card, (x, y))
        draw.rectangle((x - 1, y - 1, x + cell_size[0], y + cell_size[1]), outline="#41546b", width=2)
        draw.text((x, y + cell_size[1] + 7), label, font=label_font, fill="#d9e4ef")
    rows = (len(items) + columns - 1) // columns
    return grid_top + rows * (cell_size[1] + 35)


def main() -> None:
    cell_size = (360, 203)
    width = 4 * cell_size[0] + 3 * 20 + 2 * 38
    height = 1_260
    canvas = Image.new("RGB", (width, height), "#0b1220")
    draw = ImageDraw.Draw(canvas)
    footer_font = _font(16)
    klein_bottom = _draw_group(
        canvas,
        draw,
        KLEIN_IMAGES,
        title="BFL FLUX.2 klein 9B | P1-a benchmark (8)",
        note="Earlier low-cost draft benchmark. Kept for comparison; not a final-character/background candidate.",
        top=30,
        columns=4,
        cell_size=cell_size,
    )
    gemini_bottom = _draw_group(
        canvas,
        draw,
        GEMINI_IMAGES,
        title="Gemini 3 Pro Image | primary-surface pilot winners (3)",
        note="Text is constrained to one designated physical prop; non-primary props are non-textual.",
        top=klein_bottom + 30,
        columns=3,
        cell_size=(480, 270),
    )
    draw.text(
        (38, min(gemini_bottom + 8, height - 28)),
        "Comparison only: AI text remains decorative. Exact verified values are rendered later by deterministic overlay.",
        font=footer_font,
        fill="#91a5bb",
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT, quality=95)
    print(OUTPUT)


if __name__ == "__main__":
    main()
