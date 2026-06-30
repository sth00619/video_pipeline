"""
Mock LLM — 주식 콘텐츠 특화 응답.
Phase 1: 더미 데이터, Phase 2: Claude API로 교체.
"""
import json
from app.providers.base import LLMProvider


# 주식 영상 6섹션 더미 콘텐츠
STOCK_SECTIONS = {
    "intro": (
        "안녕하세요, {keyword} 관련해서 가장 많이 받는 질문 한 가지로 시작하겠습니다. "
        "지금 이 시점에 매수해도 될까요, 아니면 조금 더 기다려야 할까요? "
        "오늘 영상에서는 이 질문에 대해 데이터와 시나리오를 바탕으로 명확하게 정리해 드리겠습니다. "
    ),
    "background": (
        "먼저 {keyword}이 지금 왜 이렇게 화두가 되고 있는지, 시장의 큰 흐름부터 살펴보겠습니다. "
        "최근 몇 주간의 거시 경제 상황, 외국인과 기관의 매매 동향, "
        "그리고 글로벌 시장의 흐름이 어떻게 영향을 주고 있는지 단계별로 설명드리겠습니다. "
        "이 배경을 알아야 다음 단계의 데이터 해석이 정확해집니다. "
    ),
    "data": (
        "이제 본격적인 데이터입니다. {keyword}의 최근 주요 지표를 정리해 보겠습니다. "
        "거래량은 어떻게 변하고 있는지, 차트상 중요한 지지선과 저항선은 어디인지, "
        "그리고 동종 업종 대비 상대 강도는 어떠한지 구체적인 숫자로 살펴봅니다. "
        "여기서 중요한 포인트 하나를 꼭 기억해 주세요. "
    ),
    "scenario": (
        "이 데이터를 바탕으로 앞으로 가능한 3가지 시나리오를 정리해 드리겠습니다. "
        "첫째, 상승 시나리오입니다. 어떤 조건이 갖춰지면 상승세가 이어질 수 있는지 살펴봅니다. "
        "둘째, 박스권 시나리오입니다. 일정 구간에서 횡보할 가능성과 그 이유를 분석합니다. "
        "셋째, 하락 시나리오입니다. 어떤 신호가 나타나면 조심해야 하는지 짚어드립니다. "
    ),
    "action": (
        "그렇다면 지금 개인 투자자가 할 수 있는 구체적인 행동은 무엇일까요? "
        "분할 매수 전략, 손절 라인 설정, 비중 조절 방법까지 단계별로 정리해 드리겠습니다. "
        "특히 시장의 변동성이 클 때 흔히 하는 실수와 그 대안도 함께 다룹니다. "
        "이 부분만 잘 적용해도 리스크 관리가 한층 단단해질 수 있습니다. "
    ),
    "conclusion": (
        "오늘 다룬 내용을 핵심만 정리해 드리겠습니다. "
        "{keyword} 관련해서 가장 중요한 포인트 세 가지를 다시 한 번 짚어 드리고, "
        "다음 영상에서 다룰 주제를 살짝 예고해 드리겠습니다. "
        "참고로 본 영상은 작성 시점 기준 정보이며, 투자 권유가 아닌 정보 제공 목적입니다. "
        "최종 판단은 본인의 책임 하에 신중하게 결정하시기 바랍니다. "
        "도움이 되셨다면 구독과 좋아요 부탁드립니다. 다음 영상에서 만나요. "
    ),
}


# 섹션별 분량 비율 (target_chars의 몇 %)
SECTION_WEIGHTS = {
    "intro": 0.10,
    "background": 0.15,
    "data": 0.25,
    "scenario": 0.25,
    "action": 0.15,
    "conclusion": 0.10,
}


class MockLLMProvider(LLMProvider):

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        s = (system_prompt or "").lower()
        u = (user_prompt or "").lower()

        # 쇼츠 하이라이트 (Phase 2)
        if "highlight" in s or "highlight" in u:
            return json.dumps([
                {"text": "이 부분이 핵심 내용입니다.", "reason": "중요 키워드 포함"},
                {"text": "두 번째 하이라이트 구간입니다.", "reason": "시청자 관심 유발"},
                {"text": "마지막 강조 포인트입니다.", "reason": "결론 및 CTA"}
            ])

        # 시놉시스
        if "synopsis" in s or "시놉시스" in u:
            keyword = self._extract_keyword(user_prompt)
            return (
                f"이 영상은 {keyword} 관련한 시장의 현재 상황, 핵심 데이터, 그리고 가능한 시나리오를 정리합니다. "
                f"개인 투자자가 지금 무엇을 점검하고 어떻게 대응하면 좋을지 구체적인 행동 가이드까지 제시합니다."
            )

        # 스크립트 — 섹션 조합 방식
        if "script" in s or "스크립트" in u or "narration" in s:
            keyword = self._extract_keyword(user_prompt)
            target_chars = self._extract_target_chars(user_prompt)
            return self._build_stock_script(keyword, target_chars)

        return "[MOCK] " + user_prompt[:80]

    @staticmethod
    def _extract_keyword(text: str) -> str:
        import re
        m = re.search(r"키워드[:\s]+([^\n]+)", text)
        if m:
            return m.group(1).strip().split('\n')[0]
        return "이 주제"

    @staticmethod
    def _extract_target_chars(text: str) -> int:
        import re
        m = re.search(r"한국어\s*(\d+)\s*자", text)
        if m:
            return int(m.group(1))
        return 6000  # default 20분

    @staticmethod
    def _build_stock_script(keyword: str, target_chars: int) -> str:
        """섹션별 가중치에 맞춰 분량 조정된 주식 영상 스크립트 생성"""
        result = []
        for section, weight in SECTION_WEIGHTS.items():
            target = int(target_chars * weight)
            template = STOCK_SECTIONS[section].format(keyword=keyword)
            section_text = MockLLMProvider._adjust(template, target)
            result.append(section_text)
        return " ".join(result)

    @staticmethod
    def _adjust(text: str, target_len: int) -> str:
        if len(text) >= target_len:
            return text[:target_len]
        # 부족하면 반복
        if not text:
            return ""
        repeats = (target_len // len(text)) + 1
        return (text * repeats)[:target_len]
