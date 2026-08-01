"""V5 장면 속 수치 배치 검증용 무과금 렌더러.

이 스크립트의 숫자는 시장 데이터가 아닌 모의값이다. 실제 운영에서는
검증된 시세 수집 결과만 같은 렌더링 위치에 주입해야 한다.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "out/v5_pilot/mock_market_metric_placement_preview"

# 표현과 충돌 검증만을 위한 값이다. 실제 시장 수치가 아니다.
MOCK_METRICS = {
    "KOSPI": "+0.63%",
    "SAMSUNG": "+2.84%",
    "SK HYNIX": "-3.16%",
    "NVIDIA": "+1.72%",
    "KOSPI CLOSE": "5,663.24",
}


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", size=size)


def _open(relative: str) -> Image.Image:
    return Image.open(ROOT / relative).convert("RGBA")


def _save(image: Image.Image, filename: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    image.convert("RGB").save(path, "PNG")
    return path


def _weather_map() -> Path:
    """지도 위의 폭풍·화살표에 직접 연결한 등락률 표기다."""
    image = _open("out/benchmark/gemini_pro_diegetic_v5_bench_05_weather/bench_05_weather.png")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    title = _font(round(width * 0.015))
    value = _font(round(width * 0.019))
    # 지도 내부의 기존 폭풍/화살표 근처에만 두어, 별도 정보 카드가 생기지 않게 한다.
    labels = (
        ("SAMSUNG", MOCK_METRICS["SAMSUNG"], .18, .37, (93, 239, 255)),
        ("SK HYNIX", MOCK_METRICS["SK HYNIX"], .34, .51, (255, 117, 102)),
        ("NVIDIA", MOCK_METRICS["NVIDIA"], .47, .35, (255, 214, 94)),
        ("KOSPI", MOCK_METRICS["KOSPI"], .36, .62, (173, 247, 119)),
    )
    for name, change, x_ratio, y_ratio, color in labels:
        x, y = round(width * x_ratio), round(height * y_ratio)
        draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=color, outline=(12, 52, 78), width=3)
        draw.line((x + 8, y - 3, x + 32, y - 25), fill=(237, 253, 255), width=3)
        tx, ty = x + 35, y - 56
        draw.text((tx, ty), name, font=title, fill=(240, 253, 255), stroke_width=3, stroke_fill=(14, 54, 84))
        draw.text((tx, ty + title.size), change, font=value, fill=color, stroke_width=3, stroke_fill=(14, 54, 84))
    return _save(image, "01_weather_map_mock_changes.png")


def _risk_plaque() -> Path:
    """기존 황동 명패 재질 안에 지수 등락률을 새긴다."""
    image = _open("out/benchmark/gemini_pro_v5_diegetic_form_revalidation_3scene/bench_06_risk.png")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    # 새 명패를 덧붙이지 않는다. AI가 이미 그린 황동 명패의 *내부 글자 영역*만
    # 같은 황동색으로 정리하고, 테두리·나사·원근은 원본을 그대로 보존한다.
    left, top, right, bottom = round(width * .037), round(height * .218), round(width * .208), round(height * .272)
    draw.rectangle((left, top, right, bottom), fill=(225, 187, 111))
    draw.line((left + 4, top + 4, right - 4, top + 4), fill=(247, 220, 157), width=2)
    label_font = _font(round(width * .013))
    value_font = _font(round(width * .021))
    draw.text((left + 10, top + 5), "KOSPI CHANGE", font=label_font, fill=(68, 42, 26))
    draw.text((left + 10, top + 27), MOCK_METRICS["KOSPI"], font=value_font, fill=(41, 83, 56), stroke_width=1, stroke_fill=(255, 239, 188))
    return _save(image, "02_risk_plaque_mock_change_v2.png")


def _checkout_display() -> Path:
    """캐릭터가 들고 있는 계산기의 원래 LCD 범위 안에 종가를 넣는다."""
    image = _open("out/benchmark/gemini_pro_diegetic_v5_retail_solo_v2/bench_02_retail.png")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    # 계산기 액정 테두리 안쪽만 채운다. 이 좌표 밖에는 어떤 패널·카드도 만들지 않는다.
    left, top, right, bottom = round(width * .530), round(height * .518), round(width * .650), round(height * .572)
    draw.rectangle((left, top, right, bottom), fill=(187, 202, 157))
    value_font = _font(round(width * .013))
    text = MOCK_METRICS["KOSPI CLOSE"]
    box = draw.textbbox((0, 0), text, font=value_font)
    draw.text((right - 8 - (box[2] - box[0]), top + 6), text, font=value_font, fill=(30, 47, 33))
    return _save(image, "03_calculator_lcd_mock_close_v2.png")


def _contact_sheet(paths: tuple[Path, ...]) -> Path:
    images = [Image.open(path).convert("RGB") for path in paths]
    thumb_width = 960
    thumbs = [image.resize((thumb_width, round(image.height * thumb_width / image.width)), Image.Resampling.LANCZOS) for image in images]
    canvas = Image.new("RGB", (thumb_width, sum(image.height for image in thumbs)), (12, 18, 27))
    cursor = 0
    for image in thumbs:
        canvas.paste(image, (0, cursor))
        cursor += image.height
    path = OUT / "mock_metric_placement_contact_sheet.png"
    canvas.save(path, "PNG")
    return path


def main() -> None:
    paths = (_weather_map(), _risk_plaque(), _checkout_display())
    sheet = _contact_sheet(paths)
    (OUT / "provenance.json").write_text(json.dumps({
        "purpose": "수치가 장면 속 소품에 자연스럽게 들어가는지 검증",
        "market_data_status": "mock_only_not_for_script_or_publication",
        "mock_metrics": MOCK_METRICS,
        "outputs": [str(path) for path in (*paths, sheet)],
        "cost_usd": 0,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(sheet)


if __name__ == "__main__":
    main()
