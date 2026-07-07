"""
ElevenLabs TTS Provider — Official ElevenLabs API + gTTS fallback

1. 공식 API 연동 (ElevenLabs Pro / Creator):
   - ELEVENLABS_API_KEY 설정 시 공식 API 호출
   - 한국어 발음 및 생동감이 뛰어난 AI 성우 음성 합성
   
2. 무료 폴백 엔진:
   - API 키 미설정 시 gTTS 무료 로봇 음성으로 자동 폴백 ($0)
"""
import os
import re
import logging
import requests
import tempfile
from pathlib import Path
from gtts import gTTS

from app.providers.base import TTSProvider, GeneratedAsset

logger = logging.getLogger(__name__)


class ElevenLabsProvider(TTSProvider):
    """
    ElevenLabs (Official API) 및 gTTS 기반 한국어 TTS 프로바이더.
    """

    def __init__(self):
        self.default_voice_id = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb") # George Multilingual

    def synthesize(self, text: str, voice_id: str = None, **kwargs) -> GeneratedAsset:
        """
        텍스트를 음성(MP3)으로 합성하여 저장.
        """
        output_path = kwargs.get("output_path")
        if not output_path:
            output_path = tempfile.mktemp(suffix=".mp3")
            
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"ElevenLabs TTS 합성 요청: len={len(text)}자, voice_id={voice_id}")

        # 1. 공식 ElevenLabs API 시도
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if api_key:
            try:
                if self._generate_elevenlabs_api(text, output_path, voice_id or self.default_voice_id, api_key):
                    logger.info(f"공식 ElevenLabs API 음성 합성 성공: {output_path}")
                    return GeneratedAsset(asset_type="audio", local_path=output_path)
            except Exception as e:
                logger.warning(f"ElevenLabs API 호출 실패, gTTS 폴백: {e}")

        # 2. gTTS 무료 폴백
        self._generate_gtts_fallback(text, output_path)
        return GeneratedAsset(asset_type="audio", local_path=output_path)

    def _generate_elevenlabs_api(self, text: str, output_path: str, voice_id: str, api_key: str) -> bool:
        """
        ElevenLabs v1/text-to-speech API 호출 (2000자 분할 지원).
        """
        if voice_id in ["gtts_ko", "default", "silent"]:
            voice_id = self.default_voice_id
            
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }
        
        MAX_CHARS = 2000
        if len(text) <= MAX_CHARS:
            payload = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "use_speaker_boost": True}
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
                    if current: parts.append(current)
                    current = sent
            if current: parts.append(current)
                
            tmp_files = []
            for idx, part in enumerate(parts):
                tmp = tempfile.mktemp(suffix=f"_el_prov_{idx}.mp3")
                payload = {
                    "text": part,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
                }
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                if resp.status_code == 200:
                    with open(tmp, "wb") as f: f.write(resp.content)
                    tmp_files.append(tmp)
                else:
                    for t in tmp_files:
                        if os.path.exists(t): os.remove(t)
                    return False
                    
            list_file = tempfile.mktemp(suffix=".txt")
            with open(list_file, "w", encoding="utf-8") as f:
                for t in tmp_files: f.write(f"file '{t}'\n")
            
            os.system(f'ffmpeg -f concat -safe 0 -i "{list_file}" -c:a copy -y "{output_path}" -loglevel error')
            for t in tmp_files:
                if os.path.exists(t): os.remove(t)
            if os.path.exists(list_file): os.remove(list_file)
            
            return os.path.exists(output_path)

    def _generate_gtts_fallback(self, text: str, output_path: str):
        """
        gTTS 기반 한국어 음성 합성 (폴백).
        """
        tts = gTTS(text=text[:3000], lang='ko', slow=False)
        tts.save(output_path)
        logger.info(f"gTTS 폴백 생성 완료: {output_path}")
