"""
대본 문장 유형 분류 유틸리티 (Content Type Classification Engine).

특정 씬/사례에 의존하지 않고, 대본의 문장 구조·패턴·개체 구성에 따라
5가지 시각적 분류(content_type)를 결정론적으로 도출하고 시각 전략을 제공함.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Dict

# Content Types
CONTENT_TYPES = [
    "concept_explainer",   # 용어/개념 정의 (~란, ~이란, ~을 의미합니다, 지표)
    "entity_news",         # 기업/기관 소식 (~가 ~를 발표/출시/증설)
    "market_index_move",   # 지수/수치 방향성 (~% 급등/하락, 포인트, 폭등, 급락)
    "macro_geopolitical",  # 원자재/거시경제/지정학 (유가, 구리, 연준, 중동, 환율)
    "comparison",          # A vs B 대비 (~는 ~하지만 ~는 ~, 반면, 대조)
]

# 패턴 정의
_CONCEPT_PATTERNS = re.compile(r"란\b|이란\b|의미합니다|개념부터|지표입니다|지표로|정의|나눈 값|알아보겠습니다|가늠하는|율이란")
_COMPARISON_PATTERNS = re.compile(r"반면|대조|상반|대비|달랐습니다|~는.*~는|만\b|지만\b|하지만\b|밑돌며|비해\b")
_MACRO_PATTERNS = re.compile(
    r"유가|구리|(?<![가-힣])금(?![가-힣])|원자재|배럴|연준|금리|환율|중동|지정학|원달러|(?<![가-힣])달러(?![가-힣])|WTI|석유|정유|정련소"
)
_INDEX_MOVE_PATTERNS = re.compile(r"급등|급락|폭등|폭락|최고치|최저치|뛰어올랐|추락|급감|상승|하락|포인트|퍼센트|%|pt\b")
_ENTITY_ACTION_PATTERNS = re.compile(r"발표|출시|증설|공급|체결|계획|개발|공개|인수|합병|공급망|요금제")

@dataclass
class VisualStrategy:
    content_type: str
    label_text_rule: str
    background_narrative_rule: str
    composition_priority: List[str]

def classify_narration_content_type(
    narration: str,
    core_entities: List[str] | None = None,
    core_figures: List[Dict[str, Any]] | None = None
) -> VisualStrategy:
    """
    대본 문장을 읽고 5가지 Content Type 중 하나로 시각화 전략을 반환한다.
    특정 씬/사례에 의존하지 않으며, 규칙과 패턴 기반으로 작동함.
    """
    text = str(narration or "").strip()
    entities = core_entities or []
    
    # 1. Comparison check
    if _COMPARISON_PATTERNS.search(text) or (len(entities) >= 2 and any(w in text for w in ["반면", "달랐", "상반", "대비", "뛰어넘"])):
        return VisualStrategy(
            content_type="comparison",
            label_text_rule="Render clear side-by-side contrasting displays for each entity with official English names.",
            background_narrative_rule="Use split-stage or dual-side comparison setup highlighting contrasting performance.",
            composition_priority=["split_stage", "dual_screens", "contrast_props"]
        )

    # 2. Concept Explainer check
    if _CONCEPT_PATTERNS.search(text) or any(term in text.upper() for term in ["PER", "PBR", "ROE", "ROA", "EPS", "EV/EBITDA"]):
        return VisualStrategy(
            content_type="concept_explainer",
            label_text_rule="Crucial: Explicitly render the core concept acronym (e.g. ROE, PER, PBR) on the central physical prop or board.",
            background_narrative_rule="Create a serene study or classroom environment with educational balance scales, formula boards, or comparison cards.",
            composition_priority=["classroom", "study_desk", "educational_diagram"]
        )

    # 3. Macro / Geopolitical check
    if _MACRO_PATTERNS.search(text):
        return VisualStrategy(
            content_type="macro_geopolitical",
            label_text_rule="Render the specific commodity or macro metric name (e.g. Copper, WTI Crude Oil, USD/KRW) on main monitor.",
            background_narrative_rule="Build a realistic industrial or geographic origin setting (refinery, mining site, commodity vault, risk control room).",
            composition_priority=["industrial_site", "risk_control_room", "macro_map"]
        )

    # 4. Entity News check
    if len(entities) > 0 and (_ENTITY_ACTION_PATTERNS.search(text) or any(e in text for e in entities)):
        return VisualStrategy(
            content_type="entity_news",
            label_text_rule="Render official English brand logos (e.g. Kakao, Hyundai Motor, Tesla) clearly on signage or screens.",
            background_narrative_rule="Maintain rich narrative environment matching the event (press conference, factory construction, product launch stage).",
            composition_priority=["press_podium", "factory_construction", "event_stage"]
        )

    # 5. Market Index Move (default / fallback for directional metric sentences)
    return VisualStrategy(
        content_type="market_index_move",
        label_text_rule="Render the market index label (e.g. KOSPI, KOSDAQ, NASDAQ) on the main display without writing numbers.",
        background_narrative_rule="Reflect market sentiment (surge or plunge charts, celebratory fireworks or alert monitors).",
        composition_priority=["briefing_podium", "trading_floor", "market_dashboard"]
    )
