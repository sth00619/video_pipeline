"""Locked visual language for every Gemini image request."""
from __future__ import annotations

from app.pipeline.scene_director import SceneSpec

STYLE_LOCK = (
    "NON-NEGOTIABLE ART DIRECTION: 2D digital cartoon illustration in an original Korean webtoon style. "
    "Bold clean dark-brown outlines on EVERY element; cel shading with soft gradients; highly saturated, organized colors; "
    "dramatic cinematic rim light and glow. The entire frame—background, character, props, blank data surfaces, and "
    "future overlay-safe areas—uses exactly the same hand-illustrated cartoon medium. "
    "A densely detailed themed background fills the frame edge-to-edge. STRICTLY NO photorealism, NO 3D render, "
    "NO photographic background, NO photo compositing, NO glossy toy material. NO text, NO letters, NO words, "
    "NO numbers, NO captions, NO logo, NO watermark anywhere in the generated image. Do not depict screens, dashboards, "
    "charts, signboards, documents, labels, UI panels, blank white rectangles, empty title cards, empty frames, boards, "
    "or presentation panels. Use unlabeled physical props and a continuous full-bleed illustrated background instead. "
    "Never mix a realistic photograph, realistic port, realistic studio, photographic texture, or a different art style into the frame."
)

# 템플릿 장면에는 빈 물리 보드를 허용한다. 전역 금지문을 그대로 쓰면
# 생성 모델이 v4의 보드 계약을 무시해 quad 검출이 구조적으로 실패한다.
TEMPLATE_STYLE_LOCK = STYLE_LOCK.replace(
    "Do not depict screens, dashboards, charts, signboards, documents, labels, UI panels, blank white rectangles, empty title cards, empty frames, boards, or presentation panels. Use unlabeled physical props and a continuous full-bleed illustrated background instead.",
    "Depict exactly one large unlabeled physical information board or screen specified by the scene template. It must be a real prop with a matte interior and dark border, never a UI card, dashboard, document, title card, or floating rectangle. Keep every other area as a continuous full-bleed illustrated background.",
)

CHARACTER_LOCK = (
    "Goldie is an original anthropomorphic gold coin mascot with an embossed dotted rim, expressive cartoon eyes and eyebrows, "
    "rosy cheeks, white-gloved four-fingered hands, and thin dark legs. Preserve the exact face, silhouette, palette and line "
    "language of the attached reference sheet; do not create a second mascot."
)


def build_prompt(spec: SceneSpec, market_chart: dict | None = None, template=None) -> str:
    props = "; ".join(spec.props[:6])
    side = f" Supporting characters: {spec.side_characters}." if spec.side_characters else ""
    
    data_surface_clause = ""
    if market_chart:
        data_surface_clause = (
            " The mascot character stands entirely within the LEFT third of the frame."
            " The RIGHT half of the frame contains a large blank illustrated charcoal chalkboard or painted cartoon panel,"
            " completely empty inside, with hand-drawn frame edges and subtle chalk texture; no text, numbers, chart,"
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
