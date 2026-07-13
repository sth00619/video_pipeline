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
import subprocess
from pathlib import Path
from typing import List, Dict
from app.utils.process_manager import is_job_stopped, register_process, unregister_process
from app import runtime_config

logger = logging.getLogger(__name__)


class TtsWorker:

    def __init__(self):
        self._whisper_model = None

    def _run_subprocess(self, cmd: str, job_id: int) -> int:
        """FFmpeg 등의 명령어를 subprocess.Popen으로 실행하고 중지 트래킹 등록"""
        if is_job_stopped(job_id):
            raise RuntimeError(f"Job {job_id} is stopped. Aborting execution.")
        logger.info(f"Running tracked subprocess (TTS): {cmd}")
        p = subprocess.Popen(cmd, shell=True)
        register_process(job_id, p)
        try:
            ret = p.wait()
            return ret
        finally:
            unregister_process(job_id, p)

    def _get_whisper_model(self):
        """faster-whisper 모델 싱글턴 (이미 설치됨)"""
        if self._whisper_model is None:
            from faster_whisper import WhisperModel
            # base 모델 사용 (이미 캐시됨)
            self._whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
            logger.info("faster-whisper base 모델 로드 완료")
        return self._whisper_model

    def synthesize(self, script: str, voice_id: str, job_id: int = 0,
                   tts_speed: float = None) -> dict:
        if not script or not script.strip():
            raise ValueError("스크립트가 비어있습니다.")

        # 배속을 요청별로 넘기지 않으면 runtime_config의 현재 값 사용
        # (/pipeline/config API로 재빌드 없이 즉시 조정 가능)
        speed = tts_speed if tts_speed is not None else runtime_config.value("tts_speed")
        subtitle_max_chars = runtime_config.value("subtitle_max_chars")

        logger.info(f"TTS v6 시작: job_id={job_id}, length={len(script)}자, speed={speed}")

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
                # [대사]와 [비주얼/감정] 사이의 텍스트만 추출
                daesa_match = re.search(r'\[대사\]\s*(.*?)\s*(?:\[비주얼|\[감정|$)', part, re.DOTALL)
                if daesa_match:
                    clean_script += daesa_match.group(1).strip() + " "
                else:
                    # [대사] 태그가 없으면 [비주얼/감정] 태그 이전의 텍스트 추출
                    no_visual = re.sub(r'\[비주얼.*$', '', part, flags=re.DOTALL).strip()
                    no_visual = re.sub(r'\[감정.*$', '', no_visual, flags=re.DOTALL).strip()
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
                used_tts = self._generate_elevenlabs(preprocessed, mp3_path, voice_id, job_id, tts_speed=speed)
                if used_tts:
                    tts_engine = "elevenlabs"
            
            if not used_tts:
                # gTTS 폴백 시에는 clean_script 전처리 적용 (발음 사전 미지원)
                used_tts = self._generate_gtts(preprocessed, mp3_path, job_id)
                if used_tts:
                    tts_engine = "gtts"
        except Exception as e:
            logger.error(f"TTS 생성 실패: {e}")

        if not used_tts or not os.path.exists(mp3_path):
            logger.warning("TTS 실패 → 무음 폴백")
            estimated = len(clean_script) / 5.0
            self._run_subprocess(
                f'ffmpeg -f lavfi -i "anullsrc=r=44100:cl=stereo" '
                f'-t {estimated:.3f} -c:a libmp3lame -b:a 128k '
                f'-y "{mp3_path}" -loglevel error',
                job_id
            )
        # 오디오 가속 적용 (atempo 필터) — ElevenLabs는 네이티브 배속 우선, 범위 이탈분이나 폴백용만 FFmpeg 처리
        if os.path.exists(mp3_path):
            apply_ffmpeg_speed = speed
            if tts_engine == "elevenlabs":
                # ElevenLabs는 0.7~1.2 범위를 이미 네이티브로 가속하여 생성함
                if 0.7 <= speed <= 1.2:
                    apply_ffmpeg_speed = 1.0
                elif speed > 1.2:
                    apply_ffmpeg_speed = speed / 1.2
                else: # speed < 0.7
                    apply_ffmpeg_speed = speed / 0.7
            
            if apply_ffmpeg_speed != 1.0:
                logger.info(f"음성 배속({apply_ffmpeg_speed:.3f}x) 적용 시작...")
                temp_mp3 = mp3_path + ".speedup.mp3"
                ret = self._run_subprocess(f'ffmpeg -i "{mp3_path}" -filter:a "atempo={apply_ffmpeg_speed}" -c:a libmp3lame -b:a 128k -y "{temp_mp3}" -loglevel error', job_id)
                if ret == 0 and os.path.exists(temp_mp3):
                    os.replace(temp_mp3, mp3_path)
                    logger.info(f"음성 배속({apply_ffmpeg_speed:.3f}x) 적용 성공")
                else:
                    logger.error(f"음성 배속 적용 실패 (exit code: {ret})")

        # 실제 MP3 길이 측정
        actual_duration = self._probe_duration(mp3_path) or len(clean_script) / 5.0
        logger.info(f"음성 길이 ({speed}x 배속 후): {actual_duration:.1f}초")

        # 3. 자막 타임스탬프 추출 (Forced Alignment → stable-ts → Whisper → 글자수 비례)
        chunks = []
        if used_tts:
            # 3a. ElevenLabs Forced Alignment 시도 (가장 정확)
            if tts_engine == "elevenlabs":
                try:
                    chunks = self._extract_timestamps_with_forced_alignment(mp3_path, clean_script, subtitle_max_chars)
                    logger.info(f"Forced Alignment 타임스탬프 추출: {len(chunks)}개 세그먼트")
                except Exception as e:
                    logger.warning(f"Forced Alignment 실패, stable-ts 폴백: {e}")
                    chunks = []

            # 3b. stable-ts 폴백 (ElevenLabs Forced Alignment 실패 또는 gTTS 엔진)
            if not chunks:
                try:
                    chunks = self._extract_timestamps_with_stable_ts(mp3_path, clean_script, subtitle_max_chars)
                    logger.info(f"stable-ts 타임스탬프 추출: {len(chunks)}개 세그먼트")
                except Exception as e:
                    logger.warning(f"stable-ts 타임스탬프 추출 실패, Whisper 폴백: {e}")
                    chunks = []

            # 3c. faster-whisper 폴백 (stable-ts 실패 시)
            if not chunks:
                try:
                    chunks = self._extract_timestamps_with_whisper(mp3_path, clean_script, subtitle_max_chars)
                    logger.info(f"Whisper 타임스탬프 추출: {len(chunks)}개 세그먼트")
                except Exception as e:
                    logger.error(f"Whisper 타임스탬프 추출 실패: {e}")
                    chunks = []

        # 4. 모든 타임스탬프 추출 실패 시 글자 수 비례 폴백
        if not chunks:
            logger.warning("글자 수 비례 타임스탬프로 폴백")
            chunks = self._fallback_timing(clean_script, actual_duration, subtitle_max_chars)

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
    def _generate_gtts(self, text: str, output_path: str, job_id: int = 0) -> bool:
        """gTTS로 한국어 음성 생성. 5000자 초과 시 분할 생성 후 concat."""
        from gtts import gTTS
        import tempfile

        MAX_CHARS = 4500

        if is_job_stopped(job_id):
            raise RuntimeError(f"Job {job_id} stopped by user.")

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
            if is_job_stopped(job_id):
                raise RuntimeError(f"Job {job_id} stopped by user.")
            tmp = tempfile.mktemp(suffix=".mp3")
            tts = gTTS(text=part, lang='ko', slow=False)
            tts.save(tmp)
            tmp_files.append(tmp)

        import tempfile as tf
        list_file = tf.mktemp(suffix=".txt")
        with open(list_file, "w") as f:
            for t in tmp_files:
                f.write(f"file '{t}'\n")

        self._run_subprocess(
            f'ffmpeg -f concat -safe 0 -i "{list_file}" '
            f'-c:a copy -y "{output_path}" -loglevel error',
            job_id
        )

        for t in tmp_files:
            if os.path.exists(t):
                os.remove(t)
        if os.path.exists(list_file):
            os.remove(list_file)

        return os.path.exists(output_path)

    def _generate_elevenlabs(self, text: str, output_path: str, voice_id: str, job_id: int = 0, tts_speed: float = None) -> bool:
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

        # Sprint 1 (S1-4): ElevenLabs 쿼터 사전 체크
        try:
            quota_resp = requests.get(
                "https://api.elevenlabs.io/v1/user/subscription",
                headers={"xi-api-key": api_key},
                timeout=10
            )
            if quota_resp.status_code == 200:
                quota_data = quota_resp.json()
                char_limit = quota_data.get("character_limit", 0)
                char_count = quota_data.get("character_count", 0)
                remaining = char_limit - char_count
                required_chars = len(text)
                logger.info(f"ElevenLabs 쿼터 정보: limit={char_limit}, count={char_count}, remaining={remaining}, required={required_chars}")
                if remaining < required_chars * 1.1:
                    logger.warning(f"ElevenLabs 잔여 쿼터 부족 ({remaining} < {required_chars * 1.1:.0f}) -> 즉시 gTTS 폴백")
                    return False
            else:
                logger.warning(f"ElevenLabs 쿼터 조회 API 실패 (status: {quota_resp.status_code}) -> 일단 API 호출 시도")
        except Exception as e:
            logger.warning(f"ElevenLabs 쿼터 조회 예외 발생: {e} -> 일단 API 호출 시도")

        if is_job_stopped(job_id):
            raise RuntimeError(f"Job {job_id} stopped by user.")
        
        # voice_id가 없거나 기본값이면 한국어 발음이 자연스러운 기본 voice_id 사용
        if not voice_id or voice_id in ["gtts_ko", "default", "silent", "gtts_whisper_ko"]:
            voice_id = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
            
        # [공식 권장] apply_text_normalization=off 쿼리 파라미터 전달 및 이중 가속/배속 파라미터
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?apply_text_normalization=off"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }

        # 네이티브 배속 설정 (0.7~1.2 범위 우선 적용)
        speed = tts_speed if tts_speed is not None else 1.0
        native_speed = 1.0
        if 0.7 <= speed <= 1.2:
            native_speed = speed
        elif speed > 1.2:
            native_speed = 1.2
        else: # speed < 0.7
            native_speed = 0.7

        # 발음 사전 로케이터 (금융 용어 발음 교정)
        pron_mgr = PronunciationManager.get_instance()
        pron_locators = pron_mgr.get_locators()
        
        def _build_payload(chunk_text: str, prev_text: str = "", next_text_val: str = "") -> dict:
            payload = {
                "text": chunk_text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": runtime_config.value("elevenlabs_stability"),
                    "similarity_boost": runtime_config.value("elevenlabs_similarity_boost"),
                    "style": runtime_config.value("elevenlabs_style"),
                    "use_speaker_boost": True,
                    "speed": native_speed
                },
                # [공식 가이드] Root level에도 normalization 끄기 설정 명시
                "apply_text_normalization": "off"
            }
            if prev_text:
                payload["previous_text"] = prev_text
            if next_text_val:
                payload["next_text"] = next_text_val
            if pron_locators:
                payload["pronunciation_dictionary_locators"] = pron_locators
            return payload
        
        MAX_CHARS = 800
        if len(text) <= MAX_CHARS:
            payload = _build_payload(text)
            success = False
            for retry in range(2):
                try:
                    resp = requests.post(url, json=payload, headers=headers, timeout=40)
                    if resp.status_code == 200:
                        with open(output_path, "wb") as f:
                            f.write(resp.content)
                        logger.info(f"ElevenLabs v3 + 발음 사전 음성 생성 성공 (단일 요청, 시도 {retry+1})")
                        success = True
                        break
                    else:
                        logger.warning(f"ElevenLabs API 시도 {retry+1} 실패: {resp.status_code}")
                except Exception as e:
                    logger.warning(f"ElevenLabs API 시도 {retry+1} 예외: {e}")
            
            if success:
                return True
            else:
                logger.warning("ElevenLabs 단일 요청 실패 -> gTTS 단일 폴백 시도")
                return self._generate_gtts(text, output_path, job_id)
        else:
            # 800자 단위 분할 (문장 경계 기준)
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
                if is_job_stopped(job_id):
                    raise RuntimeError(f"Job {job_id} stopped by user.")
                tmp = tf.mktemp(suffix=f"_el_{idx}.mp3")
                
                # 이전 청크와 다음 청크를 힌트로 넘겨 억양 단절 보정
                prev_p = parts[idx - 1] if idx > 0 else ""
                next_p = parts[idx + 1] if idx + 1 < len(parts) else ""
                
                payload = _build_payload(part, prev_text=prev_p, next_text_val=next_p)
                chunk_success = False
                
                # 2회 재시도 루프
                for retry in range(2):
                    try:
                        resp = requests.post(url, json=payload, headers=headers, timeout=40)
                        if resp.status_code == 200:
                            with open(tmp, "wb") as f:
                                f.write(resp.content)
                            tmp_files.append(tmp)
                            logger.info(f"ElevenLabs 분할 {idx+1}/{len(parts)} 성공 (시도 {retry+1})")
                            chunk_success = True
                            break
                        else:
                            logger.warning(f"ElevenLabs 분할 {idx+1} 시도 {retry+1} 실패: {resp.status_code}")
                    except Exception as e:
                        logger.warning(f"ElevenLabs 분할 {idx+1} 시도 {retry+1} 예외: {e}")
                
                # 청크 레벨 폴백: ElevenLabs 실패 시 gTTS로 해당 청크 대체
                if not chunk_success:
                    logger.warning(f"ElevenLabs 분할 {idx+1} 최종 실패 -> gTTS 폴백 적용")
                    try:
                        from gtts import gTTS
                        tts = gTTS(text=part, lang='ko', slow=False)
                        tts.save(tmp)
                        tmp_files.append(tmp)
                        logger.info(f"gTTS 분할 {idx+1}/{len(parts)} 성공 (폴백)")
                    except Exception as ge:
                        logger.error(f"gTTS 분할 {idx+1} 폴백 실패: {ge} -> 무음 청크 생성")
                        estimated = len(part) / 5.0
                        self._run_subprocess(
                            f'ffmpeg -f lavfi -i "anullsrc=r=44100:cl=stereo" '
                            f'-t {estimated:.3f} -c:a libmp3lame -b:a 128k '
                            f'-y "{tmp}" -loglevel error',
                            job_id
                        )
                        tmp_files.append(tmp)
                    
            list_file = tf.mktemp(suffix=".txt")
            with open(list_file, "w", encoding="utf-8") as f:
                for t in tmp_files:
                    f.write(f"file '{t}'\n")
            
            self._run_subprocess(
                f'ffmpeg -f concat -safe 0 -i "{list_file}" '
                f'-c:a copy -y "{output_path}" -loglevel error',
                job_id
            )
            for t in tmp_files:
                if os.path.exists(t): os.remove(t)
            if os.path.exists(list_file): os.remove(list_file)
            
            logger.info(f"음성 생성 및 병합 완료 ({len(parts)}개 조각, 하이브리드 모드)")
            return os.path.exists(output_path)

    # ============================
    # ElevenLabs Forced Alignment → 정밀 자막 타이밍
    # ============================
    def _extract_timestamps_with_forced_alignment(self, mp3_path: str, original_script: str,
                                                    subtitle_max_chars: int = 22) -> list[dict]:
        """
        ElevenLabs Forced Alignment API를 사용하여 단어 단위 정밀 타임스탬프를 추출합니다.

        [버그 수정] 이전 버전은 자막 청크 자체를 preprocessed_text(발음 전처리된
        텍스트, 예: "이천칠백팔십포인트")로 분할해서 썼습니다. 그러면 실제 음성이
        읽은 발음대로 화면 자막이 나오게 되어, 대본에 쓴 "2,780포인트" 표기와
        자막이 달라지는 문제가 있었습니다 ("스크립트=자막 100% 일치" 요구사항에 어긋남).

        수정: 자막에 표시할 텍스트는 원본(가독형) original_script 기준으로 분할하고,
        Forced Alignment 결과와의 매핑 비율만 "각 청크를 개별 전처리했을 때의
        글자 수"를 기준으로 계산합니다. 전처리 후 글자 수가 실제 발음 시간과
        훨씬 비례하기 때문에, 화면 자막은 원본 그대로 유지하면서 타이밍
        정확도만 개선됩니다.
        """
        import requests

        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            return []

        # 화면에 보일 자막 청크는 원본(가독형) 텍스트 기준으로 분할
        text_chunks = self._split_script_into_chunks(original_script, max_chars=subtitle_max_chars)
        if not text_chunks:
            return []

        # TTS에 실제로 전달된 것과 동일한 전처리 텍스트로 FA API 호출 (음성=정렬 대상 일치)
        clean_text = re.sub(r'^##\s*.+$', '', original_script, flags=re.MULTILINE).strip()
        preprocessed_text = self._preprocess_for_tts(clean_text)

        with open(mp3_path, "rb") as audio_file:
            resp = requests.post(
                "https://api.elevenlabs.io/v1/forced-alignment",
                headers={"xi-api-key": api_key},
                files={"file": ("audio.mp3", audio_file, "audio/mpeg")},
                data={"text": preprocessed_text},
                timeout=120,
            )

        if resp.status_code != 200:
            logger.warning(f"Forced Alignment API 실패: {resp.status_code} {resp.text}")
            return []

        alignment = resp.json()
        raw_words = alignment.get("words", [])
        if not raw_words:
            logger.warning("Forced Alignment 결과에 단어가 없음")
            return []

        engine_words = [
            {"word": w.get("text", ""), "start": w.get("start", 0.0), "end": w.get("end", 0.0)}
            for w in raw_words
        ]
        logger.info(f"Forced Alignment 단어 {len(engine_words)}개 추출 완료")

        chunks = self._map_timestamps_by_preprocessed_length(text_chunks, engine_words)
        logger.info(f"Forced Alignment 정밀 매핑 완료 (자막=원본, 타이밍=발음전처리 기준): {len(text_chunks)}개 청크")
        return chunks

    # ============================
    # 공용 타임스탬프 매핑 (핵심 버그 수정 지점 — FA/stable-ts/whisper 공통 사용)
    # ============================
    def _map_timestamps_by_preprocessed_length(self, text_chunks: List[str],
                                                engine_words: List[Dict]) -> List[dict]:
        """
        text_chunks: 자막에 표시할 원본(가독형) 텍스트 청크 목록
        engine_words: [{"word":str, "start":float, "end":float}, ...]

        기존 버그: 원본 텍스트의 글자 수 비율로 시간을 나누면, 숫자나 영문
        약어처럼 "표기는 짧지만 실제 발음은 긴" 구간에서 타이밍이 어긋납니다.
        (예: "FOMC"는 4글자지만 "에프오엠씨"로 5음절 발음됨)

        수정: 각 청크를 개별적으로 _preprocess_for_tts()에 통과시킨 후의 글자
        수를 비율 계산 기준으로 사용합니다. 전처리 후 글자 수는 실제 발음
        시간과 훨씬 비례합니다.
        """
        preprocessed_lengths = [
            max(len(self._preprocess_for_tts(c).replace(" ", "")), 1)
            for c in text_chunks
        ]
        total_len = max(sum(preprocessed_lengths), 1)
        total_engine_chars = max(sum(len(w["word"].replace(" ", "")) for w in engine_words), 1)
        num_words = len(engine_words)

        chunks = []
        cum_len = 0
        w_idx = 0
        cum_engine_chars = 0
        prev_end = 0.0

        for idx, chunk_text in enumerate(text_chunks):
            cum_len += preprocessed_lengths[idx]
            target_ratio = cum_len / total_len
            target_engine_chars = target_ratio * total_engine_chars

            start_w_idx = w_idx
            while w_idx < num_words and cum_engine_chars < target_engine_chars:
                cum_engine_chars += len(engine_words[w_idx]["word"].replace(" ", ""))
                w_idx += 1

            if w_idx > start_w_idx:
                chunk_start = engine_words[start_w_idx]["start"]
                chunk_end = engine_words[w_idx - 1]["end"]
            else:
                chunk_start = prev_end
                chunk_end = prev_end + 0.5

            if chunk_start < prev_end:
                chunk_start = prev_end
            if chunk_end <= chunk_start:
                chunk_end = chunk_start + 0.5

            if idx == len(text_chunks) - 1 and num_words > 0:
                chunk_end = max(chunk_end, engine_words[-1]["end"])

            duration = round(chunk_end - chunk_start, 3)
            chunks.append({
                "index": idx + 1,
                "text": chunk_text,
                "start": round(chunk_start, 3),
                "duration": duration,
            })
            prev_end = chunk_start + duration

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
    # stable-ts (cross-attention 기반) → 정밀 자막 싱크
    # ============================
    def _extract_timestamps_with_stable_ts(self, mp3_path: str, original_script: str,
                                             subtitle_max_chars: int = 22) -> list[dict]:
        """
        stable-ts 라이브러리 (stable_whisper)를 사용하여 cross-attention 기반
        단어 단위 정밀 타임스탬프를 추출합니다.

        faster-whisper 역방향 STT보다 더 정확한 이유:
        - DTW(Dynamic Time Warping) + cross-attention 가중치로 단어 경계 감지
        - vad=True로 무음 구간 스킵 → 타임스탬프 드리프트 방지
        - 한국어 구절 단위 자동 재결합 (regroup=True)
        """
        try:
            import stable_whisper
        except ImportError:
            raise ImportError("stable-ts가 설치되지 않았습니다. pip install 'stable-ts[fw]'")

        logger.info("stable-ts (cross-attention) 타임스탬프 추출 시작...")
        model = stable_whisper.load_faster_whisper(
            "base",
            device="cpu",
            compute_type="int8"
        )
        result = model.transcribe_stable(
            mp3_path,
            language="ko",
            vad=True,       # 무음 구간 자동 스킵 → 드리프트 방지
            regroup=True,   # 자연스러운 한국어 구절 단위 재결합
        )

        # 단어 단위 타임스탬프 수집
        stable_words = []
        for segment in result.segments:
            if hasattr(segment, "words") and segment.words:
                for word in segment.words:
                    stable_words.append({
                        "word": word.word.strip(),
                        "start": round(word.start, 3),
                        "end": round(word.end, 3),
                    })

        if not stable_words:
            logger.warning("stable-ts 단어 추출 결과 없음")
            return []

        logger.info(f"stable-ts 단어 {len(stable_words)}개 추출 완료")

        text_chunks = self._split_script_into_chunks(original_script, max_chars=subtitle_max_chars)
        if not text_chunks:
            return []

        # [버그 수정] 기존에는 원본 글자수 비례로 매핑해서 숫자/약어 구간에서
        # 드리프트가 발생했습니다. 공용 헬퍼(발음 전처리 길이 기준)로 교체.
        chunks = self._map_timestamps_by_preprocessed_length(text_chunks, stable_words)
        logger.info(f"stable-ts 정밀 매핑 완료 (발음전처리 길이 기준): {len(text_chunks)}개 청크")
        return chunks

    # ============================
    # faster-whisper 역방향 STT → 원본 텍스트 매핑
    # ============================

    def _extract_timestamps_with_whisper(self, mp3_path: str, original_script: str,
                                           subtitle_max_chars: int = 22) -> list[dict]:
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

        text_chunks = self._split_script_into_chunks(original_script, max_chars=subtitle_max_chars)
        if not text_chunks or not whisper_words:
            return []

        # [버그 수정] 원본 글자수 비례 매핑 → 공용 헬퍼(발음 전처리 길이 기준)로 교체
        chunks = self._map_timestamps_by_preprocessed_length(text_chunks, whisper_words)
        logger.info(f"Whisper 정밀 매핑 완료 (발음전처리 길이 기준): 원본 {len(text_chunks)}개 청크에 타임스탬프 부여")
        return chunks

    # ============================
    # 폴백 타이밍 (글자 수 비례)
    # ============================
    def _fallback_timing(self, script: str, total_duration: float,
                          subtitle_max_chars: int = 22) -> list[dict]:
        """Whisper 실패 시 글자 수 비례로 타이밍 계산 (단어 잘림 없는 원본 텍스트 분할)"""
        text_chunks = self._split_script_into_chunks(script, max_chars=subtitle_max_chars)
        if not text_chunks:
            return []

        # 여기서도 전처리 후 글자수를 기준으로 비율 계산 (숫자/약어 드리프트 방지)
        preprocessed_lengths = [
            max(len(self._preprocess_for_tts(c).replace(" ", "")), 1)
            for c in text_chunks
        ]
        total_chars = max(sum(preprocessed_lengths), 1)
        chunks = []
        cursor = 0.0

        for idx, chunk_text in enumerate(text_chunks):
            char_len = preprocessed_lengths[idx]
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
        text = re.sub(r'([+-]?\d+\.?\d*)%', r'\1포인트', text)
        text = re.sub(r'\+(\d)', r'플러스 \1', text)
        text = re.sub(r'(?<!\d)-(\d)', r'마이너스 \1', text)
        text = re.sub(r'(\d+)pt\b', r'\1포인트', text)
        text = re.sub(r'(\d{1,3}),(\d{3})', r'\1\2', text)

        # 숫자 -> 한글 한글화 함수 (4자리 블록 만/억/조 단위 완벽 지원)
        def num_to_kor(num_str: str) -> str:
            if not num_str:
                return ""
            if num_str == "0":
                return "영"
            if re.match(r'^0+$', num_str):
                return "영" * len(num_str)
            
            # 0으로 시작하는 숫자(예: 010)는 단순 자릿수 단위 없이 한 글자씩 읽음
            if num_str.startswith("0"):
                digit_names = ["영", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
                return "".join(digit_names[int(d)] for d in num_str)

            # 한국어 표준 자릿수 한글화 (4자리 단위: 만, 억, 조, 경)
            units_4 = ["", "만", "억", "조", "경"]
            units_1 = ["", "십", "백", "천"]
            digits = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
            
            # 4자리 단위로 크기 맞춤
            num_str = num_str.zfill(((len(num_str) + 3) // 4) * 4)
            chunks = [num_str[i:i+4] for i in range(0, len(num_str), 4)]
            chunks.reverse()
            
            result_parts = []
            for chunk_idx, chunk in enumerate(chunks):
                chunk_val = int(chunk)
                if chunk_val == 0:
                    continue
                
                chunk_str = ""
                for i, digit in enumerate(chunk):
                    d_val = int(digit)
                    if d_val == 0:
                        continue
                    
                    digit_name = digits[d_val]
                    position = 3 - i  # 3: 천, 2: 백, 1: 십, 0: 일
                    # 십, 백, 천 단위 바로 앞의 '일'은 자연스럽게 생략 (예: 일십 -> 십, 일백 -> 백)
                    if d_val == 1 and position > 0:
                        digit_name = ""
                    
                    chunk_str += digit_name + units_1[position]
                
                # '일만'은 한국어 구어체에서 보통 '만'으로 읽음
                if chunk_str == "일" and chunk_idx == 1:
                    chunk_str = ""
                
                result_parts.append(chunk_str + units_4[chunk_idx])
            
            result_parts.reverse()
            res = "".join(result_parts)
            return res if res else "영"

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
