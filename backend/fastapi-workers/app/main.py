import os
import json
import logging
import hashlib
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.workers.shorts_worker import ShortsWorker
from app.workers.keyword_worker import KeywordWorker
from app.workers.script_worker import ScriptWorker
from app.workers.tts_worker import TtsWorker
from app.workers.images_worker import ImagesWorker
from app.workers.longform_worker import LongformWorker
from app.workers.sfx_worker import SfxWorker
from app.workers.bgm_worker import BgmWorker
from app.workers.pronunciation_manager import PronunciationManager
from app.config import APP_MODE, CLAUDE_MODEL
from app import runtime_config
from app.utils.fal_billing import get_fal_credit_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Video Pipeline Workers", version="0.4.0")

DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

shorts_worker = None
keyword_worker = None
script_worker = None
tts_worker = None
images_worker = None
longform_worker = None
sfx_worker = None
bgm_worker = None


def get_shorts_worker():
    global shorts_worker
    if shorts_worker is None:
        shorts_worker = ShortsWorker()
    return shorts_worker

def get_keyword_worker():
    global keyword_worker
    if keyword_worker is None:
        keyword_worker = KeywordWorker()
    return keyword_worker

def get_script_worker():
    global script_worker
    if script_worker is None:
        script_worker = ScriptWorker()
    return script_worker

def get_tts_worker():
    global tts_worker
    if tts_worker is None:
        tts_worker = TtsWorker()
    return tts_worker

def get_images_worker():
    global images_worker
    if images_worker is None:
        images_worker = ImagesWorker()
    return images_worker

def get_longform_worker():
    global longform_worker
    if longform_worker is None:
        longform_worker = LongformWorker()
    return longform_worker

def get_sfx_worker():
    global sfx_worker
    if sfx_worker is None:
        sfx_worker = SfxWorker()
    return sfx_worker

def get_bgm_worker():
    global bgm_worker
    if bgm_worker is None:
        bgm_worker = BgmWorker()
    return bgm_worker


@app.on_event("startup")
async def startup_event():
    """서버 시작 시 발음 사전 초기화"""
    try:
        result = PronunciationManager.get_instance().initialize()
        logger.info(f"발음 사전 초기화: {result}")
    except Exception as e:
        logger.warning(f"발음 사전 초기화 실패 (TTS는 정상 작동): {e}")


@app.get("/health")
def health():
    return {"status": "ok", "mode": APP_MODE, "claude_model": CLAUDE_MODEL}


@app.get("/providers/status")
def provider_status():
    return {
        "youtube": {"configured": bool(os.environ.get("YOUTUBE_API_KEY", "").strip()), "provider": "YouTube Data API v3"},
        "anthropic": {"configured": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())},
        "elevenlabs": {"configured": bool(os.environ.get("ELEVENLABS_API_KEY", "").strip())},
        "gemini": {
            "image_model": "gemini-3-pro-image",
            "quality_tier": runtime_config.value("image_quality_tier"),
        },
        "fal": get_fal_credit_status(),
    }


# ============================
# 신규 — 파이프라인 파라미터 실시간 조정 API
#
# TTS 속도, ElevenLabs 목소리 설정, BGM 볼륨, 자막 크기, Kling 인트로
# 길이 등을 여기로 GET/POST하면 코드 수정이나 Docker 재빌드 없이
# 다음 Job부터 바로 반영됩니다.
# ============================
class PipelineConfigUpdate(BaseModel):
    tts_speed: Optional[float] = None
    chars_per_minute: Optional[int] = None
    scene_duration_sec: Optional[float] = None
    subtitle_max_chars: Optional[int] = None
    subtitle_font_size: Optional[int] = None
    subtitle_theme: Optional[str] = None
    image_headline_overlay: Optional[bool] = None
    image_provider: Optional[str] = None
    image_quality_tier: Optional[str] = None
    pro_image_max_scenes: Optional[int] = None
    gemini_pro_batch_enabled: Optional[bool] = None
    gemini_pro_batch_fallback_enabled: Optional[bool] = None
    gemini_service_tier: Optional[str] = None
    gemini_pro_max_attempts: Optional[int] = None
    gemini_pro_retry_base_seconds: Optional[float] = None
    gemini_pro_request_delay_seconds: Optional[float] = None
    gemini_parallel_enabled: Optional[bool] = None
    gemini_max_concurrency: Optional[int] = None
    gemini_retry_max: Optional[int] = None
    gemini_rpm_soft_cap: Optional[int] = None
    gemini_adaptive_backoff_enabled: Optional[bool] = None
    longform_scene_max_workers: Optional[int] = None
    visual_qa_enabled: Optional[bool] = None
    visual_qa_max_scenes: Optional[int] = None
    elevenlabs_voice_id: Optional[str] = None
    elevenlabs_stability: Optional[float] = None
    elevenlabs_similarity_boost: Optional[float] = None
    elevenlabs_style: Optional[float] = None
    bgm_volume: Optional[float] = None
    zoompan_speed: Optional[float] = None
    zoompan_max_zoom: Optional[float] = None
    intro_kling_seconds_5min: Optional[int] = None
    intro_kling_seconds_10min: Optional[int] = None
    intro_kling_seconds_15min: Optional[int] = None
    intro_kling_seconds_20min: Optional[int] = None
    intro_kling_max_clips: Optional[int] = None
    img_cost_flash_1k_usd: Optional[float] = None
    img_cost_pro_2k_usd: Optional[float] = None
    kling_cost_per_clip_usd: Optional[float] = None
    usd_krw: Optional[float] = None
    max_budget_per_video_krw: Optional[int] = None
    budget_retry_buffer_pct: Optional[float] = None


