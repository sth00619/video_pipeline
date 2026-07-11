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
  모델: claude-sonnet-4-6
  Extended Thinking: 프롬프트 상의 Chain-of-Thought로 구현 (Unexpected keyword error 방지)
"""
import os
import re
import json
import logging
from typing import Optional

from app.workers.market_data_collector import MarketDataCollector
from app.config import CLAUDE_MODEL

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

# images_worker.py의 _render_section() 딕셔너리 키와 동일한 영문 키.
# [버그 수정] 예전에는 이 씬 목록에 "section" 키가 아예 없어서, AI 이미지
# 생성이 실패했을 때 쓰이는 matplotlib 폴백 렌더러가 scene.get("section", ...)
# 기본값(f"scene_{i}")으로만 빠지고, 결국 항상 _render_line_chart로만
# 렌더링되고 있었습니다 (intro/data/scenario/action/conclusion 다양성이
# 폴백 상황에서는 실질적으로 죽어 있었음). 이제 씬 순서에 따라 실제로
# 6종 중 하나를 배정합니다.
SECTION_TYPES = ["intro", "background", "data", "scenario", "action", "conclusion"]


def _assign_section_type(index: int, total: int) -> str:
    if total <= 1:
        return SECTION_TYPES[0]
    ratio = index / max(total - 1, 1)
    bucket = min(int(ratio * len(SECTION_TYPES)), len(SECTION_TYPES) - 1)
    return SECTION_TYPES[bucket]
# ── 팩트체크용 시스템 프롬프트 ────────────────────────────────
FACT_CHECK_SYSTEM_PROMPT = """당신은 한국 주식 시장 및 글로벌 매크로/국제정세 전문 팩트체커입니다.

역할:
- 수집된 실제 시장 데이터, 뉴스 기사, 국제 정세 정보 등을 바탕으로 사실을 검증합니다
- 데이터에 없는 내용이나 수치는 절대 만들어내지 않습니다
- 불확실한 내용은 제외합니다
- 수치와 기사의 출처 및 논리적 일관성을 철저하게 검증합니다

절대 금지:
- 제공된 데이터에 없는 구체적 수치, 기사 제목, 정세 팩트 등 정보 창작
- 추측을 사실인 것처럼 표현
- 모호한 표현으로 검증을 회피"""

# ── 스크립트 생성용 시스템 프롬프트 ─────────────────────────────
SCRIPT_SYSTEM_PROMPT = """당신은 한국의 인기 경제 유튜브 채널 "경제사냥꾼" 스타일의 대본 작가입니다.

작성 원칙:
- 친근하지만 전문적인 톤 (반말 아닌 존댓말, "~습니다/~해요" 혼용)
- <verified_facts>의 수치만 사용, 목록에 없는 구체적 수치는 절대 창작 금지
- 수치를 자연스럽게 구어체로 표현: "코스닥이 785포인트를 기록했습니다"
- 각 씬은 자연스럽게 다음 씬으로 연결
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

🎯 씬 구성 규칙:
- 대본은 반드시 ## 씬 [번호]: [제목] 형식의 헤더로 구분해주세요.
- 각 헤더 아래에는 실제 한국어로 낭독할 대사 텍스트만 바로 작성하세요.
- [대사]나 [비주얼]과 같은 태그는 절대 포함하지 마십시오.

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
        # 한국어 TTS 1.3x 배속 기준 분당 약 610자 (원본 470자 × 1.3 = 611자)
        target_chars = target_minutes * 610  # 1.3x 배속 기준 실제 독해 속도

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
위 실제 시장 데이터에서 '{keyword}' 관련 핵심 사실들을 가능한 많이 추출하세요. (개수에 한정을 두지 마십시오)

규칙:
1. 단순 지수나 거래대금 같은 수치 정보뿐만 아니라, 뉴스 기사 정보, 글로벌 매크로 동향, 국제 정세 및 정책 정보 등 모든 신뢰성 있는 정보를 포함하세요.
2. 반드시 market_data에 명시되어 존재하는 내용만 사용하고, 데이터에 없는 정보나 추측성 수치는 절대 포함하지 마세요.
3. 각 사실에 데이터 내 출처 필드명이나 노드 경로를 명시하세요.
4. 불확실하거나 애매한 내용은 배제하고 확실한 사실만 기술하세요.

