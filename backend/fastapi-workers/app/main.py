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
from app.config import APP_MODE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Video Pipeline Workers", version="0.3.0")

DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

shorts_worker = None
keyword_worker = None
script_worker = None


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


@app.get("/health")
def health():
    return {"status": "ok", "mode": APP_MODE}


# ============================
# Phase 2 — 쇼츠 (analyze + cut)
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
async def analyze_shorts(
    file: UploadFile = File(...),
    shorts_count: int = Query(default=3),
    job_id: int = Query(default=0),
):
    if not file.filename or not file.filename.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
        raise HTTPException(400, "지원하지 않는 형식. mp4/mov/avi/mkv만 가능.")

    job_dir = DATA_DIR / "jobs" / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    ext = os.path.splitext(file.filename)[1].lower() or ".mp4"
    source_path = job_dir / f"source{ext}"

    content = await file.read()
    with open(source_path, "wb") as f:
        f.write(content)
    logger.info(f"원본 영상 저장: {source_path}")

    try:
        worker = get_shorts_worker()
        analysis = worker.analyze(str(source_path), shorts_count=shorts_count)
    except Exception as e:
        logger.exception("쇼츠 분석 실패")
        raise HTTPException(500, f"분석 실패: {str(e)}")

    return {
        "job_id": job_id,
        "source_video_path": str(source_path),
        "transcript": analysis["transcript"],
        "words": analysis["words"],
        "suggested_segments": analysis["suggested_segments"],
    }


@app.post("/workers/shorts/cut")
async def cut_shorts(request: ShortsCutRequest):
    source = Path(request.source_video_path)
    if not source.exists():
        raise HTTPException(404, f"원본 영상 없음: {source}")

    job_id = request.job_id or 0
    output_dir = DATA_DIR / "jobs" / str(job_id) / "shorts"
    output_dir.mkdir(parents=True, exist_ok=True)

    segments = [s.dict() for s in request.segments]
    try:
        worker = get_shorts_worker()
        clips = worker.cut(str(source), segments, str(output_dir))
    except Exception as e:
        logger.exception("쇼츠 자르기 실패")
        raise HTTPException(500, f"자르기 실패: {str(e)}")

    return {"job_id": job_id, "clips": clips}


@app.get("/workers/shorts/download")
def download_clip(path: str):
    if not os.path.exists(path):
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    return FileResponse(path, media_type="video/mp4", filename=os.path.basename(path))


# ============================
# Phase 3-1 — 키워드 탐색
# ============================
class KeywordSearchRequest(BaseModel):
    seed: str
    limit: int = 5
    job_id: Optional[int] = 0


@app.post("/workers/keyword/search")
async def keyword_search(request: KeywordSearchRequest):
    try:
        worker = get_keyword_worker()
        return worker.search(request.seed, request.limit, request.job_id or 0)
    except Exception as e:
        logger.exception("키워드 탐색 실패")
        raise HTTPException(500, f"키워드 탐색 실패: {str(e)}")


# ============================
# Phase 3-2 — 스크립트 생성
# ============================
class ScriptGenerateRequest(BaseModel):
    keyword: str
    target_minutes: int = 20
    job_id: Optional[int] = 0


@app.post("/workers/script/generate")
async def script_generate(request: ScriptGenerateRequest):
    try:
        worker = get_script_worker()
        return worker.generate(
            request.keyword,
            target_minutes=request.target_minutes,
            job_id=request.job_id or 0,
        )
    except Exception as e:
        logger.exception("스크립트 생성 실패")
        raise HTTPException(500, f"스크립트 생성 실패: {str(e)}")


# ============================
# 디버깅용 — 트랜스크립트 단독 API
# ============================
@app.post("/workers/transcribe")
async def transcribe(file: UploadFile = File(...)):
    from app.providers.factory import get_transcript_provider
    import tempfile
    tmp = tempfile.mktemp(suffix=".mp4")
    try:
        content = await file.read()
        with open(tmp, "wb") as f:
            f.write(content)
        provider = get_transcript_provider()
        segments = provider.transcribe(tmp)
        return {"segments": [
            {"text": s.text, "start": s.start, "end": s.end, "words": s.words}
            for s in segments
        ]}
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
