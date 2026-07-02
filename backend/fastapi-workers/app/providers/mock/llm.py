"""
Mock LLM — 주식 영상 6섹션 고유 콘텐츠 (반복 없음)
각 섹션이 충분한 길이를 가져서 패딩 반복 불필요.
"""
import json
import re
from app.providers.base import LLMProvider


STOCK_SCRIPT_SECTIONS = {
    "intro": [
        "안녕하세요, 오늘 영상에서는 {keyword} 관련해서 가장 많이 받는 질문으로 시작하겠습니다.",
        "지금 이 시점에 매수해도 될까요, 아니면 조금 더 기다려야 할까요?",
        "결론부터 말씀드리면, 지금은 신중한 접근이 필요한 구간입니다.",
        "왜 그런지, 오늘 영상에서 데이터와 시나리오를 바탕으로 명확하게 정리해 드리겠습니다.",
        "영상을 끝까지 보시면 지금 어떤 포지션을 취해야 하는지 감이 잡히실 겁니다.",
        "그럼 바로 시작합니다.",
    ],
    "background": [
        "먼저 {keyword} 관련 시장의 큰 흐름부터 살펴보겠습니다.",
        "최근 몇 주간 거시 경제 환경이 크게 변화하고 있습니다.",
        "미국 연준의 통화 정책 방향, 달러 인덱스 움직임, 그리고 원달러 환율이 핵심 변수입니다.",
        "특히 외국인 투자자의 매매 패턴을 보면 흥미로운 변화가 감지됩니다.",
        "기관 투자자와 외국인의 매수세가 최근 2주간 방향이 엇갈리고 있는데요.",
        "이 부분이 현재 시장의 방향성을 결정하는 가장 중요한 포인트입니다.",
        "글로벌 시장에서도 비슷한 패턴이 관찰됩니다.",
        "유럽 증시와 일본 증시의 최근 흐름도 같이 살펴볼 필요가 있습니다.",
        "이 배경을 알아야 다음 단계의 데이터 해석이 정확해집니다.",
    ],
    "data": [
        "이제 본격적인 데이터를 살펴보겠습니다.",
        "{keyword} 관련 최근 주요 지표를 정리해 보면 몇 가지 눈에 띄는 포인트가 있습니다.",
        "먼저 거래량입니다. 최근 거래량이 20일 평균 대비 상당히 증가한 상태입니다.",
        "이는 시장 참여자들의 관심이 높아지고 있다는 신호입니다.",
        "차트상 중요한 지지선과 저항선을 확인해 보겠습니다.",
        "현재 가격대에서 1차 지지선은 최근 저점 부근이고, 2차 지지선은 60일 이동평균선입니다.",
        "저항선은 최근 고점 부근과 120일 이동평균선이 겹치는 구간입니다.",
        "동종 업종 대비 상대 강도를 보면 현재는 시장 평균을 소폭 상회하고 있습니다.",
        "RSI 지표는 과매수 구간에 근접하고 있어 단기 조정 가능성도 염두에 둬야 합니다.",
        "MACD 지표는 아직 상승 추세를 유지하고 있지만 신호선과의 간격이 좁아지는 중입니다.",
        "펀더멘털 측면에서 보면 PER과 PBR 모두 업종 평균 대비 적정 수준입니다.",
        "실적 컨센서스를 살펴보면 다음 분기 매출은 전년 동기 대비 성장이 예상됩니다.",
        "여기서 핵심 포인트 하나를 반드시 기억하세요. 거래량과 가격의 방향이 일치하는지 여부입니다.",
    ],
    "scenario": [
        "이 데이터를 바탕으로 앞으로 가능한 세 가지 시나리오를 정리합니다.",
        "첫째, 상승 시나리오입니다.",
        "만약 외국인 매수세가 지속되고 거래량이 유지된다면 저항선 돌파 가능성이 있습니다.",
        "이 경우 다음 목표가는 최근 고점 대비 약 5에서 8퍼센트 위 구간으로 예상됩니다.",
        "상승 시나리오의 핵심 조건은 글로벌 증시의 동반 상승과 원달러 환율 안정입니다.",
        "둘째, 박스권 시나리오입니다.",
        "현재 지지선과 저항선 사이에서 횡보하는 구간이 지속될 수 있습니다.",
        "이 경우 단기 트레이딩 전략이 유효하며, 지지선 근처에서 분할 매수를 고려할 수 있습니다.",
        "박스권 기간은 보통 2주에서 4주 정도 지속되는 패턴이 많습니다.",
        "셋째, 하락 시나리오입니다.",
        "만약 지지선이 무너지고 거래량이 급감한다면 추가 하락 가능성이 있습니다.",
        "이 경우 손절 라인을 미리 정해두고 리스크 관리에 집중해야 합니다.",
        "하락 시나리오의 트리거는 예상보다 강한 긴축 정책이나 글로벌 악재 발생입니다.",
        "세 가지 시나리오 각각의 확률을 현재 시점에서 판단하면 상승 40, 박스권 35, 하락 25 정도로 봅니다.",
    ],
    "action": [
        "그렇다면 지금 개인 투자자가 할 수 있는 구체적인 행동은 무엇일까요?",
        "첫째, 분할 매수 전략을 추천드립니다.",
        "한 번에 전액 투자하기보다 3회에서 5회로 나누어 진입하는 것이 안전합니다.",
        "특히 지지선 근처에서 1차 매수, 추가 하락 시 2차 매수를 고려하세요.",
        "둘째, 손절 라인을 반드시 설정하세요.",
        "투자 원금 대비 마이너스 5에서 7퍼센트를 손절 기준으로 잡는 것을 권합니다.",
        "셋째, 포트폴리오 비중을 점검하세요.",
        "한 종목에 전체 자산의 20퍼센트 이상을 배분하는 것은 리스크가 큽니다.",
        "넷째, 시장의 변동성이 클 때 흔히 하는 실수를 피하세요.",
        "공포에 의한 패닉 셀과 탐욕에 의한 추격 매수가 가장 흔한 실수입니다.",
        "다섯째, 다음 주요 이벤트 일정을 확인하세요.",
        "실적 발표, FOMC 회의, 옵션 만기일 등 주요 이벤트 전후로 변동성이 커질 수 있습니다.",
    ],
    "conclusion": [
        "오늘 다룬 내용을 핵심만 정리해 드리겠습니다.",
        "{keyword} 관련해서 가장 중요한 포인트 세 가지입니다.",
        "하나, 현재 시장은 상승과 박스권 사이에서 방향을 탐색하는 구간입니다.",
        "둘, 거래량과 외국인 매매 동향이 방향성의 핵심 신호입니다.",
        "셋, 분할 매수와 손절 라인 설정으로 리스크 관리를 철저히 하세요.",
        "참고로 본 영상은 작성 시점 기준 정보이며, 투자 권유가 아닌 정보 제공 목적입니다.",
        "최종 투자 판단은 본인의 책임 하에 신중하게 결정하시기 바랍니다.",
        "다음 영상에서는 더 깊이 있는 분석을 준비하고 있으니 기대해 주세요.",
        "도움이 되셨다면 구독과 좋아요 부탁드립니다. 다음 영상에서 만나요.",
    ],
}

