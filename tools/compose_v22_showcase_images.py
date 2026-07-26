"""Regenerate the four approved-style showcase plates with v3 P0 grammar.

Plates supply only scene art. This deterministic script owns every readable
Korean glyph, value, bar, and graph mark.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FONT = Path(__file__).resolve().parents[1] / "backend" / "fastapi-workers" / "app" / "assets" / "fonts" / "BlackHanSans-Regular.ttf"
LICENSE = FONT.parent / "LICENSES" / "BlackHanSans-OFL-1.1.txt"
NAVY = "#071A3A"; CREAM = "#FFF4D6"; YELLOW = "#F6BE28"; PAPER_GRAY = "#A99F8A"


def _font(size: int):
    if not FONT.is_file() or not LICENSE.is_file():
        raise RuntimeError("licensed display font bundle missing")
    return ImageFont.truetype(str(FONT), size)


def _center(draw: ImageDraw.ImageDraw, box, text: str, size: int, fill: str, *, stroke: int = 0, stroke_fill: str = NAVY):
    face = _font(size); bounds = draw.multiline_textbbox((0, 0), text, font=face, align="center", spacing=max(4, size // 8), stroke_width=stroke)
    x = box[0] + (box[2] - box[0] - (bounds[2] - bounds[0])) / 2; y = box[1] + (box[3] - box[1] - (bounds[3] - bounds[1])) / 2
    draw.multiline_text((x, y), text, font=face, fill=fill, align="center", spacing=max(4, size // 8), stroke_width=stroke, stroke_fill=stroke_fill)


def _ink_bar(draw: ImageDraw.ImageDraw, rect, fill: str, width: int):
    left, top, right, bottom = rect
    points = [(left - 2, bottom), (left + 1, top + 2), (right + 2, top - 1), (right - 1, bottom)]
    draw.polygon(points, fill=fill); draw.line(points + [points[0]], fill=NAVY, width=width, joint="curve")
    for x in range(left + width * 2, right - width, width * 4):
        draw.line((x, bottom - width * 2, min(right - 1, x + (bottom - top) // 5), top + width * 2), fill=NAVY, width=1)


def thumbnail(source: Path, output: Path):
    image = Image.open(source).convert("RGBA"); draw = ImageDraw.Draw(image); width, height = image.size
    # Editorial burst replaces the former rounded application-card panel.
    cx, cy, rx, ry = int(width * .28), int(height * .35), int(width * .23), int(height * .25)
    points = []
    for index in range(24):
        angle = -1.57 + index * 6.283 / 24; factor = 1.10 if index % 2 == 0 else .88
        import math
        points.append((cx + math.cos(angle) * rx * factor, cy + math.sin(angle) * ry * factor))
    draw.polygon(points, fill=CREAM, outline=NAVY); draw.line(points + [points[0]], fill=NAVY, width=max(4, width // 260), joint="curve")
    _center(draw, (int(width*.08), int(height*.18), int(width*.48), int(height*.42)), "지금 사도\n늦지 않을까?", int(width*.050), YELLOW, stroke=max(3, width//360))
    _center(draw, (int(width*.09), int(height*.45), int(width*.47), int(height*.53)), "핵심 지표 3가지만 확인", int(width*.019), NAVY)
    image.convert("RGB").save(output, "PNG")


def copy_explainer(source: Path, output: Path):
    image = Image.open(source).convert("RGBA"); draw = ImageDraw.Draw(image); width, height = image.size
    _center(draw, (int(width*.11), int(height*.17), int(width*.69), int(height*.34)), "금리 인하가\n주가에 주는 영향은?", int(width*.041), CREAM, stroke=max(1, width//720), stroke_fill="#16382E")
    _center(draw, (int(width*.15), int(height*.42), int(width*.66), int(height*.55)), "금리 하락  →  자금 조달 비용 하락", int(width*.024), YELLOW)
    _center(draw, (int(width*.15), int(height*.58), int(width*.66), int(height*.68)), "기업 이익 기대가 높아질 수 있어요", int(width*.021), CREAM)
    image.convert("RGB").save(output, "PNG")


def line_chart(source: Path, output: Path):
    image = Image.open(source).convert("RGBA"); draw = ImageDraw.Draw(image); width, height = image.size
    left, top, right, bottom = int(width*.38), int(height*.16), int(width*.92), int(height*.75)
    _center(draw, (left, top, right, top + int(height*.11)), "코스피 지수화", int(width*.028), CREAM, stroke=max(2, width//650))
    _center(draw, (left, top + int(height*.12), right, top + int(height*.20)), "지수화(7/21=100)", int(width*.019), CREAM)
    _center(draw, (left, int(height*.37), right, int(height*.55)), "107.0", int(width*.072), YELLOW, stroke=max(3, width//360))
    draw.line((int(width*.73), int(height*.60), int(width*.87), int(height*.39)), fill=NAVY, width=max(8, width//110))
    draw.line((int(width*.73), int(height*.60), int(width*.87), int(height*.39)), fill=YELLOW, width=max(4, width//180))
    tip = (int(width*.89), int(height*.36)); draw.polygon([tip, (tip[0]-int(width*.045), tip[1]+int(height*.02)), (tip[0]-int(width*.012), tip[1]+int(height*.07))], fill=YELLOW, outline=NAVY)
    _center(draw, (left, int(height*.67), right, bottom), "기준 대비 +7.0% 상승", int(width*.025), CREAM, stroke=max(1, width//760))
    image.convert("RGB").save(output, "PNG")


def comparison_chart(source: Path, output: Path):
    image = Image.open(source).convert("RGBA"); draw = ImageDraw.Draw(image); width, height = image.size
    left, top, right, bottom = int(width*.52), int(height*.18), int(width*.88), int(height*.84); baseline = int(height*.67)
    _center(draw, (left, top, right, top+int(height*.10)), "운송비 비교", int(width*.027), NAVY, stroke=max(1, width//800), stroke_fill=CREAM)
    draw.line((left+int(width*.02), baseline, right-int(width*.02), baseline), fill=NAVY, width=max(3, width//310))
    bars = [("기준", 100, PAPER_GRAY), ("절감안", 72, YELLOW)]
    for index, (label, value, colour) in enumerate(bars):
        x1 = left + int(width*(.06 + index*.16)); x2 = x1 + int(width*.10); bar_height = int(value / 120 * height * .38)
        _ink_bar(draw, (x1, baseline-bar_height, x2, baseline), colour, max(3, width//430))
        _center(draw, (x1-int(width*.02), baseline-bar_height-int(height*.08), x2+int(width*.02), baseline-bar_height-int(height*.015)), str(value), int(width*.027), NAVY, stroke=max(1, width//850), stroke_fill=CREAM)
        _center(draw, (x1-int(width*.03), baseline+int(height*.01), x2+int(width*.03), baseline+int(height*.06)), label, int(width*.017), NAVY)
    _center(draw, (left, int(height*.74), right, bottom-int(height*.02)), "절감안 적용 시 운송비 28% 감소", int(width*.018), NAVY)
    image.convert("RGB").save(output, "PNG")


def main(args: list[str]):
    if len(args) != 5: raise SystemExit("usage: compose_v22_showcase_images.py THUMB COPY LINE BAR OUTPUT_DIR")
    thumb, copy, line, bar, output_dir = map(Path, args); output_dir.mkdir(parents=True, exist_ok=True)
    thumbnail(thumb, output_dir / "01-thumbnail.png"); copy_explainer(copy, output_dir / "02-text-explainer.png")
    line_chart(line, output_dir / "03-line-chart.png"); comparison_chart(bar, output_dir / "04-comparison-bars.png")
    print("03 comparison_basis=지수화(7/21=100)")
    print("04 accent_colors=[#F6BE28] neutral=[#071A3A,#A99F8A,#FFF4D6]")


if __name__ == "__main__": main(sys.argv[1:])
