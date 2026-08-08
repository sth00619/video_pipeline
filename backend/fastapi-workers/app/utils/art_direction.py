"""Rule-based art direction for varied, coherent finance-video scenes.

This is intentionally deterministic: the LLM supplies the factual narration,
while this module turns it into a repeatable visual brief without inventing
facts or copying a reference channel's branded assets.
"""
from __future__ import annotations

from typing import Any


FAMILY_BY_SECTION = {
    "intro": ["hero_metaphor", "news_headline", "topic_stage"],
    "background": ["industry_environment", "news_context", "history_classroom"],
    "data": ["data_lab", "factory_dashboard", "market_arena"],
    "scenario": ["cause_effect", "split_outcomes", "character_role"],
    "action": ["comparison_board", "analyst_desk", "investor_arena"],
    "conclusion": ["takeaway_stage", "classroom_takeaway", "contract_room"],
}

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

V5_ARCHETYPES = {
    "port_emergency":    "폭풍우 항구, 컨테이너, 비상등 — 공급망 충격/수출 경고 전용",
    "retail_shock":      "마트 계산대, 가격표 폭탄 — 물가/소비자 부담 전용",
    "classroom":         "칠판, 교실 — 개념/용어 설명 전용",
    "weather_map":       "기상캐스터 맵 — 전망/확률/지역별 영향 전용",
    "split_stage":       "무대 좌우 대비 — A vs B 비교 전용",
    "trade_calculator":  "황금 저울 — 밸류에이션/관세 균형 전용",
    "data_lab":          "홀로그램 데이터 랩 — 지표 종합/대시보드 전용",
    "risk_control_room": "관제실, 게이지 — 리스크 경고/변동성 전용",
    "briefing_podium":   "발표 무대, 마이크 — 결과 발표/브리핑 전용",
    "real_estate_office":"부동산 사무실 — 부동산 관련 전용",
    "job_market_hall":   "채용 게시판 홀 — 고용/일자리 전용",
}

SHARED_STYLE_LOCK_PROMPT = (
    "NON-NEGOTIABLE ART DIRECTION: 2D digital cartoon illustration in an original Korean webtoon style. "
    "BOLD THICK BLACK INK OUTLINES (3-5px equivalent) on EVERY element; cel shading with soft gradients; highly saturated, organized colors; "
    "dramatic cinematic rim light and glow. The entire frame—background, character, props, blank data surfaces, and "
    "future overlay-safe areas—uses exactly the same hand-illustrated cartoon medium. "
    "A densely detailed themed background fills the frame edge-to-edge. STRICTLY NO photorealism, NO 3D render, "
    "NO photographic background, NO photo compositing, NO glossy toy material. NO text, NO letters, NO words, "
    "NO numbers, NO captions, NO logo, NO watermark anywhere in the generated image. "
    "NO speech bubbles, comic balloons, caption chips, title cards, lower-thirds, or detached callout boxes. "
    "Do not depict screens, dashboards, "
    "charts, signboards, documents, labels, UI panels, blank white rectangles, empty title cards, empty frames, boards, "
    "or presentation panels. Use unlabeled physical props and a continuous full-bleed illustrated background instead. "
    "Never mix a realistic photograph, realistic port, realistic studio, photographic texture, or a different art style into the frame."
)

SHARED_MASCOT_STYLE_LOCK_PROMPT = (
    "The gold coin mascot character MUST be prominently sized, occupying at minimum 1/3 of the frame height. "
    "The circular coin face is ALWAYS fully visible — never obscured by helmets, masks, or visors (any hat or hard hat sits on top of the coin, face remains 100% visible). "
    "Perfectly round golden face, big expressive cartoon eyes with white highlights, rosy pink cheeks, warm smile or matching expression. "
    "White cartoon gloves, brown cartoon shoes, full body visible, proportional cartoon body."
)

ARCHETYPE_TO_COSTUME = {
    "port_emergency": "safety_vest",
    "retail_shock": "detective",
    "classroom": "professor",
    "weather_map": "reporter",
    "split_stage": "formal",
    "trade_calculator": "detective",
    "data_lab": "analyst",
    "risk_control_room": "analyst",
    "briefing_podium": "tuxedo_host",
    "real_estate_office": "formal",
    "job_market_hall": "formal",
    "earnings_stage": "tuxedo_host",
}

ARCHETYPE_TO_FAMILY = {
    "port_emergency": "industry_environment",
    "retail_shock": "industry_environment",
    "classroom": "history_classroom",
    "weather_map": "news_context",
    "split_stage": "split_outcomes",
    "trade_calculator": "comparison_board",
    "data_lab": "data_lab",
    "risk_control_room": "factory_dashboard",
    "briefing_podium": "hero_metaphor",
    "real_estate_office": "contract_room",
    "job_market_hall": "topic_stage",
}

ARCHETYPE_EXCLUSIVE_KEYWORDS = {
    "real_estate_office": {
        "required_any": ["부동산", "아파트", "집값", "분양", "전세", "월세", "토지", "주택"],
    },
    "job_market_hall": {
        "required_any": ["고용", "일자리", "취업", "채용", "실업", "구직", "인력"],
    },
}

