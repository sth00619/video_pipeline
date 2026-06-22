import os
import logging
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from app.workers.shorts_worker import ShortsWorker
from app.config import APP_MODE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Video Pipeline Workers", version="0.1.0")

# 워커 인스턴스 (싱글턴)
shorts_worker = None


def get_shorts_worker():
    global shorts_worker
    if shorts_worker is None:
        shorts_worker = ShortsWorker()
    return shorts_worker


# ============================
# Health Check
# ============================
@app.get("/health")
def health():
    return {"status": "ok", "mode": APP_MODE}


# ============================
# 쇼츠 생성 API
# ============================
class ShortsRequest(BaseModel):
    job_id: int
    shorts_count: int = 3


@app.post("/workers/shorts/upload")
async def create_shorts_from_upload(
    file: UploadFile = File(...),
    shorts_count: int = 3,
    job_id: int = 0
):
    """영상 파일 업로드 → 쇼츠 생성"""
    if not file.filename.endswith((".mp4", ".mov", ".avi", ".mkv")):
        raise HTTPException(400, "지원하지 않는 파일 형식입니다. mp4/mov/avi/mkv 만 가능합니다.")

    # 임시 파일로 저장
    tmp_input = tempfile.mktemp(suffix=os.path.splitext(file.filename)[1])
    output_dir = tempfile.mkdtemp()

    try:
        content = await file.read()
        with open(tmp_input, "wb") as f:
            f.write(content)

        logger.info(f"쇼츠 생성 시작: job_id={job_id}, count={shorts_count}")
        worker = get_shorts_worker()
        clips = worker.process(tmp_input, shorts_count=shorts_count, output_dir=output_dir)

        if not clips:
            raise HTTPException(500, "쇼츠 생성에 실패했습니다.")

        return {
            "job_id": job_id,
            "clips": [
                {
                    "index": c.index,
                    "text": c.text,
                    "start": round(c.start, 2),
                    "end": round(c.end, 2),
                    "output_path": c.output_path
                }
                for c in clips
            ]
        }
    finally:
        if os.path.exists(tmp_input):
            os.remove(tmp_input)


@app.get("/workers/shorts/download")
def download_clip(path: str):
    """생성된 쇼츠 클립 다운로드"""
    if not os.path.exists(path):
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    return FileResponse(path, media_type="video/mp4",
                        filename=os.path.basename(path))


# ============================
# 트랜스크립트 API
# ============================
@app.post("/workers/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """영상 → 단어 단위 타임스탬프 JSON"""
    from app.providers.factory import get_transcript_provider
    tmp = tempfile.mktemp(suffix=".mp4")
    try:
        content = await file.read()
        with open(tmp, "wb") as f:
            f.write(content)
        provider = get_transcript_provider()
        segments = provider.transcribe(tmp)
        return {
            "segments": [
                {"text": s.text, "start": s.start, "end": s.end, "words": s.words}
                for s in segments
            ]
        }
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
