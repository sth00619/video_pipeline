"""
Nana Banana AI Image Provider — pollinations.ai 기반

무인증 무료 AI 이미지 생성 엔진.
금융/주식 관련 씬 텍스트를 영문 프롬프트로 변환하여
고품질 일러스트를 생성한다.

비용: $0 (API 키 불필요)
"""
import os
import logging
import urllib.parse
import urllib.request
from pathlib import Path

from app.providers.base import ImageProvider

logger = logging.getLogger(__name__)

# 금융 테마 프롬프트 스타일 수식어
FINANCE_STYLE = (
    "professional financial infographic, dark navy blue background, "
    "neon cyan and gold accents, modern 3D render style, "
    "stock market data visualization, premium quality, "
    "cinematic lighting, 8k resolution, minimalist design"
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
    Pollinations.ai 기반 무료 AI 이미지 생성 프로바이더.
    intro / action / conclusion 씬에 사용.
    """

    def __init__(self):
        self.base_url = "https://image.pollinations.ai/prompt"
        self.width = 1920
        self.height = 1080

    def generate(self, prompt: str, output_path: str, **kwargs) -> str:
        """
        프롬프트를 기반으로 AI 이미지를 생성하여 output_path에 저장.
        
        Args:
            prompt: 씬 텍스트 (한국어 가능, 영문 변환 처리)
            output_path: 저장할 이미지 파일 경로
            **kwargs: section (str), keyword (str) 등 추가 컨텍스트
        
        Returns:
            저장된 이미지 파일 경로
        """
        section = kwargs.get("section", "default")
        keyword = kwargs.get("keyword", "stock market KOSPI")

        # 섹션별 영문 프롬프트 구성
        template = SECTION_PROMPTS.get(section, DEFAULT_PROMPT)
        english_prompt = template.format(keyword=keyword)

        # URL 인코딩
        encoded = urllib.parse.quote(english_prompt)
        url = f"{self.base_url}/{encoded}?width={self.width}&height={self.height}&nologo=true&seed={hash(prompt) % 100000}"

        logger.info(f"NanaBanana 이미지 생성 요청: section={section}, url_len={len(url)}")

        try:
            # 디렉토리 생성
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            # HTTP GET으로 이미지 다운로드
            req = urllib.request.Request(url, headers={
                "User-Agent": "VideoPipeline/1.0"
            })
            with urllib.request.urlopen(req, timeout=30) as response:
                image_data = response.read()

            if len(image_data) < 1000:
                raise ValueError(f"이미지 크기 비정상: {len(image_data)} bytes")

            with open(output_path, "wb") as f:
                f.write(image_data)

            logger.info(f"NanaBanana 이미지 저장 완료: {output_path} ({len(image_data)/1024:.1f}KB)")
            return output_path

        except Exception as e:
            logger.error(f"NanaBanana 이미지 생성 실패: {e}")
            raise