def keyword_fallback(text: str, recent_prev: str = "", previous_archetypes: list[str] | None = None, total_scene_count: int | None = None) -> str:
    """LLM API가 없거나 파싱 오류 발생 시 대사 내러티브 상황 기반 키워드 폴백."""
    # 하드 블랙리스트 2종 (대사 미포함 시 절대 선택 불가)
    if any(kw in text for kw in ["부동산", "아파트", "집값", "분양", "전세"]):
        return "real_estate_office"
    if any(kw in text for kw in ["고용", "일자리", "취업", "채용", "실업"]):
        return "job_market_hall"

    # classroom (칠판 구도) 빈도 상한선 체크 (전체 씬의 max 15%, 최소 1개)
    prev_list = previous_archetypes or []
    classroom_count = prev_list.count("classroom")
    classroom_cap = max(1, round((total_scene_count or 10) * 0.15))
    allow_classroom = classroom_count < classroom_cap

    candidates = []
    if allow_classroom and any(kw in text for kw in ["개념", "용어", "의미", "정의", "뜻", "설명", "원리"]):
        candidates.append("classroom")
    if any(kw in text for kw in ["전망", "방향", "예측", "지역", "글로벌", "대외"]):
        candidates.append("weather_map")
    if any(kw in text for kw in ["비교", "대비", "반면", "vs", "versus", "상반"]):
        candidates.append("split_stage")
    if any(kw in text for kw in ["물가", "소비자", "가격", "인플레", "장바구니"]):
        candidates.append("retail_shock")
    if any(kw in text for kw in ["저울", "밸류에이션", "균형", "적정"]):
        candidates.append("trade_calculator")
    if any(kw in text for kw in ["급락", "폭락", "폭등", "급등", "붕괴", "패닉", "위기", "충격", "변동성", "불안", "요동", "흔들", "하락세", "공포", "리스크"]):
        candidates.append("risk_control_room")
    if any(kw in text for kw in ["수출", "무역", "공급망", "관세", "해운", "물류", "외부충격", "글로벌 공급", "원자재", "에너지"]):
        candidates.append("port_emergency")
    if any(kw in text for kw in ["지수", "포인트", "마감", "종가", "반등", "상승", "돌파", "외국인", "기관", "수급", "매수", "발표", "브리핑"]):
        candidates.append("briefing_podium")
    if any(kw in text for kw in ["분석", "데이터", "지표", "통계", "대시보드", "차트", "그래프", "추이", "흐름", "실적", "매출", "분기"]):
        candidates.append("data_lab")

    for cand in candidates:
        if cand != recent_prev:
            return cand
    return candidates[0] if candidates else ("data_lab" if recent_prev == "briefing_podium" else "briefing_podium")


