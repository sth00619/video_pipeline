"""이미지 모델이 아닌 결정론적 방식으로 대본 문구를 합성한다."""
from __future__ import annotations

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


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


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


def script_caption(scene: dict) -> str:
    """대본의 핵심 문장을 숫자 없이 짧은 표면 문구로 정리한다."""
    candidate = str(
        scene.get("title") or scene.get("bubble_text") or scene.get("content") or scene.get("text") or ""
    ).strip()
    candidate = re.sub(r"^씬\s*\d+\s*:\s*", "", candidate)
    candidate = re.sub(r"\s*[·|]\s*\d+\s*$", "", candidate)
    candidate = re.sub(r"\d+[\d,.]*(?:\s*(?:%|p|퍼센트|조|억|만|원|달러|포인트|개월|년))?", "", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" .,!?:;·-–")
    return (candidate or "시장 흐름을 살펴봅니다")[:22].rstrip()


def _scene_source(scene: dict) -> str:
    """대본과 Claude가 지정한 시각 의도를 함께 의미형 장면 계획에 반영한다."""
    return " ".join(
        str(scene.get(key) or "")
        for key in ("title", "bubble_text", "content", "text", "visual_intent")
    )


def script_visual_phrase(scene: dict) -> str:
    """대본의 의미를 실제 수치 없는 영어 시각 문구로 바꾼다."""
    source = _scene_source(scene)
    if "반도체" in source:
        return "SEMICONDUCTOR GOES DOWN" if any(token in source for token in ("하락", "폭락", "약세")) else "SEMICONDUCTOR OUTLOOK"
    if "공급망" in source or "수출" in source:
        return "SUPPLY CHAIN AT RISK"
    if "공포" in source or "VIX" in source.upper():
        return "FEAR IS COOLING" if any(token in source for token in ("식었", "진정", "완화")) else "MARKET FEAR"
    if "달러" in source or "환율" in source:
        return "DOLLAR UNDER PRESSURE"
    if any(token in source for token in ("국내만", "글로벌", "세계")):
        return "GLOBAL MARKETS TOGETHER"
    if any(token in source for token in ("마트", "장바구니", "소비자물가", "생필품")):
        return "GROCERY BILL SPIKES" if any(token in source for token in ("상승", "급등", "비싸", "부담")) else "PRICES AT THE COUNTER"
    if any(token in source for token in ("점유율", "지분", "시장점유율")):
        return "MARKET SHARE SPLIT"
    if any(token in source for token in ("하락", "폭락", "약세", "급락")):
        return "MARKET GOES DOWN"
    if any(token in source for token in ("반등", "상승", "회복", "급등")):
        return "MARKET BOUNCES BACK"
    return "MARKET OUTLOOK"


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
    if any(token in source for token in ("반등", "상승", "회복", "개선", "증가")):
        return "up"
    return "neutral"
