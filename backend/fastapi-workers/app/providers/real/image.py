"""
Nana Banana AI Image Provider — Official Gemini API + pollinations.ai fallback

1. 공식 API 연동 (Nano Banana Pro / Gemini 3 Pro Image):
   - GEMINI_API_KEY 또는 GOOGLE_API_KEY 설정 시 공식 Google AI Studio API 사용
   - 비동기 Batch 및 고화질 16:9 (1920x1080) 원본 지원
   
2. 캐릭터 일관성 유지 (Reference Prompting):
   - 경제사냥꾼 스타일의 '돈 사냥꾼 마스코트 캐릭터' 프롬프트를 모든 씬에 주입
   - 씬마다 표정과 동작만 바뀌며 동일 캐릭터가 계속 등장하도록 연출
   
3. 무료 폴백 엔진:
   - API 키 미설정 시 기존 pollinations.ai 무료 프록시로 자동 폴백 ($0)
"""
import os
import json
import base64
import logging
import urllib.parse
import urllib.request
from pathlib import Path

from app.providers.base import ImageProvider

logger = logging.getLogger(__name__)

# 캐릭터 일관성 유지 프롬프트 (의인화된 금색 코인 마스코트 캐릭터)
CHARACTER_STYLE = (
    "featuring a cute gold coin mascot character, chibi cartoon style, round shiny gold coin with face, arms and legs, "
    "wearing small navy business suit with gold tie, "
)

# 금융 테마 프롬프트 스타일 수식어
FINANCE_STYLE = (
    "professional financial news studio background, dark navy blue background (#0d1b2a), "
    "3D render, smooth shading, anime cartoon style, high-quality, cinematic lighting"
)


class NanaBananaProvider(ImageProvider):
    """
    Nano Banana Pro (Google Gemini API) 및 pollinations.ai 기반 이미지 생성 프로바이더.
    """

    def __init__(self):
        self.fallback_url = "https://image.pollinations.ai/prompt"
        self.width = 1920
        self.height = 1080

    def generate_image(self, prompt: str, output_path: str, **kwargs) -> str:
        """images_worker.py에서 호출하는 메서드 별칭"""
        return self.generate(prompt=prompt, output_path=output_path, **kwargs)

    def generate(self, prompt: str, output_path: str, **kwargs) -> str:
        """
        프롬프트를 기반으로 AI 이미지를 생성하여 output_path에 저장.
        """
        # 캐릭터 스타일 프롬프트 결정
        char_style = kwargs.get("character_style_prompt")
        if char_style == "none" or char_style == "disable":
            char_prompt = ""
        elif char_style:
            char_prompt = char_style
        else:
            char_prompt = CHARACTER_STYLE

        # 만약 프롬프트가 한글이거나 너무 짧다면 키워드/섹션을 기반으로 구성
        is_english = all(ord(c) < 128 for c in prompt.replace(" ", "").replace(",", "").replace(".", ""))
        
        if not is_english or len(prompt) < 30:
            section = kwargs.get("section", "default")
            keyword = kwargs.get("keyword", "stock market KOSPI")
            base_prompt = f"A scene representing {keyword} and {section}. " + char_prompt + FINANCE_STYLE
        else:
            base_prompt = prompt
            # 만약 스타일 관련 키워드가 부족하다면 추가 주입
            if char_prompt and "banknote" not in base_prompt.lower() and "coin" not in base_prompt.lower():
                base_prompt = char_prompt + base_prompt
            if "vector" not in base_prompt.lower() and "cartoon" not in base_prompt.lower():
                base_prompt = base_prompt + ", " + FINANCE_STYLE

        logger.info(f"NanaBanana 이미지 생성 요청: prompt_len={len(base_prompt)}")

        # 디렉토리 생성
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 1. 공식 Gemini API (Nano Banana Pro) 시도
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            try:
                character_image_path = kwargs.get("character_image_path")
                if self._generate_gemini_api(base_prompt, output_path, api_key, character_image_path):
                    logger.info(f"공식 Gemini API (Nano Banana Pro) 이미지 생성 성공: {output_path}")
                    return output_path
            except Exception as e:
                logger.warning(f"공식 Gemini API 호출 실패, 무료 프록시로 폴백: {e}")

        # 2. 무료 pollinations.ai 프록시 폴백
        return self._generate_pollinations(base_prompt, output_path)

    def _generate_gemini_api(self, prompt: str, output_path: str, api_key: str, character_image_path: str = None) -> bool:
        """
        Google AI Studio 공식 gemini-3.1-flash-image API 호출 (429 Rate Limit 대응 재시도 탑재).
        """
        import requests
        import time
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image:generateContent?key={api_key}"
        
        parts = [{"text": prompt}]
        if character_image_path and os.path.exists(character_image_path):
            try:
                with open(character_image_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                mime = "image/png" if character_image_path.lower().endswith(".png") else "image/jpeg"
                parts.insert(0, {
                    "inlineData": {
                        "mimeType": mime,
                        "data": img_b64
                    }
                })
                logger.info(f"Gemini API 요청에 캐릭터 레퍼런스 이미지 추가 완료: {character_image_path}")
            except Exception as e:
                logger.warning(f"캐릭터 레퍼런스 이미지 로드/인코딩 실패: {e}")

        payload = {
            "contents": [
                {
                    "parts": parts
                }
            ],
            "generationConfig": {
                "responseModalities": ["IMAGE"]
            }
        }
        headers = {"Content-Type": "application/json"}
        
        # Free Tier Rate Limit (2 RPM) 대응: 최대 5회 재시도 (매번 35초 대기)
        MAX_ATTEMPTS = 5
        for attempt in range(MAX_ATTEMPTS):
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                try:
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            inline_data = parts[0].get("inlineData", {})
                            if inline_data and "data" in inline_data:
                                img_bytes = base64.b64decode(inline_data["data"])
                                with open(output_path, "wb") as f:
                                    f.write(img_bytes)
                                return True
                except Exception as e:
                    logger.error(f"Gemini API 응답 파싱 에러: {e}")
                    return False
            elif resp.status_code == 429:
                wait_time = 35
                logger.warning(f"Gemini API 할당량 초과(429) 감지. {wait_time}초 후 재시도합니다. (시도 {attempt + 1}/{MAX_ATTEMPTS})")
                time.sleep(wait_time)
            else:
                logger.warning(f"Gemini API HTTP 에러 ({resp.status_code}): {resp.text}")
                return False
                
        logger.error(f"Gemini API 재시도 횟수 초과로 이미지 생성 실패: {prompt[:40]}...")
        return False

    def _generate_pollinations(self, prompt: str, output_path: str) -> str:
        """
        Pollinations.ai 기반 무료 AI 이미지 생성 (폴백).
        """
        encoded = urllib.parse.quote(prompt)
        url = f"{self.fallback_url}/{encoded}?width={self.width}&height={self.height}&nologo=true&seed={hash(prompt) % 100000}"

        req = urllib.request.Request(url, headers={
            "User-Agent": "VideoPipeline/1.0"
        })
        with urllib.request.urlopen(req, timeout=30) as response:
            image_data = response.read()

        if len(image_data) < 1000:
            raise ValueError(f"이미지 크기 비정상: {len(image_data)} bytes")

        with open(output_path, "wb") as f:
            f.write(image_data)

        logger.info(f"NanaBanana(Pollinations) 이미지 저장 완료: {output_path} ({len(image_data)/1024:.1f}KB)")
        return output_path
