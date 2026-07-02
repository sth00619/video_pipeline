"""
Phase 3-3 v4 — TTS 워커 (청크별 gTTS + 정확한 타임스탬프)

핵심 개선:
  1. 청크별 개별 gTTS 생성 → 각 청크 실제 음성 길이 측정
  2. 측정된 실제 길이로 타임스탬프 계산 → 자막-음성 완벽 동기화
  3. 자막 스타일: 굵은 텍스트 + 검정 박스 배경 (경제사냥꾼 스타일)
  4. 주식 수치 전처리 (%, pt, FOMC 등)

구조:
  chunk_1.mp3 (실제 3.2초) → start=0.0, duration=3.2
  chunk_2.mp3 (실제 4.1초) → start=3.2, duration=4.1
  ...
  concat → full.mp3
  타임스탬프 = 각 청크 실제 길이의 누적값
"""
import os
import re
import tempfile
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MIN_CHUNK_CHARS = 80
MAX_CHUNK_CHARS = 110


class TtsWorker:

    def synthesize(self, script: str, voice_id: str, job_id: int = 0) -> dict:
        if not script or not script.strip():
            raise ValueError("스크립트가 비어있습니다.")

        logger.info(f"TTS 생성 시작: job_id={job_id}, length={len(script)}자")

        # 1. 청크 분할
        chunks_text = self._split_script(script)
        logger.info(f"청크 분할: {len(chunks_text)}개")

        job_dir = Path(f"/app/data/jobs/{job_id}/tts")
        job_dir.mkdir(parents=True, exist_ok=True)
        chunk_dir = job_dir / "chunks"
        chunk_dir.mkdir(exist_ok=True)
        mp3_path = job_dir / "full.mp3"

        # 2. 청크별 gTTS 생성 + 실제 길이 측정
        chunk_info = []
        chunk_mp3s = []
        cursor = 0.0
        used_gtts = False

        try:
            from gtts import gTTS
            gtts_available = True
        except ImportError:
            gtts_available = False
            logger.error("gTTS 미설치")

        for i, text in enumerate(chunks_text):
            chunk_path = str(chunk_dir / f"chunk_{i:03d}.mp3")
            preprocessed = self._preprocess_for_tts(text)

            duration = None
            if gtts_available:
                try:
                    tts = gTTS(text=preprocessed, lang='ko', slow=False)
                    tts.save(chunk_path)
                    duration = self._probe_duration(chunk_path)
                    if duration and duration > 0:
                        used_gtts = True
                    else:
                        raise ValueError("duration 측정 실패")
                except Exception as e:
                    logger.warning(f"chunk_{i} gTTS 실패: {e}, 폴백 사용")
                    duration = None

            # gTTS 실패 시 글자수 기반 추정 + 무음 생성
            if duration is None:
                duration = round(len(text) / 6.2, 2)  # 실측 기반 6.2자/초
                os.system(
                    f'ffmpeg -f lavfi -i "anullsrc=r=44100:cl=stereo" '
                    f'-t {duration:.3f} -c:a libmp3lame -b:a 128k '
                    f'-y "{chunk_path}" -loglevel error'
                )

            chunk_info.append({
                "index": i + 1,
                "text": text,
                "start": round(cursor, 3),
                "duration": round(duration, 3),
            })
            chunk_mp3s.append(chunk_path)
            cursor += duration

        total_duration = round(cursor, 2)
        logger.info(f"청크 처리 완료: {len(chunk_info)}개, 총 {total_duration:.1f}초, gtts={used_gtts}")

        # 3. 청크 MP3 concat → full.mp3
        list_file = str(chunk_dir / "list.txt")
        with open(list_file, "w") as f:
            for p in chunk_mp3s:
                f.write(f"file '{p}'\n")

        ret = os.system(
            f'ffmpeg -f concat -safe 0 -i "{list_file}" '
            f'-c:a copy -y "{mp3_path}" -loglevel error'
        )

        if ret != 0 or not os.path.exists(str(mp3_path)):
            # concat 실패 시 무음으로 대체
            logger.error("concat 실패, 무음 폴백")
            os.system(
                f'ffmpeg -f lavfi -i "anullsrc=r=44100:cl=stereo" '
                f'-t {total_duration:.3f} -c:a libmp3lame -b:a 128k '
                f'-y "{mp3_path}" -loglevel error'
            )

        # 실제 full.mp3 duration 검증
        actual = self._probe_duration(str(mp3_path))
        if actual:
            logger.info(f"full.mp3 실제 길이: {actual:.1f}초 (예상: {total_duration:.1f}초)")

        logger.info(f"TTS 완료: {total_duration:.1f}초, gtts={used_gtts}, chunks={len(chunk_info)}")

        return {
            "job_id": job_id,
            "audio_path": str(mp3_path),
            "voice_id": "gtts_ko" if used_gtts else "silent",
            "total_duration": total_duration,
            "chunks": chunk_info,
            "used_gtts": used_gtts,
        }

    def _split_script(self, script: str) -> list[str]:
        sentences = re.split(r'(?<=[.!?。])\s+', script.strip())
        chunks = []
        current = ""
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if len(current) + len(sent) + 1 <= MAX_CHUNK_CHARS:
                current = (current + " " + sent).strip() if current else sent
            else:
                if current:
                    chunks.append(current)
                if len(sent) > MAX_CHUNK_CHARS:
                    sub = self._split_long(sent)
                    chunks.extend(sub[:-1])
                    current = sub[-1] if sub else ""
                else:
                    current = sent
        if current:
            chunks.append(current)
        return [c for c in chunks if c.strip()]

    def _split_long(self, sent: str) -> list[str]:
        parts = re.split(r'(?<=,)\s+|(?<=，)\s*', sent)
        result, current = [], ""
        for part in parts:
            if len(current) + len(part) <= MAX_CHUNK_CHARS:
                current = (current + " " + part).strip() if current else part
            else:
                if current:
                    result.append(current)
                current = part[:MAX_CHUNK_CHARS]
        if current:
            result.append(current)
        return result if result else [sent[:MAX_CHUNK_CHARS]]

    @staticmethod
    def _preprocess_for_tts(text: str) -> str:
        text = re.sub(r'([+-]?\d+\.?\d*)%', r'\1퍼센트', text)
        text = re.sub(r'\+(\d)', r'플러스 \1', text)
        text = re.sub(r'(?<!\d)-(\d)', r'마이너스 \1', text)
        text = re.sub(r'(\d+)pt', r'\1포인트', text)
        text = re.sub(r'(\d{1,3}),(\d{3})', r'\1\2', text)
        text = re.sub(r'\bFOMC\b', '에프오엠씨', text)
        text = re.sub(r'\bRSI\b', '알에스아이', text)
        text = re.sub(r'\bMACD\b', '맥디', text)
        text = re.sub(r'\bPER\b', '퍼', text)
        text = re.sub(r'\bPBR\b', '피비알', text)
        text = re.sub(r'\bS&P\b', '에스앤피', text)
        text = re.sub(r'\bETF\b', '이티에프', text)
        return text

    @staticmethod
    def _probe_duration(path: str) -> float | None:
        result = os.popen(
            f'ffprobe -v error -show_entries format=duration '
            f'-of default=noprint_wrappers=1:nokey=1 "{path}"'
        ).read().strip()
        try:
            return float(result)
        except ValueError:
            return None
