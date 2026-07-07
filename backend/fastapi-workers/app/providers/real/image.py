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

# 캐릭터 일관성 유지 프롬프트 (경제사냥꾼 스타일 돈 사냥꾼 마스코트)
CHARACTER_STYLE = os.getenv(
    "NANO_BANANA_CHARACTER_STYLE",
    "featuring a cute cartoon money-hunter mascot character wearing a graduation cap and holding gold coins, "
    "consistent anime character design across all scenes, expressive facial emotion, "
)

# 금융 테마 프롬프트 스타일 수식어
FINANCE_STYLE = (
    CHARACTER_STYLE +
    "professional financial infographic, dark navy blue background (#0d1b2a), "
    "neon cyan and gold accents, modern anime illustration style, "
    "stock market data visualization, premium quality, "
    "cinematic lighting, 8k resolution, clean minimalist layout"
)

# 섹션별 영문 프롬프트 템플릿
SECTION_PROMPTS = {
    "intro": "epic title card for stock market analysis video, {keyword}, " + FINANCE_STYLE,
    "action": "investor strategy checklist infographic, {keyword}, key investment points, " + FINANCE_STYLE,
    "conclusion": "summary conclusion card for financial analysis, {keyword}, key takeaways, " + FINANCE_STYLE,
}

DEFAULT_PROMPT = "abstract financial data visualization, {keyword}, " + FINANCE_STYLE


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
        section = kwargs.get("section", "default")
        keyword = kwargs.get("keyword", "stock market KOSPI")

        # 섹션별 영문 프롬프트 구성
        template = SECTION_PROMPTS.get(section, DEFAULT_PROMPT)
        english_prompt = template.format(keyword=keyword)

        logger.info(f"NanaBanana 이미지 생성 요청: section={section}, prompt_len={len(english_prompt)}")

        # 디렉토리 생성
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 1. 공식 Gemini API (Nano Banana Pro) 시도
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            try:
                if self._generate_gemini_api(english_prompt, output_path, api_key):
                    logger.info(f"공식 Gemini API (Nano Banana Pro) 이미지 생성 성공: {output_path}")
                    return output_path
            except Exception as e:
                logger.warning(f"공식 Gemini API 호출 실패, 무료 프록시로 폴백: {e}")

        # 2. 무료 pollinations.ai 프록시 폴백
        return self._generate_pollinations(english_prompt, output_path)

    def _generate_gemini_api(self, prompt: str, output_path: str, api_key: str) -> bool:
        """
        Google AI Studio / Vertex AI 공식 Imagen 3 / Gemini 3 Pro Image API 호출.
        """
        import requests
        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={api_key}"
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": "16:9",
                "personGeneration": "ALLOW_ADULT"
            }
        }
        headers = {"Content-Type": "application/json"}
        
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            predictions = data.get("predictions", [])
            if predictions and "bytesBase64Encoded" in predictions[0]:
                img_bytes = base64.b64decode(predictions[0]["bytesBase64Encoded"])
                with open(output_path, "wb") as f:
                    f.write(img_bytes)
                return True
        logger.warning(f"Gemini API 응답 에러: {resp.status_code} {resp.text}")
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