# 섹션별 분량 비율
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

        if "highlight" in s or "highlight" in u:
            return json.dumps([
                {"text": "이 부분이 핵심 내용입니다.", "reason": "중요 키워드 포함"},
                {"text": "두 번째 하이라이트 구간입니다.", "reason": "시청자 관심 유발"},
                {"text": "마지막 강조 포인트입니다.", "reason": "결론 및 CTA"}
            ])

        if "synopsis" in s or "시놉시스" in u:
            keyword = self._extract_keyword(user_prompt)
            return (
                f"이 영상은 {keyword} 관련한 시장의 현재 상황과 핵심 데이터를 분석합니다. "
                f"상승, 박스권, 하락 세 가지 시나리오를 데이터 근거와 함께 제시하고, "
                f"개인 투자자가 지금 취할 수 있는 구체적인 매매 전략과 리스크 관리 방법을 안내합니다."
            )

        if "script" in s or "스크립트" in u or "narration" in s:
            keyword = self._extract_keyword(user_prompt)
            target_chars = self._extract_target_chars(user_prompt)
            return self._build_stock_script(keyword, target_chars)

        return "[MOCK] " + user_prompt[:80]

    @staticmethod
    def _extract_keyword(text: str) -> str:
        m = re.search(r"키워드[:\s]+([^\n]+)", text)
        if m:
            return m.group(1).strip().split('\n')[0]
        return "이 주제"

    @staticmethod
    def _extract_target_chars(text: str) -> int:
        m = re.search(r"한국어\s*(\d+)\s*자", text)
        if m:
            return int(m.group(1))
        return 6000

    @staticmethod
    def _build_stock_script(keyword: str, target_chars: int) -> str:
        result_parts = []
        for section_name, weight in SECTION_WEIGHTS.items():
            section_target = int(target_chars * weight)
            sentences = STOCK_SCRIPT_SECTIONS.get(section_name, [])
            # 각 문장에 keyword 삽입
            formatted = [s.format(keyword=keyword) for s in sentences]
            section_text = " ".join(formatted)

            # 분량 부족 시 문장 순서대로 반복하되, 변형 추가
            if len(section_text) < section_target:
                extra_needed = section_target - len(section_text)
                extra_sentences = [
                    f"이 부분은 {keyword} 관련해서 특히 주목해야 할 포인트입니다.",
                    f"투자자 입장에서 이 데이터가 왜 중요한지 조금 더 설명드리겠습니다.",
                    f"실제 사례를 보면 이런 패턴이 반복적으로 나타나고 있습니다.",
                    f"전문가들의 의견도 이 부분에서는 대체로 일치하는 편입니다.",
                    f"과거 유사한 상황에서 시장이 어떻게 반응했는지 참고할 필요가 있습니다.",
                    f"이 흐름이 지속될 경우 향후 2주에서 한 달 사이에 변화가 예상됩니다.",
                    f"다만 변수가 많은 구간이므로 포지션 관리에 각별히 신경 쓰셔야 합니다.",
                    f"여기서 놓치면 안 되는 핵심이 하나 더 있습니다.",
                ]
                padding = " ".join(extra_sentences)
                while len(section_text) < section_target:
                    section_text += " " + padding
                section_text = section_text[:section_target]

            result_parts.append(section_text.strip())

        return " ".join(result_parts)