@app.get("/pipeline/config")
def get_pipeline_config():
    """현재 적용 중인 파이프라인 파라미터 전체를 반환합니다."""
    return runtime_config.get()


@app.post("/pipeline/config")
def update_pipeline_config(update: PipelineConfigUpdate):
    """전달된 파라미터만 즉시 갱신합니다. (다음 Job부터 바로 반영, 재빌드 불필요)"""
    try:
        updated = runtime_config.update(**update.dict(exclude_none=True))
        return {"status": "ok", "config": updated}
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))


@app.post("/pipeline/config/reset")
def reset_pipeline_config():
    """환경변수 기본값으로 되돌립니다."""
    return {"status": "ok", "config": runtime_config.reset_to_env_defaults()}


@app.get("/workers/quality/{job_id}")
def get_quality_report(job_id: int, stage: Optional[str] = None):
    """Return persisted deterministic quality-gate results for a job."""
    quality_dir = DATA_DIR / "jobs" / str(job_id) / "quality"
    if not quality_dir.exists():
        raise HTTPException(404, "quality report not found")
    allowed = {"tts", "images", "longform"}
    stages = [stage] if stage else sorted(allowed)
    if stage and stage not in allowed:
        raise HTTPException(400, "invalid quality report stage")
    reports = {}
    for name in stages:
        path = quality_dir / f"{name}.json"
        if path.exists():
            try:
                reports[name] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                reports[name] = {"error": "unreadable quality report"}
    if not reports:
        raise HTTPException(404, "quality report not found")
    return {"job_id": job_id, "reports": reports}


# ============================
# Phase 2 — 쇼츠
# ============================
class ShortsSegment(BaseModel):
    index: int
    text: Optional[str] = None
    start: float
    end: float
    reason: Optional[str] = None

class ShortsCutRequest(BaseModel):
    source_video_path: str
    segments: List[ShortsSegment]
    job_id: Optional[int] = 0

@app.post("/workers/shorts/analyze")
async def analyze_shorts(file: UploadFile = File(...), shorts_count: int = Query(default=3), job_id: int = Query(default=0)):
    if not file.filename or not file.filename.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
        raise HTTPException(400, "지원하지 않는 형식.")
    job_dir = DATA_DIR / "jobs" / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    ext = os.path.splitext(file.filename)[1].lower() or ".mp4"
    source_path = job_dir / f"source{ext}"
    content = await file.read()
    with open(source_path, "wb") as f: f.write(content)
    try:
        analysis = get_shorts_worker().analyze(str(source_path), shorts_count=shorts_count)
        # Whisper provides timestamps; the LLM turns each timestamped chunk
        # into a concise, readable scene script without changing its range.
        analysis["transcript_segments"] = get_shorts_worker().enhance_scene_script(
            analysis["transcript_segments"]
        )
        analysis["transcript"] = " ".join(
            scene.get("text", "") for scene in analysis["transcript_segments"]
        )
    except Exception as e:
        raise HTTPException(500, f"분석 실패: {str(e)}")
    return {
        "job_id": job_id,
        "source_video_path": str(source_path),
        "transcript": analysis["transcript"],
        "transcript_segments": analysis["transcript_segments"],
        "words": analysis["words"],
        "suggested_segments": analysis["suggested_segments"],
        "total_duration": analysis["total_duration"],
    }

class ShortsScene(BaseModel):
    index: int
    text: str
    start: float
    duration: float

class ShortsExtractScenariosRequest(BaseModel):
    job_id: int
    scenes: List[ShortsScene]

class ShortsNormalizeScenesRequest(BaseModel):
    source_video_path: str
    scenes: List[ShortsScene]

@app.post("/workers/shorts/normalize-scenes")
async def normalize_shorts_scenes(request: ShortsNormalizeScenesRequest):
    source = Path(request.source_video_path)
    if not source.exists():
        raise HTTPException(404, f"Source video not found: {source}")
    try:
        normalized = get_shorts_worker().normalize_scenes(
            [scene.dict() for scene in request.scenes], str(source)
        )
        return {"source_video_path": str(source), "scenes": normalized}
    except Exception as e:
        raise HTTPException(500, f"Scene timeline normalization failed: {str(e)}")

class ShortsCutMergeRequest(BaseModel):
    source_video_path: str
    segments: List[ShortsSegment]
    job_id: Optional[int] = 0
    output_path: str

@app.post("/workers/shorts/extract-scenarios")
async def extract_scenarios(request: ShortsExtractScenariosRequest):
    try:
        scenes_list = [s.dict() for s in request.scenes]
        analysis = get_shorts_worker().extract_scenarios(scenes_list, job_id=request.job_id)
        return analysis
    except Exception as e:
        raise HTTPException(500, f"시나리오 추출 실패: {str(e)}")