먼저 생각을 정리한 후, 다음 형식으로 번호와 사실을 작성하세요.
형식: 번호. [출처] 사실 내용 (구체적 수치, 기사 제목, 정세 팩트 포함)
</task>"""

        r1 = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            system=FACT_CHECK_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": r1_content}],
        )
        messages.append({"role": "user", "content": r1_content})
        messages.append({"role": "assistant", "content": r1.content})
        fact_check_log.append(f"Round 1 완료: {_count_text(r1.content)}자")
        logger.info("팩트체크 Round 1 완료")

        # ── Round 2: 교차 검증 ──────
        logger.info("팩트체크 Round 2: 교차 검증")

        r2_content = """위 Round 1에서 추출한 사실들을 비판적으로 검토하세요:

검토 항목:
1. 각 내용이 원본 market_data와 정확히 일치하며 날조가 없는가?
2. 수치(단위 포함), 기사 내용, 국제 정세 팩트가 데이터와 정확히 매칭되는가?
3. 서로 상충되거나 사실 여부가 불명확한 내용이 있는가?
4. 시간적으로 최신 데이터가 맞는가?

제거하거나 수정해야 할 사실이 있으면 구체적으로 지적하고, 검증에 통과한 최종 사실 목록을 다시 작성하세요."""

        messages.append({"role": "user", "content": r2_content})
        r2 = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=3000,
            system=FACT_CHECK_SYSTEM_PROMPT,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": r2.content})
        fact_check_log.append(f"Round 2 완료: {_count_text(r2.content)}자")
        logger.info("팩트체크 Round 2 완료")

        # ── Round 3: 최종 검증 사실 JSON 확정 ─────────────────
        logger.info("팩트체크 Round 3: JSON 최종 확정")
        r3_content = """검토 결과를 반영하여, 최종 검증된 사실 목록을 아래 JSON 형식으로만 출력하세요.
신뢰도(confidence)가 0.9 미만이거나 데이터 출처가 불명확한 항목은 반드시 제외하세요. (0.9 이상의 높은 신뢰성을 가진 데이터만 포함)
단, 너무 사소한 정보까지 나열하면 토큰 제한으로 도중에 잘릴 수 있으니 가장 핵심적인 매크로 수치, 지표, 중요 뉴스 등 위주로 최대 15개까지만 엄선하여 JSON 배열로 만드세요.

```json
[
  {
    "fact": "사실 내용 (한국어, 수치/뉴스/정세 관련 구체적 정보 포함)",
    "figure": "핵심 정보/수치 (예: 2,783.5pt, +1.2%, +3,200억원, 또는 핵심 뉴스 키워드)",
    "source_field": "market_data 내 경로 (예: kr.index.kospi.close, 또는 news.titles)",
    "confidence": 0.9~1.0
  }
]
```

JSON 코드블록 안에만 내용을 넣으세요. 다른 설명은 불필요합니다."""

        messages.append({"role": "user", "content": r3_content})
        r3 = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4000,
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
            f"- {f['fact']} (상세 정보: {f.get('figure', 'N/A')}, 출처: {f.get('source_field', 'N/A')}, 신뢰도: {f.get('confidence', 0):.2f})"
            for f in verified_facts
        ) if verified_facts else "데이터 수집 불완전 — 일반적 시장 분석으로 대체"

        # 시장 요약
        market_summary = _build_market_summary_for_script(market_data)

        num_scenes = _calc_scene_count(target_minutes)
        chars_per_scene = target_chars // num_scenes if num_scenes > 0 else 60

        user_prompt = f"""<verified_facts>
{facts_text}
</verified_facts>

<market_context>
{market_summary}
</market_context>

