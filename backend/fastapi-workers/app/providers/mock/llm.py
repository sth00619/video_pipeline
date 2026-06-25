"""
Mock LLM Provider — API 키 없이 동작
Phase 3 실가동 시 ClaudeProvider 또는 OpenAIProvider로 교체.
"""
import json
from app.providers.base import LLMProvider


class MockLLMProvider(LLMProvider):

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        s = system_prompt.lower()
        u = user_prompt.lower()

        # 쇼츠 하이라이트 (Phase 2)
        if "highlight" in s or "highlight" in u:
            return json.dumps([
                {"text": "이 부분이 핵심 내용입니다.", "reason": "중요 키워드 포함"},
                {"text": "두 번째 하이라이트 구간입니다.", "reason": "시청자 관심 유발"},
                {"text": "마지막 강조 포인트입니다.", "reason": "결론 및 CTA"}
            ])

        # 시놉시스
        if "synopsis" in s or "시놉시스" in u:
            return "이 영상은 시청자가 가장 궁금해하는 핵심을 단계별로 풀어주는 가이드입니다. 흥미로운 도입과 실용적인 본론, 명확한 결론으로 구성됩니다."

        # 스크립트 생성
        if "script" in s or "스크립트" in u or "narration" in s:
            return self._mock_script_for_prompt(user_prompt)

        return "[MOCK 응답] " + user_prompt[:80]

    @staticmethod
    def _mock_script_for_prompt(user_prompt: str) -> str:
        # Mock 스크립트 — 길이는 1000~1500자 정도. 실제 워커가 분량 보정.
        return (
            "안녕하세요, 오늘 영상에서는 여러분이 가장 궁금해하셨던 주제를 깊이 있게 다뤄보겠습니다. "
            "먼저 이 주제가 왜 중요한지, 어떤 배경에서 등장했는지부터 차근차근 살펴볼게요. "
            "많은 분들이 처음 접할 때 막막하다고 느끼시는데요, 사실 핵심 원리만 이해하면 어렵지 않습니다. "
            "두 번째로, 실제로 어떻게 적용할 수 있는지 구체적인 예시와 함께 단계별로 설명드리겠습니다. "
            "여기서는 자주 하는 실수와 그 해결책도 같이 정리해 드릴게요. "
            "세 번째로, 한 단계 더 나아가고 싶은 분들을 위한 심화 팁을 공유합니다. "
            "이 부분만 잘 활용해도 다른 분들과 큰 차이를 만들 수 있습니다. "
            "네 번째로, 자주 묻는 질문들을 모아서 한 번에 답변드리겠습니다. "
            "혹시 영상에서 다루지 않은 궁금한 점이 있다면 댓글로 남겨주세요. 적극적으로 답변드리겠습니다. "
            "마지막으로 오늘 다룬 내용을 핵심만 빠르게 정리해드리고, 다음 영상에서 다룰 주제를 살짝 예고해 드릴게요. "
            "끝까지 시청해 주셔서 감사하고, 도움이 되셨다면 구독과 좋아요 부탁드립니다. 다음 영상에서 만나요."
        ) * 6  # 약 6배 반복으로 6000자 근처