@app.post("/workers/shorts/cut-merge")
async def cut_merge_shorts(request: ShortsCutMergeRequest):
    source = Path(request.source_video_path)
    if not source.exists():
        raise HTTPException(404, f"원본 영상 없음: {source}")
    try:
        segments_list = [s.dict() for s in request.segments]
        clip = get_shorts_worker().cut_and_merge(str(source), segments_list, request.output_path)
        return {"job_id": request.job_id, "clip": clip}
    except Exception as e:
        raise HTTPException(500, f"병합 자르기 실패: {str(e)}")

@app.post("/workers/shorts/cut")
async def cut_shorts(request: ShortsCutRequest):
    source = Path(request.source_video_path)
    if not source.exists(): raise HTTPException(404, f"원본 영상 없음: {source}")
    job_id = request.job_id or 0
    output_dir = DATA_DIR / "jobs" / str(job_id) / "shorts"
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        clips = get_shorts_worker().cut(str(source), [s.dict() for s in request.segments], str(output_dir))
    except Exception as e:
        raise HTTPException(500, f"자르기 실패: {str(e)}")
    return {"job_id": job_id, "clips": clips}

@app.get("/workers/shorts/download")
def download_clip(path: str):
    if not os.path.exists(path): raise HTTPException(404, "파일 없음")
    return FileResponse(path, media_type="video/mp4", filename=os.path.basename(path))


# ============================
# Phase 3-1 — 키워드
# ============================
class KeywordSearchRequest(BaseModel):
    seed: str = ""
    limit: int = 5
    category: str = "CUSTOM"
    outperformer_count: int = 1
    job_id: Optional[int] = 0

@app.post("/workers/keyword/search")
def keyword_search(request: KeywordSearchRequest):
    try:
        return get_keyword_worker().search(category=request.category, seed=request.seed, limit=request.limit, outperformer_count=request.outperformer_count, job_id=request.job_id or 0)
    except Exception as e:
        raise HTTPException(500, f"키워드 탐색 실패: {str(e)}")


class TrendingRequest(BaseModel):
    keyword: str = ""
    limit: int = 10

@app.post("/workers/trending/youtube")
def trending_youtube(request: TrendingRequest):
    try:
        from app.providers.factory import get_trending_video_analyzer
        analyzer = get_trending_video_analyzer()
        videos = analyzer.collect(category="", seed=request.keyword, limit=request.limit)
        return {"videos": [v.__dict__ for v in videos]}
    except Exception as e:
        raise HTTPException(500, f"트렌딩 비디오 검색 실패: {str(e)}")


@app.post("/workers/overlay/preview")
async def overlay_preview(
    image: UploadFile = File(...),
    name: str = Form("코스피"),
    value: float = Form(...),
    change: float = Form(...),
    change_pct: float = Form(...),
    market: str = Form("kr"),
    placement_mode: str = Form("anchor"),
    anchor: str = Form("top_right"),
    margin: int = Form(40),
    x: int = Form(0),
    y: int = Form(0),
):
    """Render a verified data card over a supplied image for local QA."""
    from app.utils.stock_overlay import Anchor, IndexData, Market, compose_on_image, render_index_card

    raw = await image.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "image is larger than 20MB")
    preview_dir = DATA_DIR / "overlay_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha256(raw).hexdigest()[:16]
    base_path = preview_dir / f"{token}_base.png"
    card_path = preview_dir / f"{token}_card.png"
    output_path = preview_dir / f"{token}_composited.png"
    base_path.write_bytes(raw)
    try:
        data = IndexData(name=name, value=value, change=change, change_pct=change_pct, market=Market(market.lower()))
        render_index_card(data, str(card_path), scale=2)
        if placement_mode.lower() == "pixel":
            compose_on_image(str(base_path), str(card_path), str(output_path), xy=(x, y))
        else:
            compose_on_image(
                str(base_path), str(card_path), str(output_path),
                anchor=Anchor(anchor.lower()), margin=max(0, margin),
            )
        return FileResponse(str(output_path), media_type="image/png", filename="overlay_preview.png")
    except (ValueError, OSError) as exc:
        raise HTTPException(400, f"overlay preview failed: {exc}") from exc


# ============================
# Phase 3-2 — 스크립트
# ============================
class ScriptGenerateRequest(BaseModel):
    keyword: str
    target_minutes: int = 20
    category: str = "CUSTOM"
    job_id: Optional[int] = 0
    market_data: Optional[dict] = None  # KeywordWorker에서 전달된 market_snapshot

    data_visuals_enabled: bool = True
    # Uses the product's original house style.  Named-channel imitation is not
    # accepted as a profile; future approved profiles remain opt-in here.
    storytelling_profile: str = "original_finance_storyteller_v1"

@app.post("/workers/script/generate")
def script_generate(request: ScriptGenerateRequest):
    try:
        return get_script_worker().generate(
            keyword=request.keyword,
            target_minutes=request.target_minutes,
            category=request.category,
            market_data=request.market_data,
            job_id=request.job_id or 0,
            data_visuals_enabled=request.data_visuals_enabled,
            storytelling_profile=request.storytelling_profile,
        )
    except Exception as e:
        raise HTTPException(500, f"스크립트 생성 실패: {str(e)}")


