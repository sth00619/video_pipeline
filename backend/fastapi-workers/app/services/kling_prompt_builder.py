import logging

logger = logging.getLogger(__name__)

KLING_MOTION_TEMPLATES = {
    # 공통 서두 (스타일 고정)
    "_style_prefix": (
        "2D cel-shaded cartoon animation, keep the exact art style, colors, "
        "line weight and character design of the source image. "
    ),
    # 공통 negative (2D 캐릭터 워핑/실사화 방지)
    "_negative": (
        "no 3D rendering, no realistic skin texture, no face morphing, "
        "no outfit change, no color shift, no extra characters, "
        "no warping hands, no jittery motion, no text distortion, "
        "no camera shake, background stays static"
    ),
    "chart_shock": (  # 급락/급등 리액션
        "0-1s: the coin mascot leans toward the chart. "
        "1-3s: eyes widen, mouth opens in surprise, small hop backward. "
        "3-5s: the red candlestick line on the screen pulses with a soft glow, "
        "tiny sparkle particles drift upward. Camera: locked, no movement."
    ),
    "pointing_explain": (  # 지표/보드 설명
        "0-2s: the mascot raises the pointer stick toward the board. "
        "2-4s: gentle tapping motion on the board, head tilts slightly. "
        "4-5s: confident nod and smile. Floating dust motes shimmer in sunlight. "
        "Camera: locked, no movement."
    ),
    "thinking_desk": (
        "0-2s: the mascot rests chin on hand, eyes glance at the laptop screen. "
        "2-4s: blinks twice, subtle breathing motion of the body. "
        "4-5s: raises one eyebrow. Screen chart glows softly. Camera: locked, no movement."
    ),
    "walking_intro": (  # 오프닝 등장
        "0-3s: the mascot walks toward camera with a light bounce in each step. "
        "3-5s: stops, waves one hand, warm smile. "
        "Background particles drift slowly. Camera: locked, no movement."
    ),
    "celebration": (
        "0-2s: the mascot raises both arms. 2-4s: small joyful jump, "
        "gold coin sparkles burst gently around. 4-5s: lands, thumbs up. "
        "Camera: locked, no movement."
    ),
}

def build_kling_motion_prompt(scene_motion_type: str) -> dict:
    """
    scene_motion_type에 맞는 프롬프트와 네거티브 프롬프트를 구성해 반환합니다.
    """
    motion_type = scene_motion_type or "walking_intro"
    if motion_type not in KLING_MOTION_TEMPLATES:
        logger.warning(f"Unknown motion type: {motion_type}. Defaulting to walking_intro.")
        motion_type = "walking_intro"
        
    prompt = KLING_MOTION_TEMPLATES["_style_prefix"] + KLING_MOTION_TEMPLATES[motion_type]
    negative = KLING_MOTION_TEMPLATES["_negative"]
    
    return {
        "prompt": prompt,
        "negative_prompt": negative
    }
