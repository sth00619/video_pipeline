"""장면의 다양성과 무관하게 모든 운영 이미지가 지켜야 하는 공통 품질 계약."""
from __future__ import annotations

from typing import Any

from app.utils.image_text_contract import build_scene_text_contract


_SHARED_QUALITY_FLOOR = (
    "dominant round gold-coin silhouette, compact limbs, and sound anatomy while scene costumes may wrap modestly below the rim",
    "intentional readable face construction at the presented scale",
    "scene-role-appropriate expression, action, and wardrobe",
    "original 2D editorial-comic ink and cel-shading family",
    "narration-specific physical economic storytelling",
    "information-rich set outside bounded text surfaces",
    "only scene-approved exact text and deterministic financial values",
)


def _direction_value(scene: dict[str, Any], *keys: str) -> str:
    spec = scene.get("scene_spec") or {}
    direction = scene.get("art_direction") or {}
    render = scene.get("v5_render_contract") or {}
    for key in keys:
        value = spec.get(key) or direction.get(key) or render.get(key)
        if str(value or "").strip():
            return str(value).strip()
    return ""


def build_scene_visual_quality_contract(
    scene: dict[str, Any] | None,
    *,
    text_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """공통 합격 하한선과 대본별 연출 변수를 분리해 한 계약으로 만든다.

    같은 의상이나 표정을 강제하지 않는다. 대신 장면이 선택한 의상·표정·행동이
    실제 결과에 맞는지, 모든 장면이 같은 품질 하한선을 넘는지를 검수한다.
    """
    source = scene or {}
    text = text_contract or build_scene_text_contract(source)
    approved_count = len(text.get("approved_texts") or [])
    if approved_count <= 1:
        max_surface_ratio = 0.16
    elif approved_count <= 4:
        max_surface_ratio = 0.22
    else:
        max_surface_ratio = 0.24
    direction = source.get("art_direction") or {}
    character_required = bool(direction.get("character_required", True))
    return {
        "version": "scene-visual-quality-floor-v2",
        "shared_quality_floor": list(_SHARED_QUALITY_FLOOR),
        "character_required": character_required,
        "scene_variables": {
            "wardrobe": _direction_value(source, "character_costume", "wardrobe", "scene_wardrobe"),
            "emotion": _direction_value(source, "character_emotion", "emotion"),
            "action": _direction_value(source, "character_action", "action"),
            "setting": _direction_value(source, "setting", "scene_setting"),
        },
        "face_policy": {
            "require_intentional_readable_construction": character_required,
            "allow_closed_or_simplified_eyes_when_expression_is_intentional": True,
            "allow_scale_appropriate_detail_reduction": True,
            "forbid_accidental_featureless_or_foreign_face_language": character_required,
        },
        "silhouette_policy": {
            "coin_disc_must_remain_dominant": character_required,
            "costume_wrap_below_rim_allowed": True,
            "independent_narrow_neck_human_trunk_forbidden": character_required,
            "maximum_visible_leg_to_coin_diameter_ratio": 0.50,
        },
        "deterministic_surface": {
            # 생성 허용 짧은 문구와 결정론 문구 모두 장면을 압도하는 거대 보드에
            # 몰리지 않도록 같은 공간 예산을 사용한다. 결정론 값 자체는 계속 모델에
            # 전달하지 않고 후단 렌더러가 쓴다.
            "required": bool(text.get("approved_texts")),
            "approved_text_count": approved_count,
            "max_single_surface_frame_ratio": max_surface_ratio,
            "minimum_storytelling_frame_ratio": 0.60,
            "must_be_scene_integrated": True,
        },
        "variation_policy": (
            "not a fixed costume, expression, pose, camera, or background template; "
            "variation is required when the approved narration calls for it"
        ),
    }


def scene_visual_quality_prompt(contract: dict[str, Any]) -> str:
    """생성 모델에 공통 하한선과 장면 변수를 혼동 없이 전달한다."""
    variables = contract.get("scene_variables") or {}
    surface = contract.get("deterministic_surface") or {}
    ratio_percent = round(float(surface.get("max_single_surface_frame_ratio") or 0.16) * 100)
    clauses = [
        "COMMON CROSS-SCENE ACCEPTANCE FLOOR: this is a quality floor, not a fixed costume, expression, pose, or background template.",
        "Keep the round gold-coin disc as the dominant unified head-and-upper-body identity and keep each visible leg roughly half the coin diameter or shorter. A scene costume may wrap modestly below the rim, but it must not become an independent narrow-necked human trunk. Keep an intentional readable face at its presented scale; deliberate closed eyes or simplified action eyes are allowed only when the full expression remains coherent.",
        "Keep the original 2D editorial-comic family with variable dark ink outlines, cel shading, layered color, and narration-specific physical economic storytelling.",
        "Outside any text-bearing surface, preserve information-rich economic storytelling with relevant props, mechanisms, depth, and causal action rather than generic decoration or empty studio space.",
    ]
    if variables.get("wardrobe"):
        clauses.append(f"This scene's wardrobe role is: {variables['wardrobe']}.")
    if variables.get("emotion"):
        clauses.append(f"This scene's expression role is: {variables['emotion']}.")
    if variables.get("action"):
        clauses.append(f"This scene's action role is: {variables['action']}.")
    if surface.get("required"):
        clauses.append(
            f"The single largest calm deterministic typography surface may occupy no more than {ratio_percent} percent of the frame; "
            "it must remain a subordinate in-world prop, while at least 60 percent of the frame communicates the scene's economic story."
        )
    return " " + " ".join(clauses)