def select_archetype_for_scene(
    narration: str,
    previous_archetypes: list[str] | None = None,
    llm_call=None,
    *,
    total_scene_count: int | None = None,
) -> dict:
    """
    대사(narration)를 읽고 11종 V5 아키타입 중 가장 적합한 무대를 선택한다.
    라운드로빈 / 씬 인덱스 / 감정 기반 임의 순환 배정을 100% 금지함.
    """
    narration_txt = str(narration or "").strip()
    if not narration_txt:
        return {"archetype": "briefing_podium", "reason": "빈 대사이므로 기본 브리핑 무대 선택", "specific_props": "presentation wall"}

    prev_list = previous_archetypes or []
    recent_prev = prev_list[-1] if prev_list else ""
    consecutive_prev = prev_list[-1] if len(prev_list) >= 2 and prev_list[-1] == prev_list[-2] else ""

    classroom_count = prev_list.count("classroom")
    classroom_cap = max(1, round((total_scene_count or 10) * 0.15))

    def is_valid_choice(arch: str, text: str) -> bool:
        if arch == "classroom" and classroom_count >= classroom_cap:
            return False
        rule = ARCHETYPE_EXCLUSIVE_KEYWORDS.get(arch)
        if not rule:
            return True
        return any(kw in text for kw in rule["required_any"])

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        arch = keyword_fallback(narration_txt, recent_prev, previous_archetypes=prev_list, total_scene_count=total_scene_count)
        return {"archetype": arch, "reason": "내용 키워드 폴백 선택", "specific_props": "studio elements"}

    system = (
        "너는 한국 주식·경제 유튜브 채널의 수석 아트 디렉터다. "
        "채널 콘텐츠는 KOSPI, KOSDAQ, 미국 주식 시장을 다루며, "
        "대본 텍스트를 읽고 11종의 무대(아키타입) 중 내러티브의 "
        "분위기·상황·경제적 맥락에 가장 어울리는 시각적 은유를 선택한다. "
        "무대는 문자 그대로의 장소가 아니라 시각적 은유다. "
        "예: 수출 감소/외부 충격 → port_emergency(항구 비상). "
        "금리 결정/시장 방향성/글로벌 전망 → weather_map(기상 예보) 또는 split_stage(시나리오 대비). "
        "지수 급락/변동성 → risk_control_room(관제실). "
        "대본에 정확한 키워드가 없어도 내러티브 맥락으로 풍부하게 판단한다. "
        "시각적 다양성을 위해 직전 씬에서 사용한 무대와 동일한 무대를 연속 3회 이상 중복 선택하지 않는다."
    )
    archetype_list = "\n".join(f"- {k}: {v}" for k, v in V5_ARCHETYPES.items())

    avoid_instruction = ""
    if consecutive_prev:
        avoid_instruction = f"\n주의: 직전 2개 씬에서 '{consecutive_prev}' 무대가 연속 사용되었습니다. 시각적 다양성을 위해 이 씬에서는 '{consecutive_prev}' 대신 다른 적절한 은유 무대(weather_map, data_lab, split_stage, trade_calculator, briefing_podium 등)를 우선 고려하라.\n"

    prompt = f"""대사: "{narration_txt}"

무대 목록 (시각적 은유 포함):
{archetype_list}
{avoid_instruction}
추가 선택 가이드:
- port_emergency: 수출/무역 위기뿐 아니라 공급망 충격, 외부 경제 충격, 글로벌 위기 장면에서도 강력한 시각 은유로 사용 가능
- weather_map: 경제 전망, 시장 방향성, 지역별 영향 장면에 적합
- risk_control_room: 지수 급등락, 변동성, 위험 경보 장면에 적합
- data_lab: 지표 분석, 데이터 대시보드, 복합 지수 설명에 적합
- classroom: 경제 개념 설명, 용어 해설, 배경 설명에 적합
- briefing_podium: 발표, 결과 공표, 정책 브리핑에 적합
- trade_calculator: 밸류에이션, 비교 분석, 균형점 논의에 적합
- split_stage: A vs B 비교, 상반된 시나리오 제시에 적합
- retail_shock: 물가, 소비자 부담, 가격 상승 장면에 적합
- real_estate_office: 부동산 관련 대사에만 선택
- job_market_hall: 고용·취업 관련 대사에만 선택

규칙:
- real_estate_office는 대사에 부동산 내용이 없으면 절대 선택하지 마라.
- job_market_hall는 대사에 고용/취업 내용이 없으면 절대 선택하지 마라.
- 나머지 9개는 내러티브 맥락과 시각적 은유 판단으로 자유롭게 선택한다.
- JSON만 반환: {{"archetype": "...", "reason": "...", "specific_props": "..."}}"""

    try:
        if callable(llm_call):
            raw = llm_call(system, [{"role": "user", "content": prompt}], 800)
        else:
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=800,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text

        cleaned = re.sub(r"```json|```", "", raw).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        json_str = match.group(0) if match else cleaned
        data = json.loads(json_str)
        chosen = str(data.get("archetype") or "").strip()
        if chosen in V5_ARCHETYPES and is_valid_choice(chosen, narration_txt):
            if len(prev_list) >= 2 and prev_list[-1] == prev_list[-2] == chosen:
                alt = keyword_fallback(narration_txt, recent_prev)
                if alt == chosen:
                    alt = next((a for a in ["weather_map", "split_stage", "trade_calculator", "classroom", "data_lab", "briefing_podium", "port_emergency"] if a != chosen and is_valid_choice(a, narration_txt)), "briefing_podium")
                chosen = alt
                reason = f"3연속 {prev_list[-1]} 중복 방지 다양성 교체 -> {chosen}"
            else:
                reason = str(data.get("reason") or "LLM 내용 기반 선택")
            return {
                "archetype": chosen,
                "reason": reason,
                "specific_props": str(data.get("specific_props") or "scene props"),
            }
        else:
            logger.warning("LLM 선택 무대 '%s'가 유효하지 않거나 대사 미스매치 — 키워드 폴백 적용", chosen)
    except Exception as exc:
        logger.warning("LLM 내용 기반 아키타입 선택 실패: %s", exc)

    arch = keyword_fallback(narration_txt, recent_prev)
    return {"archetype": arch, "reason": "내용 키워드 폴백 선택", "specific_props": "scene props"}


def flag_archetype_content_mismatch(scene: dict[str, Any]) -> dict[str, Any] | None:
    archetype = str(scene.get("archetype") or (scene.get("art_direction") or {}).get("family") or "")
    rule = ARCHETYPE_EXCLUSIVE_KEYWORDS.get(archetype)
    if not rule:
        return None
    narration = str(scene.get("content") or scene.get("text") or "")
    if not any(kw in narration for kw in rule["required_any"]):
        return {
            "scene_id": scene.get("scene_id") or scene.get("index"),
            "archetype": archetype,
            "warning": "narration_archetype_mismatch",
            "narration": narration[:40],
        }
    return None


CAMERAS = ["wide establishing shot", "medium editorial shot", "low-angle hero shot", "over-the-shoulder explanation shot"]
LIGHTING = ["soft studio key light", "dramatic rim light", "bright editorial daylight", "cinematic practical lights"]

TOPICS = [
    ("semiconductor", ("HBM", "반도체", "메모리", "칩", "파운드리"),
     "semiconductor factory and server infrastructure", ["memory chip", "server rack", "wafer", "robot arm"]),
    ("ai_cloud", ("AI", "클라우드", "데이터센터", "서버"),
     "AI data-center and cloud infrastructure", ["server rack", "glowing compute chip", "data stream"]),
    ("market_flow", ("외국인", "기관", "수급", "매수", "매도"),
     "stock-market trading floor and flow of capital", ["order board", "market arrows", "trading tickets"]),
    ("earnings", ("실적", "매출", "영업이익", "가이던스"),
     "earnings briefing room and business dashboard", ["earnings report", "growth bar", "briefing screen"]),
    ("macro", ("금리", "환율", "유가", "인플레이션", "FOMC"),
     "global macroeconomic control room", ["interest-rate dial", "currency globe", "oil gauge"]),
    ("contract", ("계약", "수주", "주문", "납품", "공급"),
     "commercial contract and supply-chain setting", ["contract folder", "handshake", "shipping container"]),
]

