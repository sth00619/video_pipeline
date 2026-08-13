"""V5 씬 계약을 운영 이미지 워커가 소비할 수 있는 형태로 만든다.

이 모듈은 이미지 API를 호출하지 않는다. ScriptWorker가 만든 ``scene_type``을
V5 archetype/프롬프트/사실 오버레이 계약으로 변환하는 순수 계획 단계다.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any
import re

from app.postprocess.text_overlay import script_caption, script_visual_plan
from app.utils.entity_english_map import ENTITY_REGISTRY, get_entity_english_name

from app.v5.providers.router import RENDER_BLOCKED_ARCHETYPES
from app.v5.scene.layout_sketcher import LayoutSketcher
from app.v5.scene.prompt_builder import (
    V5_STYLE_CONTRACT_VERSION,
    SceneSpec,
    build_prompt,
)
from app.v5.scene.scene_type_archetypes import (
    SCENE_TYPES,
    ArchetypeSelection,
    primary_surface_region,
    recommend_v5_archetype,
)


# 검증을 거친 11개 archetype의 캐릭터 연출 기본값이다. 대본 수치나 사실을
# 여기서 만들지 않으며, 씬 내용은 archetype 추천에만 사용한다.
# 포지션 다양화 (BENCHMARK_SCENES 관찰 기반 — prompt_builder.py 참조):
#   bench_02_retail  → left   bench_06_risk  → center   bench_07_trade → left
#   bench_08_datalab → center (이하 나머지 → right)
# layout_instruction이 <layout_contract>로 마지막에 주입되므로
# 여기서의 position 값이 Gemini 프롬프트 final position을 결정한다.
PRESENTATION_BY_ARCHETYPE: dict[str, tuple[str, str, str, str]] = {
    # (emotion, costume, pose, character_position)
    "port_emergency":    ("alarm",      "safety_vest",       "alarmed_run",     "right"),
    "retail_shock":      ("surprise",   "analyst",           "calculator_hold", "left"),
    "classroom":         ("explain",    "professor",         "point_left",      "right"),
    "weather_map":       ("explain",    "reporter",          "present",         "right"),
    "risk_control_room": ("concern",    "reporter",          "present",         "center"),
    "trade_calculator":  ("confidence", "vest",              "think",           "left"),
    "data_lab":          ("explain",    "reporter",          "present",         "center"),
    "briefing_podium":   ("confidence", "tuxedo_host",       "present",         "right"),
    "real_estate_office":("explain",    "architect_planner", "calculator_hold", "left"),
    "job_market_hall":   ("explain",    "reporter",          "present",         "left"),
    # earnings_stage: 기업실적·EPS·배당 — 중앙 연단에서 자신감 있는 발표 포즈
    "earnings_stage":    ("confidence", "tuxedo_host",       "present",         "center"),
}


# 기존 PRESENTATION_BY_ARCHETYPE 4요소 계약은 검수 도구와의 호환성을 위해
# 유지하고, 포즈 후보만 별도 선택 계약으로 보강한다. 씬 인덱스 기반 순환은
# 같은 입력에서 같은 결과를 내므로 재생성·감사 시에도 재현할 수 있다.
POSES_BY_ARCHETYPE: dict[str, tuple[str, ...]] = {
    "port_emergency": ("alarmed_run", "point_left"),
    "retail_shock": ("calculator_hold", "think"),
    "classroom": ("point_left", "present"),
    "weather_map": ("present", "point_left"),
    "risk_control_room": ("present", "think"),
    "trade_calculator": ("think", "calculator_hold"),
    "data_lab": ("present", "point_left"),
    "briefing_podium": ("present", "point_left"),
    "real_estate_office": ("calculator_hold", "present"),
    "job_market_hall": ("present", "point_left"),
    "earnings_stage": ("present", "point_left"),
}


def _select_pose(poses: tuple[str, ...], index: int) -> str:
    """씬 인덱스 기반 결정론적 순환 선택으로 재현성을 유지한다."""
    if not poses:
        return "present"
    return poses[index % len(poses)]


# 생성·검수·산출물 원장에 공통으로 남기는 세 가지 장면 계약이다. 이 계약은
# 이미지 API 제공자와 무관하며, V5 프롬프트와 후속 영상 조립이 같은 규칙을
# 소비하게 하는 단일 기준점이다.
VISUAL_MODE_CONTRACTS: dict[str, dict[str, str]] = {
    "article_evidence": {
        "asset_source": "verified_article_capture",
        "text_policy": "source_capture_only",
        "overlay_policy": "underline_highlight_and_source_credit_only",
        "numeric_visual_policy": "source_document_only",
        "character_policy": "no_generated_mascot",
    },
    "semantic_illustration": {
        "asset_source": "v5_gemini_scene",
        "text_policy": "strict_textless",
        "overlay_policy": "ass_subtitle_only",
        "numeric_visual_policy": "prohibited",
        "character_policy": "fixed_reference_when_character_required",
    },
    "archetype_explainer": {
        "asset_source": "v5_gemini_scene",
        "text_policy": "single_script_caption_on_primary_prop",
        "overlay_policy": "ass_subtitle_only",
        "numeric_visual_policy": "prohibited",
        "character_policy": "fixed_reference_when_character_required",
    },
}


def _build_v5_verified_overlays(
    verified_facts: list | None,
    archetype: str,
    primary_region: tuple[float, float, float, float],
) -> list[dict[str, Any]] | None:
    """verified_facts에서 diegetic_surface_fact overlay를 자동 생성한다.

    생성 규칙:
    - value가 fact["figure"] 또는 fact["fact"] 원문에 정확히 포함돼야 한다.
      이는 downstream facts_from_verified_scene()와 동일한 조건이다.
    - primary_surface_region 좌표를 anchor로 사용하므로 V5 표면 범위 검증을
      자동으로 통과한다.
    - primary 표면 하나에 사실 하나(첫 번째 통과 사실만 사용).
    - 어느 사실도 조건을 만족하지 않으면 None을 반환한다.

    이 함수는 숫자를 생성하거나 변형하지 않는다. verified_facts 원문 값만
    그대로 사용한다.
    """
    if not isinstance(verified_facts, list) or not verified_facts:
        return None
    if not primary_region or not archetype:
        return None

    x, y, w, h = primary_region

    # downstream facts_from_verified_scene()과 동일한 normalise 로직
    def _norm(s: str) -> str:
        return "".join(s.split()).casefold()

    for i, fact in enumerate(verified_facts):
        if not isinstance(fact, dict):
            continue
        value = str(fact.get("value") or "").strip()
        if not value:
            continue
        # value가 figure·fact 원문에 그대로 있어야 downstream 검증을 통과한다
        evidence = " ".join(str(fact.get(k) or "") for k in ("figure", "fact"))
        if _norm(value) not in _norm(evidence):
            continue
        label = str(fact.get("indicator") or fact.get("label") or "").strip()
        return [
            {
                "source_ref": f"facts[{i}]",
                "value": value,
                "label": label,
                "visualization": "text",
                "anchor": {
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "kind": "primary_surface",
                },
            }
        ]
    return None


def _scene_identifier(scene: dict[str, Any], index: int) -> str:
    return str(scene.get("scene_id") or scene.get("id") or f"scene_{index:03d}")


def _is_information_scene(scene_type: str) -> bool:
    return scene_type in {"metric", "graph", "diagram", "text"}


def _visual_mode(scene: dict[str, Any], scene_type: str) -> str:
    """실제 기사·상황 서사·정보형 소품을 구분해 롱폼의 반복을 막는다."""
    kind = str(scene.get("visual_kind") or scene.get("visual_type") or "").lower()
    if scene.get("article_capture") or kind in {"article_evidence", "article_scene"}:
        return "article_evidence"
    explicit_mode = str(scene.get("visual_mode") or "").strip()
    if explicit_mode in VISUAL_MODE_CONTRACTS:
        return explicit_mode
    return "archetype_explainer" if _is_information_scene(scene_type) else "semantic_illustration"


def _motion_contract(visual_mode: str, visual_text_policy: str, character_required: bool) -> dict[str, Any]:
    """이미지 유형별 Fal 모션 사용 가능 범위를 명시한다.

    모션은 영상의 초반 집중도를 높이는 선택 기능일 뿐, 이미지 계약을 바꾸는
    수단이 아니다. 따라서 읽을 글자·기사 캡처·정보 표면이 있는 장면은 항상
    정지 이미지로 유지하고, 텍스트 없는 일반형 장면도 편집자가 명시 선택한
    경우에만 Fal 입력으로 보낸다.
    """
    eligible = visual_mode == "semantic_illustration" and visual_text_policy == "strict_textless"
    return {
        "eligible": eligible,
        # eligible한 씬(텍스트/숫자 없는 순수 삽화)은 자동 선택을 허용한다.
        # eligible=False인 씬(기사 캡처·정보 표면 포함)은 여전히 수동 선택만 허용해
        # 숫자·텍스트 왜곡 위험을 완전히 차단한다.
        "requires_explicit_selection": not eligible,
        "character_required": character_required,
        "default_motion_type": "pointing_explain" if character_required else "ambient_context",
        "blocked_reasons": [] if eligible else [
            "article_capture_or_script_caption_or_information_surface",
        ],
    }


def _korean_context_visual_brief(scene: dict[str, Any]) -> str:
    """대본의 한국 맥락을 로고 없이 현지 공간·소품으로 전달한다."""
    source = " ".join(
        str(scene.get(key) or "")
        for key in (
            "narration", "script", "narration_text", "text_for_tts",
            "title", "content", "text", "visual_intent", "topic",
        )
    ).lower()
    if any(token in source for token in ("홈플러스", "하림", "마트", "슈퍼", "유통", "소비")):
        brief = (
            "When this scene is Korean retail, use a recognizably Korean hypermarket exterior or interior: Korean-style storefront proportions, "
            "produce crates, delivery carts, and local urban streets, but no real brand logo, readable Korean text, or price labels"
        )
    elif any(token in source for token in ("코스피", "코스닥", "삼성", "하이닉스", "국내", "한국", "원·달러", "원달러")):
        brief = (
            "Use a recognizably Korean business setting: Seoul-like office towers, Korean brokerage dealing-room proportions, local street and harbor details, "
            "or a Korean semiconductor industrial landscape; never use a generic Western storefront, real company logo, readable Korean text, or numeric signage"
        )
    else:
        brief = (
            "Use a Korean editorial-economic visual sensibility with locally familiar urban, retail, office, port, or factory details whenever the script has a Korea connection; "
            "do not use logos, readable Korean text, or numeric signage"
        )

    # 바인더 결과가 이미 있으면 재사용하고, V5 계약이 바인더보다 먼저 만들어지는
    # 최초 계획 호출에서만 레지스트리를 순회한다. 검증된 영문명은 의미 grounding
    # 전용이며 이미지 안에 회사명·로고·글자로 렌더링하지 않는다.
    candidates = scene.get("core_entities")
    if not isinstance(candidates, list) or not candidates:
        candidates = [entity for entity in ENTITY_REGISTRY if entity.lower() in source]
    entities_found: list[str] = []
    for entity in candidates:
        english_text, confidence = get_entity_english_name(str(entity))
        if confidence == "verified" and english_text not in entities_found:
            entities_found.append(english_text)
    if entities_found:
        brief = (
            f"{brief} Featured entities for semantic grounding only; do not render their names or logos: "
            f"{', '.join(entities_found[:3])}."
        )

    return brief


def _distinct_archetype_input(scene: dict[str, Any], previous_archetype: str) -> dict[str, Any]:
    """명시 선택은 보존하고, 바로 앞 장면과 같은 정보형 무대를 피한다."""
    candidate = dict(scene)
    if not previous_archetype or candidate.get("visual_archetype"):
        return candidate
    recommendation = recommend_v5_archetype(candidate)
    if recommendation.archetype == previous_archetype and recommendation.alternatives:
        candidate["visual_archetype"] = recommendation.alternatives[0]
        candidate["visual_mix_adjustment"] = {
            "reason": "consecutive_archetype_avoidance",
            "previous_archetype": previous_archetype,
            "selected_archetype": recommendation.alternatives[0],
        }
    return candidate


def plan_v5_scene_contract(scene: dict[str, Any], index: int) -> dict[str, Any]:
    """한 씬의 V5 배경·사실층 계약을 반환한다.

    ``v5_verified_overlays``의 사실성 검증과 실제 표면 교체는
    ``verified_surface_payload``와 info-surface 원근 합성기가 담당한다.
    이 함수는 좌표를 추정하거나 수치를 만들어 넣지 않는다.
    """
    scene_type = str(scene.get("scene_type") or "").strip().lower()
    if scene_type not in SCENE_TYPES:
        raise ValueError(f"V5 운영 씬에는 유효한 scene_type이 필요합니다: {scene_type or '(없음)'}")

    selection = recommend_v5_archetype(scene)
    if selection.archetype in RENDER_BLOCKED_ARCHETYPES:
        raise ValueError(f"현재 렌더 차단 archetype이 추천되었습니다: {selection.archetype}")
    presentation = PRESENTATION_BY_ARCHETYPE.get(selection.archetype)
    if presentation is None:
        raise ValueError(f"V5 운영용 캐릭터 연출이 없는 archetype: {selection.archetype}")

    emotion, costume, default_pose, character_position = presentation
    pose = _select_pose(POSES_BY_ARCHETYPE.get(selection.archetype, (default_pose,)), index)

    # 씬 방향성 기반 감정 오버라이드 (archetype 기본값보다 우선).
    # alarm / surprise 는 archetype 서사 강도가 높으므로 방향성으로 덮지 않는다.
    _DIRECTION_EMOTION_OVERRIDE: dict[str, dict[str, str]] = {
        "up":      {"explain": "happy",   "confidence": "happy",  "concern": "explain"},
        "down":    {"explain": "concern", "confidence": "concern", "happy": "concern"},
        "neutral": {},
    }
    _LOCKED_EMOTIONS = {"alarm", "surprise"}
    if emotion not in _LOCKED_EMOTIONS:
        from app.postprocess.text_overlay import script_visual_direction
        _direction = script_visual_direction(scene)
        emotion = _DIRECTION_EMOTION_OVERRIDE.get(_direction, {}).get(emotion, emotion)

    spec = SceneSpec(
        scene_id=_scene_identifier(scene, index),
        archetype=selection.archetype,
        emotion=emotion,
        costume=costume,
        pose=pose,
        character_position=character_position,
        character_required=bool(scene.get("character_required", True)),
    )
    visual_mode = _visual_mode(scene, scene_type)
    is_general_selection = bool(selection and selection.scene_type == "general")
    information_scene = (visual_mode == "archetype_explainer") and not is_general_selection
    visual_mode_contract = VISUAL_MODE_CONTRACTS[visual_mode]
    has_verified_surface_content = False
    policy = "script_captioned" if information_scene else "strict_textless"
    semantic_plan = script_visual_plan(scene)
    semantic_direction = semantic_plan["direction"]
    semantic_caption = semantic_plan["caption"] if information_scene else ""
    semantic_visual_brief = semantic_plan["prop_visuals"] if information_scene else semantic_plan["background_visuals"]
    layout = LayoutSketcher.for_mascot_position(
        spec.scene_id,
        occupancy=spec.frame_occupancy,
        position=spec.character_position,
    ) if spec.character_required else None
    prompt = build_prompt(
        spec,
        scene_type_selection=selection,
        visual_text_policy=policy,
        layout_instruction=layout.prompt_instruction() if layout else None,
        semantic_direction=semantic_direction,
        semantic_caption=semantic_caption,
        semantic_visual_brief=semantic_visual_brief,
        locale_visual_brief=_korean_context_visual_brief(scene),
    )
    visual_constraints = str(scene.get("visual_constraints") or "").strip()
    if visual_constraints:
        prompt = f"{prompt} <scene_specific_constraints> {visual_constraints} </scene_specific_constraints>"

    # hero/body는 Router가 Gemini Pro 우선 lane을 선택한다. draft에서만 klein
    # 후보가 될 수 있으며, 운영 계획은 draft를 지정하지 않는다.
    tier = "hero" if information_scene else "body"
    return {
        "scene_id": spec.scene_id,
        "scene_type": scene_type,
        "visual_mode": visual_mode,
        "visual_mode_contract": visual_mode_contract,
        "selection": {
            **asdict(selection),
            "physical_surfaces": list(selection.physical_surfaces),
            "alternatives": list(selection.alternatives),
        },
        "scene_spec": asdict(spec),
        "prompt_en": prompt,
        "provider": "gemini_pro",
        "tier": tier,
        "visual_text_policy": policy,
        "motion_contract": _motion_contract(
            visual_mode,
            policy,
            spec.character_required,
        ),
        "style_contract_version": V5_STYLE_CONTRACT_VERSION,
        "primary_surface_region": primary_surface_region(selection.archetype),
        "surface_caption": {
            "english": semantic_caption,
            "korean": script_caption(scene),
            "direction": semantic_direction,
            "target": selection.primary_physical_surface,
        } if information_scene else None,
        "semantic_visual_plan": semantic_plan,
        "verified_overlay_mode": "non_numeric_prompt_embedded_script_caption" if information_scene else "not_applicable",
        "verified_overlay_present": has_verified_surface_content,
    }


def attach_v5_scene_contracts(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """원본 필드를 보존하며 각 씬에 V5 운영 계약을 첨부한다."""
    planned: list[dict[str, Any]] = []
    previous_archetype = ""
    for index, source in enumerate(scenes):
        scene = _distinct_archetype_input(source, previous_archetype)
        contract = plan_v5_scene_contract(scene, index)
        scene["visual_mode"] = contract["visual_mode"]
        scene["motion_contract"] = contract["motion_contract"]
        scene["v5_render_contract"] = contract
        # 기존 워커의 프롬프트 필드를 그대로 이용하되, V5 계약이 우선임을
        # 별도 필드로도 남겨 후속 감사와 드라이런에서 확인할 수 있게 한다.
        scene["v5_scene_type_selection"] = contract["selection"]
        scene["v5_scene_spec"] = contract["scene_spec"]
        # 수치 전달의 기본 경로는 ASS 자막·TTS 내레이션이다.
        # WO-6C 이후: verified_facts에 figure·fact 원문이 있는 씬은 v5_verified_overlays를
        # 자동 생성해 archetype primary 표면에 수치를 Pillow로 추가 합성한다.
        # 수동으로 v5_verified_overlays를 지정한 씬은 자동 생성을 건너뛴다.
        # V5 final lane은 hero/body 모두 Gemini Pro만 사용한다. 기존 품질
        # 분배기가 flash로 낮추거나 전역 IMAGE_PROVIDER가 fal이어도 이 계약을
        # 가진 씬의 모델 선택은 바뀌지 않는다.
        if "v5_verified_overlays" not in scene:
            _injected = _build_v5_verified_overlays(
                scene.get("verified_facts"),
                contract["selection"]["archetype"],
                tuple(contract["primary_surface_region"]),
            )
            if _injected:
                scene["v5_verified_overlays"] = _injected
                contract["verified_overlay_present"] = True
                contract["verified_overlay_mode"] = "diegetic_surface_fact"
                scene["v5_render_contract"] = contract

        image_profile = dict(scene.get("image_profile") or {})
        image_profile.update({
            "tier": "pro",
            "model": "gemini-3-pro-image",
            "image_size": "2K",
            "v5_final_lane": True,
        })
        scene["image_profile"] = image_profile
        planned.append(scene)
        if contract["visual_mode"] != "article_evidence":
            previous_archetype = contract["selection"]["archetype"]
    return planned


def prompt_for_scene(scene: dict[str, Any]) -> str | None:
    """V5 운영 계약이 있으면 해당 프롬프트만 반환한다."""
    contract = scene.get("v5_render_contract")
    if not isinstance(contract, dict):
        return None
    prompt = contract.get("prompt_en")
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    # 실제 검증 수치가 있는 장면에서는 화풍용 픽셀 범위도 제거한다.
    # 이미지 모델과 감사 로그가 이를 금융 수치로 오인할 여지를 없앤다.
    if scene.get("verified_facts") or scene.get("facts"):
        prompt = re.sub(
            r"\s*\(3-5px equivalent\)", "", prompt, flags=re.IGNORECASE
        )
    # provider 호출보다 앞선 마지막 계약 경계에서 검증 수치를 차단한다.
    from app.v5.scene.prompt_fact_guard import assert_prompt_has_no_verified_numbers
    assert_prompt_has_no_verified_numbers(prompt, scene)
    return prompt


def is_v5_final_lane_scene(scene: dict[str, Any]) -> bool:
    """해당 씬이 V5 Gemini Pro 운영 계약을 갖는지 반환한다."""
    contract = scene.get("v5_render_contract")
    return isinstance(contract, dict) and contract.get("provider") == "gemini_pro"


def v5_provider_options(scene: dict[str, Any]) -> dict[str, Any]:
    """기존 이미지 제공자에 전달할 V5 최종 lane 강제 옵션이다.

    호출 횟수는 이 함수가 아니라 요청 단위 비용 게이트가 관리한다. 여기서는
    모델 하향 폴백과 제공자 혼합만 막고, HTTP 내부 재시도도 한 번으로 제한한다.
    """
    if not is_v5_final_lane_scene(scene):
        return {}
    return {
        "image_provider": "gemini",
        "gemini_model": "gemini-3-pro-image",
        "gemini_image_size": "2K",
        "gemini_service_tier": "standard",
        # 일시적인 5xx는 품질과 무관한 공급자 오류이므로, 예약된 재시도 버퍼 안에서
        # 같은 프롬프트를 한 번만 추가 시도한다. 그 외 임의 변형 재생성은 허용하지 않는다.
        "gemini_max_attempts": 2,
        "suppress_legacy_style_lock": True,
        "style_locked": True,
        "gemini_reference_contract_declared": True,
    }
