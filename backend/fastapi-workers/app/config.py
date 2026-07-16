import os

APP_MODE = os.getenv("APP_MODE", "local")

# S3/MinIO
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_BUCKET = os.getenv("S3_BUCKET_NAME", "ai-video-assets")

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# API Keys (prod only)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_TTS_MODEL = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
KLING_API_KEY = os.getenv("KLING_API_KEY", "")
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY", "")
FAL_KEY = os.getenv("FAL_KEY", "")

# ─── 신규: 시장 데이터 / 뉴스 API Keys ─────────────────
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")       # 미국 주식 뉴스·시세
FRED_API_KEY = os.getenv("FRED_API_KEY", "")              # 연준 거시경제 지표
DART_API_KEY = os.getenv("DART_API_KEY", "")              # 한국 공시 PER/PBR (선택)
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")        # 네이버 검색 API
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "") # 네이버 검색 API

# Claude 모델 — 프로젝트 고정값. 임의 변경 절대 금지.
# (keyword_worker.py에 "claude-sonnet-5"라는 오타가 있었고,
#  providers/real/llm.py에는 구형 모델이 하드코딩되어 있었던 것을
#  이 상수로 통일해서 재발을 방지합니다.)
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
ANTHROPIC_PROMPT_CACHE_ENABLED = os.getenv("ANTHROPIC_PROMPT_CACHE_ENABLED", "true").lower() in {"1", "true", "yes"}
ANTHROPIC_PROMPT_CACHE_TTL = os.getenv("ANTHROPIC_PROMPT_CACHE_TTL", "5m")

# ══════════════════════════════════════════════════════════
# 파이프라인 동작 파라미터 초기값 (신규)
#
# 여기 값은 "컨테이너 시작 시 1회 로딩되는 기본값"입니다. 클라이언트
# 피드백에 맞춰 실시간으로 조정하려면 이 파일을 고치지 말고
# GET/POST /pipeline/config API(= app/runtime_config.py)를 쓰세요.
# 그러면 Docker 재빌드 없이 다음 Job부터 즉시 반영됩니다.
# ══════════════════════════════════════════════════════════
# ElevenLabs Korean narration at 1.25x.  The Job 123 measurement was
# 216 spoken characters in 38.6 seconds, so 340 non-space characters/minute
# keeps the generated script close to the requested final duration.
TTS_SPEED = float(os.getenv("TTS_SPEED", "1.25"))
CHARS_PER_MINUTE = int(os.getenv("CHARS_PER_MINUTE", "340"))
SCENE_DURATION_SEC = float(os.getenv("SCENE_DURATION_SEC", "5.5"))
SUBTITLE_MAX_CHARS = int(os.getenv("SUBTITLE_MAX_CHARS", "16"))
SUBTITLE_FONT_SIZE = int(os.getenv("SUBTITLE_FONT_SIZE", "76"))
SUBTITLE_THEME = os.getenv("SUBTITLE_THEME", "economy")  # economy | knowledge
IMAGE_HEADLINE_OVERLAY = os.getenv("IMAGE_HEADLINE_OVERLAY", "false").lower() in {"1", "true", "yes"}
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "gemini")   # gemini | fal | auto
# A 20-minute timeline may contain ~240 scenes.  Hybrid keeps the 2D comic
# direction for every scene while reserving Pro/2K latency for story anchors
# and verified data scenes; all-Pro is still available by explicit override.
IMAGE_QUALITY_TIER = os.getenv("IMAGE_QUALITY_TIER", "hybrid")  # flash | hybrid | pro
PRO_IMAGE_MAX_SCENES = int(os.getenv("PRO_IMAGE_MAX_SCENES", "48"))
# Batch API has a 24-hour completion SLO, so it is an economy/background mode,
# not the default path for a user waiting for a finished video.
GEMINI_PRO_BATCH_ENABLED = os.getenv("GEMINI_PRO_BATCH_ENABLED", "false").lower() in {"1", "true", "yes"}
# Batch has a separate prepaid-credit contract. Never switch an interactive
# long-form job onto it unless an operator explicitly enables it.
GEMINI_PRO_BATCH_FALLBACK_ENABLED = os.getenv("GEMINI_PRO_BATCH_FALLBACK_ENABLED", "false").lower() in {"1", "true", "yes"}
GEMINI_SERVICE_TIER = os.getenv("GEMINI_SERVICE_TIER", "standard").lower()
# Pace and retry synchronous Pro 2K requests without changing their model.
GEMINI_PRO_MAX_ATTEMPTS = int(os.getenv("GEMINI_PRO_MAX_ATTEMPTS", "5"))
GEMINI_PRO_RETRY_BASE_SECONDS = float(os.getenv("GEMINI_PRO_RETRY_BASE_SECONDS", "10"))
GEMINI_PRO_REQUEST_DELAY_SECONDS = float(os.getenv("GEMINI_PRO_REQUEST_DELAY_SECONDS", "3"))
# Bound image API fan-out so a long job is faster without turning rate limits
# into missing scenes.  These are runtime-tunable through /pipeline/config.
GEMINI_PARALLEL_ENABLED = os.getenv("GEMINI_PARALLEL_ENABLED", "true").lower() in {"1", "true", "yes"}
GEMINI_MAX_CONCURRENCY = int(os.getenv("GEMINI_MAX_CONCURRENCY", "8"))
GEMINI_RETRY_MAX = int(os.getenv("GEMINI_RETRY_MAX", "3"))
GEMINI_RPM_SOFT_CAP = int(os.getenv("GEMINI_RPM_SOFT_CAP", "60"))
GEMINI_ADAPTIVE_BACKOFF_ENABLED = os.getenv("GEMINI_ADAPTIVE_BACKOFF_ENABLED", "true").lower() in {"1", "true", "yes"}
LONGFORM_SCENE_MAX_WORKERS = int(os.getenv("LONGFORM_SCENE_MAX_WORKERS", "6"))
VISUAL_QA_ENABLED = os.getenv("VISUAL_QA_ENABLED", "true").lower() in {"1", "true", "yes"}
# Vision QA is an anchor-sample review, not a second API call for every one
# of 240 scenes. File/codec validation still covers every scene.
VISUAL_QA_MAX_SCENES = int(os.getenv("VISUAL_QA_MAX_SCENES", "24"))

ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
ELEVENLABS_STABILITY = float(os.getenv("ELEVENLABS_STABILITY", "0.62"))
ELEVENLABS_SIMILARITY_BOOST = float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.80"))
ELEVENLABS_STYLE = float(os.getenv("ELEVENLABS_STYLE", "0.05"))

