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

# YouTube 공개 지표 성과등급의 기본값. runtime_config를 통해 무중단으로 조정한다.
KEYWORD_SCORE_WEIGHT_MULTIPLE = float(os.getenv("KEYWORD_SCORE_WEIGHT_MULTIPLE", "0.5"))
KEYWORD_SCORE_WEIGHT_VELOCITY = float(os.getenv("KEYWORD_SCORE_WEIGHT_VELOCITY", "0.3"))
KEYWORD_SCORE_WEIGHT_LIKE = float(os.getenv("KEYWORD_SCORE_WEIGHT_LIKE", "0.1"))
KEYWORD_SCORE_WEIGHT_COMMENT = float(os.getenv("KEYWORD_SCORE_WEIGHT_COMMENT", "0.1"))
KEYWORD_LIKE_RATE_BENCHMARK = float(os.getenv("KEYWORD_LIKE_RATE_BENCHMARK", "0.02"))
KEYWORD_COMMENT_RATE_BENCHMARK = float(os.getenv("KEYWORD_COMMENT_RATE_BENCHMARK", "0.002"))
# Small channels can produce a large view/subscriber multiple from a single
# lucky upload. They do not qualify as automatic recommendation evidence.
# 추천 근거는 "작은 채널의 우연한 한 건"을 막으면서도 일주일 안의
# 신선한 시장 이슈를 충분히 확보해야 한다. 3천/3천 + 0.25x 조합은
# 5천/5천 단일 하한보다 풀을 넓히되, 반응이 거의 없는 영상은 제외한다.
KEYWORD_MIN_SOURCE_SUBSCRIBERS = int(os.getenv("KEYWORD_MIN_SOURCE_SUBSCRIBERS", "3000"))
KEYWORD_MIN_SOURCE_VIEWS = int(os.getenv("KEYWORD_MIN_SOURCE_VIEWS", "3000"))
KEYWORD_MIN_SOURCE_VIEWER_MULTIPLE = float(os.getenv("KEYWORD_MIN_SOURCE_VIEWER_MULTIPLE", "0.25"))
KEYWORD_EXCLUDE_LIVE = os.getenv("KEYWORD_EXCLUDE_LIVE", "true").lower() in {"1", "true", "yes"}

# ══════════════════════════════════════════════════════════
# 파이프라인 동작 파라미터 초기값 (신규)
#
# 여기 값은 "컨테이너 시작 시 1회 로딩되는 기본값"입니다. 클라이언트
# 피드백에 맞춰 실시간으로 조정하려면 이 파일을 고치지 말고
# GET/POST /pipeline/config API(= app/runtime_config.py)를 쓰세요.
# 그러면 Docker 재빌드 없이 다음 Job부터 즉시 반영됩니다.
# ══════════════════════════════════════════════════════════
# Fast post-generation speed-up flattens pauses and emphasis.  Keep narration
# close to natural speed; reduce the script target accordingly to preserve the
# requested video duration instead of compressing the actor's performance.
TTS_SPEED = float(os.getenv("TTS_SPEED", "1.0"))
# Measured Korean long-form narration pace for the configured channel voice.
# This is deliberately much higher than the old generic estimate because the
# contract counts only visible Hangul characters, while finance scripts carry
# dates, prices and ticker-like terms that are expanded before synthesis.
CHARS_PER_MINUTE = int(os.getenv("CHARS_PER_MINUTE", "400"))
SCENE_DURATION_SEC = float(os.getenv("SCENE_DURATION_SEC", "5.5"))
SUBTITLE_MAX_CHARS = int(os.getenv("SUBTITLE_MAX_CHARS", "16"))
SUBTITLE_FONT_SIZE = int(os.getenv("SUBTITLE_FONT_SIZE", "76"))
SUBTITLE_THEME = os.getenv("SUBTITLE_THEME", "economy")  # economy | knowledge
IMAGE_HEADLINE_OVERLAY = os.getenv("IMAGE_HEADLINE_OVERLAY", "false").lower() in {"1", "true", "yes"}
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "gemini")   # gemini | fal | auto
# A 20-minute timeline may contain ~240 scenes.  Hybrid keeps the 2D comic
# direction for every scene while reserving Pro/2K latency for story anchors
# and verified data scenes; all-Pro is still available by explicit override.
IMAGE_QUALITY_TIER = os.getenv("IMAGE_QUALITY_TIER", "pro")  # flash | hybrid | pro
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
GEMINI_MAX_CONCURRENCY = int(os.getenv("GEMINI_MAX_CONCURRENCY", "6"))
GEMINI_RETRY_MAX = int(os.getenv("GEMINI_RETRY_MAX", "3"))
IMAGE_SAME_ERROR_BREAK_COUNT = int(os.getenv("IMAGE_SAME_ERROR_BREAK_COUNT", "5"))
GEMINI_RPM_SOFT_CAP = int(os.getenv("GEMINI_RPM_SOFT_CAP", "60"))
GEMINI_ADAPTIVE_BACKOFF_ENABLED = os.getenv("GEMINI_ADAPTIVE_BACKOFF_ENABLED", "true").lower() in {"1", "true", "yes"}
LONGFORM_SCENE_MAX_WORKERS = int(os.getenv("LONGFORM_SCENE_MAX_WORKERS", "2"))
VISUAL_QA_ENABLED = os.getenv("VISUAL_QA_ENABLED", "true").lower() in {"1", "true", "yes"}
# Vision QA is an anchor-sample review, not a second API call for every one
# of 240 scenes. File/codec validation still covers every scene.
VISUAL_QA_MAX_SCENES = int(os.getenv("VISUAL_QA_MAX_SCENES", "24"))

ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "dlKJ5VptCbYxal4doUO5")
ELEVENLABS_STABILITY = float(os.getenv("ELEVENLABS_STABILITY", "0.62"))
ELEVENLABS_SIMILARITY_BOOST = float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.80"))
ELEVENLABS_STYLE = float(os.getenv("ELEVENLABS_STYLE", "0.05"))
# V3 uses a small, controlled performance range: the intro may be natural and
# expressive, while the long-form body stays stable and repeatable.
TTS_MODEL_INTRO = os.getenv("TTS_MODEL_INTRO", "eleven_v3")
TTS_MODEL_BODY = os.getenv("TTS_MODEL_BODY", "eleven_v3")
TTS_STABILITY_INTRO = float(os.getenv("TTS_STABILITY_INTRO", "0.5"))
TTS_STABILITY_BODY = float(os.getenv("TTS_STABILITY_BODY", "0.5"))
TTS_CER_THRESHOLD = float(os.getenv("TTS_CER_THRESHOLD", "0.15"))
TTS_MAX_RETRIES = int(os.getenv("TTS_MAX_RETRIES", "3"))
TTS_POSTPROCESS_ENABLED = os.getenv("TTS_POSTPROCESS_ENABLED", "true").lower() in {"1", "true", "yes"}
# ElevenLabs already supplies natural Korean sentence breaths.  Do not splice
# extra silence at every punctuation mark; it makes narration staccato.
TTS_SENTENCE_PAUSE_MS = int(os.getenv("TTS_SENTENCE_PAUSE_MS", "350"))
TTS_PARAGRAPH_PAUSE_MS = int(os.getenv("TTS_PARAGRAPH_PAUSE_MS", "400"))
# When short factual statements are joined into a thought group, use one
# editorial beat at the group boundary instead of a stop after every sentence.
TTS_THOUGHT_GROUP_PAUSE_MS = int(os.getenv("TTS_THOUGHT_GROUP_PAUSE_MS", "1100"))

