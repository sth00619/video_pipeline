"""
스크립트 생성 워커 v3 — 3-Round 팩트체크 + 실데이터 기반

핵심 변경:
  v2: Claude 1-shot 스크립트 생성
  v3: 실제 시장 데이터를 컨텍스트로 제공 + Claude Extended Thinking (프롬프트 CoT)
      3-Round 팩트체크 파이프라인:
        Round 1 — 시장 데이터에서 핵심 사실 5개 추출
        Round 2 — 교차 검증 (수치 일관성, 상충 데이터 탐지)
        Round 3 — 최종 검증된 사실 JSON 확정
      최종 스크립트: 검증된 사실의 수치만 사용, 창작 금지

Claude 설정:
  모델: claude-3-5-sonnet-20241022
  Extended Thinking: 프롬프트 상의 Chain-of-Thought로 구현 (Unexpected keyword error 방지)
"""
import os
import re
import json
import logging
from typing import Optional

from app.workers.market_data_collector import MarketDataCollector

logger = logging.getLogger(__name__)

CATEGORY_LABELS = {
    "KOSPI": "코스피(한국 종합주가지수)",
    "KOSDAQ": "코스닥",
    "US_STOCKS": "미국 주식(나스닥/S&P500)",
    "INDIVIDUAL_STOCK": "개별 종목",
    "GLOBAL_MACRO": "글로벌 매크로 경제",
    "CRYPTO": "암호화폐",
    "CUSTOM": "주식시장 전반",
}

SECTION_NAMES = ["인트로", "시장 배경", "핵심 데이터", "시나리오 분석", "실행 가이드", "결론"]

# ── 팩트체크용 시스템 프롬프트 ────────────────────────────────
FACT_CHECK_SYSTEM_PROMPT = """당신은 한국 주식 시장 전문 팩트체커입니다.

역할:
- 수집된 실제 시장 데이터를 바탕으로 사실을 검증합니다
- 데이터에 없는 수치는 절대 만들어내지 않습니다
- 불확실한 내용은 "데이터 부족"으로 명시합니다
- 수치의 논리적 일관성을 검토합니다 (예: 하락장인데 외국인 대규모 매수는 확인 필요)

절대 금지:
- 제공된 데이터에 없는 구체적 수치(지수값, %, 금액 등) 창작
- 추측을 사실인 것처럼 표현
- 모호한 표현으로 검증을 회피"""

# ── 스크립트 생성용 시스템 프롬프트 ─────────────────────────────
SCRIPT_SYSTEM_PROMPT = """당신은 한국의 인기 경제 유튜브 채널 "경제사냥꾼" 스타일의 대본 작가입니다.

작성 원칙:
- 친근하지만 전문적인 톤 (반말 아닌 존댓말, "~습니다/~해요" 혼용)
- <verified_facts>의 수치만 사용, 목록에 없는 구체적 수치는 절대 창작 금지
- 수치를 자연스럽게 구어체로 표현: "코스피가 2,783포인트를 기록했습니다"
- 각 섹션은 자연스럽게 다음 섹션으로 연결
- 과장된 클릭베이트 표현 지양, 신뢰도 있는 분석 어조
- 시청자에게 직접 말하는 듯한 구어체 (예: "여러분", "지금 보시는 것처럼")
- 투자 조언이 아닌 정보 제공 관점 유지
- 한국어 맞춤법과 표준 띄어쓰기 규정을 철저히 준수하여 가독성이 높고 자연스러운 문장이 되도록 하세요. (조사나 어미의 잘못된 띄어쓰기 금지)

🎯 자막 최적화 (가장 중요):
- 문장은 반드시 짧게 끊어서 작성하세요 (1문장 = 15자 이내가 이상적)
- 긴 설명은 여러 짧은 문장으로 분리하세요
  좋은 예: "코스피가 올랐어요. 무려 40포인트나요. 정말 놀라운 상승이죠."
  나쁜 예: "코스피가 40포인트나 상승하면서 투자자들의 관심이 집중되고 있습니다."
- 각 문장은 반드시 마침표(.), 요, 다, 죠, 네 등으로 명확히 종결하세요
- 숫자와 기호는 읽기 쉽도록 아라비아 숫자와 표준 기호로 작성하세요: 예) 2,783포인트, 1.2%, 2억 5,800만 주 (소리 나는 대로 '이천칠백...' 표기 절대 금지)
- 문장 중간에 쉼표로 끊지 말고, 마침표로 완전히 종결하세요

절대 금지사항:
- 확정적 미래 예측 ("반드시 오릅니다" 등) 금지
- 특정 종목에 대한 직접적인 매수/매도 지시 금지
- <verified_facts>에 없는 수치나 날짜 창작 금지"""


