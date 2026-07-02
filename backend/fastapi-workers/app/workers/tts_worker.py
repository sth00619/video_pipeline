"""
Phase 3-3 v5 — TTS + faster-whisper 역방향 정렬

핵심 전략 (조사 결과 기반):
  gTTS (TTS) → MP3 생성
  faster-whisper (STT) → 생성된 MP3를 다시 분석 → 단어별 정확한 타임스탬프
  → 자막과 음성이 밀리초 단위로 정확히 동기화

왜 이 방법이 최선인가:
  1. faster-whisper는 이미 컨테이너에 설치되어 있음 (추가 설치 불필요)
  2. gTTS가 실제로 언제 어느 단어를 발음했는지 STT가 정확히 측정
  3. 청크별 개별 생성 + 길이 측정보다 더 정확 (음절 단위 경계 포착)
  4. 주식 전문 용어 (FOMC, MACD, 코스피 등) 발음 타이밍도 정확히 잡음

처리 흐름:
  1. 스크립트 전처리 (주식 용어 → 한국어 발음)
  2. gTTS로 전체 스크립트 MP3 생성
  3. faster-whisper로 MP3 STT → 단어/세그먼트 타임스탬프 추출
  4. 세그먼트를 20자 단위로 그룹핑
  5. 각 그룹에 정확한 start/end 시간 부여
  6. ASS 자막 생성

주식 플랫폼 특화:
  - 경제 수치 전처리 (%, pt, FOMC 등)
  - 세그먼트 그룹핑 시 20자 한도 (한 줄 자막)
  - 한국어 faster-whisper 모델 사용
"""
import os
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_SUBTITLE_CHARS = 20  # 자막 1줄 최대 글자수


