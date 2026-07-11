"""
Claude LLM Provider — Official Anthropic API

1. 공식 API 연동 (Claude 3.5 Sonnet / Haiku):
   - ANTHROPIC_API_KEY 설정 시 공식 API 호출
   - 경제사냥꾼 스타일 대본 생성 및 팩트체크
"""
import os
import logging
import anthropic

from app.providers.base import LLMProvider

logger = logging.getLogger(__name__)


class ClaudeProvider(LLMProvider):
    """
    Anthropic Claude 공식 API 기반 LLM 프로바이더.
    """

    def __init__(self, model: str = None):
        # 버그 수정: 구형 모델("claude-3-5-sonnet-20241022")이 기본값으로
        # 하드코딩되어 있었습니다. 프로젝트 고정 모델(claude-sonnet-4-6)로 교체.
        from app.config import CLAUDE_MODEL
        self.model = model or CLAUDE_MODEL
        self.api_key = os.getenv("ANTHROPIC_API_KEY")

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """
        Claude API를 호출하여 텍스트 생성.
        """
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY 미설정 → Mock 응답 반환")
            return "## 인트로\n키워드 관련 시장 동향입니다.\n\n## 배경\n최근 주요 금융 기관 보고서에 따르면 성장세가 지속되고 있습니다.\n\n## 결론\n투자 전략 확립이 필요합니다."

        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.model,
                max_tokens=kwargs.get("max_tokens", 4096),
                temperature=kwargs.get("temperature", 0.7),
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Claude API 호출 실패: {e}")
            raise