# ============================
# Phase 3-3 — TTS
# ============================
class TtsGenerateRequest(BaseModel):
    script: str
    voice_id: str = "default_ko"
    job_id: Optional[int] = 0
    tts_speed: Optional[float] = None  # 생략 시 runtime_config의 현재 기본값 사용


class TtsPreviewRequest(BaseModel):
    voice_id: str
    text: str

@app.post("/workers/tts/generate")
def tts_generate(request: TtsGenerateRequest):
    try:
        return get_tts_worker().synthesize(
            request.script, request.voice_id, request.job_id or 0,
            tts_speed=request.tts_speed,
        )
    except Exception as e:
        raise HTTPException(500, f"TTS 생성 실패: {str(e)}")

@app.get("/workers/tts/download")
def download_tts(path: str):
    if not os.path.exists(path): raise HTTPException(404, "파일 없음")
    return FileResponse(path, media_type="audio/mpeg", filename=os.path.basename(path))


@app.get("/workers/tts/voices")
def get_elevenlabs_voices():
    """ElevenLabs 계정에서 사용 가능한 모든 성우 목소리 목록 조회"""
    # Keep a stable 21-voice catalog visible in the UI even before an API key is configured.
    fallback = [
        {"voice_id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel (여성 · 차분한 설명)", "category": "premade"},
        {"voice_id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi (여성 · 자신감 있는 진행)", "category": "premade"},
        {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella (여성 · 따뜻한 내레이션)", "category": "premade"},
        {"voice_id": "MF3mGyEYCl7XYWbV9V6O", "name": "Elli (여성 · 친근한 교육)", "category": "premade"},
        {"voice_id": "ThT5KcBeYPX3keUQqHPh", "name": "Dorothy (여성 · 밝은 뉴스)", "category": "premade"},
        {"voice_id": "XrExE9yKIg1WjnnlVkGX", "name": "Matilda (여성 · 안정적인 해설)", "category": "premade"},
        {"voice_id": "jBpfuIE2acCO8z3wKNLl", "name": "Gigi (여성 · 활기찬 진행)", "category": "premade"},
        {"voice_id": "jsCqWAovK2LkecY7zXl4", "name": "Freya (여성 · 부드러운 시사)", "category": "premade"},
        {"voice_id": "ErXwobaYiN019PkySvjV", "name": "Antoni (남성 · 신뢰감 있는 해설)", "category": "premade"},
        {"voice_id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh (남성 · 깊은 저음)", "category": "premade"},
        {"voice_id": "VR6AewLTigWG4xSOukaG", "name": "Arnold (남성 · 다큐멘터리)", "category": "premade"},
        {"voice_id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (남성 · 금융 뉴스)", "category": "premade"},
        {"voice_id": "yoZ06aMxZJJ28mfd3POQ", "name": "Sam (남성 · 차분한 분석)", "category": "premade"},
        {"voice_id": "flq6f7yk4E4fJM5XTYuZ", "name": "Michael (남성 · 전문 해설)", "category": "premade"},
        {"voice_id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel (남성 · 영국식 뉴스)", "category": "premade"},
        {"voice_id": "N2lVS1w4EtoT3dr4eOWO", "name": "Callum (남성 · 시사 토론)", "category": "premade"},
        {"voice_id": "IKne3meq5aSn9XLyUdCD", "name": "Charlie (남성 · 선명한 전달)", "category": "premade"},
        {"voice_id": "SAz9YHcvj6GT2YYXdXww", "name": "River (중성 · 차분한 정보)", "category": "premade"},
        {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George (남성 · 따뜻한 스토리텔러)", "category": "premade"},
        {"voice_id": "Xb7hH8MSUJpSbSDYk0k2", "name": "Alice (여성 · 몰입감 있는 교육)", "category": "premade"},
        {"voice_id": "pFZP5JQG7iQjIQuC4Bku", "name": "Liam (남성 · 또렷한 금융 해설)", "category": "premade"},
    ]
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        return fallback
    try:
        import requests
        resp = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": api_key},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            voices = data.get("voices", [])
            return [
                {
                    "voice_id": v.get("voice_id"),
                    "name": v.get("name"),
                    "category": v.get("category"),
                    "description": v.get("description") or f"{v.get('labels', {}).get('accent', '')} {v.get('labels', {}).get('gender', '')}",
                    "preview_url": v.get("preview_url")
                }
                for v in voices
            ]
        else:
            logger.warning(f"ElevenLabs Voices API 실패: {resp.status_code} {resp.text}")
            return fallback
    except Exception as e:
        logger.error(f"ElevenLabs 목소리 조회 중 오류: {e}")
        return fallback


@app.post("/workers/tts/preview")
def preview_elevenlabs_voice(request: TtsPreviewRequest):
    """Render one short audition sentence, cached by voice and exact text."""
    text = (request.text or "").strip()
    voice_id = (request.voice_id or "").strip()
    if not voice_id or voice_id in {"default_ko", "gtts_ko", "default"}:
        raise HTTPException(400, "ElevenLabs voice_id가 필요합니다")
    if not text:
        raise HTTPException(400, "미리듣기 문장을 입력하세요")
    if len(text) > 100:
        raise HTTPException(422, "미리듣기는 100자 이내만 가능합니다")

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "ELEVENLABS_API_KEY가 설정되지 않았습니다")

    digest = hashlib.sha256(f"{voice_id}\0{text}".encode("utf-8")).hexdigest()
    cache_key = f"tts:preview:v1:{digest}"
    redis_client = None
    try:
        import redis
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
        )
        cached = redis_client.get(cache_key)
        if cached:
            logger.info("TTS preview cache hit: voice_id=%s hash=%s", voice_id, digest[:12])
            return Response(content=cached, media_type="audio/mpeg", headers={"X-Preview-Cache": "HIT"})
    except Exception as exc:
        logger.warning("TTS preview Redis unavailable; rendering uncached: %s", exc)

    import requests
    from app.config import ELEVENLABS_TTS_MODEL
    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        json={
            "text": text,
            "model_id": ELEVENLABS_TTS_MODEL,
            "language_code": "ko",
            "voice_settings": {
                "stability": runtime_config.value("elevenlabs_stability"),
                "similarity_boost": runtime_config.value("elevenlabs_similarity_boost"),
                "style": 0.0,
                "use_speaker_boost": True,
            },
            "apply_text_normalization": "off",
        },
        timeout=40,
    )
    if response.status_code != 200:
        logger.warning("TTS preview failed: voice_id=%s status=%s", voice_id, response.status_code)
        raise HTTPException(response.status_code, "ElevenLabs 미리듣기 생성에 실패했습니다")
    if redis_client is not None:
        try:
            redis_client.setex(cache_key, 7 * 24 * 60 * 60, response.content)
            logger.info("TTS preview cache write: voice_id=%s hash=%s", voice_id, digest[:12])
        except Exception as exc:
            logger.warning("TTS preview cache write failed: %s", exc)
    return Response(content=response.content, media_type="audio/mpeg", headers={"X-Preview-Cache": "MISS"})


