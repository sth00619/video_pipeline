"""V5 씬 계약을 운영 이미지 워커가 소비할 수 있는 형태로 만든다.

이 모듈은 이미지 API를 호출하지 않는다. ScriptWorker가 만든 ``scene_type``을
V5 archetype/프롬프트/사실 오버레이 계약으로 변환하는 순수 계획 단계다.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.v5.providers.router import RENDER_BLOCKED_ARCHETYPES
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
PRESENTATION_BY_ARCHETYPE: dict[str, tuple[str, str, str, str]] = {
    "port_emergency": ("alarm", "safety_vest", "alarmed_run", "right"),
    "retail_shock": ("surprise", "analyst", "calculator_hold", "left"),
    "classroom": ("explain", "professor", "point_left", "right"),
    "weather_map": ("explain", "reporter", "present", "right"),
    "risk_control_room": ("concern", "formal", "present", "center"),
    "trade_calculator": ("confidence", "vest", "think", "left"),
    "data_lab": ("explain", "reporter", "present", "right"),
    "briefing_podium": ("explain", "reporter", "present", "center"),
    "real_estate_office": ("explain", "analyst", "calculator_hold", "right"),
    "job_market_hall": ("explain", "reporter", "present", "left"),
}


def _scene_identifier(scene: dict[str, Any], index: int) -> str:
    return str(scene.get("scene_id") or scene.get("id") or f"scene_{index:03d}")


def _is_information_scene(scene_type: str) -> bool:
    return scene_type in {"metric", "graph", "diagram", "text"}


def plan_v5_scene_contract(scene: dict[str, Any], index: int) -> dict[str, Any]:
    """한 씬의 V5 배경·사실층 계약을 반환한다.

    ``v5_verified_overlays``의 사실성 검증 및 실제 합성은 렌더 후
    ``diegetic_fact_overlay``가 담당한다. 이 함수는 좌표를 추정하거나
    수치를 만들어 넣지 않는다.
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

    emotion, costume, pose, character_position = presentation
    spec = SceneSpec(
        scene_id=_scene_identifier(scene, index),
        archetype=selection.archetype,
        emotion=emotion,
        costume=costume,
        pose=pose,
        character_position=character_position,
    )
    information_scene = _is_information_scene(scene_type)
    policy = "diegetic_decorative" if information_scene else "strict_textless"
    prompt = build_prompt(spec, scene_type_selection=selection, visual_text_policy=policy)

    # hero/body는 Router가 Gemini Pro 우선 lane을 선택한다. draft에서만 klein
    # 후보가 될 수 있으며, 운영 계획은 draft를 지정하지 않는다.
    tier = "hero" if information_scene else "body"
    return {
        "scene_id": spec.scene_id,
        "scene_type": scene_type,
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
        "style_contract_version": V5_STYLE_CONTRACT_VERSION,
        "primary_surface_region": primary_surface_region(selection.archetype),
        "verified_overlay_mode": (
            "apply_verified_values_after_generation" if information_scene else "not_applicable"
        ),
        "verified_overlay_present": bool(scene.get("v5_verified_overlays")),
    }


def attach_v5_scene_contracts(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """원본 필드를 보존하며 각 씬에 V5 운영 계약을 첨부한다."""
    planned: list[dict[str, Any]] = []
    for index, source in enumerate(scenes):
        scene = dict(source)
        contract = plan_v5_scene_contract(scene, index)
        scene["v5_render_contract"] = contract
        # 기존 워커의 프롬프트 필드를 그대로 이용하되, V5 계약이 우선임을
        # 별도 필드로도 남겨 후속 감사와 드라이런에서 확인할 수 있게 한다.
        scene["v5_scene_type_selection"] = contract["selection"]
        scene["v5_scene_spec"] = contract["scene_spec"]
        # V5 final lane은 hero/body 모두 Gemini Pro만 사용한다. 기존 품질
        # 분배기가 flash로 낮추거나 전역 IMAGE_PROVIDER가 fal이어도 이 계약을
        # 가진 씬의 모델 선택은 바뀌지 않는다.
        image_profile = dict(scene.get("image_profile") or {})
        image_profile.update({
            "tier": "pro",
            "model": "gemini-3-pro-image",
            "image_size": "2K",
            "v5_final_lane": True,
        })
        scene["image_profile"] = image_profile
        planned.append(scene)
    return planned


def prompt_for_scene(scene: dict[str, Any]) -> str | None:
    """V5 운영 계약이 있으면 해당 프롬프트만 반환한다."""
    contract = scene.get("v5_render_contract")
    if not isinstance(contract, dict):
        return None
    prompt = contract.get("prompt_en")
    return str(prompt) if isinstance(prompt, str) and prompt.strip() else None


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
        "gemini_max_attempts": 1,
        "suppress_legacy_style_lock": True,
        "style_locked": True,
        "gemini_reference_contract_declared": True,
    }
