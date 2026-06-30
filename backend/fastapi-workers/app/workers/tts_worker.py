"""
Phase 3-3 — TTS 음성 합성 워커

핵심:
  1. 스크립트를 청크(문장 단위)로 분할
  2. 각 청크의 추정 시간 계산 (한국어 분당 300자 = 초당 5자)
  3. 전체 음성 mp3 생성 (Mock: FFmpeg 무음)
  4. 청크별 타이밍 정보를 chunks로 반환

chunks 정보는 다음 단계에서 활용됨:
  - Phase 3-4: 이미지를 어느 시점에 배치할지 결정
  - Phase 3-5: 자막 동기화
"""
import os
import re
import shutil
import logging
from pathlib import Path

from app.providers.factory import get_tts_provider

logger = logging.getLogger(__name__)

# 한국어 평균 발화 속도
KO_CHARS_PER_SECOND = 5.0
# 청크 최소 길이 (너무 짧은 청크는 합침)
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

        # 2. 전체 음성 생성 (Mock: FFmpeg 무음 mp3)
        generated = self.tts.synthesize(script, voice_id)
        # 영구 폴더로 이동
        job_dir = Path(f"/app/data/jobs/{job_id}/tts")
        job_dir.mkdir(parents=True, exist_ok=True)
        permanent_path = job_dir / "full.mp3"
        shutil.move(generated.local_path, permanent_path)

        # 3. 청크별 시간 계산
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
        logger.info(f"TTS 완료: 총 {total_duration}초, 파일={permanent_path}")

        return {
            "job_id": job_id,
            "audio_path": str(permanent_path),
            "voice_id": voice_id,
            "total_duration": total_duration,
            "chunks": chunk_info,
        }

    @staticmethod
    def _split_script(script: str) -> list[str]:
        """
        스크립트를 자연스러운 단위로 분할.
        - 문장 단위 (마침표/물음표/느낌표 기준)
        - 너무 짧으면 합침 (MIN_CHUNK_CHARS 미만)
        - 너무 길면 그대로 (이미지 1장이 길어도 OK)
        """
        # 문장 분리
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