PALETTES = {
    "positive": {"name": "growth_gold", "colors": "mostly deep navy and white, one warm yellow emphasis, muted gray"},
    "risk": {"name": "risk_crimson", "colors": "mostly charcoal and white, one deep crimson warning, muted gray"},
    "neutral": {"name": "editorial_blue", "colors": "mostly deep navy, white, and muted blue-gray; at most one warm yellow emphasis"},
    "industrial": {"name": "industrial_navy", "colors": "mostly steel gray and dark navy, one safety-yellow cue, white highlights"},
}

EDITORIAL_COMIC_STYLE = (
    "NON-NEGOTIABLE: Original 2D Korean finance editorial cartoon, not an imitation of any existing channel or mascot. "
    "Use confident variable-width black ink contours, simple 2-to-3 tone cel shading, and a subtle printed-comic texture. "
    "Build a readable foreground, midground, and detailed background; use one dominant visual idea, intentional asymmetry, "
    "and an expressive silhouette. The mascot, background, props, blank chart board, and future overlay-safe areas must be one cohesive cartoon illustration. "
    "Use a restrained, scene-led colour script: one dominant background palette, white/black typography, and at most one warm emphasis colour. "
    "Never use rainbow data colours, neon UI gradients, glowing dashboard grids, decorative colour coding, or several competing coloured cards. "
    "Only a verified data scene may contain a simple in-world board; it must read as a physical cartoon prop, not a technology studio. "
    "Every scene must be a fresh, story-specific illustration rather than a reused set: use a detailed location, tangible props, foreground depth, dramatic weather or lighting only when the narration warrants it, and expressive character acting. "
    "Aim for polished Korean editorial-animation key art: energetic hand-inked contours, layered painted scenery, rich prop detail, and cinematic but readable staging; never flat vector clip art or generic corporate stock illustration. "
    "Do not add a blank circle, empty chart, empty sign, or generic panel merely as decoration. Every information surface must be a justified object in the scene and must be filled by verified post-production data, otherwise omit it. "
    "Avoid photorealism, Pixar-like glossy 3D, plastic toy material, empty dark studio backgrounds, generic gold coin characters, "
    "and generic gold piles, explosions, rockets, fire, or space metaphors unless explicitly required."
)

# A data visual is a prop selected by the story, not a permanent chalkboard.
# The renderer still receives one rectangular safe region, while the image
# generator is told what that region physically is in the current scene.
DATA_SURFACE_BY_FAMILY = {
    "data_lab": ("monitor", "a large blank wall monitor or desk terminal, with a matte non-glowing screen"),
    "factory_dashboard": ("inspection_clipboard", "a blank clipped inspection sheet attached to a machine guard"),
    "market_arena": ("trading_ticket", "a blank printed market ticket or referee score card held beside the action"),
    "comparison_board": ("ledger_card", "a blank cream ledger card pinned beside the compared physical objects"),
    "analyst_desk": ("desk_report", "a blank printed analyst report lying flat on the desk"),
    "news_context": ("map_cloud", "one or two blank illustrated cloud labels anchored directly over the relevant map locations"),
    "industry_environment": ("product_label", "a blank inspection tag attached directly to the relevant product or container"),
}

# Marker surfaces are deliberately scene props, not generic beige cards.  The
# detector later verifies the real generated geometry before any exact copy is
# rendered.  Map clouds are irregular masks and are therefore never quad-warped.
SURFACE_CONTRACT_BY_KIND = {
    "monitor": {"geometry": "planar_quad", "marker_rgb": (65, 86, 102), "border_rgb": (15, 27, 42), "preferred_side": "left", "preferred_region": {"x": .05, "y": .10, "width": .42, "height": .60}, "tilt_hint": "nearly front-facing matte monitor"},
    "inspection_clipboard": {"geometry": "planar_quad", "marker_rgb": (225, 210, 175), "border_rgb": (76, 53, 34), "preferred_side": "right", "preferred_region": {"x": .52, "y": .11, "width": .42, "height": .60}, "tilt_hint": "slightly tilted clipped inspection sheet"},
    "trading_ticket": {"geometry": "planar_quad", "marker_rgb": (205, 220, 214), "border_rgb": (21, 42, 51), "preferred_side": "left", "preferred_region": {"x": .06, "y": .12, "width": .40, "height": .56}, "tilt_hint": "slightly tilted printed score ticket"},
    "ledger_card": {"geometry": "planar_quad", "marker_rgb": (231, 214, 177), "border_rgb": (82, 54, 30), "preferred_side": "left", "preferred_region": {"x": .05, "y": .12, "width": .42, "height": .57}, "tilt_hint": "slightly tilted ledger card pinned to the compared prop"},
    "desk_report": {"geometry": "planar_quad", "marker_rgb": (219, 225, 218), "border_rgb": (44, 53, 51), "preferred_side": "left", "preferred_region": {"x": .08, "y": .42, "width": .48, "height": .36}, "tilt_hint": "a report lying at a real desk perspective"},
    "product_label": {"geometry": "planar_quad", "marker_rgb": (217, 200, 159), "border_rgb": (65, 48, 31), "preferred_side": "right", "preferred_region": {"x": .56, "y": .20, "width": .32, "height": .42}, "tilt_hint": "a small hanging inspection tag on the product"},
    "map_cloud": {"geometry": "irregular_mask", "marker_rgb": None, "border_rgb": None, "preferred_side": "left", "preferred_region": {"x": .08, "y": .16, "width": .36, "height": .26}, "tilt_hint": "a blank illustrated cloud label anchored to the map"},
    "scene_card": {"geometry": "planar_quad", "marker_rgb": (213, 220, 212), "border_rgb": (45, 55, 56), "preferred_side": "right", "preferred_region": {"x": .52, "y": .14, "width": .40, "height": .54}, "tilt_hint": "a real physical information card attached to the key prop"},
}


