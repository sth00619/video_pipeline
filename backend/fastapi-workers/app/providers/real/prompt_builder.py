"""Locked visual language for every Gemini image request."""
from __future__ import annotations

from app.pipeline.scene_director import SceneSpec

STYLE_LOCK = (
    "2D digital comic illustration in an original Korean webtoon style. Bold clean dark-brown outlines on EVERY element; "
    "cel shading with soft gradients; highly saturated, organized colors; dramatic cinematic rim light and glow. "
    "The entire frame—background, character, and props—uses exactly the same illustration medium. "
    "A densely detailed themed background fills the frame edge-to-edge. STRICTLY NO photorealism, NO 3D render, "
    "NO photographic background, NO photo compositing, NO glossy toy material. NO text, NO letters, NO words, "
    "NO numbers, NO captions, NO logo, NO watermark anywhere in the generated image. Do not depict screens, dashboards, "
    "charts, signboards, documents, labels, UI panels, blank white rectangles, empty title cards, empty frames, boards, "
    "or presentation panels. Use unlabeled physical props and a continuous full-bleed illustrated background instead."
)

CHARACTER_LOCK = (
    "Goldie is an original anthropomorphic gold coin mascot with an embossed dotted rim, expressive cartoon eyes and eyebrows, "
    "rosy cheeks, white-gloved four-fingered hands, and thin dark legs. Preserve the exact face, silhouette, palette and line "
    "language of the attached reference sheet; do not create a second mascot."
)


def build_prompt(spec: SceneSpec) -> str:
    props = "; ".join(spec.props[:6])
    side = f" Supporting characters: {spec.side_characters}." if spec.side_characters else ""
    return "\n".join((
        STYLE_LOCK, CHARACTER_LOCK,
        f"SCENE: Goldie is a {spec.character_role} wearing {spec.character_costume}.",
        f"ACTION: {spec.character_action}. Emotion: {spec.character_emotion}.",
        f"SETTING: {spec.setting}. BACKGROUND PROPS, all visible: {props}.",
        f"CAMERA: {spec.camera}." + side,
        "Keep the top-left and lower 18 percent as ordinary full-bleed illustrated background; keep them visually readable "
        "for post-production text, but never create blank space, a board, a card, a rectangle, or any panel there.",
    ))
