"""Compose four v2.2/v3 showcase images with deterministic Korean text.

The generated plates are intentionally clean: no character, text, or charts.
This script owns the final layer order so numbers and Korean copy remain exact,
and the canonical Goldie sprite is always composited last.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
CHARACTER_SHEET = ROOT / "backend" / "fastapi-workers" / "assets" / "character" / "goldie_sheet_v1.png"
OUTPUT_DIR = ROOT / "artifacts" / "v22_final_samples_v3"

PLATES = {
    "thumbnail": Path(r"C:\Users\song\.codex\generated_images\019f9899-dce0-7663-b07f-2886e82d142c\call_cryB91jTaJDQpUZKPq8TK93h.png"),
    "text": Path(r"C:\Users\song\.codex\generated_images\019f9899-dce0-7663-b07f-2886e82d142c\call_UGWi3JgJKA57Ad3esdpwVAiN.png"),
    "line": Path(r"C:\Users\song\.codex\generated_images\019f9899-dce0-7663-b07f-2886e82d142c\call_KfZa16kOuohfehKrdO108VnZ.png"),
    "gauge": Path(r"C:\Users\song\.codex\generated_images\019f9899-dce0-7663-b07f-2886e82d142c\call_zVRxy828K2MQcKesPH3Jaye4.png"),
}

SIZE = (1920, 1080)
INK = "#3D1712"
NAVY = "#071A3A"
DEEP_NAVY = "#031126"
YELLOW = "#F6BE28"
YELLOW_LIGHT = "#FFE170"
CREAM = "#FFF4D8"
PAPER = "#FFF1C8"
RED = "#C94B3C"
GRAY = "#75808A"
BLUE_GRAY = "#53657B"
WHITE = "#FFFDF2"


def font(size: int) -> ImageFont.FreeTypeFont:
    candidates = (
        Path(r"C:\Windows\Fonts\malgunbd.ttf"),
        Path(r"C:\Windows\Fonts\malgun.ttf"),
        ROOT / "backend" / "fastapi-workers" / "app" / "assets" / "fonts" / "BlackHanSans-Regular.ttf",
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def text_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    size: int,
    fill: str,
    *,
    align: str = "center",
    stroke: int = 0,
    stroke_fill: str = INK,
    spacing: int | None = None,
) -> None:
    face = font(size)
    line_spacing = spacing if spacing is not None else max(6, size // 6)
    bounds = draw.multiline_textbbox((0, 0), text, font=face, align=align, spacing=line_spacing, stroke_width=stroke)
    tw = bounds[2] - bounds[0]
    th = bounds[3] - bounds[1]
    if align == "left":
        x = box[0]
    elif align == "right":
        x = box[2] - tw
    else:
        x = box[0] + (box[2] - box[0] - tw) / 2
    y = box[1] + (box[3] - box[1] - th) / 2
    draw.multiline_text(
        (x, y),
        text,
        font=face,
        fill=fill,
        align=align,
        spacing=line_spacing,
        stroke_width=stroke,
        stroke_fill=stroke_fill,
    )


def fit_plate(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGB")
    iw, ih = image.size
    target_w, target_h = SIZE
    scale = max(target_w / iw, target_h / ih)
    resized = image.resize((round(iw * scale), round(ih * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h)).convert("RGBA")


def extract_sprite(crop_box: tuple[int, int, int, int]) -> Image.Image:
    sheet = Image.open(CHARACTER_SHEET).convert("RGBA")
    crop = sheet.crop(crop_box).convert("RGBA")
    bg = crop.getpixel((0, 0))[:3]
    alpha = Image.new("L", crop.size, 0)
    pixels = crop.load()
    alpha_pixels = alpha.load()
    for y in range(crop.height):
        for x in range(crop.width):
            r, g, b, _ = pixels[x, y]
            diff = abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2])
            if diff > 42:
                alpha_pixels[x, y] = 255
            elif diff > 18:
                alpha_pixels[x, y] = int((diff - 18) / 24 * 255)
    alpha = alpha.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(0.35))
    crop.putalpha(alpha)
    bbox = alpha.getbbox()
    if not bbox:
        return crop
    return crop.crop(bbox)


SPRITES = {
    "front": (910, 115, 1668, 910),
    "side": (1780, 90, 2518, 920),
    "happy": (2075, 955, 2728, 1510),
}


def place_sprite(base: Image.Image, sprite_name: str, box: tuple[int, int, int, int]) -> None:
    sprite = extract_sprite(SPRITES[sprite_name])
    max_w = box[2] - box[0]
    max_h = box[3] - box[1]
    scale = min(max_w / sprite.width, max_h / sprite.height)
    sprite = sprite.resize((round(sprite.width * scale), round(sprite.height * scale)), Image.Resampling.LANCZOS)
    x = box[0] + (max_w - sprite.width) // 2
    y = box[1] + (max_h - sprite.height)
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.ellipse((x + 50, y + sprite.height - 54, x + sprite.width - 40, y + sprite.height + 12), fill=(0, 0, 0, 82))
    base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9)))
    base.alpha_composite(sprite, (x, y))


def rounded_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, outline: str = YELLOW, width: int = 8, radius: int = 32) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=INK, width=width + 5)
    inset = width + 3
    inner = (box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset)
    draw.rounded_rectangle(inner, radius=max(8, radius - inset), outline=outline, width=width)


def compose_thumbnail() -> None:
    image = fit_plate(PLATES["thumbnail"])
    draw = ImageDraw.Draw(image)
    text_box(draw, (155, 180, 1190, 520), "지금 사도\n늦지 않을까?", 128, YELLOW, stroke=5, stroke_fill=INK, spacing=14)
    text_box(draw, (210, 575, 1125, 680), "핵심 지표 3가지만 확인", 50, WHITE, stroke=2, stroke_fill=INK)
    draw.rounded_rectangle((245, 735, 920, 812), radius=22, fill=(246, 190, 40, 235), outline=INK, width=5)
    text_box(draw, (270, 736, 895, 812), "실전 데이터 기반 샘플", 34, DEEP_NAVY)
    place_sprite(image, "side", (1290, 260, 1905, 1060))
    image.convert("RGB").save(OUTPUT_DIR / "01-thumbnail.png", "PNG")


def compose_text_image() -> None:
    image = fit_plate(PLATES["text"])
    draw = ImageDraw.Draw(image)
    text_box(draw, (780, 135, 1790, 300), "금리보다 중요한 건\n현금흐름입니다", 72, CREAM, stroke=3, stroke_fill=INK, spacing=8)
    bullets = [
        ("1", "매출 성장보다 현금 유입"),
        ("2", "비용 증가보다 마진 방어"),
        ("3", "뉴스보다 숫자 확인"),
    ]
    y = 380
    for index, body in bullets:
        draw.ellipse((835, y + 6, 898, y + 69), fill=YELLOW, outline=INK, width=5)
        text_box(draw, (835, y + 6, 898, y + 69), index, 34, NAVY)
        text_box(draw, (930, y - 3, 1705, y + 78), body, 42, WHITE, align="left", stroke=2, stroke_fill=INK)
        y += 112
    draw.rounded_rectangle((865, 745, 1720, 835), radius=24, fill=(201, 75, 60, 235), outline=INK, width=5)
    text_box(draw, (895, 750, 1690, 833), "결론은 차트가 아니라 지속성", 39, WHITE, stroke=1, stroke_fill=INK)
    place_sprite(image, "front", (90, 245, 720, 1060))
    image.convert("RGB").save(OUTPUT_DIR / "02-text-explainer.png", "PNG")


def compose_line_chart() -> None:
    image = fit_plate(PLATES["line"])
    draw = ImageDraw.Draw(image)
    panel = (135, 165, 1075, 760)
    rounded_panel(draw, panel, (5, 20, 48, 232), YELLOW, width=7, radius=28)
    text_box(draw, (180, 205, 710, 280), "운송비 지수 추세", 46, CREAM, align="left", stroke=2, stroke_fill=INK)
    text_box(draw, (250, 286, 940, 338), "최근 5주 100 → 124  (+24%)", 32, YELLOW_LIGHT, stroke=1, stroke_fill=INK)
    plot = (230, 390, 990, 665)
    for i, label in enumerate(["90", "100", "110", "120", "130"]):
        y = plot[3] - i * (plot[3] - plot[1]) / 4
        draw.line((plot[0], y, plot[2], y), fill=(255, 244, 216, 76), width=2)
        text_box(draw, (165, int(y - 24), 220, int(y + 24)), label, 24, "#C8D4E6")
    values = [100, 108, 97, 116, 124]
    labels = ["1주", "2주", "3주", "4주", "5주"]
    points: list[tuple[float, float]] = []
    for i, value in enumerate(values):
        x = plot[0] + i * (plot[2] - plot[0]) / 4
        y = plot[3] - (value - 90) * (plot[3] - plot[1]) / 40
        points.append((x, y))
    draw.line(points, fill=YELLOW, width=10, joint="curve")
    draw.line([(x, y + 16) for x, y in points], fill=(61, 23, 18, 130), width=5, joint="curve")
    for (x, y), label, value in zip(points, labels, values):
        draw.ellipse((x - 14, y - 14, x + 14, y + 14), fill=YELLOW_LIGHT, outline=INK, width=4)
        text_box(draw, (int(x - 48), plot[3] + 18, int(x + 48), plot[3] + 62), label, 23, "#D9E2F2")
        text_box(draw, (int(x - 52), int(y - 60), int(x + 52), int(y - 22)), str(value), 24, WHITE, stroke=1, stroke_fill=INK)
    draw.rounded_rectangle((755, 218, 1015, 300), radius=22, fill=(201, 75, 60, 235), outline=INK, width=4)
    text_box(draw, (770, 224, 1000, 295), "주의 구간", 31, WHITE)
    place_sprite(image, "front", (1235, 235, 1880, 1070))
    image.convert("RGB").save(OUTPUT_DIR / "03-line-chart-numbers.png", "PNG")


def arc(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], start: int, end: int, fill: str, width: int) -> None:
    draw.arc(box, start=start, end=end, fill=fill, width=width)


def compose_gauge_chart() -> None:
    image = fit_plate(PLATES["gauge"])
    draw = ImageDraw.Draw(image)
    text_box(draw, (115, 110, 1080, 195), "운송비 절감 효과", 54, NAVY, stroke=1, stroke_fill=CREAM)
    text_box(draw, (170, 205, 1015, 258), "기준 100 대비 절감안 72", 34, RED, stroke=1, stroke_fill=CREAM)
    cx, cy, radius = 620, 540, 270
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    arc(draw, box, 150, 390, "#D2B980", 46)
    arc(draw, box, 150, 323, YELLOW, 46)
    arc(draw, (box[0] - 4, box[1] - 4, box[2] + 4, box[3] + 4), 150, 390, INK, 6)
    text_box(draw, (cx - 220, cy - 95, cx + 220, cy - 15), "72", 92, NAVY)
    text_box(draw, (cx - 240, cy + 10, cx + 240, cy + 72), "절감안 지수", 36, NAVY)
    text_box(draw, (cx - 255, cy + 82, cx + 255, cy + 142), "28% 감소", 48, RED, stroke=1, stroke_fill=CREAM)
    cards = [
        ((205, 776, 455, 936), "기준", "100", GRAY),
        ((492, 776, 742, 936), "절감안", "72", YELLOW),
        ((779, 776, 1029, 936), "차이", "-28", RED),
    ]
    for box_card, label, value, color in cards:
        draw.rounded_rectangle(box_card, radius=22, fill=(255, 244, 216, 238), outline=INK, width=5)
        draw.rectangle((box_card[0] + 8, box_card[1] + 8, box_card[2] - 8, box_card[1] + 22), fill=color)
        text_box(draw, (box_card[0] + 12, box_card[1] + 30, box_card[2] - 12, box_card[1] + 78), label, 26, NAVY)
        text_box(draw, (box_card[0] + 12, box_card[1] + 78, box_card[2] - 12, box_card[3] - 18), value, 47, color, stroke=1, stroke_fill=INK)
    place_sprite(image, "side", (1240, 250, 1880, 1068))
    image.convert("RGB").save(OUTPUT_DIR / "04-gauge-comparison-numbers.png", "PNG")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    plates_dir = OUTPUT_DIR / "plates"
    plates_dir.mkdir(exist_ok=True)
    for name, plate in PLATES.items():
        if not plate.is_file():
            raise FileNotFoundError(plate)
        shutil.copy2(plate, plates_dir / f"{name}_plate.png")
    compose_thumbnail()
    compose_text_image()
    compose_line_chart()
    compose_gauge_chart()


if __name__ == "__main__":
    main()
