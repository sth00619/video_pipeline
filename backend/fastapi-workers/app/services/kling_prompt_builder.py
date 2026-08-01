import logging

logger = logging.getLogger(__name__)


KLING_MOTION_TEMPLATES = {
    # 공통 선두: 카메라와 기존 사실 표기를 바꾸지 않는다.
    "_style_prefix": (
        "2D cel-shaded cartoon animation. Preserve the exact source image composition, "
        "character identity, line weight, palette, and all existing scene objects. "
        "Camera is locked: no pan, zoom, dolly, roll, shake, reframing, or crop change. "
        "Animate only the mascot, one existing reactive prop, and one light or particle effect. "
        "Preserve every existing written mark, number, chart shape, and factual overlay exactly; "
        "do not create, erase, translate, redraw, morph, or animate any text or number. "
    ),
    # 공통 네거티브: 숫자/글자 보존과 배경 재설계를 함께 차단한다.
    "_negative": (
        "no 3D rendering, no photorealism, no face morphing, no outfit change, "
        "no color shift, no extra characters, no warped hands, no jitter, "
        "no camera movement, no background redesign, no new screen, no new panel, "
        "no text distortion, no number distortion, no chart redraw, no changing labels, "
        "no changing factual overlay"
    ),
    "chart_shock": (  # 급락/급등 리액션
        "0–1s: the mascot sharply leans back and raises one open hand in a single surprised reaction. "
        "1–3s: the mascot takes one short backward step and settles. "
        "3–5s: one existing alert light or existing chart glow briefly brightens once, then returns to its original state; "
        "three to five small dust or sparkle particles rise and fade. "
        "Do not animate, redraw, or change any chart line, text, number, label, or overlay. Camera remains locked."
    ),
    "pointing_explain": (  # 지표/보드 설명
        "0–2s: the mascot raises the existing pointer or open hand toward the already-visible information surface. "
        "2–4s: make one gentle tap or one short presenting sweep, then stop; do not draw on the surface. "
        "4–5s: the mascot gives one confident nod while a soft existing room light subtly blooms and a few dust motes drift. "
        "Do not animate, redraw, or change any chart, text, number, label, or overlay. Camera remains locked."
    ),
    "thinking_desk": (
        "0–2s: the mascot rests its chin on one hand and glances once toward an existing desk prop. "
        "2–4s: one blink and a small eyebrow raise; keep the body otherwise still. "
        "4–5s: an existing desk lamp reflection or ambient rim light softly pulses once while a few dust motes fade through the air. "
        "Do not animate, redraw, or change any screen contents, chart, text, number, label, or overlay. Camera remains locked."
    ),
    "walking_intro": (  # 오프닝 등장
        "0–3s: the mascot makes exactly two small in-place walking steps within its original footprint; "
        "do not approach the camera or change framing. 3–5s: the mascot stops and gives one short wave. "
        "If an existing physical prop can naturally react, make only that prop sway slightly; otherwise use only a few background particles. "
        "Do not create or change signs, text, numbers, charts, labels, or overlays. Camera remains locked."
    ),
    "celebration": (
        "0–2s: the mascot raises both arms once. 2–4s: one compact joyful hop in place, then land in the same position. "
        "4–5s: one existing warm light or already-present sparkle effect brightens gently and fades. "
        "Do not create trophies, coins, labels, numbers, charts, or text; do not alter any existing overlay. Camera remains locked."
    ),
}


def build_kling_motion_prompt(scene_motion_type: str) -> dict:
    """씬의 모션 유형에 맞는 고정 카메라 프롬프트와 네거티브를 반환한다."""
    motion_type = scene_motion_type or "walking_intro"
    if motion_type not in KLING_MOTION_TEMPLATES:
        logger.warning("Unknown motion type: %s. Defaulting to walking_intro.", motion_type)
        motion_type = "walking_intro"

    return {
        "prompt": KLING_MOTION_TEMPLATES["_style_prefix"] + KLING_MOTION_TEMPLATES[motion_type],
        "negative_prompt": KLING_MOTION_TEMPLATES["_negative"],
    }