# ============================
# Phase 3-4 — 이미지 + GIF
# ============================
class ImagesGenerateRequest(BaseModel):
    tts_meta: str      # TTS 결과 JSON 문자열
    script_meta: str   # 스크립트 결과 JSON 문자열
    job_id: Optional[int] = 0
    character_image_path: Optional[str] = None
    character_style_prompt: Optional[str] = None
    character_poses_dir: Optional[str] = None  # [S2-4] 이중 레이어 합성용 포즈 디렉토리
    # [Sprint 3] LoRA 캐릭터 파인튜닝 파라미터
    lora_model_id: Optional[str] = None        # safetensors CDN URL (Fal.ai flux-lora)
    lora_trigger_word: Optional[str] = None    # LoRA 활성화 트리거 단어
    lora_scale: Optional[float] = 1.0          # LoRA 적용 강도 (0.8~1.2)


@app.post("/workers/images/generate")
def images_generate(request: ImagesGenerateRequest):
    try:
        return get_images_worker().generate(
            tts_meta_json=request.tts_meta,
            script_meta_json=request.script_meta,
            job_id=request.job_id or 0,
            character_image_path=request.character_image_path,
            character_style_prompt=request.character_style_prompt,
            character_poses_dir=request.character_poses_dir,
            # [Sprint 3] LoRA 파라미터 전달
            lora_model_id=request.lora_model_id,
            lora_trigger_word=request.lora_trigger_word,
            lora_scale=request.lora_scale,
        )
    except Exception as e:
        logger.exception("이미지 생성 실패")
        raise HTTPException(500, f"이미지 생성 실패: {str(e)}")
class ImagesBatchStatusRequest(BaseModel):
    job_id: int


@app.post("/workers/images/batch-status")
def images_batch_status(request: ImagesBatchStatusRequest):
    try:
        from app.utils.gemini_batch import poll
        return poll(request.job_id)
    except Exception as e:
        logger.exception("Gemini Pro Batch status failed")
        raise HTTPException(500, f"Gemini Pro Batch status failed: {str(e)}")


@app.get("/workers/images/download")
def download_image(path: str):
    if not os.path.exists(path): raise HTTPException(404, "파일 없음")
    media = "image/png" if path.endswith(".png") else "image/gif"
    return FileResponse(path, media_type=media, filename=os.path.basename(path))




# ============================
# Phase 3-5A — 롱폼 조립
# ============================
class LongformGenerateRequest(BaseModel):
    tts_meta: str
    scenes_meta: str
    gifs_meta: str
    job_id: Optional[int] = 0

@app.post("/workers/longform/generate")
def longform_generate(request: LongformGenerateRequest):
    try:
        # A new generate/rebuild request is an explicit retry, so clear a prior
        # user/error stop marker before starting fresh worker processes.
        from app.utils.process_manager import clear_job_stop
        clear_job_stop(request.job_id or 0)
        return get_longform_worker().assemble(
            tts_meta_json=request.tts_meta,
            scenes_meta_json=request.scenes_meta,
            gifs_meta_json=request.gifs_meta,
            job_id=request.job_id or 0,
        )
    except Exception as e:
        logger.exception("롱폼 조립 실패")
        raise HTTPException(500, f"롱폼 조립 실패: {str(e)}")

@app.get("/workers/longform/download")
def download_longform(path: str):
    if not os.path.exists(path): raise HTTPException(404, "파일 없음")
    return FileResponse(path, media_type="video/mp4", filename=os.path.basename(path))

