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
    "ambient_context": (
        "0s: keep every person and mascot completely still. Animate only one existing practical light, "
        "one existing cable or machine glow, and a few small dust motes. 3s: the glow returns to its original state. "
        "Do not introduce a mascot, person, hand, sign, text, number, chart, or new prop. Camera remains locked."
    ),
}


def build_kling_motion_prompt(scene_or_motion_type) -> dict:
    """장면 메타데이터를 반영한 고정 카메라 프롬프트와 네거티브를 반환한다."""
    scene = scene_or_motion_type if isinstance(scene_or_motion_type, dict) else {}
    motion_type = str(scene.get("motion_type") if scene else scene_or_motion_type or "walking_intro")
    if scene and not bool(scene.get("character_required", True)) and not scene.get("motion_type"):
        motion_type = "ambient_context"
    if motion_type not in KLING_MOTION_TEMPLATES:
        logger.warning("Unknown motion type: %s. Defaulting to walking_intro.", motion_type)
        motion_type = "walking_intro"

    # 대본/에디터가 준 동작·감정·편집 신호를 실제 요청에 반영한다. 값이
    # 비어 있으면 템플릿만 사용하며, 숫자/사실 데이터를 새로 만들지 않는다.
    action = str(scene.get("character_action") or scene.get("action") or "").strip()
    emotion = str(scene.get("emotion_tag") or scene.get("emotion") or "").strip()
    edit = str(scene.get("edit_marker") or scene.get("edit") or "").strip()
    metadata_clause = " ".join(
        clause for clause in (
            f"Character action: {action}." if action else "",
            f"Emotion: {emotion}." if emotion else "",
            f"Edit beat: {edit}." if edit else "",
        ) if clause
    )

    style_prefix = KLING_MOTION_TEMPLATES["_style_prefix"]
    if scene and not bool(scene.get("character_required", True)):
        style_prefix = style_prefix.replace(
            "Animate only the mascot, one existing reactive prop, and one light or particle effect. ",
            "Animate only one existing reactive prop and one light or particle effect; do not introduce a mascot or person. ",
        )

    return {
        "prompt": style_prefix + metadata_clause + " " + KLING_MOTION_TEMPLATES[motion_type],
        "negative_prompt": KLING_MOTION_TEMPLATES["_negative"],
    }
