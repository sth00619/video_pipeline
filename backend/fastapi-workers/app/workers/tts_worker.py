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

        logger.info(f"TTS v6 시작: job_id={job_id}, length={len(script)}자")

        job_dir = Path(f"/app/data/jobs/{job_id}/tts")
        job_dir.mkdir(parents=True, exist_ok=True)
        mp3_path = str(job_dir / "full.mp3")

        # 1. 마크다운 헤더, [대사]/[비주얼] 태그 및 영어 비주얼 설명 제거하여 깨끗한 낭독용 스크립트 추출
        clean_script = ""
        if "##" in script or "[대사]" in script:
            parts = re.split(r'(?m)^##\s*', script)
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                # [대사]와 [비주얼] 사이의 텍스트만 추출
                daesa_match = re.search(r'\[대사\]\s*(.*?)\s*(?:\[비주얼\]|$)', part, re.DOTALL)
                if daesa_match:
                    clean_script += daesa_match.group(1).strip() + " "
                else:
                    # [대사] 태그가 없으면 [비주얼] 태그 이전의 텍스트 추출
                    no_visual = re.sub(r'\[비주얼\].*$', '', part, flags=re.DOTALL).strip()
                    # 첫 줄(씬 제목) 제거
                    lines = no_visual.split('\n')
                    if len(lines) > 1:
                        clean_script += " ".join(lines[1:]).strip() + " "
                    else:
                        clean_script += no_visual + " "
            clean_script = clean_script.strip()
        else:
            clean_script = script.strip()

        preprocessed = self._preprocess_for_tts(clean_script)

        # 2. 음성 생성 (ElevenLabs v3 → gTTS → 무음 폴백)
        used_tts = False
        tts_engine = "silent"
        try:
            if os.getenv("ELEVENLABS_API_KEY"):
                logger.info("ELEVENLABS_API_KEY 감지 → ElevenLabs v3 AI 성우 + 발음 사전 적용")
                used_tts = self._generate_elevenlabs(preprocessed, mp3_path, voice_id)
                if used_tts:
                    tts_engine = "elevenlabs"
            
            if not used_tts:
                # gTTS 폴백 시에는 clean_script 전처리 적용 (발음 사전 미지원)
                used_tts = self._generate_gtts(preprocessed, mp3_path)
                if used_tts:
                    tts_engine = "gtts"
        except Exception as e:
            logger.error(f"TTS 생성 실패: {e}")

        if not used_tts or not os.path.exists(mp3_path):
            logger.warning("TTS 실패 → 무음 폴백")
            estimated = len(clean_script) / 5.0
            os.system(
                f'ffmpeg -f lavfi -i "anullsrc=r=44100:cl=stereo" '
                f'-t {estimated:.3f} -c:a libmp3lame -b:a 128k '
                f'-y "{mp3_path}" -loglevel error'
            )
        # 1.35x 오디오 가속 적용 (atempo 필터)
        if os.path.exists(mp3_path):
            logger.info("음성 배속(1.35x) 적용 시작...")
            temp_mp3 = mp3_path + ".speedup.mp3"
            # atempo=1.35 필터로 오디오 속도 높임
            ret = os.system(f'ffmpeg -i "{mp3_path}" -filter:a "atempo=1.35" -c:a libmp3lame -b:a 128k -y "{temp_mp3}" -loglevel error')
            if ret == 0 and os.path.exists(temp_mp3):
                os.replace(temp_mp3, mp3_path)
                logger.info("음성 배속(1.35x) 적용 성공")
            else:
                logger.error(f"음성 배속 적용 실패 (exit code: {ret})")

        # 실제 MP3 길이 측정
        actual_duration = self._probe_duration(mp3_path) or len(clean_script) / 5.0
        logger.info(f"음성 길이 (1.35x 배속 후): {actual_duration:.1f}초")

        # 3. 자막 타임스탬프 추출 (Forced Alignment → Whisper → 글자수 비례)
        chunks = []
        if used_tts:
            # 3a. ElevenLabs Forced Alignment 시도 (가장 정확)
            if tts_engine == "elevenlabs":
                try:
                    chunks = self._extract_timestamps_with_forced_alignment(mp3_path, clean_script)
                    logger.info(f"Forced Alignment 타임스탬프 추출: {len(chunks)}개 세그먼트")
                except Exception as e:
                    logger.warning(f"Forced Alignment 실패, Whisper 폴백: {e}")
                    chunks = []

            # 3b. Whisper 폴백 (Forced Alignment 실패 또는 gTTS 엔진일 때)
            if not chunks:
                try:
                    chunks = self._extract_timestamps_with_whisper(mp3_path, clean_script)
                    logger.info(f"Whisper 타임스탬프 추출: {len(chunks)}개 세그먼트")
                except Exception as e:
                    logger.error(f"Whisper 타임스탬프 추출 실패: {e}")
                    chunks = []

        # 4. 모든 타임스탬프 추출 실패 시 글자 수 비례 폴백
        if not chunks:
            logger.warning("글자 수 비례 타임스탬프로 폴백")
            chunks = self._fallback_timing(clean_script, actual_duration)

        logger.info(f"TTS v6 완료: {actual_duration:.1f}초, chunks={len(chunks)}, engine={tts_engine}")

        return {
            "job_id": job_id,
            "audio_path": mp3_path,
            "voice_id": tts_engine if used_tts else "silent",
            "total_duration": round(actual_duration, 2),
            "chunks": chunks,
            "used_gtts": used_tts and (tts_engine == "gtts"),
            "used_elevenlabs": (tts_engine == "elevenlabs"),
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

    def _generate_elevenlabs(self, text: str, output_path: str, voice_id: str) -> bool:
        """
        ElevenLabs v3 + 발음 사전 기반 한국어 AI 성우 음성 생성.
        원본 스크립트 텍스트를 그대로 전달하고, 발음 사전이 금융 용어 발음을 교정합니다.
        """
        import requests
        import tempfile as tf
        from app.workers.pronunciation_manager import PronunciationManager

        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            return False
        
        # voice_id가 없거나 기본값이면 한국어 발음이 자연스러운 기본 voice_id 사용
        if not voice_id or voice_id in ["gtts_ko", "default", "silent", "gtts_whisper_ko"]:
            voice_id = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
            
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }

        # 발음 사전 로케이터 (금융 용어 발음 교정)
        pron_mgr = PronunciationManager.get_instance()
        pron_locators = pron_mgr.get_locators()
        
        def _build_payload(chunk_text: str) -> dict:
            payload = {
                "text": chunk_text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.0,
                    "use_speaker_boost": True
                }
            }
            if pron_locators:
                payload["pronunciation_dictionary_locators"] = pron_locators
            return payload
        
        MAX_CHARS = 2000
        if len(text) <= MAX_CHARS:
            payload = _build_payload(text)
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                logger.info("ElevenLabs v3 + 발음 사전 음성 생성 성공 (단일 요청)")
                return True
            else:
                logger.warning(f"ElevenLabs API 실패: {resp.status_code} {resp.text}")
                return False
        else:
            # 2000자 단위 분할 (문장 경계 기준)
            parts = []
            current = ""
            for sent in re.split(r'(?<=[.!?])\s+', text):
                if len(current) + len(sent) <= MAX_CHARS:
                    current = (current + " " + sent).strip()
                else:
                    if current:
                        parts.append(current)
                    current = sent
            if current:
                parts.append(current)
                
            tmp_files = []
            for idx, part in enumerate(parts):
                tmp = tf.mktemp(suffix=f"_el_{idx}.mp3")
                payload = _build_payload(part)
                resp = requests.post(url, json=payload, headers=headers, timeout=90)
                if resp.status_code == 200:
                    with open(tmp, "wb") as f:
                        f.write(resp.content)
                    tmp_files.append(tmp)
                    logger.info(f"ElevenLabs 분할 {idx+1}/{len(parts)} 성공")
                else:
                    logger.warning(f"ElevenLabs 부분 생성 실패: {resp.status_code}")
                    for t in tmp_files:
                        if os.path.exists(t): os.remove(t)
                    return False
                    
            list_file = tf.mktemp(suffix=".txt")
            with open(list_file, "w", encoding="utf-8") as f:
                for t in tmp_files:
                    f.write(f"file '{t}'\n")
            
            os.system(
                f'ffmpeg -f concat -safe 0 -i "{list_file}" '
                f'-c:a copy -y "{output_path}" -loglevel error'
            )
            for t in tmp_files:
                if os.path.exists(t): os.remove(t)
            if os.path.exists(list_file): os.remove(list_file)
            
            logger.info(f"ElevenLabs v3 분할 음성 생성 및 병합 성공 ({len(parts)}개 조각)")
            return os.path.exists(output_path)

    # ============================
    # ElevenLabs Forced Alignment → 정밀 자막 타이밍
    # ============================
    def _extract_timestamps_with_forced_alignment(self, mp3_path: str, original_script: str) -> list[dict]:
        """
        ElevenLabs Forced Alignment API를 사용하여 단어 단위 정밀 타임스탬프를 추출합니다.
        Whisper 역방향 STT보다 훨씬 정확하며, 원본 텍스트를 그대로 정렬합니다.
        """
        import requests

        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            return []

        # 원본 스크립트에서 자막 청크 분할
        text_chunks = self._split_script_into_chunks(original_script, max_chars=22)
        if not text_chunks:
            return []

        # Forced Alignment API 호출 (음성 발음에 맞추어 전처리된 텍스트로 정합)
        clean_text = re.sub(r'^##\s*.+$', '', original_script, flags=re.MULTILINE).strip()
        preprocessed_alignment_text = self._preprocess_for_tts(clean_text)
        
        with open(mp3_path, "rb") as audio_file:
            resp = requests.post(
                "https://api.elevenlabs.io/v1/forced-alignment",
                headers={"xi-api-key": api_key},
                files={"file": ("audio.mp3", audio_file, "audio/mpeg")},
                data={"text": preprocessed_alignment_text},
                timeout=120,
            )

        if resp.status_code != 200:
            logger.warning(f"Forced Alignment API 실패: {resp.status_code} {resp.text}")
            return []

        alignment = resp.json()
        words = alignment.get("words", [])
        if not words:
            logger.warning("Forced Alignment 결과에 단어가 없음")
            return []

        logger.info(f"Forced Alignment 단어 {len(words)}개 추출 완료")
        # 단어 타임스탬프를 원본 텍스트 청크에 매핑
        total_orig_chars = max(sum(len(c.replace(' ', '')) for c in text_chunks), 1)
        total_fa_chars = max(sum(len(w.get('text', '').replace(' ', '')) for w in words), 1)

        chunks = []
        cum_orig_chars = 0
        w_idx = 0
        cum_fa_chars = 0
        num_words = len(words)
        prev_end = 0.0

        for idx, chunk_text in enumerate(text_chunks):
            chunk_char_len = len(chunk_text.replace(' ', ''))
            cum_orig_chars += chunk_char_len
            target_ratio = cum_orig_chars / total_orig_chars
            target_fa_chars = target_ratio * total_fa_chars

            start_w_idx = w_idx
            while w_idx < num_words and cum_fa_chars < target_fa_chars:
                w_text = words[w_idx].get('text', '')
                cum_fa_chars += len(w_text.replace(' ', ''))
                w_idx += 1

            if w_idx > start_w_idx:
                chunk_start = words[start_w_idx].get('start', prev_end)
                chunk_end = words[w_idx - 1].get('end', prev_end + 0.5)
            else:
                chunk_start = prev_end
                chunk_end = prev_end + 0.5

            if chunk_start < prev_end:
                chunk_start = prev_end
            if chunk_end <= chunk_start:
                chunk_end = chunk_start + 0.5

            if idx == len(text_chunks) - 1 and num_words > 0:
                chunk_end = max(chunk_end, words[-1].get('end', chunk_end))

            duration = round(chunk_end - chunk_start, 3)
            chunks.append({
                "index": idx + 1,
                "text": chunk_text,
                "start": round(chunk_start, 3),
                "duration": duration,
            })
            prev_end = chunk_start + duration

        logger.info(f"Forced Alignment 정밀 매핑 완료: {len(text_chunks)}개 청크")
        return chunks

    # ============================
    # 자막 청크 분할 (단어 잘림 방지 + 마크다운 제거)
    # ============================
    @staticmethod
    def _split_script_into_chunks(script: str, max_chars: int = 22) -> list[str]:
        """원본 스크립트에서 마크다운 헤더(##)를 제거하고, 단어가 중간에 잘리지 않도록 문장/구절 단위로 깔끔하게 분할"""
        clean_script = re.sub(r'^##\s*.+$', '', script, flags=re.MULTILINE).strip()
        
        # 문장 종결 부호 및 어미, 쉼표 등 자연스러운 호흡 지점에서 분리 (파이썬 re 모듈의 고정폭 lookbehind 제한 준수)
        raw_sentences = re.split(
            r'(?<=[.!?。])\s+|'
            r'(?<=다\.)\s+|(?<=다)\s+|'
            r'(?<=요\.)\s+|(?<=요)\s+|'
            r'(?<=죠\.)\s+|(?<=죠)\s+|'
            r'(?<=네\.)\s+|(?<=네)\s+|'
            r'(?<=까\.)\s+|(?<=까)\s+|'
            r'(?<=며,)\s+|(?<=고,)\s+|'
            r'(?<=으면서)\s+',
            clean_script
        )
        raw_sentences = [s.strip() for s in raw_sentences if s.strip()]
        
        text_chunks = []
        for sent in raw_sentences:
            words = sent.split()
            current_line = []
            current_len = 0
            for w in words:
                new_len = current_len + len(w) + (1 if current_line else 0)
                if new_len > max_chars and current_line:
                    text_chunks.append(" ".join(current_line))
                    current_line = [w]
                    current_len = len(w)
                else:
                    current_line.append(w)
                    current_len = new_len
            if current_line:
                text_chunks.append(" ".join(current_line))
                
        return text_chunks

    # ============================
    # faster-whisper 역방향 STT → 원본 텍스트 매핑
    # ============================
    def _extract_timestamps_with_whisper(self, mp3_path: str, original_script: str) -> list[dict]:
        """
        핵심: gTTS/ElevenLabs로 생성된 MP3를 faster-whisper로 분석하여 시간 곡선을 구한 뒤,
        사용자가 작성한 원본 스크립트(100% 일치 텍스트)에 타임스탬프를 정밀 매핑.
        발음 기반 STT 오타/문법 왜곡을 원천 차단함.
        """
        model = self._get_whisper_model()
        segments, info = model.transcribe(
            mp3_path,
            language="ko",
            word_timestamps=True,
            beam_size=1,
            best_of=1,
            temperature=0,
        )

        whisper_words = []
        for seg in segments:
            if seg.words:
                for w in seg.words:
                    whisper_words.append({
                        "word": w.word.strip(),
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                    })

        text_chunks = self._split_script_into_chunks(original_script, max_chars=22)
        if not text_chunks:
            return []

        if not whisper_words:
            return []
        # 원본 스크립트와 Whisper STT 간의 글자수 누적 비율 매핑
        total_orig_chars = max(sum(len(c.replace(" ", "")) for c in text_chunks), 1)
        total_whisper_chars = max(sum(len(w["word"].replace(" ", "")) for w in whisper_words), 1)

        chunks = []
        cum_orig_chars = 0
        w_idx = 0
        cum_whisper_chars = 0
        num_whisper = len(whisper_words)
        prev_end = 0.0

        for idx, chunk_text in enumerate(text_chunks):
            chunk_char_len = len(chunk_text.replace(" ", ""))
            cum_orig_chars += chunk_char_len
            target_ratio = cum_orig_chars / total_orig_chars
            target_whisper_chars = target_ratio * total_whisper_chars

            start_w_idx = w_idx
            while w_idx < num_whisper and cum_whisper_chars < target_whisper_chars:
                cum_whisper_chars += len(whisper_words[w_idx]["word"].replace(" ", ""))
                w_idx += 1

            if w_idx > start_w_idx:
                chunk_start = whisper_words[start_w_idx]["start"]
                chunk_end = whisper_words[w_idx - 1]["end"]
            else:
                chunk_start = prev_end
                chunk_end = prev_end + 0.5

            if chunk_start < prev_end:
                chunk_start = prev_end
            if chunk_end <= chunk_start:
                chunk_end = chunk_start + 0.5

            if idx == len(text_chunks) - 1 and num_whisper > 0:
                chunk_end = max(chunk_end, whisper_words[-1]["end"])

            duration = round(chunk_end - chunk_start, 3)
            chunks.append({
                "index": idx + 1,
                "text": chunk_text,
                "start": round(chunk_start, 3),
                "duration": duration,
            })
            prev_end = chunk_start + duration

        logger.info(f"Whisper 정밀 매핑 완료: 원본 {len(text_chunks)}개 청크에 타임스탬프 부여")
        return chunks

    # ============================
    # 폴백 타이밍 (글자 수 비례)
    # ============================
    def _fallback_timing(self, script: str, total_duration: float) -> list[dict]:
        """Whisper 실패 시 글자 수 비례로 타이밍 계산 (단어 잘림 없는 원본 텍스트 분할)"""
        text_chunks = self._split_script_into_chunks(script, max_chars=22)
        if not text_chunks:
            return []

        total_chars = max(sum(len(c.replace(" ", "")) for c in text_chunks), 1)
        chunks = []
        cursor = 0.0

        for idx, chunk_text in enumerate(text_chunks):
            char_len = len(chunk_text.replace(" ", ""))
            ratio = char_len / total_chars
            duration = round(total_duration * ratio, 3)
            if idx == len(text_chunks) - 1:
                duration = round(max(total_duration - cursor, 0.1), 3)

            chunks.append({
                "index": idx + 1,
                "text": chunk_text,
                "start": round(cursor, 3),
                "duration": duration,
            })
            cursor = round(cursor + duration, 3)

        return chunks

    # ============================
    # 주식 텍스트 전처리
    # ============================
    @staticmethod
    def _preprocess_for_tts(text: str) -> str:
        """주식/경제 용어를 gTTS/ElevenLabs가 자연스럽게 읽도록 전처리"""
        text = re.sub(r'^##\s*.+$', '', text, flags=re.MULTILINE).strip()
        text = re.sub(r'([+-]?\d+\.?\d*)%', r'\1퍼센트', text)
        text = re.sub(r'\+(\d)', r'플러스 \1', text)
        text = re.sub(r'(?<!\d)-(\d)', r'마이너스 \1', text)
        text = re.sub(r'(\d+)pt\b', r'\1포인트', text)
        text = re.sub(r'(\d{1,3}),(\d{3})', r'\1\2', text)

        # 숫자 -> 한글 한글화 함수
        def num_to_kor(num_str: str) -> str:
            if not num_str:
                return ""
            if num_str == "0":
                return "영"
            if re.match(r'^0+$', num_str):
                return "영" * len(num_str)
            val = int(num_str)
            if val >= 10000:
                # 5자리 이상 대형 숫자는 한 자씩 읽기
                return "".join(["영", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"][int(d)] for d in num_str)
            units = ["", "십", "백", "천"]
            nums = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
            res = ""
            length = len(num_str)
            for i, digit in enumerate(num_str):
                d_val = int(digit)
                if d_val != 0:
                    digit_name = nums[d_val]
                    if d_val == 1 and (length - 1 - i) > 0:
                        digit_name = ""
                    res += digit_name + units[length - 1 - i]
            return res

        # 소수점 변환 (소수부 각 자릿수 개별 읽기: e.g. 6.56 -> 육 점 오육, 1.125 -> 일 점 일이오)
        def repl_decimal(match):
            int_part = match.group(1)
            dec_part = match.group(2)
            int_kor = num_to_kor(int_part)
            digit_names = ["영", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
            dec_kor = "".join(digit_names[int(d)] for d in dec_part)
            # 사용자의 요청에 따라 강한 발음인 '쩜' 대신 자연스러운 '점'을 사용하고, 앞뒤 공백을 주어 자연스러운 호흡 유도
            return f"{int_kor} 점 {dec_kor}"

        text = re.sub(r'(\d+)\.(\d+)', repl_decimal, text)

        def repl_num(match):
            return num_to_kor(match.group(0))

        # 독립된 숫자들을 모두 한글로 변환 (예: 7246 -> 칠천이백사십육)
        text = re.sub(r'\b\d+\b', repl_num, text)

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