def _surface_contract(kind: str, character_placement: str) -> dict[str, Any]:
    contract = {"surface_kind": kind, **SURFACE_CONTRACT_BY_KIND.get(kind, SURFACE_CONTRACT_BY_KIND["scene_card"])}
    preferred = dict(contract["preferred_region"])
    # Place the prop opposite the mascot when the family permits it.  This is
    # a planning hint only; detector ambiguity always fails safely.
    if "right" in character_placement and preferred.get("x", 0) > .5:
        preferred["x"] = .08
    elif "left" in character_placement and preferred.get("x", 0) < .5:
        preferred["x"] = .52
    contract["preferred_region"] = preferred
    return contract

WARDROBE_BY_FAMILY = {
    "hero_metaphor": ("hero_business", "tailored navy analyst suit with a gold accent"),
    "news_headline": ("analyst", "clean broadcaster jacket and notebook"),
    "topic_stage": ("explaining", "smart casual presenter outfit"),
    "industry_environment": ("engineer", "industrial safety helmet and workwear"),
    "news_context": ("analyst", "clean broadcaster jacket and notebook"),
    "history_classroom": ("teacher", "teacher cardigan with a pointer"),
    "data_lab": ("scientist", "white lab coat and data goggles"),
    "factory_dashboard": ("engineer", "industrial safety helmet and workwear"),
    "market_arena": ("analyst", "sporty market referee jacket"),
    "cause_effect": ("explaining", "smart casual presenter outfit"),
    "split_outcomes": ("thinking", "neutral analyst outfit with contrasting light"),
    "character_role": ("explorer", "field explorer vest and utility cap"),
    "comparison_board": ("explaining", "analyst suit with a presentation clicker"),
    "analyst_desk": ("thinking", "navy analyst suit at a desk"),
    "investor_arena": ("pointing", "market coach jacket"),
    "takeaway_stage": ("happy", "tailored navy analyst suit with a gold accent"),
    "classroom_takeaway": ("teacher", "teacher cardigan with a pointer"),
    "contract_room": ("analyst", "formal business suit with contract folder"),
}

# Phase 2: role costumes are concrete library keys, not prose-only direction.
# Every role has neutral/highlight/worried variants. Older generic libraries
# retain a fallback pose until the channel opts in to generating the new set.
ROLE_COSTUME_BY_FAMILY = {
    "hero_metaphor": "field_reporter", "news_headline": "anchor", "topic_stage": "anchor",
    "industry_environment": "field_reporter", "news_context": "anchor", "history_classroom": "professor",
    "data_lab": "analyst", "factory_dashboard": "analyst", "market_arena": "referee",
    "cause_effect": "anchor", "split_outcomes": "referee", "character_role": "field_reporter",
    "comparison_board": "referee", "analyst_desk": "analyst", "investor_arena": "referee",
    "takeaway_stage": "anchor", "classroom_takeaway": "professor", "contract_room": "analyst",
}

# The reference frames supplied for review show that the character should not
# always occupy the same side or the same amount of the image.  These are
# reusable *composition grammar* tokens, not a copy of any channel branding:
# they describe where an original mascot, a real in-world information surface,
# and a later deterministic text layer may safely coexist in a 16:9 cartoon.
REFERENCE_COMPOSITION_BY_FAMILY = {
    "hero_metaphor": {"id": "hero_reaction", "character_placement": "left third", "character_area_target": .48, "information_area_target": .26},
    "news_headline": {"id": "headline_reaction", "character_placement": "right third", "character_area_target": .46, "information_area_target": .30},
    "topic_stage": {"id": "topic_explainer", "character_placement": "right third", "character_area_target": .42, "information_area_target": .28},
    "industry_environment": {"id": "field_alert", "character_placement": "center foreground", "character_area_target": .52, "information_area_target": .25},
    "news_context": {"id": "news_map", "character_placement": "right third", "character_area_target": .44, "information_area_target": .31},
    "history_classroom": {"id": "chalkboard_lesson", "character_placement": "right third", "character_area_target": .43, "information_area_target": .40},
    "data_lab": {"id": "data_lab", "character_placement": "right third", "character_area_target": .44, "information_area_target": .42},
    "factory_dashboard": {"id": "factory_panel", "character_placement": "left third", "character_area_target": .42, "information_area_target": .42},
    "market_arena": {"id": "market_scoreboard", "character_placement": "right third", "character_area_target": .46, "information_area_target": .38},
    "cause_effect": {"id": "cause_effect", "character_placement": "left third", "character_area_target": .48, "information_area_target": .30},
    "split_outcomes": {
        "id": "split_comparison", "character_placement": "center foreground", "character_area_target": .30, "information_area_target": .48,
        "scene_recipe": "a dramatic left-versus-right physical world split: one stressed environment and one stabilised environment, the mascot mediating in the foreground; two large blank illustrated parchment notices at upper left and upper right, with one blank white burst between them",
        "information_surfaces": [
            {"kind": "parchment", "x": .05, "y": .07, "width": .32, "height": .28},
            {"kind": "burst", "x": .40, "y": .05, "width": .20, "height": .25},
            {"kind": "parchment", "x": .63, "y": .07, "width": .32, "height": .28},
        ],
    },
    "character_role": {"id": "role_story", "character_placement": "left third", "character_area_target": .50, "information_area_target": .25},
    "comparison_board": {"id": "comparison_board", "character_placement": "right third", "character_area_target": .42, "information_area_target": .42},
    "analyst_desk": {"id": "analyst_take", "character_placement": "right third", "character_area_target": .42, "information_area_target": .28},
    "investor_arena": {"id": "decision_arena", "character_placement": "left third", "character_area_target": .46, "information_area_target": .30},
    "takeaway_stage": {"id": "takeaway", "character_placement": "center foreground", "character_area_target": .48, "information_area_target": .24},
    "classroom_takeaway": {"id": "chalkboard_takeaway", "character_placement": "right third", "character_area_target": .42, "information_area_target": .40},
    "contract_room": {"id": "contract_explainer", "character_placement": "left third", "character_area_target": .45, "information_area_target": .30},
}


