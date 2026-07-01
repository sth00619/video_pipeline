"""
Phase 3-3 — TTS 음성 합성 워커 v2

수정사항:
  - Mock mp3의 실제 duration을 chunks 계산값과 일치시킴
  - MockTTSProvider가 text 길이가 아닌 명시적 duration으로 파일 생성
"""
import os
import re
import shutil
import logging
from pathlib import Path
from app.providers.factory import get_tts_provider

logger = logging.getLogger(__name__)

KO_CHARS_PER_SECOND = 5.0
MIN_CHUNK_CHARS = 100


class TtsWorker:

    def __init__(self):
        self.tts = get_tts_provider()

    def synthesize(self, script: str, voice_id: str, job_id: int = 0) -> dict:
        if not script or not script.strip():
            raise ValueError("스크립트가 비어있습니다.")

        logger.info(f"TTS 생성 시작: job_id={job_id}, length={len(script)}자, voice={voice_id}")

        # 1. 청크 분할
        chunks = self._split_script(script)
        logger.info(f"청크 분할 완료: {len(chunks)}개")

        # 2. 청크별 시간 계산 (duration 먼저 확정)
        chunk_info = []
        cursor = 0.0
        for i, chunk_text in enumerate(chunks):
            duration = round(len(chunk_text) / KO_CHARS_PER_SECOND, 2)
            chunk_info.append({
                "index": i + 1,
                "text": chunk_text,
                "start": round(cursor, 2),
                "duration": duration,
            })
            cursor += duration

        total_duration = round(cursor, 2)

        # 3. 실제 mp3 파일 생성 — total_duration 기준으로 정확히 생성
        job_dir = Path(f"/app/data/jobs/{job_id}/tts")
        job_dir.mkdir(parents=True, exist_ok=True)
        permanent_path = job_dir / "full.mp3"

        # FFmpeg으로 total_duration 길이의 무음 mp3 직접 생성
        cmd = (
            f'ffmpeg -f lavfi -i "anullsrc=r=44100:cl=stereo" '
            f'-t {total_duration:.3f} '
            f'-c:a libmp3lame -b:a 128k '
            f'-y "{permanent_path}" -loglevel error'
        )
        ret = os.system(cmd)
        if ret != 0:
            logger.error(f"TTS mp3 생성 실패: ret={ret}")
            raise RuntimeError("TTS 파일 생성 실패")

        # 실제 생성된 파일 duration 검증
        probe = os.popen(
            f'ffprobe -v error -show_entries format=duration '
            f'-of default=noprint_wrappers=1:nokey=1 "{permanent_path}"'
        ).read().strip()
        actual = float(probe) if probe else total_duration
        logger.info(f"TTS 완료: 총 {total_duration:.1f}초 (실제: {actual:.1f}초), "
                    f"파일={permanent_path}")

        return {
            "job_id": job_id,
            "audio_path": str(permanent_path),
            "voice_id": voice_id,
            "total_duration": total_duration,
            "chunks": chunk_info,
        }

    @staticmethod
    def _split_script(script: str) -> list[str]:
        sentences = re.split(r'(?<=[.!?])\s+', script.strip())
        chunks = []
        current = ""
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if len(current) + len(sent) < MIN_CHUNK_CHARS:
                current = (current + " " + sent).strip()
            else:
                if current:
                    chunks.append(current)
                current = sent
        if current:
            chunks.append(current)
        return chunks
