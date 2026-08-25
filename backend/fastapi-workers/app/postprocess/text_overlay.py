"""이미지 모델이 아닌 결정론적 방식으로 대본 문구를 합성한다."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


COLORS = {
    "positive": (232, 90, 40),
    "negative": (30, 60, 200),
    "alert": (200, 20, 20),
    "neutral": (20, 120, 60),
}
FONT_CANDIDATES = (
    "/app/assets/fonts/BlackHanSans-Regular.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
)
SURFACE_FONT_CANDIDATES = (
    # OCR와 작은 정보 표면 가독성은 장식성이 강한 제목 폰트보다 정자형
    # 고딕이 안정적이다. 선 굵기는 외곽선으로 원래 만화 스타일에 맞춘다.
    "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/app/assets/fonts/BlackHanSans-Regular.ttf",
)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _surface_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in SURFACE_FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return _font(size)


def add_headline(image_path: str, output_path: str, headline: str, mood: str = "neutral") -> str:
    """레거시 헤드라인 합성 호환 함수다."""
    image = Image.open(image_path).convert("RGBA")
    if not headline:
        image.convert("RGB").save(output_path, quality=95)
        return output_path
    width, height = image.size
    size = max(38, int(height * 0.105))
    font = _font(size)
    draw = ImageDraw.Draw(image)
    color = COLORS.get(mood, COLORS["neutral"])
    x, y = int(width * 0.04), int(height * 0.035)
    shadow_offset = max(2, size // 24)
    stroke_width = max(3, size // 14)
    draw.text(
        (x + shadow_offset, y + shadow_offset), headline, font=font,
        fill=(0, 0, 0, 150), stroke_width=stroke_width, stroke_fill=(0, 0, 0, 150),
    )
    draw.text(
        (x, y), headline, font=font, fill=(*color, 255),
        stroke_width=stroke_width, stroke_fill=(18, 22, 32, 255),
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output_path, quality=95)
    return output_path


def add_surface_caption(
    image_path: str,
    text: str,
    region: tuple[float, float, float, float],
) -> dict:
    """기존 물리 표면 위에 승인 대본 기반 한글 문구를 결정론적으로 합성한다."""
    caption = str(text or "").strip()
    if not caption:
        return {"image_path": image_path, "text": "", "bbox": None}
    image = Image.open(image_path).convert("RGBA")
    width, height = image.size
    x, y, region_width, region_height = region
    left, top = round(x * width), round(y * height)
    right, bottom = round((x + region_width) * width), round((y + region_height) * height)
    if left < 0 or top < 0 or right > width or bottom > height or left >= right or top >= bottom:
        raise ValueError("결정론 표면 문구 좌표가 이미지 범위를 벗어났습니다.")

    padding = max(10, round(min(right - left, bottom - top) * .08))
    max_width = max(20, right - left - padding * 2)
    max_height = max(20, bottom - top - padding * 2)
    font = None
    for size in range(max(18, round(max_height * .42)), 15, -1):
        candidate = _surface_font(size)
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        bbox = probe.multiline_textbbox((0, 0), caption, font=candidate, spacing=max(4, size // 5), align="center")
        if bbox[2] - bbox[0] <= max_width and bbox[3] - bbox[1] <= max_height:
            font = candidate
            break
    if font is None:
        raise ValueError("물리 표면에 비해 승인 문구가 너무 깁니다.")

    # 표면 평균 밝기에 따라 잉크를 고르되, 외곽선으로 원래 2D 만화 선화와
    # 같은 가독성을 유지한다. 별도의 사각 UI 카드는 만들지 않는다.
    luminance = image.convert("L").crop((left, top, right, bottom)).resize((1, 1)).getpixel((0, 0))
    fill = (26, 31, 44, 255) if luminance >= 132 else (250, 247, 232, 255)
    stroke = (250, 247, 232, 235) if luminance >= 132 else (17, 24, 39, 235)
    draw = ImageDraw.Draw(image)
    spacing = max(4, int(getattr(font, "size", 20)) // 5)
    bbox = draw.multiline_textbbox((0, 0), caption, font=font, spacing=spacing, align="center")
    text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    # 밝은 정보판의 한글 획에 두꺼운 반전 외곽선을 두르면 Tesseract가
    # `억`을 `열`처럼 읽는 사례가 있었다. 밝은 물리 표면은 얇은 외곽선만,
    # 어두운 표면은 선화와 분리되는 2px 외곽선을 사용한다.
    stroke_width = 1 if luminance >= 132 else max(2, round(min(width, height) * .0018))
    draw.multiline_text(
        (left + (right - left - text_width) / 2, top + (bottom - top - text_height) / 2 - bbox[1]),
        caption,
        font=font,
        fill=fill,
        spacing=spacing,
        align="center",
        stroke_width=stroke_width,
        stroke_fill=stroke,
    )
    original_format = Image.open(image_path).format or "PNG"
    if original_format in {"JPEG", "JPG"}:
        image.convert("RGB").save(image_path, "JPEG", quality=95)
    else:
        image.save(image_path, original_format)
    text_left = round(left + (right - left - text_width) / 2)
    text_top = round(top + (bottom - top - text_height) / 2)
    rendered_bbox = [
        max(0, text_left - padding),
        max(0, text_top - padding),
        min(width, text_left + text_width + padding),
        min(height, text_top + text_height + padding),
    ]
    final_image = Image.open(image_path).convert("RGB")
    crop = final_image.crop(tuple(rendered_bbox))
    return {
        "image_path": image_path,
        "text": caption,
        # OCR은 복잡한 전체 장면이 아니라 실제 렌더된 글자 주변만 읽는다.
        "bbox": rendered_bbox,
        "font_size": int(getattr(font, "size", 0) or 0),
        "stroke_width": stroke_width,
        "text_sha256": hashlib.sha256(caption.encode("utf-8")).hexdigest(),
        "rendered_crop_sha256": hashlib.sha256(crop.tobytes()).hexdigest(),
        "render_policy_version": 2,
    }


def script_caption(scene: dict) -> str:
    """대본의 핵심 문장을 숫자 없이 짧은 표면 문구로 정리한다."""
    candidate = str(
        scene.get("title")
        or scene.get("bubble_text")
        or scene.get("narration")
        or scene.get("script")
        or scene.get("narration_text")
        or scene.get("text_for_tts")
        or scene.get("content")
        or scene.get("text")
        or ""
    ).strip()
    candidate = re.sub(r"^씬\s*\d+\s*:\s*", "", candidate)
    candidate = re.sub(r"\s*[·|]\s*\d+\s*$", "", candidate)
    candidate = re.sub(r"\d+[\d,.]*(?:\s*(?:%|p|퍼센트|조|억|만|원|달러|포인트|개월|년))?", "", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" .,!?:;·-–")
    return (candidate or "시장 흐름을 살펴봅니다")[:22].rstrip()


def _scene_source(scene: dict) -> str:
    """대본과 Claude가 지정한 시각 의도를 함께 의미형 장면 계획에 반영한다.

    NOTE: 키 우선순위는 변경하지 않는다.
    narration/script/text_for_tts 키를 앞에 추가해 ScriptWorker가
    해당 키에 내레이션을 저장한 씬도 정상 인식하게 한다.
    """
    return " ".join(
        str(scene.get(key) or "")
        for key in (
            "narration", "script", "narration_text", "text_for_tts",
            "title", "bubble_text", "content", "text", "visual_intent",
        )
    )


def script_visual_phrase(scene: dict) -> str:
    """대본의 의미를 실제 수치 없는 영어 시각 문구로 바꾼다.

    CHANGELOG (P0 recovery):
    - _scene_source()가 narration/script 키를 포함하므로 source 연산 자동 개선됨
    - 금리·물가·부동산·한국증시·미국증시·채권·유가·고용·연준 등 키워드 확장
    - 마지막 return을 "MARKET OUTLOOK" 고정에서 방향성 기반 동적 문구로 교체
    """
    source = _scene_source(scene)
    source_upper = source.upper()

    # ── 기존 분기 (변경 없음) ──────────────────────────────────────
    if "반도체" in source:
        return "SEMICONDUCTOR GOES DOWN" if any(t in source for t in ("하락", "폭락", "약세")) else "SEMICONDUCTOR OUTLOOK"
    if "공급망" in source or "수출" in source:
        return "SUPPLY CHAIN AT RISK"
    if "공포" in source or "VIX" in source_upper:
        return "FEAR IS COOLING" if any(t in source for t in ("식었", "진정", "완화")) else "MARKET FEAR"
    if "달러" in source or "환율" in source:
        return "DOLLAR UNDER PRESSURE"
    if any(t in source for t in ("국내만", "글로벌", "세계")):
        return "GLOBAL MARKETS TOGETHER"
    if any(t in source for t in ("마트", "장바구니", "소비자물가", "생필품")):
        return "GROCERY BILL SPIKES" if any(t in source for t in ("상승", "급등", "비싸", "부담")) else "PRICES AT THE COUNTER"
    if any(t in source for t in ("점유율", "지분", "시장점유율")):
        return "MARKET SHARE SPLIT"
    if any(t in source for t in ("하락", "폭락", "약세", "급락")):
        return "MARKET GOES DOWN"
    if any(t in source for t in ("반등", "상승", "회복", "급등")):
        return "MARKET BOUNCES BACK"

    # ── 신규 확장: 주식/금융 핵심 키워드 ─────────────────────────────
    if any(t in source for t in ("연준", "FOMC", "파월", "Fed")):
        return "FED WATCH"
    if any(t in source for t in ("금리", "기준금리", "금리인상", "금리인하")):
        return "RATE CUT SIGNAL" if any(t in source for t in ("인하", "완화", "피벗")) else "RATE HIKE PRESSURE"
    if any(t in source for t in ("인플레이션", "물가", "CPI", "PPI")):
        return "INFLATION COOLING" if any(t in source for t in ("완화", "하락", "안정")) else "INFLATION RISING"
    if any(t in source for t in ("부동산", "주택", "아파트", "전셋값")):
        return "REAL ESTATE TREND"
    if any(t in source for t in ("코스피", "코스닥", "국내증시", "국내주식")):
        return "KOREAN MARKET UPDATE"
    if any(t in source for t in ("나스닥", "S&P", "뉴욕증시", "미국주식", "다우")):
        return "US MARKET WATCH"
    if any(t in source for t in ("국채", "채권", "장단기", "스프레드")):
        return "BOND YIELD WATCH"
    if any(t in source for t in ("유가", "원유", "WTI", "브렌트", "에너지")):
        return "OIL PRICE WATCH"
    if any(t in source for t in ("고용", "실업", "일자리", "비농업")):
        return "JOBS REPORT WATCH"
    if any(t in source for t in ("무역", "무역적자", "무역흑자")):
        return "TRADE BALANCE SIGNAL"
    if any(t in source for t in ("기업실적", "실적", "영업이익", "EPS")):
        return "EARNINGS SPOTLIGHT"
    if any(t in source for t in ("경기", "GDP", "성장률", "경기침체", "리세션")):
        return "GROWTH OUTLOOK"
    if any(t in source for t in ("소비", "소비자심리", "소매판매")):
        return "CONSUMER SPENDING"
    if any(t in source for t in ("투자", "외국인", "기관", "개인")):
        return "CAPITAL FLOW"

    # ── 최후 폴백: 방향성 기반 동적 문구 ("MARKET OUTLOOK" 고정 완전 제거) ──
    direction = script_visual_direction(scene)
    if direction == "up":
        return "TREND REVERSAL UP"
    if direction == "down":
        return "TREND REVERSAL DOWN"
    return "ECONOMIC ANALYSIS"


def script_visual_plan(scene: dict) -> dict[str, str]:
    """대본 의미를 수치 없는 문구·그래프·상황 소품 계획으로 고정 변환한다."""
    source = _scene_source(scene).lower()
    caption = script_visual_phrase(scene)
    direction = script_visual_direction(scene)
    plan = {
        "caption": caption,
        "direction": direction,
        "prop_visuals": "an unlabeled trend line, directional arrows, color blocks, and physical analytical marks",
        "background_visuals": "layered scene-native tools and objects that explain the script meaning without readable text",
    }
    if "semiconductor" in source or "반도체" in source:
        plan.update({
            "prop_visuals": "a large unlabelled silicon wafer, microchip silhouettes, circuit traces, and a descending non-numeric chart",
            "background_visuals": "an electronics-factory mural, chip trays, and circuit-board patterns integrated into the same studio set",
        })
    elif any(token in source for token in ("dollar", "exchange rate", "달러", "환율")):
        plan.update({
            "prop_visuals": "a world-map silhouette, an unmarked currency-note shape pressed by a bold downward arrow, and a descending non-numeric chart",
            "background_visuals": "shipping-route arcs, globe markers, and trade-flow lines integrated into the same set without lettering",
        })
    elif any(token in source for token in ("fear", "vix", "공포", "변동성")):
        plan.update({
            "prop_visuals": "one large analog fear gauge moving from red toward calm green, dimming warning lamps, and a downward non-numeric trace",
            "background_visuals": "risk-control console lights, a closed umbrella, and a cracked crate as non-textual risk metaphors",
        })
    elif any(token in source for token in ("supply chain", "export", "supply", "공급망", "수출")):
        plan.update({
            "prop_visuals": "container silhouettes, cargo-route arrows, a broken chain link, and connected non-numeric flow lines",
            "background_visuals": "a cargo ship, cranes, and stacked containers in one continuous port setting",
        })
    elif any(token in source for token in ("점유율", "지분", "시장점유율", "market share", "ownership")):
        # 소매/장바구니 분기보다 먼저 검사한다: "market share"류 문구가
        # 영어 visual_intent에 "grocery" 같은 소매 힌트를 함께 포함해도
        # 비중·점유 비교라는 더 구체적인 신호를 우선해야 한다.
        plan.update({
            "prop_visuals": (
                "a literal circular pie chart, drawn exactly like a pizza cut into 2-3 unevenly sized wedge slices radiating from "
                "one center point, each wedge a distinct flat color with a thin outline; this must clearly read as a round pie-chart "
                "diagram icon, not a bar chart, not a flow arrow, not a gauge, and not a scale — no numbers and no labels on the wedges"
            ),
            "background_visuals": "corporate signage silhouettes and layered comparison panels integrated into the same set without lettering",
        })
    elif any(token in source for token in ("마트", "장바구니", "소비자물가", "생필품", "grocery", "retail")):
        plan.update({
            "prop_visuals": "a checkout-counter silhouette, a shopping-basket shape, unlabeled price-tag outlines, and a non-numeric bar chart matching the scene direction",
            "background_visuals": "a recognizably Korean hypermarket aisle with shelving, product silhouettes, and checkout-lane signage integrated into the same store set",
        })
    elif any(token in source for token in ("buy", "매수")):
        plan.update({
            "caption": "BUY SIGNAL",
            "direction": "up",
            "prop_visuals": "a rising non-numeric trend arrow, a green signal lamp, and an open gate symbol",
            "background_visuals": "optimistic market tools and layered upward motion lines in the same physical setting",
        })
    elif any(token in source for token in ("sell", "매도")):
        plan.update({
            "caption": "SELL SIGNAL",
            "direction": "down",
            "prop_visuals": "a descending non-numeric trend arrow, a red signal lamp, and a closing gate symbol",
            "background_visuals": "warning tools and layered downward motion lines in the same physical setting",
        })
    explicit_intent = str(scene.get("visual_intent") or "").strip()
    if explicit_intent and not any(character.isdigit() for character in explicit_intent):
        plan["background_visuals"] = (
            f"{plan['background_visuals']}. SCENE-SPECIFIC SCRIPT VISUAL: {explicit_intent}"
        )
    return plan


def script_visual_direction(scene: dict) -> str:
    """대본 의미에 맞는 비수치 추세 방향을 반환한다."""
    source = _scene_source(scene)
    if any(token in source for token in ("하락", "폭락", "약세", "위험", "압박", "감소", "식었", "진정", "완화")):
        return "down"
    if any(token in source for token in ("반등", "상승", "회복", "개선", "증가", "급등")):
        return "up"
    return "neutral"
