"""
ElevenLabs TTS Provider — Official ElevenLabs API + gTTS fallback

⚠️ 중복 경로 안내:
  실제 롱폼 파이프라인의 TTS는 이 파일이 아니라
  app/workers/tts_worker.py가 ElevenLabs API를 직접 호출합니다
  (배속 적용, Forced Alignment, 발음 사전까지 전부 tts_worker.py에
  구현되어 있음). 이 파일(ElevenLabsProvider)은 get_tts_provider()
  팩토리를 통해서만 접근되는데, 현재 코드베이스 어디에서도
  get_tts_provider()를 호출하는 곳이 확인되지 않았습니다 — 즉 지금은
  거의 쓰이지 않는 경로로 보입니다 (shorts_worker.py 등에서 쓰고
  있다면 예외).

  완전히 안 쓰이는 게 맞다면 나중에 정리(삭제) 대상으로 남겨두고,
  일단은 tts_worker.py와 설정값(모델/voice_settings)이 따로 놀지
  않도록 runtime_config를 참조하도록만 맞춰뒀습니다.

v2에서 바뀐 것:
  - model_id를 "eleven_multilingual_v2" → tts_worker.py와 동일한
    "eleven_v3"로 통일
  - voice_settings(stability/similarity_boost/style)를 runtime_config
    참조로 변경 (하드코딩된 0.5/0.75와 tts_worker.py의 실제 운영값이
    서로 다르게 존재하던 것을 통일)
"""
import os
import re
import logging
import requests
import tempfile
from pathlib import Path
from gtts import gTTS

from app.providers.base import TTSProvider, GeneratedAsset
from app import runtime_config

logger = logging.getLogger(__name__)


class ElevenLabsProvider(TTSProvider):
    """
    ElevenLabs (Official API) 및 gTTS 기반 한국어 TTS 프로바이더.
    """

    def __init__(self):
        self.default_voice_id = os.getenv("ELEVENLABS_VOICE_ID") or runtime_config.value("elevenlabs_voice_id")

    def synthesize(self, text: str, voice_id: str = None, **kwargs) -> GeneratedAsset:
        """텍스트를 음성(MP3)으로 합성하여 저장."""
        output_path = kwargs.get("output_path")
        if not output_path:
            output_path = tempfile.mktemp(suffix=".mp3")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"ElevenLabs TTS 합성 요청: len={len(text)}자, voice_id={voice_id}")

        api_key = os.getenv("ELEVENLABS_API_KEY")
        if api_key:
            try:
                if self._generate_elevenlabs_api(text, output_path, voice_id or self.default_voice_id, api_key):
                    logger.info(f"공식 ElevenLabs API 음성 합성 성공: {output_path}")
                    return GeneratedAsset(asset_type="audio", local_path=output_path)
            except Exception as e:
                logger.warning(f"ElevenLabs API 호출 실패, gTTS 폴백: {e}")

        self._generate_gtts_fallback(text, output_path)
        return GeneratedAsset(asset_type="audio", local_path=output_path)

    def _generate_elevenlabs_api(self, text: str, output_path: str, voice_id: str, api_key: str) -> bool:
        """ElevenLabs v1/text-to-speech API 호출 (2000자 분할 지원)."""
        if voice_id in ["gtts_ko", "default", "silent"]:
            voice_id = self.default_voice_id

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }

        voice_settings = {
            "stability": runtime_config.value("elevenlabs_stability"),
            "similarity_boost": runtime_config.value("elevenlabs_similarity_boost"),
            "style": runtime_config.value("elevenlabs_style"),
            "use_speaker_boost": True,
        }

        MAX_CHARS = 2000
        if len(text) <= MAX_CHARS:
            payload = {
                "text": text,
                "model_id": "eleven_v3",
                "voice_settings": voice_settings,
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                return True
            logger.warning(f"ElevenLabs API 응답 에러: {resp.status_code} {resp.text}")
            return False
        else:
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
                tmp = tempfile.mktemp(suffix=f"_el_prov_{idx}.mp3")
                payload = {
                    "text": part,
                    "model_id": "eleven_v3",
                    "voice_settings": voice_settings,
                }
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                if resp.status_code == 200:
                    with open(tmp, "wb") as f:
                        f.write(resp.content)
                    tmp_files.append(tmp)
                else:
                    for t in tmp_files:
                        if os.path.exists(t):
                            os.remove(t)
                    return False

            list_file = tempfile.mktemp(suffix=".txt")
            with open(list_file, "w", encoding="utf-8") as f:
                for t in tmp_files:
                    f.write(f"file '{t}'\n")

            os.system(f'ffmpeg -f concat -safe 0 -i "{list_file}" -c:a copy -y "{output_path}" -loglevel error')
            for t in tmp_files:
                if os.path.exists(t):
                    os.remove(t)
            if os.path.exists(list_file):
                os.remove(list_file)

            return os.path.exists(output_path)

    def _generate_gtts_fallback(self, text: str, output_path: str):
        """gTTS 기반 한국어 음성 합성 (폴백)."""
        tts = gTTS(text=text[:3000], lang='ko', slow=False)
        tts.save(output_path)
        logger.info(f"gTTS 폴백 생성 완료: {output_path}")