def _costume_state(section: str, mood: str) -> str:
    if mood == "risk" or section == "intro":
        return "worried"
    if mood == "positive" or section == "conclusion":
        return "highlight"
    return "neutral"


def _topic(text: str) -> tuple[str, str, list[str]]:
    for name, keywords, setting, props in TOPICS:
        if any(keyword.lower() in text.lower() for keyword in keywords):
            return name, setting, props
    return "finance", "premium Korean finance editorial studio", ["financial chart silhouette", "briefing screen", "document folder"]


def _mood(text: str) -> str:
    risk = ("하락", "급락", "위험", "우려", "부족", "경고", "악화", "매도", "둔화")
    positive = ("상승", "성장", "증가", "호재", "개선", "돌파", "수주", "회복")
    if any(word in text for word in risk):
        return "risk"
    if any(word in text for word in positive):
        return "positive"
    return "neutral"




def _topic(text: str) -> tuple[str, str, list[str]]:
    for name, keywords, setting, props in TOPICS:
        if any(keyword.lower() in text.lower() for keyword in keywords):
            return name, setting, props
    return "finance", "premium Korean finance editorial studio", ["financial chart silhouette", "briefing screen", "document folder"]


def _mood(text: str) -> str:
    risk = ("하락", "급락", "위험", "우려", "부족", "경고", "악화", "매도", "둔화")
    positive = ("상승", "성장", "증가", "호재", "개선", "돌파", "수주", "회복")
    if any(word in text for word in risk):
        return "risk"
    if any(word in text for word in positive):
        return "positive"
    return "neutral"


