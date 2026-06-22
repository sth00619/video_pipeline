import json
from app.providers.base import LLMProvider


class MockLLMProvider(LLMProvider):
    """Mock LLM — API 없이 가짜 응답 반환 (흐름 테스트용)"""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if "highlight" in system_prompt.lower() or "highlight" in user_prompt.lower():
            return json.dumps([
                {"text": "이 부분이 핵심 내용입니다.", "reason": "중요 키워드 포함"},
                {"text": "두 번째 하이라이트 구간입니다.", "reason": "시청자 관심 유발"},
                {"text": "마지막 강조 포인트입니다.", "reason": "결론 및 CTA"}
            ])
        if "synopsis" in system_prompt.lower():
            return "이 영상은 AI 기술의 최신 동향을 다루며, 실용적인 활용 방안을 소개합니다."
        if "script" in system_prompt.lower():
            return "안녕하세요! 오늘은 AI 기술에 대해 알아보겠습니다. [MOCK 스크립트]"
        return "[MOCK 응답] " + user_prompt[:100]