class SingleImageGenerateRequest(BaseModel):
    index: int
    text: str
    section: str
    job_id: int
    character_image_path: Optional[str] = None
    character_style_prompt: Optional[str] = None
    character_poses_dir: Optional[str] = None  # [S2-4]

@app.post("/workers/images/generate-single")
async def generate_single_image(request: SingleImageGenerateRequest):
    try:
        job_dir = DATA_DIR / "jobs" / str(request.job_id) / "images"
        job_dir.mkdir(parents=True, exist_ok=True)
        img_path = str(job_dir / f"scene_{request.index:03d}.png")

        images_worker = get_images_worker()

        # [S2-3] 이중 레이어 합성 모드 (poses_dir 제공 시)
        if request.character_poses_dir and Path(request.character_poses_dir).exists():
            ai_provider = None
            try:
                from app.providers.factory import get_image_provider
                ai_provider = get_image_provider()
            except Exception:
                pass
            if ai_provider:
                bg_path = str(job_dir / f"scene_{request.index:03d}_bg.png")
                images_worker._generate_background_layer(
                    ai_provider, request.text, bg_path, request.section, "neutral"
                )
                images_worker._composite_character(
                    bg_path, request.character_poses_dir, "neutral", img_path, request.job_id
                )
                return {"status": "ok", "image_path": img_path}

        # AI 이미지 생성 시도 (일러스트 모드)
        ai_provider = None
        try:
            from app.providers.factory import get_image_provider
            ai_provider = get_image_provider()
        except Exception:
            pass

        if ai_provider:
            try:
                ai_provider.generate_image(
                    prompt=request.text,
                    output_path=img_path,
                    section=request.section,
                    keyword=request.text[:30],
                    character_image_path=request.character_image_path,
                    character_style_prompt=request.character_style_prompt,
                    image_provider=runtime_config.value("image_provider"),
                    gemini_model="gemini-3-pro-image",
                    gemini_image_size="2K",
                    gemini_service_tier=runtime_config.value("gemini_service_tier"),
                    gemini_max_attempts=runtime_config.value("gemini_pro_max_attempts"),
                    gemini_retry_base_seconds=runtime_config.value("gemini_pro_retry_base_seconds"),
                    style_locked=False,
                )
                return {"status": "ok", "image_path": img_path}
            except Exception as e:
                logger.warning(f"단일 AI 이미지 생성 실패, Matplotlib 폴백: {e}")

        # Matplotlib 차트 폴백
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        images_worker._render_section(request.section, request.text, img_path, plt)
        return {"status": "ok", "image_path": img_path}
    except Exception as e:
        logger.exception("단일 이미지 생성 실패")
        raise HTTPException(500, f"단일 이미지 생성 실패: {str(e)}")

# ============================
# [S2-2] 캐릭터 포즈 라이브러리 생성
# ============================
class CharacterLibraryRequest(BaseModel):
    channel_id: str
    character_description: str
    regenerate: bool = False

@app.post("/workers/character-library/generate")
async def generate_character_library(request: CharacterLibraryRequest):
    """
    [S2-2] 주어진 캐릭터 설명으로 7개 포즈(neutral/happy/surprised/worried/thinking/explaining/pointing)를
    배치 생성하고 배경 제거 후 /app/data/characters/<channel_id>/poses/ 에 저장합니다.
    """
    try:
        from app.workers.character_library_worker import CharacterLibraryWorker
        worker = CharacterLibraryWorker()
        result = worker.generate_library(
            channel_id=request.channel_id,
            character_description=request.character_description,
            regenerate=request.regenerate
        )
        return result
    except Exception as e:
        logger.exception("캐릭터 라이브러리 생성 실패")
        raise HTTPException(500, f"생성 실패: {str(e)}")

@app.get("/workers/character-library/list")
async def list_character_libraries():
    """[S2-2] 구성된 모든 칔널 라이브러리 목록 조회"""
    try:
        from app.workers.character_library_worker import CharacterLibraryWorker
        return {"channels": CharacterLibraryWorker().list_channels()}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/workers/character-library/{channel_id}")
async def get_character_library_status(channel_id: str):
    """Return the usable pose names and metadata for one channel library."""
    try:
        from app.workers.character_library_worker import CharacterLibraryWorker
        return CharacterLibraryWorker().get_library_status(channel_id)
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/workers/character-library/{channel_id}/pose/{pose}")
async def get_pose_image(channel_id: str, pose: str):
    """[S2-2] 특정 칔널의 포즈 이미지 다운로드"""
    try:
        from app.workers.character_library_worker import CharacterLibraryWorker
        path = CharacterLibraryWorker().get_pose_path(channel_id, pose)
        if not path:
            raise HTTPException(404, f"포즈 이미지 없음: channel={channel_id}, pose={pose}")
        return FileResponse(path, media_type="image/png", filename=f"{channel_id}_{pose}.png")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ============================
# [Sprint 3] LoRA 캐릭터 파인튜닝
# ============================