BGM_VOLUME = float(os.getenv("BGM_VOLUME", "0.12"))

# Image-to-video is deliberately limited to the contiguous opening hook.  All
# later scenes are rendered as static images: no FFmpeg zoom, pan, or transition
# effects are permitted because they can introduce visible jitter in charts,
# captions, and aligned numerical graphics.
INTRO_MOTION_SECONDS_SHORT = float(os.getenv("INTRO_MOTION_SECONDS_SHORT", "40"))
INTRO_MOTION_SECONDS_LONG = float(os.getenv("INTRO_MOTION_SECONDS_LONG", "60"))
INTRO_MOTION_SHORT_THRESHOLD = float(os.getenv("INTRO_MOTION_SHORT_THRESHOLD", "660"))
INTRO_KLING_MAX_CLIPS = int(os.getenv("INTRO_KLING_MAX_CLIPS", "12"))  # legacy API compatibility
INTRO_MOTION_CLIP_COUNT = int(os.getenv("INTRO_MOTION_CLIP_COUNT", "12"))
INTRO_MOTION_CLIP_SECONDS = int(os.getenv("INTRO_MOTION_CLIP_SECONDS", "5"))
INTRO_MOTION_ENABLED = os.getenv("INTRO_MOTION_ENABLED", "True").lower() == "true"
INTRO_MOTION_TEST_MODE = os.getenv("INTRO_MOTION_TEST_MODE", "False").lower() == "true"
MAX_IMAGE_HOLD_SECONDS = int(os.getenv("MAX_IMAGE_HOLD_SECONDS", "8"))

# Budget values are placeholders: replace them with the current AI Studio/Fal
# console rates before production.  The preflight never hard-codes a price.
IMG_COST_FLASH_1K_USD = float(os.getenv("IMG_COST_FLASH_1K_USD", "0.045"))
IMG_COST_PRO_2K_USD = float(os.getenv("IMG_COST_PRO_2K_USD", "0.134"))
KLING_COST_PER_CLIP_USD = float(os.getenv("KLING_COST_PER_CLIP_USD", "0.35"))  # 5 sec × $0.07/sec, audio off
USD_KRW = float(os.getenv("USD_KRW", "1400"))
MAX_BUDGET_PER_VIDEO_KRW = int(os.getenv("MAX_BUDGET_PER_VIDEO_KRW", "40000"))
BUDGET_RETRY_BUFFER_PCT = float(os.getenv("BUDGET_RETRY_BUFFER_PCT", "10"))