<constraints>
- 위 verified_facts에 제시된 수치, 뉴스 기사, 글로벌 경제/정세 팩트들만 스크립트 작성에 사용하세요.
- 목록에 없는 구체적 수치(지수값, %, 금액 등)나 핵심 팩트는 절대 새로 날조하거나 창작하지 마세요.
- 사실 데이터 간의 유기적 흐름을 살려 전문적이면서 친근한 톤앤매너로 작성해 주세요.
- 각 씬 대사는 약 {chars_per_scene}자 내외로 작성해 주세요 (음성 재생 시 5~6초 분량).
</constraints>

다음 조건으로 한국어 주식 유튜브 대본을 씬(Scene) 단위로 나누어 작성해주세요:
카테고리: {category_label}
핵심 키워드/주제: {keyword}
목표 분량: 약 {target_chars}자 (약 {target_minutes}분 분량)
분할 씬 수: 총 {num_scenes}개 내외 (각 씬별로 음성 5~6초 분량, 약 {chars_per_scene}자)

출력 형식:
각 씬은 반드시 아래 형식으로 작성해 주세요. 다른 서론이나 결론은 생략하고 씬 목록만 출력하세요.

## 씬 [번호]: [씬 제목]
(여기에 대사 텍스트를 바로 작성하세요. [대사] 또는 [비주얼] 태그는 절대 작성하지 마세요.)