@app.post("/workers/lora/train")
async def lora_train(
    channel_id: str = Query(..., description="채널 고유 ID"),
    trigger_word: str = Query(default="mycoin", description="LoRA 활성화 트리거 단어 (영문+숫자만)"),
    steps: int = Query(default=1000, description="학습 스텝 수 (권장: 1000~2000)"),
    is_style: bool = Query(default=False, description="스타일 LoRA 여부 (False=캐릭터/주제 LoRA)"),
    zip_file: UploadFile = File(..., description="캐릭터 레퍼런스 이미지 ZIP 파일"),
):
    """
    [Sprint 3] 채널 마스코트 캐릭터 LoRA 파인튜닝 학습 시작.

    캐릭터 이미지(최소 10~20장)를 ZIP으로 묶어 업로드하면
    Fal.ai flux-lora-fast-training 으로 개인화 LoRA 모델을 학습합니다.

    - 학습 비용: ~$3~5 / 1회
    - 소요 시간: 약 5~15분
    - 완료 후 GET /workers/lora/status/{request_id} 로 상태 조회
    - COMPLETED 시 반환된 lora_model_url 을 채널 프로필 loraModelId에 저장
    """
    try:
        from app.workers.lora_trainer_worker import LoraTrainerWorker

        # ZIP 파일 임시 저장
        zip_data = await zip_file.read()
        lora_dir = DATA_DIR / "lora" / channel_id
        lora_dir.mkdir(parents=True, exist_ok=True)
        zip_path = str(lora_dir / "reference_images.zip")
        with open(zip_path, "wb") as f:
            f.write(zip_data)
        logger.info(f"LoRA 학습 ZIP 저장: {zip_path} ({len(zip_data)//1024}KB)")

        worker = LoraTrainerWorker()
        result = worker.train(
            channel_id=channel_id,
            zip_path=zip_path,
            trigger_word=trigger_word,
            steps=steps,
            is_style=is_style,
        )
        return result
    except Exception as e:
        logger.exception("LoRA 학습 시작 실패")
        raise HTTPException(500, f"LoRA 학습 시작 실패: {str(e)}")


@app.get("/workers/lora/status/{request_id}")
async def lora_status(request_id: str):
    """
    [Sprint 3] LoRA 학습 진행 상태 조회.

    응답 status:
      - IN_QUEUE: 큐 대기 중
      - IN_PROGRESS: 학습 진행 중
      - COMPLETED: 완료 (lora_model_url 포함)
      - FAILED / ERROR: 실패
    """
    try:
        from app.workers.lora_trainer_worker import LoraTrainerWorker
        worker = LoraTrainerWorker()
        return worker.get_status(request_id)
    except Exception as e:
        logger.exception("LoRA 상태 조회 실패")
        raise HTTPException(500, f"LoRA 상태 조회 실패: {str(e)}")


@app.get("/workers/lora/channel/{channel_id}")
async def lora_channel_meta(channel_id: str):
    """[Sprint 3] 채널의 LoRA 학습 메타데이터 조회"""
    try:
        from app.workers.lora_trainer_worker import LoraTrainerWorker
        meta = LoraTrainerWorker().get_channel_training_meta(channel_id)
        if not meta:
            raise HTTPException(404, f"채널 '{channel_id}'의 LoRA 학습 이력 없음")
        return meta
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

# ============================
# 디버깅
# ============================
@app.post("/workers/transcribe")
async def transcribe(file: UploadFile = File(...)):
    from app.providers.factory import get_transcript_provider
    import tempfile
    tmp = tempfile.mktemp(suffix=".mp4")
    try:
        content = await file.read()
        with open(tmp, "wb") as f: f.write(content)
        segments = get_transcript_provider().transcribe(tmp)
        return {"segments": [{"text": s.text, "start": s.start, "end": s.end, "words": s.words} for s in segments]}
    finally:
        if os.path.exists(tmp): os.remove(tmp)


# ============================
# Phase 2+ — 효과음 / BGM / 발음 사전
# ============================
class SfxRequest(BaseModel):
    job_id: int
    sections: list = []

class BgmRequest(BaseModel):
    job_id: int
    category: str = "CUSTOM"
    duration_seconds: int = 60