class ScriptWorker:

    def __init__(self):
        self.collector = MarketDataCollector()

    def generate(self, keyword: str, category: str, target_minutes: int,
                 market_data: Optional[dict] = None, job_id: int = 0) -> dict:
        category_label = CATEGORY_LABELS.get(category, "주식시장")
        target_chars = target_minutes * 300  # 한국어 분당 300자 기준

        logger.info(f"스크립트 생성 v3: job_id={job_id}, keyword={keyword}, "
                    f"category={category}, target={target_minutes}분")

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY 미설정 — Mock 스크립트로 폴백")
            return self._mock_generate(keyword, category_label, target_minutes, job_id)

        # 시장 데이터 수집 (전달받지 못한 경우)
        if not market_data:
            try:
                market_data = self.collector.collect_for_category(category, keyword)
                logger.info("시장 데이터 직접 수집 완료")
            except Exception as e:
                logger.warning(f"시장 데이터 수집 실패: {e} — 데이터 없이 진행")
                market_data = {}

        try:
            # 3-Round 팩트체크
            verified_facts, fact_check_log = self._multi_round_fact_check(
                keyword, category_label, market_data, api_key
            )

            # 검증된 사실 기반 스크립트 생성
            script_text, sections = self._generate_with_verified_facts(
                keyword, category_label, target_minutes, target_chars,
                verified_facts, market_data, api_key
            )
            used_real_llm = True

        except Exception as e:
            logger.error(f"Claude API 호출 실패: {e} — Mock으로 폴백")
            script_text, sections = self._mock_script(keyword, category_label, target_minutes)
            verified_facts = []
            fact_check_log = [f"오류: {str(e)}"]
            used_real_llm = False

        logger.info(f"스크립트 생성 완료: {len(script_text)}자, "
                    f"검증사실={len(verified_facts)}개, real_llm={used_real_llm}")

        return {
            "job_id": job_id,
            "keyword": keyword,
            "script": script_text,
            "sections": sections,
            "char_count": len(script_text),
            "verified_facts": verified_facts,
            "fact_check_rounds": 3,
            "fact_check_log": fact_check_log,
            "market_snapshot_used": bool(market_data),
            "used_real_llm": used_real_llm,
        }

    # ──────────────────────────────────────────────────────────
    # 3-Round 팩트체크 파이프라인
    # ──────────────────────────────────────────────────────────
    def _multi_round_fact_check(self, keyword: str, category_label: str,
                                 market_data: dict, api_key: str) -> tuple[list, list]:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        messages = []
        fact_check_log = []

        market_json = json.dumps(market_data, ensure_ascii=False, indent=2)

        # ── Round 1: 핵심 사실 추출 ──
        logger.info("팩트체크 Round 1: 핵심 사실 추출")

        r1_content = f"""<market_data>
{market_json}
</market_data>

<task>
위 실제 시장 데이터에서 '{keyword}' 관련 핵심 사실 5개를 추출하세요.

규칙:
1. 반드시 market_data에 존재하는 실제 수치(숫자, %)만 사용
2. 데이터에 없는 수치는 절대 포함하지 마세요
3. 각 사실에 출처 필드명 명시 (예: kr.index.kospi.close)
4. 불확실하거나 애매한 내용은 제외

먼저 생각을 정리한 후, 다음 형식으로 번호와 사실을 작성하세요.
형식: 번호. [출처] 사실 내용 (수치 포함)
</task>"""

        r1 = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4000,
            system=FACT_CHECK_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": r1_content}],
        )
        messages.append({"role": "user", "content": r1_content})
        messages.append({"role": "assistant", "content": r1.content})
        fact_check_log.append(f"Round 1 완료: {len(r1.content)}자")
        logger.info("팩트체크 Round 1 완료")

        # ── Round 2: 교차 검증 ──────
        logger.info("팩트체크 Round 2: 교차 검증")

        r2_content = """위 Round 1에서 추출한 5가지 사실을 비판적으로 검토하세요:

검토 항목:
1. 각 수치가 원본 market_data와 정확히 일치하는가?
2. 서로 상충되거나 논리적으로 이상한 데이터가 있는가?
   (예: 코스피가 크게 하락했는데 외국인이 대규모 순매수? → 실제 일어날 수 있지만 명확히 언급)
3. 수치의 단위가 올바른가? (예: 억원 vs 만원, pt vs %)
4. 시간적으로 맞는 데이터인가? (당일 데이터인지 확인)

제거하거나 수정해야 할 사실이 있으면 구체적으로 지적하고,
수정된 최종 사실 목록을 다시 작성하세요."""

        messages.append({"role": "user", "content": r2_content})
        r2 = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=3000,
            system=FACT_CHECK_SYSTEM_PROMPT,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": r2.content})
        fact_check_log.append(f"Round 2 완료: {len(r2.content)}자")
        logger.info("팩트체크 Round 2 완료")

        # ── Round 3: 최종 검증 사실 JSON 확정 ─────────────────
        logger.info("팩트체크 Round 3: JSON 최종 확정")

        r3_content = """검토 결과를 반영하여, 최종 검증된 사실 목록을 아래 JSON 형식으로만 출력하세요.
confidence가 0.7 미만이거나 데이터 출처가 불명확한 항목은 제외하세요.

```json
[
  {
    "fact": "사실 내용 (한국어, 구체적 수치 포함)",
    "figure": "핵심 수치 (예: 2,783.5pt, +1.2%, +3,200억원)",
    "source_field": "market_data 내 경로 (예: kr.index.kospi.close)",
    "confidence": 0.0~1.0
  }
]
```

JSON 코드블록 안에만 내용을 넣으세요. 다른 설명은 불필요합니다."""

        messages.append({"role": "user", "content": r3_content})
        r3 = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2000,
            system=FACT_CHECK_SYSTEM_PROMPT,
            messages=messages,
        )
        fact_check_log.append("Round 3 완료")
        logger.info("팩트체크 Round 3 완료")

        # JSON 파싱
        verified_facts = self._parse_verified_facts(r3.content)
        logger.info(f"검증된 사실 {len(verified_facts)}개 확정")

        return verified_facts, fact_check_log

    # ──────────────────────────────────────────────────────────
    # 검증된 사실 기반 스크립트 생성
    # ──────────────────────────────────────────────────────────
    def _generate_with_verified_facts(self, keyword: str, category_label: str,
                                       target_minutes: int, target_chars: int,
                                       verified_facts: list, market_data: dict,
                                       api_key: str) -> tuple[str, list]:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)

        facts_text = "\n".join(
            f"- {f['fact']} (수치: {f.get('figure', 'N/A')}, 신뢰도: {f.get('confidence', 0):.1f})"
            for f in verified_facts
        ) if verified_facts else "데이터 수집 불완전 — 일반적 시장 분석으로 대체"

        # 시장 요약
        market_summary = _build_market_summary_for_script(market_data)

        user_prompt = f"""<verified_facts>
{facts_text}
</verified_facts>

<market_context>
{market_summary}
</market_context>

<constraints>
- 위 verified_facts에 있는 수치만 사용하세요
- 목록에 없는 구체적 수치(지수값, %, 금액 등)는 절대 창작하지 마세요
- 불확실한 수치가 필요한 경우 "관련 지표를 개별적으로 확인하시기 바랍니다"로 대체
</constraints>

다음 조건으로 한국어 주식 유튜브 대본을 작성해주세요:
카테고리: {category_label}
핵심 키워드/주제: {keyword}
목표 분량: 약 {target_chars}자 (약 {target_minutes}분 분량)

구조 (6개 섹션, 각 섹션 앞에 "## 섹션명"으로 표시):
## 인트로
시청자의 관심을 끄는 도입부. 오늘 실제 시장 상황을 언급하며 핵심 질문 제시.

## 시장 배경
verified_facts 기반으로 오늘 {category_label} 시장 상황 설명.

## 핵심 데이터
verified_facts의 구체적인 수치와 지표를 자연스러운 구어체로 전달.

## 시나리오 분석
실제 데이터를 근거로 상승/하락 시나리오를 균형있게 제시.

## 실행 가이드
투자자가 참고할 수 있는 체크포인트 (매수/매도 권유 아닌 관찰 포인트).

## 결론
핵심 3가지 요약 및 다음 영상 예고."""

        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=8000,
            system=SCRIPT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        full_text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )

        sections = _parse_sections(full_text)
        clean_text = full_text.strip()
        clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)

        return clean_text, sections

    # ──────────────────────────────────────────────────────────
    # Mock 폴백 (기존 유지)
    # ──────────────────────────────────────────────────────────
    def _mock_generate(self, keyword, category_label, target_minutes, job_id):
        script_text, sections = self._mock_script(keyword, category_label, target_minutes)
        return {
            "job_id": job_id,
            "keyword": keyword,
            "script": script_text,
            "sections": sections,
            "char_count": len(script_text),
            "verified_facts": [],
            "fact_check_rounds": 0,
            "fact_check_log": ["ANTHROPIC_API_KEY 미설정 — Mock 모드"],
            "market_snapshot_used": False,
            "used_real_llm": False,
        }

    def _mock_script(self, keyword, category_label, target_minutes):
        chars_per_section = (target_minutes * 300) // 6
        templates = [
            (f"안녕하세요, 여러분! 오늘은 '{keyword}'에 대해 깊이 있게 살펴보겠습니다. "
             f"{category_label} 시장에서 최근 가장 화제가 되고 있는 이슈인데요, "
             f"끝까지 보시면 투자 판단에 도움이 되실 겁니다."),
            (f"먼저 {category_label} 시장의 최근 흐름을 짚어보겠습니다. "
             f"최근 며칠간 변동성이 확대되면서 투자자들의 관심이 집중되고 있습니다."),
            (f"핵심 데이터를 살펴보면, 외국인과 기관의 매매 동향이 엇갈리고 있습니다. "
             f"거래량 또한 평소 대비 증가하는 모습을 보이고 있습니다."),
            (f"이제 두 가지 시나리오를 생각해볼 수 있습니다. "
             f"첫 번째는 상승 시나리오, 두 번째는 하락 시나리오입니다."),
            (f"투자자분들이 참고하실 체크포인트를 정리해드립니다. "
             f"매수나 매도를 권유하는 것이 아니라, 관찰해야 할 지표를 말씀드리는 것입니다."),
            (f"오늘 내용을 3가지로 정리하면, 첫째 시장 변동성 확대, 둘째 데이터 기반 판단의 중요성, "
             f"셋째 리스크 관리입니다. 다음 영상에서 더 자세히 다뤄보겠습니다."),
        ]
        sections = []
        for name, content in zip(SECTION_NAMES, templates):
            padded = (content + " ") * max(1, chars_per_section // max(len(content), 1))
            sections.append({
                "title": name,
                "content": padded[:chars_per_section],
                "char_count": chars_per_section,
            })
        full_script = "\n\n".join(s["content"] for s in sections)
        return full_script, sections

    def _parse_verified_facts(self, content_blocks) -> list:
        """Claude 응답에서 JSON 배열 파싱"""
        text = ""
        # content_blocks가 list 형태(response.content)이거나 단일 텍스트(string)일 수 있으므로 처리
        if isinstance(content_blocks, str):
            text = content_blocks
        elif isinstance(content_blocks, list):
            for block in content_blocks:
                if hasattr(block, "text"):
                    text += block.text
                elif isinstance(block, str):
                    text += block
                elif hasattr(block, "get"):
                    text += block.get("text", "")
        else:
            text = str(content_blocks)

        try:
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
            if json_match:
                return json.loads(json_match.group(1).strip())
            # 코드블록 없이 배열만 있는 경우
            arr_match = re.search(r'\[[\s\S]*\]', text)
            if arr_match:
                return json.loads(arr_match.group())
        except Exception as e:
            logger.warning(f"verified_facts JSON 파싱 실패: {e}")
        return []


# ──────────────────────────────────────────────────────────
# 유틸 함수
# ──────────────────────────────────────────────────────────
def _parse_sections(full_text: str) -> list:
    """## 섹션명 기준으로 분리"""
    parts = re.split(r'^##\s*(.+)$', full_text, flags=re.MULTILINE)
    sections = []
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            title = parts[i].strip()
            content = parts[i + 1].strip()
            sections.append({"title": title, "content": content, "char_count": len(content)})
    return sections


def _count_text(content_blocks) -> int:
    """응답 블록에서 텍스트 총 길이"""
    if isinstance(content_blocks, str):
        return len(content_blocks)
    total = 0
    if isinstance(content_blocks, list):
        for block in content_blocks:
            if hasattr(block, "text"):
                total += len(block.text)
            elif isinstance(block, str):
                total += len(block)
    return total


def _build_market_summary_for_script(market_data: dict) -> str:
    """스크립트 생성용 시장 요약 (더 상세)"""
    lines = []
    kr = market_data.get("kr")
    if kr:
        idx = kr.get("index", {})
        kospi = idx.get("kospi")
        if kospi:
            dir_str = "상승" if kospi["change_pct"] > 0 else "하락"
            lines.append(f"코스피 지수: {kospi['close']:,.1f}pt "
                         f"(전일 대비 {dir_str} {abs(kospi['change_pct']):.2f}%)")
        kosdaq = idx.get("kosdaq")
        if kosdaq:
            dir_str = "상승" if kosdaq["change_pct"] > 0 else "하락"
            lines.append(f"코스닥 지수: {kosdaq['close']:,.1f}pt "
                         f"(전일 대비 {dir_str} {abs(kosdaq['change_pct']):.2f}%)")
        sd = kr.get("supply_demand", {}).get("kospi", {})
        if sd.get("foreign_net_buy"):
            lines.append(f"외국인 코스피 순매수: {sd['foreign_net_buy']}")
        if sd.get("institution_net_buy"):
            lines.append(f"기관 코스피 순매수: {sd['institution_net_buy']}")
        mi = kr.get("market_indicators", {})
        if mi.get("usd_krw"):
            lines.append(f"달러/원 환율: {mi['usd_krw']:,.1f}원")
        tops = kr.get("top_stocks", [])
        if tops:
            lines.append(f"시가총액 상위 종목: {', '.join(t['name'] for t in tops[:5])}")

    us = market_data.get("us")
    if us:
        idx = us.get("index", {})
        for name, label in [("sp500", "S&P500"), ("nasdaq", "나스닥"), ("vix", "VIX")]:
            d = idx.get(name)
            if d:
                dir_str = "상승" if d["change_pct"] > 0 else "하락"
                lines.append(f"{label}: {d['close']:,.2f} "
                             f"(전일 대비 {dir_str} {abs(d['change_pct']):.2f}%)")
        macro = us.get("macro", {})
        if macro.get("fed_rate"):
            lines.append(f"연준 기준금리: {macro['fed_rate']:.2f}%")
        if macro.get("cpi"):
            lines.append(f"미국 CPI(전월): {macro['cpi']:.1f}")
        if macro.get("unemployment"):
            lines.append(f"미국 실업률: {macro['unemployment']:.1f}%")
        if macro.get("us_10yr_yield"):
            lines.append(f"미국 10년 국채 금리: {macro['us_10yr_yield']:.2f}%")

    return "\n".join(lines) if lines else "시장 데이터 없음 — 일반적 시장 분석으로 대체"
