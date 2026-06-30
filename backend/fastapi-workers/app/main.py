import os
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.workers.shorts_worker import ShortsWorker
from app.workers.keyword_worker import KeywordWorker
from app.workers.script_worker import ScriptWorker
from app.workers.tts_worker import TtsWorker
from app.workers.images_worker import ImagesWorker
from app.config import APP_MODE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Video Pipeline Workers", version="0.3.5")

DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

shorts_worker = None
keyword_worker = None
script_worker = None
tts_worker = None
images_worker = None


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


@app.get("/health")
def health():
    return {"status": "ok", "mode": APP_MODE}


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
    except Exception as e:
        raise HTTPException(500, f"분석 실패: {str(e)}")
    return {"job_id": job_id, "source_video_path": str(source_path), "transcript": analysis["transcript"], "words": analysis["words"], "suggested_segments": analysis["suggested_segments"]}

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
async def keyword_search(request: KeywordSearchRequest):
    try:
        return get_keyword_worker().search(category=request.category, seed=request.seed, limit=request.limit, outperformer_count=request.outperformer_count, job_id=request.job_id or 0)
    except Exception as e:
        raise HTTPException(500, f"키워드 탐색 실패: {str(e)}")


# ============================
# Phase 3-2 — 스크립트
# ============================
class ScriptGenerateRequest(BaseModel):
    keyword: str
    target_minutes: int = 20
    category: str = "CUSTOM"
    job_id: Optional[int] = 0

@app.post("/workers/script/generate")
async def script_generate(request: ScriptGenerateRequest):
    try:
        return get_script_worker().generate(keyword=request.keyword, target_minutes=request.target_minutes, category=request.category, job_id=request.job_id or 0)
    except Exception as e:
        raise HTTPException(500, f"스크립트 생성 실패: {str(e)}")


# ============================
# Phase 3-3 — TTS
# ============================
class TtsGenerateRequest(BaseModel):
    script: str
    voice_id: str = "default_ko"
    job_id: Optional[int] = 0

@app.post("/workers/tts/generate")
async def tts_generate(request: TtsGenerateRequest):
    try:
        return get_tts_worker().synthesize(request.script, request.voice_id, request.job_id or 0)
    except Exception as e:
        raise HTTPException(500, f"TTS 생성 실패: {str(e)}")

@app.get("/workers/tts/download")
def download_tts(path: str):
    if not os.path.exists(path): raise HTTPException(404, "파일 없음")
    return FileResponse(path, media_type="audio/mpeg", filename=os.path.basename(path))


# ============================
# Phase 3-4 — 이미지 + GIF
# ============================
class ImagesGenerateRequest(BaseModel):
    tts_meta: str      # TTS 결과 JSON 문자열
    script_meta: str   # 스크립트 결과 JSON 문자열
    job_id: Optional[int] = 0

@app.post("/workers/images/generate")
async def images_generate(request: ImagesGenerateRequest):
    try:
        return get_images_worker().generate(
            tts_meta_json=request.tts_meta,
            script_meta_json=request.script_meta,
            job_id=request.job_id or 0,
        )
    except Exception as e:
        logger.exception("이미지 생성 실패")
        raise HTTPException(500, f"이미지 생성 실패: {str(e)}")


@app.get("/workers/images/download")
def download_image(path: str):
    if not os.path.exists(path): raise HTTPException(404, "파일 없음")
    media = "image/png" if path.endswith(".png") else "image/gif"
    return FileResponse(path, media_type=media, filename=os.path.basename(path))


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