예시:
## 씬 1: 반도체 위기 경보
반도체 시장이 흔들립니다. 삼성전자가 하락세를 보이네요. 투자자들의 걱정이 깊어집니다.
"""

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8000,
            system=SCRIPT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        full_text = "".join(
            block.text for block in response.content
            if hasattr(block, "text") and isinstance(block.text, str)
        )

        sections = _parse_sections(full_text)
        
        # 전체 낭독용 스크립트는 씬의 대사 부분을 이어붙여서 구성합니다.
        full_narration = " ".join(s["content"] for s in sections)
        clean_text = full_narration.strip()

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
        num_scenes = _calc_scene_count(target_minutes)
        sections = []
        for i in range(num_scenes):
            narration = (
                f"이것은 {keyword}와 {category_label} 관련한 {i+1}번째 씬 대사입니다. "
                "시장의 거래량 추이와 수급 주체들의 흐름을 상세하게 분석하고 있으며, "
                "변동성에 흔들리지 않는 차분한 대응이 필요합니다. "
                "개인 투자자들은 자산 배분과 분할 매수를 적극 고려해 보시는 것이 권장됩니다."
            )
            prompt = (
                f"A cute green banknote cartoon character with glasses and a headset, showing an analytical expression, "
                f"pointing at a financial board representing scene {i+1}, corporate news office studio background, clean 2D vector style"
            )
            sections.append({
                "title": f"씬 {i+1}",
                "content": narration,
                "prompt": prompt,
                "char_count": len(narration)
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
                if hasattr(block, "text") and isinstance(block.text, str):
                    text += block.text
                elif isinstance(block, str):
                    text += block
                elif hasattr(block, "get"):
                    text += block.get("text", "") or ""
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
def _calc_scene_count(target_minutes: int) -> int:
    """목표 분량별 씬(이미지) 수 계산 — 5~6초/씬 기준
    
    1.3x 배속 TTS 기준:
    - 1분(60초) / 5.5초 = 약 11씬
    - 5분(300초) / 5.5초 = 약 55씬
    - 10분(600초) / 5.5초 = 약 109씬
    - 15분(900초) / 5.5초 = 약 164씬
    - 20분(1200초) / 5.5초 = 약 218씬
    """
    secs_per_scene = 5.5
    total_seconds = target_minutes * 60
    return max(1, round(total_seconds / secs_per_scene))


# 한국어 키워드 → Kling image-to-video 영어 비주얼 액션 프롬프트 매핑 테이블
_VISUAL_KEYWORD_MAP = [
    (["RAM", "메모리", "HBM", "D램", "DRAM", "낸드", "NAND"],
     "glowing RAM memory sticks with electric blue light pulses flickering, dark tech background"),
    (["GPU", "그래픽카드", "그래픽 카드", "NVIDIA", "엔비디아"],
     "GPU chip with heat lines and neon green circuits dynamic flickering glow, dark lab"),
    (["반도체", "칩", "웨이퍼", "파운드리", "TSMC", "삼성전자", "SK하이닉스"],
     "semiconductor chip circuit board glowing neon, tech particles floating, clean room atmosphere"),
    (["AI", "인공지능", "ChatGPT", "LLM", "딥러닝"],
     "neural network nodes pulsing blue light, AI brain visualization, futuristic digital glow"),
    (["상승", "급등", "폭등", "돌파", "반등", "강세", "호재"],
     "green rising stock chart lines surging upward with glowing candles, financial screen, bullish momentum"),
    (["하락", "급락", "폭락", "붕괴", "매도", "악재", "리스크"],
     "red declining stock chart crashing downward, bearish candles, financial danger alert screen"),
    (["외국인", "기관", "순매수", "수급"],
     "financial dashboard with investor flow data, buy and sell signals, data stream visualization"),
    (["금리", "FOMC", "연준", "Fed", "기준금리"],
     "US Federal Reserve building with dollar signs floating, interest rate gauge chart rising"),
    (["달러", "환율", "원달러", "USD"],
     "dollar bills and Korean won with exchange rate ticker, USD KRW currency display"),
    (["코스피", "코스닥", "지수", "증시"],
     "Korean stock exchange index chart glowing on dark screen, financial ticker board"),
    (["CPI", "인플레이션", "물가"],
     "inflation chart rising with price tags glowing, economic indicator dashboard"),
    (["채권", "국채", "금리"],
     "government bond yield chart rising, financial bonds glowing on dark screen"),
    (["원유", "유가", "WTI", "원자재"],
     "oil barrels with price ticker glowing, commodity market chart"),
    (["매수", "타이밍", "기회", "진입"],
     "green buy arrow glowing on stock chart, optimal entry point highlighted"),
    (["결론", "정리", "요약", "마무리"],
     "financial summary dashboard with glowing data points, conclusion slide cinematic"),
]


def _generate_visual_prompt(scene_text: str, pose: str) -> str:
    """씬 대본 키워드 기반 영어 비주얼 프롬프트 자동 생성 (Kling image-to-video 최적화)"""
    # 1. 키워드 매칭 또는 기본 배경 다변화 순환 선택
    bg_prompt = None
    for keywords, visual in _VISUAL_KEYWORD_MAP:
        if any(k in scene_text for k in keywords):
            bg_prompt = visual
            break

    if not bg_prompt:
        default_bgs = [
            "professional financial news studio background, dark navy blue background (#0d1b2a), glowing data screen",
            "modern high-tech corporate office meeting room, holographic financial charts, dark blue ambient lighting",
            "futuristic cyber stock market trading floor, abstract data streams flowing, dark navy and neon cyan theme",
            "clean minimalist financial analyst desk, laptop showing stock graphs, warm accent lights, dark background"
        ]
        # 텍스트 길이와 문자 코드로 유니크한 인덱스 계산
        str_hash = sum(ord(c) for c in scene_text) if scene_text else 0
        bg_index = str_hash % len(default_bgs)
        bg_prompt = default_bgs[bg_index]

    # 2. 구체적 언급 대상(회사명, 기관) 추출 및 번역 매핑
    entity_map = {
        "삼성전자": "Samsung Electronics",
        "삼성": "Samsung",
        "SK하이닉스": "SK hynix",
        "하이닉스": "SK hynix",
        "엔비디아": "NVIDIA",
        "애플": "Apple",
        "마이크로소프트": "Microsoft",
        "테슬라": "Tesla",
        "구글": "Google",
        "메타": "Meta",
        "현대차": "Hyundai",
        "기아": "Kia",
        "TSMC": "TSMC",
        "ASML": "ASML",
        "연준": "US Federal Reserve",
        "Fed": "US Fed",
        "한국은행": "Bank of Korea",
        "한은": "Bank of Korea",
        "국민연금": "NPS",
    }
    extracted_entities = []
    for ko, en in entity_map.items():
        if ko in scene_text:
            if en not in extracted_entities:
                extracted_entities.append(en)

    # 3. 수치/퍼센트 추출 및 매핑
    # 예: 1.5%, 3,500포인트, 50,000원, 100달러, 20조
    num_matches = re.findall(r'(\d+(?:,\d+)?(?:\.\d+)?)\s*(%|포인트|원|달러|pt|억|조|배)', scene_text)
    unit_map = {
        "%": "%",
        "포인트": "pts",
        "원": " KRW",
        "달러": " USD",
        "pt": "pt",
        "억": "00M",
        "조": "T",
        "배": "x",
    }
    extracted_nums = []
    for val, unit in num_matches:
        en_unit = unit_map.get(unit, unit)
        extracted_nums.append(f"{val}{en_unit}")

    # 4. 프롬프트 세부 묘사 덧붙임
    details = []
    if extracted_entities:
        details.append(f"representing {', '.join(extracted_entities)}")
    if extracted_nums:
        details.append(f"displaying metrics like {', '.join(extracted_nums)}")

    if details:
        bg_prompt = f"{bg_prompt}, {', '.join(details)}"

    # 5. 최종 캐릭터 프롬프트 조립
    char_prompt = (
        f"A cute gold coin mascot character, chibi cartoon style, round shiny gold coin with face, arms and legs, "
        f"wearing small navy business suit with gold tie, showing a {pose}, "
        f"generic plain smooth surface with no currency symbol. "
    )
    style_prompt = "3D render, smooth shading, anime cartoon style, high-quality, cinematic lighting"
    return f"{char_prompt}{bg_prompt}, {style_prompt}"


def get_character_pose_from_text(text: str) -> str:
    # worried
    if any(k in text for k in ["위험", "폭락", "급락", "우려", "손실", "적자", "하락", "부담", "리스크", "경고", "피해", "하락세", "부진", "타격", "악재", "부정"]):
        return "worried, looking concerned and warning the audience"
    # surprised
    if any(k in text for k in ["충격", "경악", "놀라운", "믿기 힘든", "사상 최대", "역대급", "이례적", "깜짝", "기습", "돌발"]):
        return "surprised, wide eyes and mouth open in shock"
    # happy / success
    if any(k in text for k in ["폭등", "급등", "상승", "호재", "이익", "성장", "성공", "기회", "긍정", "수익", "돌파", "반등", "급등세", "최고치"]):
        return "happy, smiling warmly and celebrating success"
    # highlight / emphasis
    if any(k in text for k in ["핵심", "중요", "주목", "기억", "강조", "포인트", "집중", "특별", "바로", "이것", "목표"]):
        return "pointing-emphasis, holding a pointer stick, serious analyst pose"
    # neutral
    return "neutral, calm and professional analyst pose"


def _parse_sections(full_text: str) -> list:
    """## 씬 제목 또는 ## 섹션명 기준으로 분리하고, 대사 텍스트를 추출하며 AI 비주얼 프롬프트를 자동 생성합니다."""
    parts = re.split(r'(?m)^##\s*(.+)$', full_text)
    raw_sections = []

    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            title = parts[i].strip()
            raw_content = parts[i + 1].strip()

            # 혹시나 구버전 태그가 포함되어 있다면 제거
            narration = raw_content
            narration = re.sub(r'\[대사\]', '', narration)
            narration = re.sub(r'\[비주얼\].*$', '', narration, flags=re.DOTALL)
            narration = narration.strip()

            raw_sections.append({"title": title, "content": narration})

    if not raw_sections:
        raw_sections.append({"title": "인트로", "content": full_text.strip()})

    total = len(raw_sections)
    sections = []
    for idx, s in enumerate(raw_sections):
        pose = get_character_pose_from_text(s["content"])
        prompt = _generate_visual_prompt(s["content"], pose)
        section_type = _assign_section_type(idx, total)
        sections.append({
            "title": s["title"],
            "content": s["content"],
            "prompt": prompt,
            "section": section_type,
            "char_count": len(s["content"]),
        })

    return sections


def _count_text(content_blocks) -> int:
    """응답 블록에서 텍스트 총 길이"""
    if isinstance(content_blocks, str):
        return len(content_blocks)
    total = 0
    if isinstance(content_blocks, list):
        for block in content_blocks:
            if hasattr(block, "text") and isinstance(block.text, str):
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