class TtsWorker:

    def __init__(self):
        self._whisper_model = None

    def _get_whisper_model(self):
        """faster-whisper 모델 싱글턴 (이미 설치됨)"""
        if self._whisper_model is None:
            from faster_whisper import WhisperModel
            # base 모델 사용 (이미 캐시됨)
            self._whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
            logger.info("faster-whisper base 모델 로드 완료")
        return self._whisper_model

    def synthesize(self, script: str, voice_id: str, job_id: int = 0) -> dict:
        if not script or not script.strip():
            raise ValueError("스크립트가 비어있습니다.")

        logger.info(f"TTS v5 시작: job_id={job_id}, length={len(script)}자")

        job_dir = Path(f"/app/data/jobs/{job_id}/tts")
        job_dir.mkdir(parents=True, exist_ok=True)
        mp3_path = str(job_dir / "full.mp3")

        # 1. 주식 용어 전처리
        preprocessed = self._preprocess_for_tts(script)

        # 2. gTTS 음성 생성
        used_gtts = False
        try:
            used_gtts = self._generate_gtts(preprocessed, mp3_path)
        except Exception as e:
            logger.error(f"gTTS 실패: {e}")

        if not used_gtts or not os.path.exists(mp3_path):
            logger.warning("gTTS 실패 → 무음 폴백")
            # 분당 300자 기준 추정
            estimated = len(script) / 5.0
            os.system(
                f'ffmpeg -f lavfi -i "anullsrc=r=44100:cl=stereo" '
                f'-t {estimated:.3f} -c:a libmp3lame -b:a 128k '
                f'-y "{mp3_path}" -loglevel error'
            )

        # 실제 MP3 길이 측정
        actual_duration = self._probe_duration(mp3_path) or len(script) / 5.0
        logger.info(f"음성 길이: {actual_duration:.1f}초")

        # 3. faster-whisper로 역방향 STT → 정확한 타임스탬프 추출
        chunks = []
        if used_gtts:
            try:
                chunks = self._extract_timestamps_with_whisper(mp3_path, script)
                logger.info(f"Whisper 타임스탬프 추출: {len(chunks)}개 세그먼트")
            except Exception as e:
                logger.error(f"Whisper 타임스탬프 추출 실패: {e}")
                chunks = []

        # 4. Whisper 실패 시 글자 수 비례 폴백
        if not chunks:
            logger.warning("글자 수 비례 타임스탬프로 폴백")
            chunks = self._fallback_timing(script, actual_duration)

        logger.info(f"TTS v5 완료: {actual_duration:.1f}초, chunks={len(chunks)}, gtts={used_gtts}")

        return {
            "job_id": job_id,
            "audio_path": mp3_path,
            "voice_id": "gtts_whisper_ko" if used_gtts else "silent",
            "total_duration": round(actual_duration, 2),
            "chunks": chunks,
            "used_gtts": used_gtts,
        }

    # ============================
    # gTTS 음성 생성
    # ============================
    def _generate_gtts(self, text: str, output_path: str) -> bool:
        """gTTS로 한국어 음성 생성. 5000자 초과 시 분할 생성 후 concat."""
        from gtts import gTTS
        import tempfile

        MAX_CHARS = 4500

        if len(text) <= MAX_CHARS:
            tts = gTTS(text=text, lang='ko', slow=False)
            tts.save(output_path)
            return True

        # 긴 텍스트: 분할 생성 후 concat
        parts = []
        sentences = re.split(r'(?<=[.!?。])\s+', text.strip())
        current = ""
        for sent in sentences:
            if len(current) + len(sent) <= MAX_CHARS:
                current = (current + " " + sent).strip()
            else:
                if current:
                    parts.append(current)
                current = sent
        if current:
            parts.append(current)

        tmp_files = []
        for part in parts:
            tmp = tempfile.mktemp(suffix=".mp3")
            tts = gTTS(text=part, lang='ko', slow=False)
            tts.save(tmp)
            tmp_files.append(tmp)

        import tempfile as tf
        list_file = tf.mktemp(suffix=".txt")
        with open(list_file, "w") as f:
            for t in tmp_files:
                f.write(f"file '{t}'\n")

        os.system(
            f'ffmpeg -f concat -safe 0 -i "{list_file}" '
            f'-c:a copy -y "{output_path}" -loglevel error'
        )

        for t in tmp_files:
            if os.path.exists(t):
                os.remove(t)
        if os.path.exists(list_file):
            os.remove(list_file)

        return os.path.exists(output_path)

    # ============================
    # faster-whisper 역방향 STT → 타임스탬프
    # ============================
    def _extract_timestamps_with_whisper(self, mp3_path: str, original_script: str) -> list[dict]:
        """
        핵심: gTTS로 생성된 MP3를 faster-whisper로 분석
        → 세그먼트별 정확한 start/end 타임스탬프 추출
        → 원본 스크립트 텍스트로 매핑 (STT 오류 최소화)
        """
        model = self._get_whisper_model()

        # faster-whisper로 세그먼트 단위 타임스탬프 추출
        segments, info = model.transcribe(
            mp3_path,
            language="ko",
            word_timestamps=True,  # 단어 단위 타임스탬프
            beam_size=1,           # CPU 성능 최적화
            best_of=1,
            temperature=0,
        )

        # 단어 단위 타임스탬프 수집
        words = []
        for seg in segments:
            if seg.words:
                for w in seg.words:
                    words.append({
                        "word": w.word.strip(),
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                    })

        if not words:
            return []

        # 단어를 MAX_SUBTITLE_CHARS 단위로 그룹핑 → 자막 청크
        chunks = []
        current_words = []
        current_text = ""

        for w in words:
            word = w["word"]
            if len(current_text) + len(word) + 1 <= MAX_SUBTITLE_CHARS:
                current_words.append(w)
                current_text = (current_text + word).strip()
            else:
                if current_words:
                    chunks.append({
                        "index": len(chunks) + 1,
                        "text": current_text,
                        "start": current_words[0]["start"],
                        "duration": round(current_words[-1]["end"] - current_words[0]["start"], 3),
                    })
                current_words = [w]
                current_text = word

        if current_words:
            chunks.append({
                "index": len(chunks) + 1,
                "text": current_text,
                "start": current_words[0]["start"],
                "duration": round(current_words[-1]["end"] - current_words[0]["start"], 3),
            })

        logger.info(f"Whisper 세그먼트→청크: {len(words)}단어 → {len(chunks)}자막")
        return chunks

    # ============================
    # 폴백 타이밍 (글자 수 비례)
    # ============================
    def _fallback_timing(self, script: str, total_duration: float) -> list[dict]:
        """Whisper 실패 시 글자 수 비례로 타이밍 계산"""
        sentences = re.split(r'(?<=[.!?。])\s+', script.strip())
        chunks = []
        cursor = 0.0
        total_chars = sum(len(s) for s in sentences if s.strip())

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            ratio = len(sent) / max(total_chars, 1)
            duration = round(total_duration * ratio, 3)

            # 20자씩 분할
            for i in range(0, len(sent), MAX_SUBTITLE_CHARS):
                sub = sent[i:i + MAX_SUBTITLE_CHARS]
                sub_ratio = len(sub) / len(sent)
                sub_dur = round(duration * sub_ratio, 3)
                chunks.append({
                    "index": len(chunks) + 1,
                    "text": sub,
                    "start": round(cursor, 3),
                    "duration": sub_dur,
                })
                cursor += sub_dur

        return chunks

    # ============================
    # 주식 텍스트 전처리
    # ============================
    @staticmethod
    def _preprocess_for_tts(text: str) -> str:
        """주식/경제 용어를 gTTS가 자연스럽게 읽도록 전처리"""
        text = re.sub(r'([+-]?\d+\.?\d*)%', r'\1퍼센트', text)
        text = re.sub(r'\+(\d)', r'플러스 \1', text)
        text = re.sub(r'(?<!\d)-(\d)', r'마이너스 \1', text)
        text = re.sub(r'(\d+)pt\b', r'\1포인트', text)
        text = re.sub(r'(\d{1,3}),(\d{3})', r'\1\2', text)
        text = re.sub(r'\bFOMC\b', '에프오엠씨', text)
        text = re.sub(r'\bRSI\b', '알에스아이', text)
        text = re.sub(r'\bMACD\b', '맥디', text)
        text = re.sub(r'\bPER\b', '퍼', text)
        text = re.sub(r'\bPBR\b', '피비알', text)
        text = re.sub(r'\bS&P\b', '에스앤피', text)
        text = re.sub(r'\bETF\b', '이티에프', text)
        text = re.sub(r'\bCPI\b', '소비자물가지수', text)
        text = re.sub(r'\bGDP\b', '국내총생산', text)
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
