"""Create static proof previews for the deterministic market-data overlay path."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(r"C:\Users\song\.codex\generated_images\019f64ac-122b-75e2-a1d9-596f19227dad")
FONT = Path(r"C:\Windows\Fonts\malgun.ttf")
BOLD = Path(r"C:\Windows\Fonts\malgunbd.ttf")


def font(size: int, heavy: bool = False):
    return ImageFont.truetype(BOLD if heavy else FONT, size)


def card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], *, fill=(9, 19, 34, 238), outline=(93, 106, 210, 210)):
    draw.rounded_rectangle(box, radius=28, fill=fill, outline=outline, width=2)


def professor_preview():
    image = Image.open(ROOT / "exec-48bd99b4-1784-459e-bc2d-ec6d988e1fe5.png").convert("RGBA")
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x, y, width, height = 60, 52, 655, 336
    card(draw, (x, y, x + width, y + height))
    draw.rounded_rectangle((x + 25, y + 28, x + 32, y + height - 28), radius=4, fill=(255, 68, 88, 255))
    draw.text((x + 58, y + 32), "KRX 공개 지수 스냅샷", font=font(25, True), fill=(207, 219, 237, 255))
    draw.text((x + 58, y + 79), "KOSPI", font=font(26, True), fill=(245, 248, 252, 255))
    draw.text((x + 58, y + 112), "7,475.94", font=font(60, True), fill=(255, 255, 255, 255))
    draw.text((x + 408, y + 133), "▲ +184.03  (+2.52%)", font=font(22, True), fill=(255, 83, 101, 255))
    draw.line((x + 58, y + 205, x + width - 40, y + 205), fill=(76, 99, 128, 180), width=2)
    draw.text((x + 58, y + 226), "KOSDAQ", font=font(23, True), fill=(207, 219, 237, 255))
    draw.text((x + 215, y + 225), "837.43", font=font(30, True), fill=(255, 255, 255, 255))
    draw.text((x + 380, y + 231), "▲ +43.43  (+5.47%)", font=font(20, True), fill=(255, 83, 101, 255))
    draw.text((x + 58, y + 286), "출처: 한국거래소(KRX) 공개 지수 · 단위: 포인트", font=font(16), fill=(159, 177, 201, 255))
    Image.alpha_composite(image, layer).convert("RGB").save(ROOT / "data-driven-2d-professor.png", quality=95)


def newsroom_preview():
    image = Image.open(ROOT / "exec-690685b6-f9f5-4333-8991-b2ba8f6d1e18.png").convert("RGBA")
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x, y, width, height = 1090, 585, 520, 320
    card(draw, (x, y, x + width, y + height), fill=(8, 20, 38, 244), outline=(55, 190, 255, 215))
    draw.text((x + 30, y + 24), "시장 지수 비교", font=font(28, True), fill=(248, 250, 252, 255))
    for index, (name, value, pct, bar_width) in enumerate((("KOSPI", "7,475.94", "+2.52%", 420), ("KOSDAQ", "837.43", "+5.47%", 105))):
        row_y = y + 82 + index * 100
        draw.text((x + 30, row_y), name, font=font(20, True), fill=(200, 216, 234, 255))
        draw.text((x + 145, row_y - 7), value, font=font(30, True), fill=(255, 255, 255, 255))
        draw.text((x + 385, row_y + 2), f"▲ {pct}", font=font(18, True), fill=(255, 83, 101, 255))
        draw.rounded_rectangle((x + 30, row_y + 47, x + 470, row_y + 62), radius=7, fill=(36, 55, 81, 255))
        draw.rounded_rectangle((x + 30, row_y + 47, x + 30 + bar_width, row_y + 62), radius=7, fill=(255, 83, 101, 255))
    draw.text((x + 30, y + 278), "KRX 공개 지수 스냅샷 · 단위: 포인트", font=font(15), fill=(154, 177, 204, 255))
    Image.alpha_composite(image, layer).convert("RGB").save(ROOT / "data-driven-2d-newsroom.png", quality=95)


if __name__ == "__main__":
    professor_preview()
    newsroom_preview()
    print(ROOT / "data-driven-2d-professor.png")
    print(ROOT / "data-driven-2d-newsroom.png")