def direct_scenes(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add a unique visual brief to every scene while avoiding adjacent repeats."""
    directed: list[dict[str, Any]] = []
    previous_archetypes: list[str] = []
    previous_palettes: list[str] = []
    total_count = len(scenes)
    for index, original in enumerate(scenes):
        scene = dict(original)
        text = str(scene.get("content") or scene.get("text") or "")
        section = str(scene.get("section") or "scenario").lower()

        # WORKORDER v2/v3: 대사 내용 기반 아키타입 선택 (인덱스 라운드로빈 100% 제거, 3연속 중복 방지, classroom 15% 캡 적용)
        selected_info = select_archetype_for_scene(
            text,
            previous_archetypes=previous_archetypes,
            total_scene_count=total_count,
        )
        archetype = selected_info["archetype"]
        previous_archetypes.append(archetype)
        family = ARCHETYPE_TO_FAMILY.get(archetype, "topic_stage")
        scene["archetype"] = archetype
        scene["archetype_reason"] = selected_info["reason"]
        scene["specific_props"] = selected_info["specific_props"]

        topic_name, setting, props = _topic(text)
        mood = _mood(text)
        palette_key = "industrial" if family in {"industry_environment", "factory_dashboard", "data_lab"} else mood
        if previous_palettes and palette_key == previous_palettes[-1]:
            palette_key = "neutral" if palette_key != "neutral" else "positive"
        wardrobe_key, wardrobe = WARDROBE_BY_FAMILY[family]
        costume_role = ARCHETYPE_TO_COSTUME.get(archetype) or ROLE_COSTUME_BY_FAMILY.get(family, "analyst")
        costume_state = _costume_state(section, mood)
        render_contract = scene.get("v5_render_contract") or {}
        visual_mode = str(
            scene.get("visual_mode") or render_contract.get("visual_mode") or ""
        ).strip()
        if visual_mode == "article_evidence":
            character_required = False
        else:
            character_required = True
        pose = scene.get("pose") or wardrobe_key
        camera = CAMERAS[index % len(CAMERAS)]
        composition = dict(REFERENCE_COMPOSITION_BY_FAMILY[family])
        character_placement = composition["character_placement"] if character_required else "none"
        # The opposite side of the mascot remains visually quiet so a cloud or
        # target-bound label can be added without covering either narration or
        # the character. Coordinates are normalized for the final compositor.
        overlay_target = (
            {"x": .53, "y": .16, "width": .36, "height": .25}
            if "left" in character_placement else
            {"x": .10, "y": .16, "width": .36, "height": .25}
        )
        data_surface = None
        data_surface_kind = None
        data_surface_prompt = None
        surface_contract = None
        if section == "data":
            # An explanation panel gets the broad side opposite the mascot.
            # Center-foreground comparison scenes receive a full-width upper
            # board and retain the middle for the referee/mediator pose.
            data_surface = (
                {"x": 110, "y": 115, "width": 780, "height": 525}
                if "right" in character_placement else
                ({"x": 1030, "y": 115, "width": 780, "height": 525}
                    if "left" in character_placement else
                    {"x": 300, "y": 80, "width": 1320, "height": 350})
            )
            data_surface_kind, data_surface_prompt = DATA_SURFACE_BY_FAMILY.get(
                family,
                ("scene_card", "one blank physical information card naturally attached to the key prop"),
            )
            surface_contract = _surface_contract(data_surface_kind, character_placement)
        direction = {
            "family": family,
            "topic": topic_name,
            "setting": setting,
            "props": props,
            "palette": PALETTES[palette_key],
            "wardrobe": wardrobe,
            "role_costume": costume_role,
            "costume_state": costume_state,
            "pose_asset": f"{costume_role}_{costume_state}",
            "fallback_pose": wardrobe_key,
            "character_required": character_required,
            "camera": camera,
            "lighting": LIGHTING[(index + 1) % len(LIGHTING)],
            "reference_composition": composition,
            # Data scenes are composed around a real in-world monitor.  The
            # generator only supplies the empty surface; deterministic code
            # Data scenes are composed around a real in-world monitor.  The
            # generator only supplies the empty surface; deterministic code
            # fills it with the factual chart after generation.
            "character_placement": character_placement,
            # This is an executable scene grammar, not merely a prompt hint.
            # The clean plate receives the factual surface first; the locked
            # alpha character is always the foreground layer so hands/fingers
            # naturally occlude the prop instead of being covered by it.
            "layer_pipeline": {
                "version": "3.0",
                "render_clean_plate": True,
                "canonical_character_required": character_required,
                "z_order": ["clean_background", "verified_info_surface", "character_foreground", "editorial_text"],
            },
            "overlay_strategy": "integrated_market_surface" if section == "data" else ("headline_card" if family == "news_headline" else "none"),
            "data_surface": data_surface,
            "data_surface_kind": data_surface_kind,
            "data_surface_prompt": data_surface_prompt,
            "surface_contract": surface_contract,
            # Classroom scenes reserve a genuine blank board.  This is the
            # only non-data surface on which the overlay grammar may render
            # explanatory Korean directly as chalk instead of a floating card.
            "editorial_text_surface": {"x": .10, "y": .16, "width": .55, "height": .42} if family in {"history_classroom", "classroom_takeaway"} else None,
            "editorial_overlay_target": overlay_target,
            "negative_constraints": ["no readable text", "no watermark", "no generic gold pile", "no unrelated fire or space scene", "no photorealism", "no mixed art styles"],
            "decorative_text_allowed": bool(scene.get(
                "decorative_text_allowed",
                family in {"news_headline", "news_context", "comparison_board", "factory_dashboard", "data_lab"},
            )),
        }
        scene["pose"] = pose
        scene["visual_mode"] = visual_mode or (
            "archetype_explainer" if character_required else "semantic_illustration"
        )
        scene["art_direction"] = direction
        scene["art_direction"] = direction
        scene["style_profile"] = "editorial_comic_2d"
        scene["visual_type"] = scene.get("visual_type") or family
        plan = dict(scene.get("visual_plan") or {})
        plan.update({"family": family, "character_required": character_required, "art_direction": direction})
        scene["visual_plan"] = plan
        directed.append(scene)
        previous_palettes.append(palette_key)
    return directed


def plan_image_quality_tiers(scenes: list[dict[str, Any]], tier: str, pro_limit: int) -> list[dict[str, Any]]:
    """모든 유료 이미지 장면을 Nano Banana Pro 2K 계약으로 고정한다."""
    if str(tier or "pro").lower() != "pro":
        raise ValueError("이미지 품질 tier는 pro만 허용합니다.")
    planned: list[dict[str, Any]] = []
    for original in scenes:
        scene = dict(original)
        scene["image_profile"] = {
            "tier": "pro",
            "model": "gemini-3-pro-image",
            "image_size": "2K",
            "reason": "pro_only_policy",
        }
        planned.append(scene)
    return planned


def compile_editorial_prompt(scene: dict[str, Any], base_prompt: str) -> str:
    direction = scene.get("art_direction") or {}
    palette = (direction.get("palette") or {}).get("colors", "high-contrast financial studio color palette, saturated rich tones with dramatic lighting contrast, deep navy blue")
    props = ", ".join(direction.get("props") or [])
    character_clause = "no mascot character; focus on the real-world context and props"
    if direction.get("character_required"):
        character_clause = (
            f"the 2D news reporter character on the {direction.get('character_placement', 'right third')}, "
            f"using the {direction.get('pose_asset', 'explaining')} pose"
        )
    # Even decorative model text becomes unstable pseudo-Korean at video
    # resolution.  A cartoon frame may contain texture, chalk dust, abstract
    # data glows, and blank illustrated props, but every readable character
    # comes from a deterministic overlay after generation.
    text_clause = "No readable text, no caption, no number, no logo, no watermark, no decorative labels. "
    data_surface_clause = ""
    composition_recipe = str(direction.get("reference_composition", {}).get("scene_recipe") or "")
    if scene.get("market_chart"):
        visual_theme = str((scene.get("market_chart") or {}).get("visual_theme") or "chalkboard")
        visual_kind = str((scene.get("market_chart") or {}).get("visual_kind") or "trend_dashboard")
        surface = direction.get("data_surface") or {}
        surface_by_theme = {
            "chalkboard": "a blank hand-drawn cartoon charcoal chalkboard panel, with subtle chalk dust, hand-inked edge highlights, and a thick uneven white outline",
            "paper_poster": "a blank warm-cream torn-paper notice pinned naturally to the scene, with a hand-inked irregular border, tape and paper texture; reserve a simple graph baseline inside",
            "factory_panel": "a blank painted factory score board with bolts and one large cream data card, never a glowing technology dashboard",
        }
        surface_by_kind = {
            "monitor": "a large blank physical monitor with a matte screen and no UI glow",
            "inspection_clipboard": "a large blank clipboard or inspection sheet physically attached to the relevant machine",
            "trading_ticket": "a large blank printed market ticket or referee score card integrated with the scene",
            "ledger_card": "a large blank warm-cream ledger card pinned beside the compared physical objects",
            "desk_report": "a large blank printed analyst report lying naturally on the desk",
            "map_cloud": "one or two blank illustrated gray cloud labels anchored to the relevant map locations",
            "product_label": "a large blank inspection tag physically attached to the relevant product or container",
            "scene_card": "a large blank physical information card naturally attached to the key prop",
        }
        visual_by_kind = {
            "trend_dashboard": "a wide price-trend, short bar-movement, and composition-chart layout",
            "change_arrow": "a bold rising or falling arrow with a short factual number block",
            "composition_pie": "one large circular composition chart with a compact legend",
            "comparison": "two tall comparison columns with room above each for an exact value",
        }
        board_side = "left" if "right" in str(direction.get("character_placement")) else "right"
        prop_description = surface_by_kind.get(
            str(direction.get("data_surface_kind") or ""),
            surface_by_theme.get(visual_theme, surface_by_theme["chalkboard"]),
        )
        contract = direction.get("surface_contract") or {}
        marker_rgb = contract.get("marker_rgb")
        marker_clause = ""
        if marker_rgb:
            marker_clause = (
                f" Its writable interior is a single matte RGB({marker_rgb[0]}, {marker_rgb[1]}, {marker_rgb[2]}) colour, "
                "surrounded by its own dark hand-inked material border; it has no writing or markings."
            )
        data_surface_clause = (
            f" Include {prop_description}; it is a fully illustrated in-world prop. "
            f"{marker_clause} "
            f"The mascot character stands entirely within the {str(direction.get('character_placement') or 'left third').upper()}. Keep the {board_side}-side board completely blank inside: "
            "no text, numbers, chart, UI, or character parts overlap it. Deterministic post-production will add the exact cartoon data graphic."
        )
    elif direction.get("editorial_text_surface"):
        data_surface_clause = (
            " Include a large blank green classroom chalkboard in the left and center of the frame. "
            "Keep its writing surface completely empty: no generated words, labels, numbers, chart marks, or character parts overlap it. "
            "Deterministic post-production will write one exact Korean explanatory chalk note on this board."
        )
    section = str(scene.get("section") or "scenario")
    recipe_clause = f"Scene recipe: {composition_recipe}. " if composition_recipe else ""
    affordance_clause = {
        "intro": " Keep the upper area as simple continuous atmosphere with low-detail texture for a later alert overlay.",
        "background": " Leave a natural low-detail area beside the map, factory, or policy prop for a later explanatory cloud overlay.",
        "scenario": " Make one physical decision prop clearly visible, with open continuous background around it for a later target-bound overlay.",
        "action": " Keep the mascot hand or pointer and its target prop unobstructed for a later decision chip.",
        "conclusion": " Keep one strong focal stage or spotlight with open upper space for a small takeaway overlay.",
    }.get(section, "")
    return (
        f"{base_prompt}. Editorial scene family: {direction.get('family', 'character_role')}. "
        f"Setting: {direction.get('setting', 'finance studio')}. Key props: {props}. "
        f"Composition: {direction.get('camera', 'medium editorial shot')}; {character_clause}. "
        f"{recipe_clause}"
        f"Color script: {palette}. Lighting: {direction.get('lighting', 'soft studio key light')}. "
        f"{EDITORIAL_COMIC_STYLE} "
        "Specific real-world business props, one clear focal relationship, restrained cartoon colours, and generous empty space around the factual information. Make all writable props look like part of this exact illustrated world. "
        f"{text_clause}"
        f"{data_surface_clause}"
        f"{affordance_clause}"
        "Reserve the lower 22 percent of the frame for separately rendered Korean subtitles."
    )


def assess_art_diversity(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    families = [str((s.get("art_direction") or {}).get("family") or "") for s in scenes]
    palettes = [str(((s.get("art_direction") or {}).get("palette") or {}).get("name") or "") for s in scenes]
    poses = [str((s.get("art_direction") or {}).get("pose_asset") or s.get("pose") or "") for s in scenes]
    warnings: list[str] = []
    if len(scenes) >= 6 and len(set(families)) < 5:
        warnings.append("low_scene_family_diversity")
    if len(scenes) >= 6 and len(set(palettes)) < 3:
        warnings.append("low_palette_diversity")
    for name, values in (("family", families), ("palette", palettes), ("pose", poses)):
        for i in range(2, len(values)):
            if values[i] and values[i] == values[i - 1] == values[i - 2]:
                warnings.append(f"three_consecutive_{name}:{i-2}-{i}")
                break
    score = max(0, 100 - 20 * len(warnings))
    return {"score": score, "warnings": warnings, "families": families, "palettes": palettes, "pose_assets": poses}