BGM_VOLUME = float(os.getenv("BGM_VOLUME", "0.12"))
ZOOMPAN_SPEED = float(os.getenv("ZOOMPAN_SPEED", "0.0008"))
ZOOMPAN_MAX_ZOOM = float(os.getenv("ZOOMPAN_MAX_ZOOM", "1.06"))

INTRO_KLING_SECONDS_5MIN = int(os.getenv("INTRO_KLING_SECONDS_5MIN", "30"))
INTRO_KLING_SECONDS_10MIN = int(os.getenv("INTRO_KLING_SECONDS_10MIN", "45"))
INTRO_KLING_SECONDS_15MIN = int(os.getenv("INTRO_KLING_SECONDS_15MIN", "60"))
INTRO_KLING_SECONDS_20MIN = int(os.getenv("INTRO_KLING_SECONDS_20MIN", "60"))
INTRO_KLING_MAX_CLIPS = int(os.getenv("INTRO_KLING_MAX_CLIPS", "11"))

# Budget values are placeholders: replace them with the current AI Studio/Fal
# console rates before production.  The preflight never hard-codes a price.
IMG_COST_FLASH_1K_USD = float(os.getenv("IMG_COST_FLASH_1K_USD", "0.045"))
IMG_COST_PRO_2K_USD = float(os.getenv("IMG_COST_PRO_2K_USD", "0.134"))
KLING_COST_PER_CLIP_USD = float(os.getenv("KLING_COST_PER_CLIP_USD", "0.45"))
USD_KRW = float(os.getenv("USD_KRW", "1400"))
MAX_BUDGET_PER_VIDEO_KRW = int(os.getenv("MAX_BUDGET_PER_VIDEO_KRW", "40000"))
BUDGET_RETRY_BUFFER_PCT = float(os.getenv("BUDGET_RETRY_BUFFER_PCT", "10"))
