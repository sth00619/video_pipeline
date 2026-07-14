"""
app/runtime_config.py — 재빌드 없이 즉시 조정 가능한 파이프라인 파라미터

지금까지 TTS 속도, ElevenLabs 목소리 설정, 씬 길이 같은 값을 바꾸려면
매번 코드를 열어 숫자를 고치고 Docker 이미지를 다시 빌드해야 했습니다.
클라이언트 피드백 대응 한 번 할 때마다 Antigravity 에이전트 세션을 새로
띄우고 빌드→테스트를 반복하는 구조라 rate limit이 금방 소진되는
원인 중 하나였습니다.

이 모듈은 그 값들을 프로세스 메모리에 올려두고, main.py의
GET/POST /pipeline/config API로 즉시 읽고 쓸 수 있게 합니다.

config.py의 값들은 "컨테이너가 처음 뜰 때의 초기값(환경변수 기준)"이고,
실제 워커들이 매 요청마다 참조하는 값은 이 모듈의 _state 입니다.

주의:
  - 이 값들은 프로세스 메모리에만 있습니다. 컨테이너가 재시작되면
    config.py의 환경변수 기본값으로 다시 초기화됩니다.
  - fastapi-workers 컨테이너를 여러 개로 수평 확장할 계획이 있다면,
    이 저장소를 Redis로 옮기는 것을 권장합니다 (REDIS_HOST가 이미
    docker-compose에 있어 전환 비용은 크지 않습니다).
"""
from app import config as _cfg

_state = {
    "tts_speed": _cfg.TTS_SPEED,
    "chars_per_minute": _cfg.CHARS_PER_MINUTE,
    "scene_duration_sec": _cfg.SCENE_DURATION_SEC,
    "subtitle_max_chars": _cfg.SUBTITLE_MAX_CHARS,
    "subtitle_font_size": _cfg.SUBTITLE_FONT_SIZE,
    "subtitle_theme": _cfg.SUBTITLE_THEME,
    "image_headline_overlay": _cfg.IMAGE_HEADLINE_OVERLAY,
    "image_provider": _cfg.IMAGE_PROVIDER,
    "image_quality_tier": _cfg.IMAGE_QUALITY_TIER,
    "pro_image_max_scenes": _cfg.PRO_IMAGE_MAX_SCENES,
    "gemini_pro_batch_enabled": _cfg.GEMINI_PRO_BATCH_ENABLED,
    "gemini_pro_batch_fallback_enabled": _cfg.GEMINI_PRO_BATCH_FALLBACK_ENABLED,
    "gemini_service_tier": _cfg.GEMINI_SERVICE_TIER,
    "visual_qa_enabled": _cfg.VISUAL_QA_ENABLED,
    "visual_qa_max_scenes": _cfg.VISUAL_QA_MAX_SCENES,
    "elevenlabs_voice_id": _cfg.ELEVENLABS_VOICE_ID,
    "elevenlabs_stability": _cfg.ELEVENLABS_STABILITY,
    "elevenlabs_similarity_boost": _cfg.ELEVENLABS_SIMILARITY_BOOST,
    "elevenlabs_style": _cfg.ELEVENLABS_STYLE,
    "bgm_volume": _cfg.BGM_VOLUME,
    "zoompan_speed": _cfg.ZOOMPAN_SPEED,
    "zoompan_max_zoom": _cfg.ZOOMPAN_MAX_ZOOM,
    "intro_kling_seconds_5min": _cfg.INTRO_KLING_SECONDS_5MIN,
    "intro_kling_seconds_10min": _cfg.INTRO_KLING_SECONDS_10MIN,
    "intro_kling_seconds_15min": _cfg.INTRO_KLING_SECONDS_15MIN,
    "intro_kling_seconds_20min": _cfg.INTRO_KLING_SECONDS_20MIN,
    "intro_kling_max_clips": _cfg.INTRO_KLING_MAX_CLIPS,
}

_TYPES = {k: type(v) for k, v in _state.items()}
_DEFAULTS = dict(_state)


def get() -> dict:
    """현재 적용 중인 전체 파라미터 스냅샷을 반환합니다."""
    return dict(_state)


def value(key: str):
    """단일 파라미터 값을 반환합니다. 워커들은 이 함수로 값을 읽습니다."""
    return _state[key]


def update(**kwargs) -> dict:
    """전달된 키만 갱신합니다 (None 값은 무시). 잘못된 키/타입은 에러."""
    for k, v in kwargs.items():
        if v is None:
            continue
        if k not in _state:
            raise KeyError(f"알 수 없는 파이프라인 파라미터: {k}")
        expected = _TYPES[k]
        try:
            _state[k] = expected(v)
        except (TypeError, ValueError):
            raise ValueError(f"{k}는 {expected.__name__} 타입이어야 합니다: 받은 값={v!r}")
    return dict(_state)


def reset_to_env_defaults() -> dict:
    """config.py의 환경변수 기본값으로 되돌립니다 (응급 복구용)."""
    _state.update(_DEFAULTS)
    return dict(_state)