@app.post("/workers/sfx/generate")
def sfx_generate(req: SfxRequest):
    """효과음 자동 생성 (ElevenLabs Sound Effects API)"""
    try:
        worker = get_sfx_worker()
        result = worker.generate(job_id=req.job_id, sections=req.sections)
        return result
    except Exception as e:
        logger.error(f"SFX 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"효과음 생성 실패: {e}")


@app.post("/workers/bgm/generate")
def bgm_generate(req: BgmRequest):
    """BGM 자동 생성 (ElevenLabs Music Generation API)"""
    try:
        worker = get_bgm_worker()
        result = worker.generate(
            job_id=req.job_id,
            category=req.category,
            duration_seconds=req.duration_seconds
        )
        return result
    except Exception as e:
        logger.error(f"BGM 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"BGM 생성 실패: {e}")


class YoutubeMetadataRequest(BaseModel):
    script_text: str
    is_shorts: bool = False


@app.post("/workers/youtube/metadata")
async def generate_youtube_metadata(request: YoutubeMetadataRequest):
    """유튜브 업로드용 메타데이터(제목 3안, 설명글, 태그) 자동 생성"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY 미설정 — Mock 유튜브 메타데이터 폴백")
        return {
            "titles": [
                f"[Mock] {'쇼츠 - ' if request.is_shorts else ''}주식 트렌드 긴급 분석",
                f"[Mock] {'쇼츠 - ' if request.is_shorts else ''}시장 변동성과 향후 전망",
                f"[Mock] {'쇼츠 - ' if request.is_shorts else ''}반도체 및 주요 테마 요약"
            ],
            "description": f"[Mock 설명글]\n오늘의 주요 시장 이슈 브리핑입니다.\n\n#주식 #재테크 #금융 {'#Shorts' if request.is_shorts else ''}",
            "tags": ["주식", "투자", "경제", "재테크", "뉴스"]
        }

    try:
        from anthropic import Anthropic
        from app.utils.anthropic_cache import cached_system, log_cache_usage
        client = Anthropic(api_key=api_key)

        system_prompt = """You are a YouTube SEO and financial content editor.
Create accurate Korean metadata from the supplied script only. Do not invent
market facts, prices, percentages, dates, companies, or guarantees. Produce
three distinct but faithful title candidates, one useful description with a
brief summary and hashtags, and 5-8 search tags. Avoid misleading investment
advice, guaranteed returns, or claims not present in the script. Return only
valid JSON with exactly these keys: titles (array of 3 strings), description
(string), tags (array of strings)."""
        prompt = f"<script>\n{request.script_text}\n</script>"

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1000,
            system=cached_system(system_prompt),
            messages=[{"role": "user", "content": prompt}]
        )
        log_cache_usage(response, "youtube_metadata")
        content_text = response.content[0].text.strip()
        
        # Clean potential markdown wrapping
        if content_text.startswith("```json"):
            content_text = content_text[7:]
        if content_text.endswith("```"):
            content_text = content_text[:-3]
        content_text = content_text.strip()
        
        import json
        metadata = json.loads(content_text)
        return metadata
    except Exception as e:
        logger.error(f"유튜브 메타데이터 생성 오류: {e}")
        raise HTTPException(status_code=500, detail=f"유튜브 메타데이터 생성 오류: {e}")


class ThumbnailRequest(BaseModel):
    job_id: int
    title: str
    format: str # "longform" | "shorts"
    output_path: str
    character_image_path: Optional[str] = None
    character_style_prompt: Optional[str] = None
    lora_model_id: Optional[str] = None
    lora_trigger_word: Optional[str] = None
    lora_scale: Optional[float] = 1.0


@app.post("/workers/youtube/thumbnail")
def generate_thumbnail(req: ThumbnailRequest):
    """유튜브 업로드용 AI 썸네일 생성"""
    try:
        from app.providers.factory import get_image_provider
        provider = get_image_provider()
        
        theme_style = (
            "bold finance poster style, vibrant stock market charts, "
            "neon blue and gold accents, high contrast, professional digital art, 8k, cinematic lighting"
        )
        prompt = f"YouTube Video Thumbnail: {req.title}. {theme_style}"
        
        width = 1920 if req.format == "longform" else 1080
        height = 1080 if req.format == "shorts" else 1920
        
        provider.width = width
        provider.height = height
        provider.generate_image(
            prompt=prompt,
            output_path=req.output_path,
            section="intro",
            keyword=req.title[:30],
            character_image_path=req.character_image_path,
            character_style_prompt=req.character_style_prompt,
            lora_model_id=req.lora_model_id,
            lora_trigger_word=req.lora_trigger_word,
            lora_scale=req.lora_scale,
        )
        return {"status": "ok", "output_path": req.output_path}
    except Exception as e:
        logger.error(f"썸네일 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"썸네일 생성 실패: {e}")


@app.post("/workers/pronunciation/init")
def pronunciation_init():
    """발음 사전 초기화/확인"""
    try:
        result = PronunciationManager.get_instance().initialize()
        return result
    except Exception as e:
        logger.error(f"발음 사전 초기화 실패: {e}")
        raise HTTPException(status_code=500, detail=f"발음 사전 초기화 실패: {e}")


# ============================
# 작업 제어 및 연쇄 삭제 기능
# ============================
import shutil

class StopJobRequest(BaseModel):
    job_id: int

@app.post("/workers/jobs/{job_id}/stop")
def stop_worker_job(job_id: int):
    """작업의 모든 백그라운드 연산을 즉시 중단"""
    try:
        from app.utils.process_manager import stop_job_processes
        stop_job_processes(job_id)
        return {"status": "ok", "message": f"Job {job_id} stopped"}
    except Exception as e:
        logger.error(f"Job {job_id} 중지 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/workers/jobs/{job_id}")
def delete_worker_job(job_id: int):
    """작업 미디어 데이터 디렉토리를 물리적으로 삭제"""
    try:
        job_dir = DATA_DIR / f"jobs/{job_id}"
        if job_dir.exists() and job_dir.is_dir():
            shutil.rmtree(job_dir)
            logger.info(f"Job {job_id} 미디어 디렉토리 삭제 완료: {job_dir}")
            return {"status": "ok", "message": f"Job {job_id} directory deleted"}
        else:
            logger.info(f"Job {job_id} 미디어 디렉토리가 존재하지 않음: {job_dir}")
            return {"status": "ok", "message": f"Job {job_id} directory not found"}
    except Exception as e:
        logger.error(f"Job {job_id} 디렉토리 삭제 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))
