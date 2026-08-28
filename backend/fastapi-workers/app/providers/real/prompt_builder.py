"""Locked visual language for every Gemini image request."""
from __future__ import annotations

from app.pipeline.scene_director import SceneSpec
from app.utils.art_direction import SHARED_STYLE_LOCK_PROMPT
from app.utils.character_integrity_contract import COIN_SILHOUETTE_CONTRACT

STYLE_LOCK = SHARED_STYLE_LOCK_PROMPT

# 전역 스타일 계약도 이제 장면이 지정한 물리 표면 하나를 허용한다. 템플릿은
# 그 허용 범위를 "정확히 하나"로 더 좁혀 보드 검출과 화풍 보존을 함께 고정한다.
TEMPLATE_STYLE_LOCK = STYLE_LOCK + (
    " Depict exactly one bounded unlabeled physical information board or screen specified by the scene template. "
    "It must be a real prop with a matte interior and dark border, never a UI card, dashboard, document, title card, or floating rectangle. "
    "Keep it subordinate to the economic story and keep every other area as a dense continuous full-bleed illustrated background."
)

CHARACTER_LOCK = (
    "Goldie is an original anthropomorphic gold coin mascot with an embossed dotted rim, expressive cartoon eyes and eyebrows, "
    "rosy cheeks and white-gloved four-fingered hands. "
    + COIN_SILHOUETTE_CONTRACT
    +
    "Preserve the broad face-construction, silhouette, palette and 2D line-language range across the attached channel references while allowing the scene-specific expression and outfit; "
    "do not create a second mascot."
)


def build_prompt(spec: SceneSpec, market_chart: dict | None = None, template=None) -> str:
    props = "; ".join(spec.props[:6])
    side = f" Supporting characters: {spec.side_characters}." if spec.side_characters else ""
    
    data_surface_clause = ""
    if market_chart:
        data_surface_clause = (
            " The mascot character stands entirely within the LEFT third of the frame."
            " The RIGHT side contains one bounded illustrated charcoal chalkboard or painted cartoon panel occupying no more than roughly 22 percent of the frame,"
            " completely empty inside, with hand-drawn frame edges and subtle chalk texture; the remaining frame stays dense with narration-specific economic context. No text, numbers, chart,"
            " or character parts overlapping the panel."
        )
        
    if template is not None:
        # v4는 생성 모델에 숫자/글자를 맡기지 않는다. 보드의 물리적 자리만
        # 장면 생성 전 계약으로 확보하고, 정보는 이후 결정론 합성으로 넣는다.
        template_scene = template.prompt_en.format(setting_detail=spec.setting)
        return "\n".join((
            TEMPLATE_STYLE_LOCK, CHARACTER_LOCK,
            f"SCENE TEMPLATE: {template_scene}",
            f"CHARACTER: Goldie wears {template.character.costume}; pose {template.character.pose_asset}; looking at the board, {template.character.hand} toward it.",
            "The character, gloves, pointer and any foreground prop must stay entirely on the opposite side of the board and never overlap its interior.",
            "The board is an unlabeled physical prop, not a UI card. All Korean copy, numbers and diagrams are post-production only.",
        ))
    return "\n".join((
        STYLE_LOCK, CHARACTER_LOCK,
        f"SCENE: Goldie is a {spec.character_role} wearing {spec.character_costume}.",
        f"ACTION: {spec.character_action}. Emotion: {spec.character_emotion}.",
        f"SETTING: {spec.setting}. BACKGROUND PROPS, all visible: {props}.",
        f"CAMERA: {spec.camera}." + side,
        "Keep the top-left and lower 18 percent as ordinary full-bleed illustrated background; keep them visually readable "
        "for post-production text, but never create blank space, a board, a card, a rectangle, or any panel there.",
        data_surface_clause
    ))
