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
from app.config import CLAUDE_MODEL, SCENE_DURATION_SEC
from app import runtime_config
from app.utils.quality_gate import enrich_scene_plans, assess_scene_plan, assess_script_house_style
from app.utils.art_direction import direct_scenes, assess_art_diversity
from app.utils.market_charts import extract_market_chart
from app.services.info_surface.hero_stat import hero_stat_from_chart
from app.services.overlay.editorial_overlay import OverlaySlot
from app.services.overlay.editorial_director import direct_editorial_overlays
from app.services.overlay.plans import (
    CopyClaim, DataOverlayPlan, SceneEditorialOverlayPlan, chart_kind_from_visual_kind,
)
from app.services.thumbnail.v2.narrative_plan import build_from_video_manifest
from app.utils.script_style import (
    DEFAULT_SCRIPT_STYLE_PROFILE,
    assess_storytelling,
    get_script_style_guide,
)
from app.utils.script_length import make_length_contract, spoken_char_count
from app.utils.narration_contract import build_script_contract
from app.utils.sentence_splitter import split_sentences
from app.workers.news_keyword_extractor import NewsKeywordExtractor
from app.utils.keyword_aliases import normalise_terms
from app.utils.script_delivery import annotate_sections, default_style_mix, pace_sections_for_runtime, validate_delivery
from app.utils.narrative_planner import fallback_plan, plan_narrative
from app.utils.flow_qa import review_flow
from app.utils.elevenlabs_mapper import map_emotion_to_elevenlabs
from app.utils.topic_evidence import is_market_level_forecast
from app.services.verbatim_guard import validate as validate_verbatim

logger = logging.getLogger(__name__)


class ScriptResearchRequiredError(RuntimeError):
    """Raised when a user-selected topic has no grounded evidence to narrate."""

    def __init__(self, message: str, missing_terms: list[str] | None = None):
        super().__init__(message)
        inferred = re.search(r"\(([^)]*)\)", message or "")
        self.missing_terms = missing_terms or (
            [term.strip() for term in inferred.group(1).split(",") if term.strip()] if inferred else []
        )


def _selected_keyword_terms(keyword: str) -> list[str]:
    """Preserve every user-selected term instead of treating the input as one seed."""
    raw_terms = re.split(r"[,\n#/|]+", keyword or "")
    terms: list[str] = []
    for raw in raw_terms:
        cleaned = re.sub(r"\s+", " ", raw).strip(" #,;|\t")
        if cleaned and cleaned not in terms:
            terms.append(cleaned)
    return terms or [str(keyword or "").strip()]


def _topic_terms_for_evidence(terms: list[str]) -> list[str]:
    """Do not make broad labels such as '경제이슈' block a specific topic."""
    generic = {
        "경제이슈", "경제", "주식", "증시", "시장", "이슈", "뉴스",
        "주간", "주요", "최근", "금주", "이번주", "오늘", "하루", "데일리", "주말"
    }
    meaningful = [term for term in terms if term.replace(" ", "") not in generic]
    return meaningful or terms[:1]


def _keyword_coverage_terms(terms: list[str]) -> list[str]:
    """Turn a selected topic phrase into verifiable subject components.

    A selected keyword is often one Korean phrase (for example
    ``삼성전자 3분기 반도체 실적``).  Requiring that exact full phrase in a
    quarter of all sentences rejects an otherwise on-topic script whenever a
    writer naturally says "삼성전자의 3분기 실적".  We instead require every
    distinctive entity/concept/time qualifier to appear, while still keeping a
    meaningful share of the narration focused on the subject.
    """
    generic = {
        "경제이슈", "경제", "주식", "증시", "시장", "이슈", "뉴스", "관련",
        "핵심", "쟁점", "영향", "확인할", "지표", "투자자", "체크포인트",
        "전망", "분석", "주간", "주요", "최근", "금주", "이번주", "오늘", "하루",
        "데일리", "주말", "이후", "이전", "전후"
    }
    result: list[str] = []
    for phrase in _topic_terms_for_evidence(terms):
        chunks = re.split(r"\s+", phrase or "")
        for raw in chunks:
            token = re.sub(r"[^0-9A-Za-z가-힣]", "", raw).strip()
            # Topic inputs are usually natural Korean phrases.  A postposition
            # such as 반등'과' must not become a separate mandatory keyword.
            token = re.sub(r"(으로|에서|에게|부터|까지|보다|처럼|과|와|은|는|이|가|을|를|의)$", "", token)
            if token and token not in generic and token not in result:
                result.append(token)
    # Keep the same canonical entities/time labels used when ranking keyword
    # candidates (삼전=삼성전자, 3분기=Q3).  This prevents a valid script from
    # failing merely because the two stages used different spelling.
    aliases = []
    for phrase in terms:
        for canonical in sorted(normalise_terms(phrase)):
            cleaned = re.sub(r"(으로|에서|에게|부터|까지|보다|처럼|과|와|은|는|이|가|을|를|의)$", "", canonical)
            if cleaned and cleaned not in generic and cleaned not in aliases:
                aliases.append(cleaned)
    return aliases or result or _topic_terms_for_evidence(terms)


def _is_market_level_forecast(terms: list[str]) -> bool:
    """Return true for broad category outlooks, not named research topics.

    A phrase such as "US stocks second-half outlook" is grounded by the
    collected US index/macro snapshot.  Requiring a news headline to match
    every geographic and calendar word turns that normal request into a false
    422.  Named companies, sectors, policies, and events still require their
    own recent article evidence.
    """
    broad_tokens = {
        "미국", "한국", "국내", "해외", "글로벌", "세계", "시장", "증시", "주식",
        "전망", "분석", "상반기", "하반기", "올해", "내년", "최근", "향후",
    }
    tokens = [
        re.sub(r"[^0-9A-Za-z가-힣]", "", token).strip()
        for phrase in terms for token in re.split(r"\s+", phrase or "")
    ]
    tokens = [token for token in tokens if token]
    return bool(tokens) and all(token in broad_tokens for token in tokens)


def _collect_keyword_news(terms: list[str]) -> list[dict]:
    extractor = NewsKeywordExtractor()
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for term in _topic_terms_for_evidence(terms):
        # A script needs topical facts, not only the general market snapshot.
        # Seven days is long enough for a researched long-form topic; the
        # manual keyword UI keeps its stricter 1–2 hour freshness window.
        for article in extractor.search_recent_news(term, max_age_hours=24 * 7, limit=6):
            identity = (str(article.get("title", "")), str(article.get("url", "")))
            if identity in seen:
                continue
            seen.add(identity)
            rows.append({**article, "matched_keyword": term})
    return rows[:12]

# 2026-08-05, 사용자 명시 지시: 문장 단위를 짧게(15~20자) 끊어 TTS에 맞는
# 대본을 구상한 뒤, 5~6초 화면 단위 묶기는 별도 단계(pace_sections_for_runtime)
# 에 맡긴다. 예전 26~38자 목표는 "문장 하나 = 화면 하나(5~6초)"를 생성
# 단계에서부터 강제해 검증 실패가 잦았다 — 문장이 조금만 길어져도(예:
# 45자) 재작성까지 다 써버리고 job 전체가 죽었다. 문장을 짧게 만들면
# 목표 글자 수 범위를 맞추기 쉽고, 상한을 살짝 넘겨도 자막 한 장의 표시
# 시간이 조금 늘어나는 정도라 안전하다. pace_sections_for_runtime은 입력
# 문장 길이와 무관하게 실제 총 글자수/목표 초 비율로 5~6초 단위를 다시
# 묶으므로, 여기서 문장을 짧게 만드는 것이 그 단계를 깨지 않는다.
_SENTENCE_TARGET_MIN_CHARS = 15
_SENTENCE_TARGET_MAX_CHARS = 20
_SENTENCE_AVG_CHARS_FOR_COUNT = 18
_SENTENCE_HARD_CAP_CHARS = 26

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
SCRIPT_SYSTEM_PROMPT = """당신은 한국 금융 콘텐츠를 위한 오리지널 대본 작가입니다.

특정 채널·작가의 고유한 말투, 반복 문구, 문장 구조를 모방하지 않습니다. 아래의
편집 원칙과 별도로 제공되는 오리지널 스토리텔링 프로필을 사용합니다.

작성 원칙:
- 친근하지만 전문적인 톤. 전체 문체는 자연스러운 존댓말·습니다체로 통일한다.
- <verified_facts>의 수치만 사용, 목록에 없는 구체적 수치는 절대 창작 금지
- 수치를 자연스럽게 구어체로 표현: "코스닥이 785포인트를 기록했습니다"
- 각 씬은 자연스럽게 다음 씬으로 연결
- 과장된 클릭베이트 표현 지양, 신뢰도 있는 분석 어조
- 시청자에게 직접 말하는 듯한 구어체 (예: "여러분", "지금 보시는 것처럼")
- 투자 조언이 아닌 정보 제공 관점 유지
- 한국어 맞춤법과 표준 띄어쓰기 규정을 철저히 준수하여 가독성이 높고 자연스러운 문장이 되도록 하세요. (조사나 어미의 잘못된 띄어쓰기 금지)

🎯 낭독·자막 최적화 (가장 중요):
- 대본 문장은 자막 줄 수가 아니라 실제 낭독 호흡을 기준으로 공백 제외 12~32자 안팎으로 작성하세요. 단, 뜻이 완결된 짧은 강조 문장은 억지로 늘리지 마세요.
- 긴 설명은 의미가 완결되는 문장으로 나누되, 짧은 문장을 세 개 이상 연속 배치하지 마세요.
  좋은 예: "이번에도 금리는 그대로입니다. 그렇다면 달라진 게 없는 걸까요? 꼭 그렇지는 않습니다."
  나쁜 예: "금리는 그대로입니다. 경제도 버티고 있습니다. 물가도 높습니다."
- 같은 설명형 평서문을 세 문장 이상 연속 배치하지 마세요. 사실에 맞춰 설명 → 질문 → 반전 → 강조 → 이유 중 역할을 바꿔 리듬을 만드세요.
- 실제 질문은 반드시 물음표(?)와 자연스러운 의문형 어미(예: "~까요?")로 끝내고, 바로 다음 문장 또는 다음 씬에서 검증 사실로 답하세요. 반전은 앞에서 제시한 통념을 실제로 뒤집을 때만 사용하세요.
- “입니다/합니다/있습니다”의 기계적 나열을 피하세요. 질문형, 부정·반전형, 강조형, 이유형을 사실관계에 맞게 섞되, 위 예문을 그대로 반복하지 마세요.
- 각 문장은 반드시 마침표(.), 물음표(?) 등으로 명확히 종결하세요
- 숫자와 기호는 천단위 콤마(,)를 절대 사용하지 말고(예: 2783포인트, 6806포인트), % 기호는 반드시 '퍼센트'로만 풀어 쓰세요. '포인트'는 지수·가격의 절대 변동값에만 사용합니다. 1.2퍼센트와 1.2포인트는 다른 의미입니다.
- 쉼표는 문장 안의 자연스러운 의미 단위에서만 제한적으로 사용하세요. 자막 길이를 맞추기 위해 쉼표·마침표·줄바꿈을 인위적으로 추가하지 마세요. 자막은 최종 음성의 문자 타임스탬프로 별도 분절됩니다.

🎯 씬 구성 규칙 (비주얼 프롬프트 작성의 핵심!):
- 대본은 반드시 ## 씬 [번호]: [제목] 형식의 헤더로 구분해주세요.
- 단순한 주식 차트나 그래프를 띄운 스튜디오 배경을 절대 금지합니다.
- 대본의 경제 상황을 **물리적인 공간이나 은유적인 상황(Situational Metaphor)**으로 치환하여 표현하세요.
  * (예시) 신주 발행 / 통화량 증가 ➡️ 돈을 찍어내는 거대한 윤전기가 있는 공장
  * (예시) 밸류에이션 / 가치 비교 ➡️ 법정 한가운데 놓인 거대한 황금 저울
  * (예시) 주가 폭락 / 실적 악화 ➡️ 붉은 화살표가 내리꽂히고 비상등이 울리는 어두운 관제실
  * (예시) 수수료 / 세금 압박 ➡️ 무거운 돌덩이가 묶인 채 가라앉는 깊은 바닷속
  * (예시) 대규모 자금 유입 / 호황 ➡️ 황금 동전이 폭포수처럼 쏟아지는 화려한 대리석 궁전
  * (예시) 시장 정체 / 박스권 장세 ➡️ 사막 한가운데 갇혀있는 투명한 거대 유리 상자
  * (예시) 물가 상승 / 인플레이션 ➡️ 뜨거운 태양 아래 아이스크림처럼 녹아내리는 지폐 다발
  * (예시) 복잡한 거시경제 / 불확실성 ➡️ 빛나는 문이 여러 개 있는 짙은 안개 속의 미로
- [비주얼 프롬프트 (영어)]에는 캐릭터 묘사를 절대 포함하지 마세요(별도의 캐릭터가 합성됩니다). 배경과 상황만 묘사하세요.
- 모든 장면은 "original 2D Korean finance editorial comic, bold ink outlines, cel shading, no text, no letters, no words, no UI elements"로 통일하세요. 3D 렌더와 실사 표현을 섞지 마세요.
- 각 헤더 아래에는 다음 여섯 개의 태그를 사용해 내용을 채우세요:
  1. [대사] : 실제 한국어로 낭독할 대사 텍스트
  2. [비주얼 설명 (한국어)] : 화면에 보여줄 구체적인 상황과 은유적 배경에 대한 설명 (한국어)
  3. [비주얼 프롬프트 (영어)] : AI 이미지 생성기용 영어 프롬프트 (오직 배경/분위기/객체만 묘사, 캐릭터 묘사 금지 + 공통 스타일/네거티브 키워드 추가)
  4. [감정] : 상황에 맞는 캐릭터 표정/포즈 (happy / worried / surprised / pointing / thinking / explaining / neutral 중 하나)
  5. [모션] : 인트로 구간(처음 약 13개 씬)인 경우에만 chart_shock, pointing_explain, thinking_desk, walking_intro, celebration 중 하나를 반드시 선택해 기술하세요. 본문 씬은 비워두거나 제외합니다.

화면 텍스트 안전 규칙:
- [말풍선], [오버레이], UI 카드, 자막용 문구를 절대 출력하지 마세요. 대사는 TTS·ASS 자막의 유일한 문자 원본입니다.
- 이미지 안의 문자 배치는 V5 이미지 계약이 별도로 결정합니다. 대본 작성 단계에서 공중 말풍선, 검은 패널, 요약 박스, 수치 카드를 계획하지 마세요.

예시:
## 씬 1: 실적 발표와 주가 하락

[대사]
실적이 사상 최대인데도 주가는 떨어집니다. 투자자들은 당황스럽죠.

[비주얼 설명 (한국어)]
'사상 최대 실적'이라 적힌 모니터 화면 밖으로 붉은색 하락 화살표가 모니터를 깨고 튀어나오는 상황. 

[비주얼 프롬프트 (영어)]
giant red downward arrow emerging from an unlabeled trading-room display, dramatic editorial composition, original 2D Korean finance comic, bold ink outlines, cel shading, no readable text

[감정]
surprised

[모션]
chart_shock

[말풍선]
당황스럽네!

절대 금지사항:
- 확정적 미래 예측 ("반드시 오릅니다" 등) 금지
- 특정 종목에 대한 직접적인 매수/매도 지시 금지
- <verified_facts>에 없는 수치나 날짜 창작 금지
- 대본 메타데이터에 말풍선·수치 카드·공중 요약 문구를 넣지 마세요. 화면 텍스트는 최종 ASS 자막과 V5의 물리적 소품 표면만 사용합니다.

🎯 영상 메타데이터 (대본 작성이 모두 끝난 후 마지막에 딱 1번만 작성):
## 메타데이터
[추천 제목]: 클릭을 유도하는 매력적인 유튜브 제목 (30자 내외)
[추천 썸네일]: 썸네일용 비주얼 프롬프트 (영어, 극적이고 시선을 끄는 상황 묘사, original 2D Korean finance editorial comic)
[더보기 설명]: 영상 하단에 들어갈 3줄 요약과 해시태그"""


class ScriptWorker:

    def __init__(self):
        self.collector = MarketDataCollector()

    def _call_llm_with_fallback(self, system_prompt: str, messages: list, max_tokens: int = 4000) -> str:
        """프로젝트 고정 Claude 모델만 호출한다.

        사실 검증·대본·수사 장치의 생성 경로를 다른 모델로 조용히 바꾸면
        결과 재현성과 검증 경계가 무너진다. 호출 실패는 상위 게이트가 처리한다.
        """
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_key:
            raise RuntimeError("ANTHROPIC_API_KEY가 없어 고정 Claude 대본 경로를 실행할 수 없습니다.")
        try:
            from anthropic import Anthropic
            from app.utils.anthropic_cache import cached_system, log_cache_usage
            client = Anthropic(api_key=anthropic_key)
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=cached_system(system_prompt),
                messages=messages,
            )
            log_cache_usage(response, "script_worker")
            content_text = "".join(block.text for block in response.content if hasattr(block, "text"))
            if not content_text:
                raise RuntimeError("Claude 응답에 텍스트가 없습니다.")
            logger.info("Claude API 호출 성공 (%s자)", len(content_text))
            self._llm_provider_log.append({"provider": "claude-sonnet-4-6", "fallback": False})
            self._llm_call_count = getattr(self, "_llm_call_count", 0) + 1
            return content_text
        except Exception as exc:
            logger.error("Claude API 호출 실패: %s", exc)
            raise RuntimeError(f"Claude 대본 호출 실패: {exc}") from exc

    @staticmethod
    def _format_name(target_minutes: int) -> str:
        return "shorts" if int(target_minutes or 0) <= 1 else "longform"

    def _rewrite_sections_for_device(
        self,
        sections: list[dict],
        verified_facts: list[dict],
        *,
        device: str,
        format_name: str,
    ) -> list[dict]:
        """Claude로 수사 장치만 보강한다.

        이 경로는 feature flag가 켜진 경우에만 실행한다. 숫자·날짜·회사명·인과
        관계를 바꾸지 않는 JSON 씬 수정만 허용하며, 이후 결정론 숫자 게이트가
        다시 검증한다.
        """
        source_rows = [
            {"index": index, "text": str(section.get("content") or section.get("text") or "")}
            for index, section in enumerate(sections)
        ]
        facts = json.dumps(verified_facts, ensure_ascii=False)
        if device == "analogy":
            instruction = (
                "추상 금융 개념을 설명하는 씬에만, 매번 새로 만든 일상 비유를 한 개 추가하세요. "
                "비유는 사실을 꾸미는 용도이며 금융 사실·수치·날짜·회사명·인과관계를 바꾸면 안 됩니다."
            )
        else:
            instruction = (
                "초보자가 헷갈릴 수 있는 한 줄 질문과 검증된 사실에 근거한 즉답을 자연스러운 전환 위치에 넣으세요. "
                "숫자·날짜·회사명·인과관계는 추가·삭제·변경하면 안 됩니다."
            )
        system = """당신은 한국 금융 대본의 수사 장치 편집자입니다.
지정된 장치만 보강하고, 특정 창작자·채널의 문장이나 시그니처를 흉내 내지 마세요.
매수·매도·보유 지시나 과장 표현을 쓰지 마세요. JSON 배열만 반환하세요.
각 원소는 {"index": 정수, "text": "수정된 한국어 대사"}여야 합니다."""
        prompt = f"""형식: {format_name}
검증 사실 묶음: {facts}
작업: {instruction}
씬: {json.dumps(source_rows, ensure_ascii=False)}"""
        try:
            raw = self._call_llm_with_fallback(system, [{"role": "user", "content": prompt}], max_tokens=5000)
            match = re.search(r"\[[\s\S]*\]", raw)
            edited = json.loads(match.group(0) if match else raw)
            if not isinstance(edited, list):
                return sections
            replacements = {
                int(item.get("index")): str(item.get("text") or "").strip()
                for item in edited if isinstance(item, dict) and str(item.get("index", "")).isdigit()
            }
            changed = [dict(section) for section in sections]
            for index, replacement in replacements.items():
                if 0 <= index < len(changed) and replacement:
                    changed[index]["content"] = replacement
                    changed[index]["text"] = replacement
                    changed[index]["char_count"] = len(replacement)
            self._llm_provider_log.append({"provider": "claude-sonnet-4-6", "fallback": False, "purpose": f"house_style_{device}"})
            return changed
        except Exception as exc:
            logger.warning("하우스 스타일 %s 보강 실패: %s", device, exc)
            return sections

    def _rewrite_sections_for_rhythm(
        self,
        sections: list[dict],
        verified_facts: list[dict],
        *,
        revision_instruction: str,
        format_name: str,
    ) -> list[dict]:
        """flow_qa가 지적한 리듬 문제를 사실은 그대로 두고 문장 형태만 고쳐 푼다.

        job 147(2026-08-04): 스크립트가 문법·사실 검증은 모두 통과했지만
        78문장 중 76문장이 같은 평서형(~습니다/입니다) 종결이었고, 설명형
        평서문이 21~25개씩 연속됐다(금지 규칙은 "3개 이상 연속 금지"). AUTO
        모드는 이런 대본을 조용히 확정하지 않고 사람 승인 대기로 멈춘다.
        `review_flow()`는 이미 Claude 자신이 만든 한 줄 교정 지시
        (``revision_instruction``)를 반환하지만, 지금까지 아무도 그 지시를
        실제 재작성에 쓰지 않아 이 값은 계산만 되고 버려지고 있었다. 이
        메서드는 그 지시를 실제로 소비해, `_rewrite_sections_for_device`와
        같은 인덱스 치환 계약으로 사실을 바꾸지 않고 문장 리듬만 고친다.
        """
        source_rows = [
            {"index": index, "text": str(section.get("content") or section.get("text") or "")}
            for index, section in enumerate(sections)
        ]
        facts = json.dumps(verified_facts, ensure_ascii=False)
        system = f"""당신은 한국 금융 대본의 리듬 편집자입니다.
사실·숫자·날짜·회사명·인과관계를 절대 추가·삭제·변경하지 마세요. 문장의 종결 어미와 역할
(설명/질문/전환/강조/이유)만 다시 섞어 리듬을 만드세요. 같은 평서문(~습니다/입니다) 종결을
세 문장 이상 연속 배치하지 마세요. 특정 창작자·채널의 문장이나 시그니처를 흉내 내지 마세요.
각 문장은 공백을 제외하고 반드시 {_SENTENCE_HARD_CAP_CHARS}자 이하여야 합니다 — 리듬을 살리려고 절이나 수식어를
덧붙여 문장을 늘리지 말고, 필요하면 문장을 둘로 나누기보다 더 짧게 다듬으세요.
JSON 배열만 반환하세요. 각 원소는 {{"index": 정수, "text": "수정된 한국어 문장"}}이어야 합니다."""
        prompt = f"""형식: {format_name}
검증 사실 묶음: {facts}
편집 지시: {revision_instruction or '같은 평서문 종결이 세 문장 이상 이어지지 않게, 질문·전환·강조·이유 문장을 사실에 맞는 곳에 자연스럽게 섞으세요.'}
씬: {json.dumps(source_rows, ensure_ascii=False)}"""
        try:
            raw = self._call_llm_with_fallback(system, [{"role": "user", "content": prompt}], max_tokens=6000)
            match = re.search(r"\[[\s\S]*\]", raw)
            edited = json.loads(match.group(0) if match else raw)
            if not isinstance(edited, list):
                return sections
            replacements = {
                int(item.get("index")): str(item.get("text") or "").strip()
                for item in edited if isinstance(item, dict) and str(item.get("index", "")).isdigit()
            }
            changed = [dict(section) for section in sections]
            skipped_overlong = []
            for index, replacement in replacements.items():
                if not (0 <= index < len(changed) and replacement):
                    continue
                # job 148 재현: 리듬을 고치려고 절을 덧붙이다 상한을 넘긴
                # 문장이 나왔고, 이는 곧바로 spoken_pacing 검사를 새로
                # 실패시켜 리듬 복구 시도 2회를 모두 소진시켰다. 리듬 하나를
                # 고치며 다른 계약(문장 길이)을 조용히 깨는 치환은 받아들이지
                # 않고 원문을 유지한다.
                if _visible_char_count(replacement) > _SENTENCE_HARD_CAP_CHARS:
                    skipped_overlong.append(index)
                    continue
                changed[index]["content"] = replacement
                changed[index]["text"] = replacement
                changed[index]["char_count"] = len(replacement)
            if skipped_overlong:
                logger.warning(
                    "리듬 재편집이 %s자 상한을 넘긴 문장 %s개를 반환해 원문을 유지함: indexes=%s",
                    _SENTENCE_HARD_CAP_CHARS, len(skipped_overlong), skipped_overlong,
                )
            self._llm_provider_log.append({"provider": "claude-sonnet-4-6", "fallback": False, "purpose": "flow_qa_rhythm_repair"})
            return changed
        except Exception as exc:
            logger.warning("리듬 재편집 실패: %s", exc)
            return sections

    def generate(self, keyword: str, category: str, target_minutes: int,
                 market_data: Optional[dict] = None, job_id: int = 0,
                 data_visuals_enabled: bool = False,
                 storytelling_profile: str = DEFAULT_SCRIPT_STYLE_PROFILE,
                 voice_id: Optional[str] = None) -> dict:
        category_label = CATEGORY_LABELS.get(category, "주식시장")
        self._llm_provider_log: list[dict] = []
        self._llm_call_count = 0
        selected_terms = _selected_keyword_terms(keyword)
        format_name = self._format_name(target_minutes)
        house_style_enabled = bool(runtime_config.value("script_house_style_enabled"))
        speed = float(runtime_config.value("tts_speed"))
        length_contract = make_length_contract(
            target_minutes,
            float(runtime_config.value("chars_per_minute")),
            speed,
            voice_id=voice_id or runtime_config.value("elevenlabs_voice_id"),
            model_id=runtime_config.value("tts_model_body"),
        )
        target_chars = int(length_contract["target_chars"])

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
            keyword_news = _collect_keyword_news(selected_terms)
            # A named topic must have its own evidence.  Generic index data is
            # never allowed to replace it with an unrelated KOSPI script.
            topic_terms = _keyword_coverage_terms(selected_terms)
            if len(topic_terms) > 1 and not keyword_news and not is_market_level_forecast(selected_terms):
                raise ScriptResearchRequiredError(
                    f"선택 키워드({', '.join(topic_terms)})의 검증 가능한 최신 근거를 찾지 못했습니다. "
                    "키워드를 수정하거나 근거 자료를 추가한 뒤 다시 시도하세요."
                )

            # 3-Round 팩트체크
            verified_facts, fact_check_log = self._multi_round_fact_check(
                keyword, category_label, market_data, selected_terms, keyword_news
            )

            try:
                narrative_plan = plan_narrative(
                    lambda system, messages, max_tokens: self._call_llm_with_fallback(system, messages, max_tokens),
                    selected_terms=selected_terms,
                    verified_facts=verified_facts,
                    candidate_context={
                        "category": category_label,
                        "market_summary": _build_market_summary_for_script(market_data)[:2000],
                        "news_titles": [str(row.get("title", ""))[:180] for row in keyword_news[:5]],
                    },
                    format_name=format_name,
                ) if runtime_config.value("script_narrative_planning_enabled") else {
                    "plan_id": "planning_disabled", "planner": "disabled", "story_beats": []
                }
            except Exception as exc:
                logger.warning("내러티브 플랜 생성 실패: %s", exc)
                narrative_plan = fallback_plan(selected_terms, verified_facts, format_name)

            # 검증된 사실 기반 스크립트 생성
            full_script, sections, meta_title, meta_thumb, meta_desc, meta_shorts = self._generate_with_verified_facts(
                keyword, category_label, target_minutes, target_chars,
                verified_facts, market_data, storytelling_profile,
                selected_terms, keyword_news, length_contract, narrative_plan,
            )
            # P2/P3은 사실 생성이 아닌 수사 장치 보강만 하며, 각각 최대 한 번의
            # Claude 호출만 사용한다. 비활성화하면 기존 생성 결과를 그대로 둔다.
            if house_style_enabled and runtime_config.value("script_pattern_analogy_enabled"):
                sections = self._rewrite_sections_for_device(
                    sections, verified_facts, device="analogy", format_name=format_name,
                )
            if house_style_enabled and runtime_config.value("script_pattern_fake_question_enabled"):
                sections = self._rewrite_sections_for_device(
                    sections, verified_facts, device="fake_reader_question", format_name=format_name,
                )
            # 장면은 이후 이미지와 타이밍의 기준이므로, 대본에서만 문단을 제거해
            # 두 계보가 달라지는 일을 허용하지 않는다.
            full_script = _narration_from_sections(sections)
            try:
                flow_qa = review_flow(
                    lambda system, messages, max_tokens: self._call_llm_with_fallback(system, messages, max_tokens),
                    script=full_script,
                    narrative_plan=narrative_plan,
                ) if runtime_config.value("script_flow_qa_enabled") else {
                    "passed": True, "method": "disabled", "transition_issues": []
                }
            except Exception as exc:
                logger.warning("대본 흐름 QA 실패: %s", exc)
                flow_qa = {"passed": False, "method": "unavailable", "transition_issues": ["흐름 QA 호출 실패"]}

            # job 147(2026-08-04): flow_qa가 리듬 문제(같은 평서문 3문장 이상
            # 연속 등)를 잡아내도 아무도 고치지 않아, AUTO 모드가 조용히
            # 넘어가지 않고 사람 승인 대기에서 영구히 멈췄다. review_flow가
            # 이미 만들어 두고 버려지던 revision_instruction으로 최대 2회까지
            # 사실은 그대로 두고 문장 리듬만 재편집한 뒤 다시 검사한다.
            if runtime_config.value("script_flow_qa_enabled"):
                for rhythm_repair_attempt in range(2):
                    if flow_qa.get("passed"):
                        break
                    instruction = str(flow_qa.get("revision_instruction") or "").strip()
                    logger.warning(
                        "Flow QA 리듬 문제 발견(repair %s/2): %s",
                        rhythm_repair_attempt + 1, instruction or "(revision_instruction 없음)",
                    )
                    sections = self._rewrite_sections_for_rhythm(
                        sections, verified_facts, revision_instruction=instruction, format_name=format_name,
                    )
                    full_script = _narration_from_sections(sections)
                    try:
                        flow_qa = review_flow(
                            lambda system, messages, max_tokens: self._call_llm_with_fallback(system, messages, max_tokens),
                            script=full_script,
                            narrative_plan=narrative_plan,
                        )
                    except Exception as exc:
                        logger.warning("리듬 재검사 실패: %s", exc)
                        break
                if flow_qa.get("passed"):
                    logger.info("Flow QA 리듬 문제가 재편집으로 해결됨 (job_id=%s)", job_id)
            # 대본 원문은 그대로 두고, 짧은 문장 조각만 5~6초 화면 체류 단위로
            # 묶는다. 이후 이미지·TTS·ASS가 모두 이 동일한 장면 계보를 사용한다.
            sections = pace_sections_for_runtime(sections, int(length_contract["target_seconds"]))
            sections = direct_scenes(enrich_scene_plans(sections))
            if data_visuals_enabled:
                for scene in sections:
                    scene["market_snapshot"] = market_data
            # 일반형·기사형·정보형 혼합 영상은 대본 의미를 소품과 상황으로
            # 설명한다. 숫자 카드와 차트 오버레이는 레거시의 명시적 데이터
            # 시각화 요청에서만 유지해 기존 기능과 분리한다.
            if data_visuals_enabled:
                sections = _attach_verified_index_overlays(sections, market_data)
                sections = _attach_verified_market_charts(sections)
            # 검증된 그래프 페이로드를 붙인 뒤 분류해야 실제 그래프 후보가
            # 지표형으로 오분류되지 않는다.
            sections = _classify_scene_types(sections)
            sections = _validate_info_scene_payloads(sections)
            if data_visuals_enabled:
                sections = direct_editorial_overlays(sections)
            # 이미지 단계가 전역 응답이 아니라 개별 씬만 전달받아도 검증 사실을
            # 재확인할 수 있도록 원문을 보존한다. 수치 생성에는 사용하지 않는다.
            for scene in sections:
                scene["verified_facts"] = verified_facts
            used_real_llm = True

        except ScriptResearchRequiredError:
            # Do not hide an evidence failure behind a fabricated mock script.
            raise
        except ValueError:
            # 길이·문장·장면 계약 실패는 실제 대본을 가짜 mock으로 바꾸지 않는다.
            raise
        except Exception as e:
            logger.error(f"LLM API 호출 실패: {e} — Mock으로 폴백")
            full_script, sections = self._mock_script(keyword, category_label, target_minutes)
            sections = pace_sections_for_runtime(sections, int(length_contract["target_seconds"]))
            sections = direct_scenes(enrich_scene_plans(sections))
            if data_visuals_enabled:
                for scene in sections:
                    scene["market_snapshot"] = market_data
            if data_visuals_enabled:
                sections = _attach_verified_index_overlays(sections, market_data)
                sections = _attach_verified_market_charts(sections)
            sections = _classify_scene_types(sections)
            sections = _validate_info_scene_payloads(sections)
            if data_visuals_enabled:
                sections = direct_editorial_overlays(sections)
            verified_facts = []
            narrative_plan = {"plan_id": "generation_fallback", "planner": "fallback", "story_beats": []}
            flow_qa = {"passed": False, "method": "generation_fallback", "transition_issues": ["생성 실패"]}
            fact_check_log = [f"오류: {str(e)}"]
            used_real_llm = False
            meta_title = "제목 자동 생성 실패"
            meta_thumb = "Stock market background"
            meta_desc = "상세 설명이 없습니다."
            meta_shorts = "쇼츠 대본 자동 생성 실패"

        logger.info(f"스크립트 생성 완료: {len(full_script)}자, job_id={job_id}")

        # Production metadata is derived after all factual narration and
        # visual planning are final. It never rewrites the approved script.
        sections = annotate_sections(sections, int(length_contract["target_seconds"]))
        # 이미지·TTS·자막이 같은 문장을 소비하도록 장면 ID와 원문 계보를 고정한다.
        for index, scene in enumerate(sections, start=1):
            scene.setdefault("scene_id", f"script_scene_{index:03d}")
        full_script = _narration_from_sections(sections)
        narration_contract = build_script_contract(full_script, sections)
        for source, scene in zip(narration_contract["scene_sources"], sections):
            scene["narration_source"] = {
                "scene_id": source["scene_id"],
                "text_sha256": source["text_sha256"],
                "canonical_text_sha256": narration_contract["canonical_text_sha256"],
            }
        for scene in sections:
            scene["elevenlabs_hint"] = map_emotion_to_elevenlabs(scene["emotion_tag"], scene["phase"])
            for sentence in scene.get("sentences", []):
                sentence["elevenlabs_hint"] = map_emotion_to_elevenlabs(sentence["emotion_tag"], scene["phase"])
        delivery_validation = validate_delivery(sections)
        scene_quality = assess_scene_plan(sections)
        rejected_scenes = [
            {
                "index": index,
                "title": scene.get("title", ""),
                "reason": (scene.get("bubble_validation") or {}).get("reasons", []),
            }
            for index, scene in enumerate(sections)
            if scene.get("scene_rejected")
        ]
        if rejected_scenes:
            scene_quality = dict(scene_quality)
            scene_quality.setdefault("warnings", []).append("rejected_ungrounded_screen_text")
            scene_quality["rejected_scenes"] = rejected_scenes
        art_quality = assess_art_diversity(sections)
        storytelling_quality = assess_storytelling(
            sections, full_script, format_name=format_name, house_style_enabled=house_style_enabled,
        )
        house_style_quality = assess_script_house_style(
            full_script,
            format_name=format_name,
            verified_facts=verified_facts,
            enabled=house_style_enabled,
            llm_labeling_enabled=bool(runtime_config.value("script_pattern_llm_labeling_enabled")),
            number_traceability_required=bool(runtime_config.value("script_pattern_numbers_enabled")),
        )
        keyword_validation = _validate_keyword_coverage(full_script, selected_terms)
        if not keyword_validation["passed"]:
            # 2026-08-05, 사용자 명시 지시: job 155에서 "전략" 같은 단어 하나가
            # 본문에 문자 그대로(혹은 등록된 동의어로) 안 보인다는 이유로 이미
            # 사실 검증(팩트체크 3라운드)까지 마친 정상 스크립트를 통째로
            # 버리고 키워드 재선정 루프(최대 5회, 매회 수 분 + Anthropic API
            # 비용)를 반복했다. 사실 검증은 이 함수 앞단(다중 라운드 팩트체크)
            # 에서 이미 끝났으므로, 이 게이트는 "글자 그대로 다시 안 보이는
            # 단어"를 이유로 작업 전체를 죽이지 않는다 — 결과를 그대로 쓰고
            # 어떤 단어가 안 보였는지는 keyword_validation에 남겨 리포트에서
            # 확인할 수 있게 한다.
            logger.warning(
                "선택 키워드 일부가 본문에 그대로 드러나지 않았지만 그대로 진행: %s",
                ", ".join(keyword_validation["missing_terms"]),
            )
        unit_validation = _validate_unit_usage(full_script)
        thumbnail_brief = _build_thumbnail_brief(keyword, sections, verified_facts)

        return {
            "job_id": job_id,
            "keyword": keyword,
            "script": full_script,
            "sections": sections,
            "narration_contract": narration_contract,
            "char_count": spoken_char_count(full_script),
            "length_contract": length_contract,
            "keyword_validation": keyword_validation,
            "unit_validation": unit_validation,
            "verified_facts": verified_facts,
            "fact_check_rounds": len(fact_check_log),
            "fact_check_log": fact_check_log,
            "market_snapshot_used": market_data is not None,
            "market_snapshot": market_data or {},
            "used_real_llm": used_real_llm,
            "llm_provider_log": self._llm_provider_log,
            "llm_call_count": self._llm_call_count,
            "narrative_plan": narrative_plan,
            "flow_qa": flow_qa,
            "requires_manual_review": (
                bool(rejected_scenes)
                or any(item.get("fallback") for item in self._llm_provider_log)
                or not house_style_quality["passed"]
            ),
            # job 150(2026-08-05), 사용자 명시 지시: flow_qa(문장 리듬·낭독
            # 페이싱)는 이미 위에서 최대 2회 자동 재편집을 거쳤다. 그래도
            # 통과 못 하는 건 "같은 어미가 3문장 연속" 같은 스타일 다양성
            # 지적이지, 사실 오류나 자막/TTS 싱크가 깨지는 문제가 아니다
            # (문장당 15~26자, 씬 개수는 _validate_scene_delivery가 별도로
            # 계속 강제한다). 이런 소프트 QA 하나 때문에 AUTO 모드가 72시간
            # 사람 승인 대기로 멈추는 건 과도한 제약이라, requires_manual_review
            # 판정에서는 제외하고 flow_qa 결과 자체는 그대로 리포트에 남긴다.
            "storytelling_profile": DEFAULT_SCRIPT_STYLE_PROFILE,
            "style_mix_applied": default_style_mix(category),
            "structure": narrative_plan.get("plan_id", "adaptive_plan"),
            "quality_report": {
                "scene_plan": scene_quality,
                "art_direction": art_quality,
                "storytelling": storytelling_quality,
                "house_style": house_style_quality,
                "flow": flow_qa,
                "delivery": delivery_validation,
                "screen_text": {"passed": not rejected_scenes, "rejected_scenes": rejected_scenes},
            },
            "thumbnail_brief": thumbnail_brief,
            "youtube_metadata": {
                "title": meta_title,
                "thumbnail_prompt": meta_thumb,
                "description": meta_desc,
                "shorts_script": meta_shorts
            }
        }

    def _multi_round_fact_check(self, keyword: str, category_label: str,
                                 market_data: dict, selected_terms: list[str],
                                 keyword_news: list[dict]) -> tuple[list, list]:
        messages = []
        fact_check_log = []
        market_json = json.dumps(market_data, ensure_ascii=False, indent=2)
        news_json = json.dumps(keyword_news, ensure_ascii=False, indent=2)

        r1_content = f"""<selected_keywords>{json.dumps(selected_terms, ensure_ascii=False)}</selected_keywords>
<category>{category_label}</category>
<market_data>
{market_json}
</market_data>
<keyword_news_evidence>
{news_json}
</keyword_news_evidence>

<task>
위 실제 시장 데이터에서 '{keyword}' 관련 핵심 사실들을 가능한 많이 추출하세요.
1. 수치, 뉴스, 매크로 동향 등 신뢰성 있는 정보 포함.
2. 데이터 내 출처 필드명 명시.
3. 데이터에 없는 내용 절대 금지.
4. Every fact must directly concern at least one selected keyword. General market context may only explain a supplied keyword fact; it must never replace the selected topic.
5. Keep point changes and percentage changes as separate, labelled values.
형식: 번호. [출처] 사실 내용
</task>"""

        r1_text = self._call_llm_with_fallback(FACT_CHECK_SYSTEM_PROMPT, [{"role": "user", "content": r1_content}], max_tokens=4000)
        messages.append({"role": "user", "content": r1_content})
        messages.append({"role": "assistant", "content": r1_text})
        fact_check_log.append(f"Round 1 완료: {_count_text(r1_text)}자")

        r2_content = "위 사실들을 비판적으로 검토하여 교차 검증하고 최종 목록을 작성하세요."
        messages.append({"role": "user", "content": r2_content})
        r2_text = self._call_llm_with_fallback(FACT_CHECK_SYSTEM_PROMPT, messages, max_tokens=3000)
        messages.append({"role": "assistant", "content": r2_text})
        fact_check_log.append(f"Round 2 완료: {_count_text(r2_text)}자")

        r3_content = """검토 결과를 반영하여 최종 사실 목록을 아래 JSON 형식으로 출력하세요.
[
  {
    "fact": "...", "figure": "...", "source_field": "...", "confidence": 1.0
  }
]"""
        messages.append({"role": "user", "content": r3_content})
        r3_text = self._call_llm_with_fallback(FACT_CHECK_SYSTEM_PROMPT, messages, max_tokens=4000)
        fact_check_log.append("Round 3 완료")
        return self._parse_verified_facts(r3_text), fact_check_log

    def _generate_with_verified_facts(self, keyword: str, category_label: str,
                                       target_minutes: int, target_chars: int,
                                       verified_facts: list, market_data: dict,
                                       storytelling_profile: str = DEFAULT_SCRIPT_STYLE_PROFILE,
                                       selected_terms: Optional[list[str]] = None,
                                       keyword_news: Optional[list[dict]] = None,
                                       length_contract: Optional[dict] = None,
                                       narrative_plan: Optional[dict] = None):
        facts_text = "\n".join(f"- {f['fact']} (상세 정보: {f.get('figure', 'N/A')}, 출처: {f.get('source_field', 'N/A')}, 신뢰도: {f.get('confidence', 0):.2f})" for f in verified_facts)
        market_summary = _build_market_summary_for_script(market_data)
        selected_terms = selected_terms or _selected_keyword_terms(keyword)
        keyword_news = keyword_news or []
        narrative_plan = narrative_plan or {"plan_id": "adaptive_plan", "story_beats": []}
        style_instruction = (
            "정보 공개 간격과 전환 횟수는 내러티브 플랜의 선택 근거와 검증 사실의 밀도에 맞춰 정한다. "
            "정해진 질문 수나 반전 횟수를 채우기 위해 문장을 추가하지 않는다."
        )
        evidence_text = "\n".join(
            f"- [{row.get('matched_keyword', '')}] {row.get('title', '')} ({row.get('source', '')})"
            for row in keyword_news
        ) or "- 없음"

        user_prompt = f"""<selected_keywords>{json.dumps(selected_terms, ensure_ascii=False)}</selected_keywords>
<category>{category_label}</category>
<verified_facts>{facts_text}</verified_facts>
<market_context>{market_summary}</market_context>
<keyword_news_evidence>{evidence_text}</keyword_news_evidence>
<narrative_plan>{json.dumps(narrative_plan, ensure_ascii=False)}</narrative_plan>
작성 규칙:
- [대사], [비주얼 설명 (한국어)], [비주얼 프롬프트 (영어)], [감정] 포함
- [대사] 블록만 합산해 공백 제외 약 {target_chars}자(±8%)로 작성. 비주얼 설명·영문 프롬프트·메타데이터는 이 분량에 포함하지 않음
- The selected keywords are mandatory subjects, not optional context. Every section must directly explain a selected keyword, its verified impact, or the relationship between the selected keyword and the category. Do not replace this with a generic market crash, geopolitical event, or index recap unless the supplied evidence explicitly connects it.
- Mention every distinctive entity, concept, and time qualifier contained in the selected topic naturally at least once. The category is the analytical lens, not a substitute for the selected topic.
- Use unit-safe facts only: percentages use '퍼센트', index or price changes use '포인트'; never call a percentage a point value.
- Write continuous, readable narration. Image scenes are derived after narration is complete; do not pad, shorten, or duplicate narration to reach a scene count.
- 내러티브 플랜의 story_beats 순서·전환 목표를 따른다. 플랜은 고정 문구나 고정 비율이 아니라 소재에 맞춘 편집 의도다. 사실의 자연스러운 설명에 필요하면 인접 비트를 합치거나 짧게 조절할 수 있지만, 새 사실을 만들지 않는다. {style_instruction}
- 앞 문장이 질문이면 바로 다음 문장 또는 다음 씬에서 검증 사실로 답한다. 같은 사실은 역할이 달라질 때만 다시 언급한다. 마지막은 도입을 반복하지 말고, 플랜의 체크포인트를 자연스럽게 정리한다.
- 낭독 리듬을 검사하므로, 설명형 ``~습니다`` 문장을 세 개 이상 연속하지 마세요. 사실에 맞는 범위에서 질문·전환·이유·강조를 섞고, 질문에는 물음표를 사용한 뒤 곧바로 근거로 답하세요.
- [대사]는 짧고 자연스러운 구어체 완결 문장 약 {max(1, round(target_chars / _SENTENCE_AVG_CHARS_FOR_COUNT))}개로 작성하세요(문장 수는 총 분량 {target_chars}자에 맞춰 자연스럽게 정해지는 목표치입니다). 각 문장은 공백 제외 {_SENTENCE_TARGET_MIN_CHARS}~{_SENTENCE_TARGET_MAX_CHARS}자 범위의 짧은 호흡이어야 하며, TTS가 한 호흡에 자연스럽게 읽을 수 있는 길이입니다.
- 한 문장이 길어질 경우 단어 중간이나 조사 앞에서 자르지 말고, 원인·전환·결론이 완결된 두 문장으로 자연스럽게 나누세요. 이미지 장면은 이후 여러 짧은 문장을 5~6초 단위로 자동으로 묶어 결정되므로, 지금은 문장 길이 계약만 지키면 됩니다.
- 세 문장 이상을 단순 설명형으로 나열하지 마세요.
- Improve only voice, pacing, transitions, and listener comprehension. Do not add, remove, substitute, or reinterpret any verified fact, number, date, company, source, or causal relationship.
- 마지막에 ## 메타데이터 섹션 추가 ([추천 제목], [추천 썸네일], [더보기 설명], [쇼츠 대본])
- 쇼츠 대본은 본 영상의 핵심만 30초 내외로 요약한 강렬한 문장으로 작성
목표 영상 길이: {target_minutes}분 / TTS 배속: {(length_contract or {}).get('tts_speed', 1.0)}x"""

        style_guide = get_script_style_guide(
            storytelling_profile,
            format_name=self._format_name(target_minutes),
            house_style_enabled=bool(runtime_config.value("script_house_style_enabled")),
        )
        for attempt in range(3):
            try:
                full_text = self._call_llm_with_fallback(
                    f"{SCRIPT_SYSTEM_PROMPT}\n\n{style_guide}",
                    [{"role": "user", "content": user_prompt}],
                    max_tokens=8000,
                )
                
                # --- 메타데이터 파싱 및 본문 분리 로직 ---
                meta_title = "제목 자동 생성 실패"
                meta_thumb = "Stock market background"
                meta_desc = "상세 설명이 없습니다."
                meta_shorts = "쇼츠 대본 자동 생성 실패"
                
                script_body = full_text
                meta_split = re.split(r'##\s*메타데이터', full_text, flags=re.IGNORECASE)
                if len(meta_split) > 1:
                    script_body = meta_split[0].strip()
                    meta_text = meta_split[1]
                    
                    t_match = re.search(r'\[추천 제목\]\s*:?\s*(.*?)(?=\[|$)', meta_text, re.DOTALL)
                    if t_match: meta_title = t_match.group(1).strip()
                    th_match = re.search(r'\[추천 썸네일\]\s*:?\s*(.*?)(?=\[|$)', meta_text, re.DOTALL)
                    if th_match: meta_thumb = th_match.group(1).strip()
                    d_match = re.search(r'\[더보기 설명\]\s*:?\s*(.*?)(?=\[|$)', meta_text, re.DOTALL)
                    if d_match: meta_desc = d_match.group(1).strip()
                    s_match = re.search(r'\[쇼츠 대본\]\s*:?\s*(.*?)(?=\[|$)', meta_text, re.DOTALL)
                    if s_match: meta_shorts = s_match.group(1).strip()

                if _needs_dialogue_length_rewrite(script_body, target_chars):
                    script_body = self._rewrite_dialogue_to_target(script_body, target_chars)

                if _needs_dialogue_length_rewrite(script_body, target_chars):
                    # job 149(2026-08-05): 사용자 명시 지시 — 총 분량이
                    # target_chars 허용폭(±8~15%)을 못 맞춘다고 작업 전체를
                    # 실패시키지 말 것. TTS 싱크에 실제로 영향을 주는 건
                    # 씬(문장) 단위 계약(_validate_scene_delivery: 문장 수,
                    # 문장당 15~26자)이지 총 글자 수 총합이 아니다. 총 분량은
                    # LLM 재작성 한 번과 결정론적 캡(문장 경계만 자르고 사실은
                    # 절대 왜곡하지 않음)으로 최대한 근접시키되, 그래도
                    # 못 맞추면 예외로 Anthropic API 호출만 낭비하며 작업
                    # 전체를 죽이는 대신 최선의 결과로 계속 진행한다. 씬 단위
                    # 계약은 바로 아래 _validate_scene_delivery가 별도로 계속
                    # 강제하므로 자막 싱크 안전성은 그대로 유지된다.
                    script_body = _cap_dialogue_to_target(script_body, target_chars)
                    if _needs_dialogue_length_rewrite(script_body, target_chars):
                        logger.warning(
                            "총 대사 분량이 목표 범위를 벗어났지만 씬 단위 계약은 유효해 그대로 진행: "
                            "actual=%s, target=%s",
                            _dialogue_char_count(script_body), target_chars,
                        )

                script_body = _cap_dialogue_to_target(script_body, target_chars)
                sections = _split_sections_for_visual_pacing(_parse_sections(
                    script_body,
                    evidence={"verified_facts": verified_facts, "market_snapshot": market_data},
                ))
                # 5.5초/씬이 아니라 목표 글자수 기준으로 완결 문장 개수를
                # 추정한다 — 화면 묶기는 pace_sections_for_runtime이
                # 별도로 담당하므로, 여기서는 "짧은 문장이 총 분량만큼
                # 충분히 있는가"만 검증하면 된다.
                target_scene_count = max(1, round(target_chars / _SENTENCE_AVG_CHARS_FOR_COUNT))
                try:
                    _validate_scene_delivery(sections, target_scene_count=target_scene_count)
                except ValueError:
                    # 문장 수가 부족하거나 문장이 길면 같은 사실 범위에서만
                    # 재편집한다. 레거시 mock으로 대체하지 않는다.
                    script_body = self._rewrite_dialogue_to_target(script_body, target_chars)
                    sections = _split_sections_for_visual_pacing(_parse_sections(
                        script_body,
                        evidence={"verified_facts": verified_facts, "market_snapshot": market_data},
                    ))
                    try:
                        _validate_scene_delivery(sections, target_scene_count=target_scene_count)
                    except ValueError as delivery_err:
                        # job 152(2026-08-05), 사용자 명시 지시: 재작성까지
                        # 시도했는데도 문장 하나가 38자를 살짝 넘는다고 job
                        # 전체를 실패시키지 않는다. 장면 수 부족(실제로 보여줄
                        # 장면이 모자람)은 여전히 하드 실패로 남기지만, 완결
                        # 문장 하나가 상한을 넘는 건 자막 한 장의 표시 시간이
                        # 조금 늘어나는 정도라 씬 단위 재구성 없이 진행한다.
                        if "장면 수가" in str(delivery_err):
                            raise
                        logger.warning("씬 길이 계약을 완전히 못 맞췄지만 그대로 진행: %s", delivery_err)
                break
            except ValueError as val_err:
                logger.warning(f"Script parsing validation failed (attempt {attempt+1}/3): {val_err}. Retrying LLM call...")
                if attempt == 2:
                    raise

        narration_script = _dedupe_adjacent_paragraphs(_narration_from_sections(sections))
        return narration_script, sections, meta_title, meta_thumb, meta_desc, meta_shorts

    def _mock_generate(self, keyword, category_label, target_minutes, job_id):
        script_text, sections = self._mock_script(keyword, category_label, target_minutes)
        sections = _classify_scene_types(sections)
        length_contract = make_length_contract(
            target_minutes,
            float(runtime_config.value("chars_per_minute")),
            float(runtime_config.value("tts_speed")),
            voice_id=runtime_config.value("elevenlabs_voice_id"),
            model_id=runtime_config.value("tts_model_body"),
        )
        selected_terms = _selected_keyword_terms(keyword)
        return {
            "job_id": job_id,
            "keyword": keyword,
            "script": script_text,
            "sections": sections,
            "char_count": spoken_char_count(script_text),
            "length_contract": length_contract,
            "keyword_validation": _validate_keyword_coverage(script_text, selected_terms),
            "unit_validation": _validate_unit_usage(script_text),
            "verified_facts": [],
            "fact_check_rounds": 0,
            "fact_check_log": ["ANTHROPIC_API_KEY 미설정 — Mock 모드"],
            "market_snapshot_used": False,
            "market_snapshot": {},
            "used_real_llm": False,
            "llm_call_count": 0,
            "narrative_plan": {"plan_id": "mock", "planner": "mock", "story_beats": []},
            "flow_qa": {"passed": False, "method": "mock", "transition_issues": ["Mock 대본"]},
            "requires_manual_review": True,
            "storytelling_profile": DEFAULT_SCRIPT_STYLE_PROFILE,
            "quality_report": {
                "scene_plan": assess_scene_plan(sections),
                "art_direction": assess_art_diversity(sections),
                "storytelling": assess_storytelling(sections, script_text),
                "flow": {"passed": False, "method": "mock"},
                "delivery": validate_delivery(sections),
                "reason": "API 키 미설정 Mock 대본 — 자동 진행 금지",
            },
            "thumbnail_brief": _build_thumbnail_brief(keyword, sections, []),
            "youtube_metadata": {
                "title": f"{keyword} 핵심 정리",
                "thumbnail_prompt": "Manual review required: no generated thumbnail prompt",
                "description": "API 키 미설정 Mock 대본입니다. 검토 후 사용하세요.",
                "shorts_script": "Mock 대본은 쇼츠 자동 생성에 사용하지 않습니다.",
            },
        }

    def _rewrite_dialogue_to_target(self, script_body: str, target_chars: int) -> str:
        """검증된 원문만 바탕으로 5~6초 장면용 완결 문장을 다시 만든다.

        job 147 재현: 55개 문장을 요청하면 Claude가 49~52개로 근소하게
        undershoot하는 일이 반복됐다(최소 53 대비 1~6개 부족). 단 한 번만
        요청하고 실패하면 원문을 그대로 반환하던 이전 구조는 이 근소한
        미달을 스스로 교정할 기회가 없었다. 최대 3회까지, 직전 결과의 실제
        문장 수를 알려주며 다시 요청한다 — 매번 새로 처음부터 요청하는 것보다
        "51개였다, 최소 53개 필요"라는 구체적 피드백이 한두 문장 추가로
        수렴할 확률이 높다.
        """
        try:
            current_chars = _dialogue_char_count(script_body)
            target_scene_count = max(1, round(target_chars / _SENTENCE_AVG_CHARS_FOR_COUNT))
            minimum_scene_count = _minimum_scene_count(target_scene_count)
            source_sections = _parse_sections(script_body)
            source_narration = _narration_from_sections(source_sections)

            correction = ""
            for rewrite_attempt in range(3):
                rewritten = self._call_llm_with_fallback(
                    "You are a Korean financial script editor.",
                    [{"role": "user", "content": f"""아래 한국어 내레이션을 같은 검증 사실 범위 안에서만 재편집하세요.
새 숫자, 날짜, 회사명, 출처, 인과관계, 투자 권유를 만들지 마세요. 원문의 사실과 불확실성 표현을 보존하세요.

반드시 JSON 문자열 배열만 반환하세요. 배열은 약 {target_scene_count}개의 짧고 자연스러운 구어체 문장입니다.
각 원소는 완결된 한국어 문장 하나이며 공백 제외 {_SENTENCE_TARGET_MIN_CHARS}~{_SENTENCE_TARGET_MAX_CHARS}자입니다. 번호, 제목, 마크다운, 설명을 넣지 마세요.
각 문장은 자연스럽게 독립적으로 들리고, 단어 중간이나 조사 앞에서 끝나면 안 됩니다.
총 대사 분량은 공백 제외 약 {target_chars}자여야 합니다. 현재 분량은 {current_chars}자입니다.
{correction}
원문:
{source_narration}"""}],
                    max_tokens=6000,
                )
                lines = _parse_dialogue_sentence_array(rewritten)
                # LLM이 정확히 target_scene_count개, 짧은 목표 글자수로만
                # 응답하길 기대하는 자체 검사가 실제 하류 계약
                # (_validate_scene_delivery, _minimum_scene_count 참조)보다
                # 더 빡빡했다. 자체 검사를 실제 하류 계약과 동일한 허용치로
                # 맞춘다.
                too_few_scenes = len(lines) < minimum_scene_count
                overlong_lines = [line for line in lines if _visible_char_count(line) > _SENTENCE_HARD_CAP_CHARS]
                if not too_few_scenes and not overlong_lines:
                    structured = _structured_script_from_dialogue_lines(lines)
                    structured_chars = _dialogue_char_count(structured)
                    if _needs_dialogue_length_rewrite(structured, target_chars) is False:
                        logger.info(
                            "Narration sentence rewrite applied (rewrite attempt %s/3): %s -> %s chars, %s scenes",
                            rewrite_attempt + 1, current_chars, structured_chars, len(lines),
                        )
                        return structured
                    # job 148 재현: 문장 수·문장당 길이는 계약을 통과했지만
                    # (예: 11개, 각 38자 이하), 총 대사 분량이 target_chars
                    # 허용 범위(±8~15%)를 벗어난 경우다. 이전 코드는 이 경우도
                    # "scenes=11 (need >= 10)"이라며 실제로는 문제가 없는
                    # 장면 수를 원인으로 잘못 로그하고, 엉뚱한 "문장 수를
                    # 늘리라"는 교정 지시를 다음 시도에 보냈다.
                    logger.warning(
                        "Narration sentence rewrite attempt %s/3 missed the total length contract: "
                        "chars=%s (target=%s, need %s~%s)",
                        rewrite_attempt + 1, structured_chars, target_chars,
                        round(target_chars * 0.92), round(target_chars * 1.15),
                    )
                    direction = "줄이세요" if structured_chars > target_chars else "늘리세요"
                    correction = (
                        f"직전 응답은 총 {structured_chars}자였고 목표는 약 {target_chars}자입니다. "
                        f"문장 수({len(lines)}개)는 유지한 채 각 문장 길이를 조정해 총 분량을 {direction}.\n"
                    )
                    continue
                if too_few_scenes:
                    logger.warning(
                        "Narration sentence rewrite attempt %s/3 missed the scene-count contract: "
                        "scenes=%s (need >= %s)",
                        rewrite_attempt + 1, len(lines), minimum_scene_count,
                    )
                    correction = (
                        f"직전 응답은 {len(lines)}개 문장이었고 최소 {minimum_scene_count}개가 필요합니다. "
                        f"이번에는 반드시 {target_scene_count}개(최소 {minimum_scene_count}개 이상)를 채우세요. "
                        "문장을 억지로 합치지 말고, 원문의 완결된 생각 단위를 더 잘게 나누어 문장 수를 늘리세요.\n"
                    )
                else:
                    longest = max(_visible_char_count(line) for line in overlong_lines)
                    logger.warning(
                        "Narration sentence rewrite attempt %s/3 missed the per-sentence length contract: "
                        "%s line(s) over %s chars, longest=%s",
                        rewrite_attempt + 1, len(overlong_lines), _SENTENCE_HARD_CAP_CHARS, longest,
                    )
                    correction = (
                        f"직전 응답 중 {len(overlong_lines)}개 문장이 공백 제외 {_SENTENCE_HARD_CAP_CHARS}자를 넘었습니다(최대 {longest}자). "
                        f"모든 문장을 공백 제외 {_SENTENCE_TARGET_MIN_CHARS}~{_SENTENCE_TARGET_MAX_CHARS}자 안에서 완결되게 다시 나누세요.\n"
                    )
        except Exception as exc:
            logger.warning("Narration length rewrite unavailable: %s", exc)
        return script_body

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
            prompt_ko = f"거대한 폭풍우가 몰아치는 바다 한가운데, 튼튼한 닻을 내리고 흔들리지 않는 황금 배."
            prompt_en = "large golden ship anchoring firmly in a massive stormy ocean, huge waves, dark clouds, original 2D Korean editorial comic, bold ink outlines, cel shading"
            sections.append({
                "title": f"씬 {i+1}",
                "content": narration,
                "prompt_ko": prompt_ko,
                "prompt_en": prompt_en,
                "prompt": prompt_en,
                "pose": "pointing",
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
# 유틸 및 파싱 함수
# ──────────────────────────────────────────────────────────
_COMPARISON_NARRATIVE_MARKERS = ("vs", "VS", "대비", "대조", "비교", "차별", "격차")


def _is_comparison_narrative(keyword: str, sections: list[dict]) -> bool:
    """대본이 A vs B 대조 구조인지 표면 문구로만 판별한다(새 사실을 만들지 않음).

    참인 경우 썸네일이 chart_warning 대신 split_versus(좌우 대비 톤)를
    고른다. 대본 원문에 실제로 쓰인 단어만 보므로, 대조 여부를 새로
    추정·창작하지 않는다.
    """
    text = " ".join([str(keyword or "")] + [
        str(section.get("title") or section.get("content") or section.get("text") or "")
        for section in sections[:6]
    ])
    return any(marker in text for marker in _COMPARISON_NARRATIVE_MARKERS)


def _build_thumbnail_brief(keyword: str, sections: list[dict], verified_facts: list[dict]) -> dict:
    """Create a conservative thumbnail contract without inventing copy or data.

    The renderer accepts only a badge with a concrete `source_ref`; a missing
    verified value simply means no badge instead of a plausible-looking fake.
    """
    narrative_plan = build_from_video_manifest(
        keyword=keyword, sections=sections, verified_facts=verified_facts,
    )
    comparison_mode = _is_comparison_narrative(keyword, sections)
    source_scene_ids = list(narrative_plan.source_scene_ids)
    for index, scene in enumerate(sections[:8]):
        role = str(scene.get("phase") or scene.get("section") or "")
        if index == 0 or role in {"data", "scenario", "action", "conclusion"}:
            source_scene_ids.append(str(scene.get("scene_id") or scene.get("id") or index))
        if len(source_scene_ids) >= 3:
            break
    hook = str(keyword or "시장 핵심 이슈").strip()
    punch = "{y:지금 확인할 핵심}"
    badge: dict[str, str] = {}
    for index, fact in enumerate(verified_facts or []):
        value = str(fact.get("figure") or fact.get("value") or "").strip()
        if value and re.search(r"\d", value):
            badge = {"value": value, "source_ref": f"facts[{index}]"}
            break
    if bool(runtime_config.value("thumbnail_v2_enabled")):
        # A scene manifest resolves the actual asset after assembly.  v2 starts
        # with chart_warning because it needs no synthetic person or article.
        # The planner/gate may replace it with article_evidence when a reviewed
        # Korean evidence frame exists.
        return {
            "template": "chart_warning",
            "language": "ko-KR",
            "headline": [
                {
                    "text": hook[:16] or "시장 핵심 이슈",
                    "spans": [{"text": hook[:16] or "시장 핵심 이슈", "tone": "white"}],
                },
                {
                    "text": "지금 확인할 핵심",
                    "spans": [
                        {"text": "지금 확인할 ", "tone": "white"},
                        {"text": "핵심", "tone": "yellow", "scale": 1.08},
                    ],
                },
            ],
            "primary_subject": {"kind": "chart", "asset_id": "manifest_chart", "source_ref": "facts[0]" if verified_facts else None},
            "secondary_subject": {"allowed": False},
            "badge": ({"label": "핵심 수치", **badge} if badge else None),
            "source_scene_ids": source_scene_ids or ["0"],
            "editorial_overlays": [slot.model_dump() for slot in narrative_plan.overlays],
            "pattern_id": narrative_plan.pattern_id,
            "narrative_plan": narrative_plan.model_dump(),
            "verified_facts": verified_facts,
            "narration": _narration_from_sections(sections),
            "generated_from": "thumbnail_v2_contract",
            "comparison_mode": comparison_mode,
        }
    return {
        "layout": "reference_headline",
        "hook_line": "{y:" + hook + "}",
        "punch_line": punch,
        "badge": badge,
        "source_scene_ids": source_scene_ids or ["0"],
        "persons": [],
        "generated_from": "verified_script_contract_v1",
    }


def _narration_from_sections(sections: list[dict]) -> str:
    """Keep editorial scene metadata out of the downloadable TTS script."""
    return "\n\n".join(
        str(section.get("content") or section.get("text") or "").strip()
        for section in sections
        if str(section.get("content") or section.get("text") or "").strip()
    )


def _dedupe_adjacent_paragraphs(text: str) -> str:
    paragraphs: list[str] = []
    previous_key = ""
    for paragraph in re.split(r"\n{2,}", text or ""):
        cleaned = re.sub(r"\s+", " ", paragraph).strip()
        key = re.sub(r"[^0-9A-Za-z가-힣]", "", cleaned).lower()
        if cleaned and key and key != previous_key:
            paragraphs.append(cleaned)
            previous_key = key
    return "\n\n".join(paragraphs)


def _validate_keyword_coverage(script: str, terms: list[str]) -> dict:
    normalized_script = re.sub(r"\s+", "", script or "").lower()
    meaningful = _keyword_coverage_terms(terms)
    script_canonical = normalise_terms(script)

    # A grounded narration does not have to repeat the user's exact wording.
    # In market copy, for example, "급락" is commonly expressed as "큰 폭으로
    # 하락", "낙폭 확대", or "지수가 밀렸다".  The evidence gate above has
    # already verified the underlying facts, so this final gate should test
    # semantic coverage rather than force an unnatural keyword insertion.
    semantic_equivalents: dict[str, tuple[str, ...]] = {
        "급락": (
            "급락", "폭락", "하락", "낙폭", "내려", "빠졌", "빠진", "무너",
            "큰폭하락", "큰폭으로하락", "급격히하락", "가파르게하락", "지수가밀", "크게떨어",
        ),
        "반등": ("반등", "회복", "되돌림", "상승전환", "반전", "낙폭을만회", "다시올"),
        "급등": ("급등", "큰폭상승", "큰폭으로상승", "가파르게상승", "크게올"),
        "하락": ("하락", "내림", "떨어", "밀려", "약세", "낙폭"),
        "상승": ("상승", "오름", "올라", "강세", "반등"),
    }

    def covered(term: str) -> bool:
        compact = re.sub(r"\s+", "", term).lower()
        if compact in normalized_script or term in script_canonical:
            return True
        return any(alias in normalized_script for alias in semantic_equivalents.get(compact, ()))

    missing = [
        term for term in meaningful
        if not covered(term)
    ]
    # Count sentence-level topical relevance, not raw token repetition.
    sentences = [line.strip() for line in re.split(r"(?<=[.!?。])\s*|\n+", script or "") if line.strip()]
    related = sum(
        1 for sentence in sentences
        if any(
            re.sub(r"\s+", "", term).lower() in re.sub(r"\s+", "", sentence).lower()
            or term in normalise_terms(sentence)
            or any(alias in re.sub(r"\s+", "", sentence).lower() for alias in semantic_equivalents.get(term, ()))
            for term in meaningful
        )
    )
    ratio = related / len(sentences) if sentences else 0.0
    return {
        # Direct mentions are a conservative proxy for semantic relevance; the
        # prompt/fact gate enforces the stronger every-section relationship.
        # Verify all keyword terms are present in the script. Emitting a fixed sentence-level density check is too restrictive for longform scripts.
        "passed": not missing,
        "selected_terms": terms,
        "missing_terms": missing,
        "related_sentence_ratio": round(ratio, 3),
        "related_sentence_count": related,
        "sentence_count": len(sentences),
    }


def _validate_unit_usage(script: str) -> dict:
    """Reject common finance narration mistakes before they reach ElevenLabs."""
    errors: list[str] = []
    # The shared splitter keeps decimal points such as 4.53 inside a sentence.
    sentences = [re.sub(r"\s+", " ", item).strip() for item in split_sentences(script or "")]
    rate_labels = ("하락률", "상승률", "등락률", "수익률", "비중")
    for compact in sentences:
        if not compact:
            continue
        for label in rate_labels:
            label_at = compact.find(label)
            if label_at < 0:
                continue
            # "코스피가 463포인트, 하락률은 6.37퍼센트" is correct.
            # Only reject a point unit in the local predicate/value span.
            predicate_span = compact[label_at:label_at + len(label) + 20]
            if "포인트" in predicate_span or "pt" in predicate_span.lower():
                errors.append(f"비율 라벨 직후 포인트 단위 사용: {compact[:80]}")
        if re.search(r"\d+(?:\.\d+)?%", compact):
            errors.append(f"TTS 전처리 전 % 기호 잔존: {compact[:80]}")
    return {"passed": not errors, "errors": errors}


def _needs_dialogue_length_rewrite(script_body: str, target_chars: int) -> bool:
    """대사가 TTS 허용 범위를 벗어나면 LLM 편집을 한 번 요청한다."""
    if not script_body or target_chars <= 0:
        return False
    actual_chars = _dialogue_char_count(script_body)
    minimum = round(target_chars * 0.92)
    maximum = round(target_chars * 1.15)
    return actual_chars < minimum or actual_chars > maximum


def _cap_dialogue_to_target(script_body: str, target_chars: int) -> str:
    """Cap only [대사] content to the requested TTS duration budget.

    Visual prompts remain intact for image generation. The cap works at sentence
    boundaries where possible and keeps every scene instead of dropping a late
    section of the story.
    """
    if not script_body or target_chars <= 0:
        return script_body

    pattern = re.compile(
        r"(?ms)(\[대사\]\s*)(.*?)(?=^\s*\[(?:비주얼|감정)|^\s*##|\Z)"
    )
    matches = list(pattern.finditer(script_body))
    if not matches:
        return script_body

    original_counts = [_visible_char_count(match.group(2)) for match in matches]
    total = sum(original_counts)
    compaction_budget = target_chars
    if total <= compaction_budget:
        return script_body

    caps = [max(1, round(count * compaction_budget / total)) for count in original_counts]
    difference = compaction_budget - sum(caps)
    for idx in range(abs(difference)):
        position = idx % len(caps)
        if difference > 0:
            caps[position] += 1
        elif caps[position] > 1:
            caps[position] -= 1

    def shorten_dialogue(value: str, limit: int) -> str:
        text = re.sub(r"\s+", " ", value).strip()
        if _visible_char_count(text) <= limit:
            return text
        kept: list[str] = []
        for sentence in split_sentences(text):
            sentence = sentence.strip()
            if not sentence:
                continue
            candidate = " ".join([*kept, sentence]).strip()
            if _visible_char_count(candidate) <= limit:
                kept.append(sentence)
            else:
                # Never cut a numeric token (or any sentence) to meet a
                # character quota. A single over-budget sentence is safer than
                # broadcasting a false number; the caller already attempted a
                # one-pass LLM rewrite before reaching this deterministic cap.
                if not kept:
                    kept.append(sentence)
                break
        return " ".join(kept).strip() or text

    shortened_values = [
        shorten_dialogue(match.group(2), cap)
        for match, cap in zip(matches, caps)
    ]
    # Per-scene proportional caps can undershoot badly when every scene has
    # two medium sentences: one fits, two exceed the local share. Fill the
    # remaining *global* budget with whole next sentences while retaining at
    # least one sentence from every scene.
    lower_bound = round(target_chars * 0.92)
    upper_bound = round(target_chars * 1.08)
    current_total = sum(_visible_char_count(value) for value in shortened_values)
    made_progress = True
    while current_total < lower_bound and made_progress:
        made_progress = False
        for index, match in enumerate(matches):
            original_sentences = [item.strip() for item in split_sentences(match.group(2)) if item.strip()]
            selected_sentences = [item.strip() for item in split_sentences(shortened_values[index]) if item.strip()]
            if len(selected_sentences) >= len(original_sentences):
                continue
            addition = original_sentences[len(selected_sentences)]
            addition_size = _visible_char_count(addition)
            if current_total + addition_size <= upper_bound:
                shortened_values[index] = f"{shortened_values[index]} {addition}".strip()
                current_total += addition_size
                made_progress = True
                if current_total >= lower_bound:
                    break

    value_iter = iter(shortened_values)

    def replace(match: re.Match) -> str:
        return match.group(1) + next(value_iter) + "\n"

    compacted = pattern.sub(replace, script_body)
    compacted_total = sum(_visible_char_count(match.group(2)) for match in pattern.finditer(compacted))
    logger.warning(
        "Narration capped for target duration: %s -> %s chars (target=%s, budget=%s)",
        total, compacted_total, target_chars, compaction_budget,
    )
    return compacted


def _visible_char_count(value: str) -> int:
    return len(re.sub(r"\s+", "", value or ""))


def _parse_dialogue_sentence_array(value: str) -> list[str]:
    """재편집 호출의 JSON 배열 응답만 허용한다."""
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    decoder = json.JSONDecoder()
    # 설명 문구에 [대사] 같은 대괄호가 있어도 실제 JSON 배열을 놓치지 않도록
    # 모든 '[' 위치에서 JSON 디코딩을 시도한다.
    for start in (index for index, char in enumerate(text) if char == "["):
        try:
            parsed, _ = decoder.raw_decode(text[start:])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
            return [re.sub(r"\s+", " ", item).strip() for item in parsed if item and item.strip()]
    return []


def _structured_script_from_dialogue_lines(lines: list[str]) -> str:
    """대사 배열을 기존 씬 파서가 소비하는 구조로만 감싼다."""
    blocks = []
    for index, line in enumerate(lines, start=1):
        blocks.append(
            f"## 장면 {index:03d}\n"
            f"[대사]\n{line}\n"
            "[비주얼 설명]\n대사 의미를 설명하는 한국형 금융 상황 장면\n"
            "[비주얼 프롬프트]\n\n"
            "[감정]\nneutral"
        )
    return "\n\n".join(blocks)


def _dialogue_char_count(script_body: str) -> int:
    pattern = re.compile(r"(?ms)\[대사\]\s*(.*?)(?=^\s*\[(?:비주얼|감정)|^\s*##|\Z)")
    matches = list(pattern.finditer(script_body or ""))
    if not matches:
        return _visible_char_count(script_body)
    return sum(_visible_char_count(match.group(1)) for match in matches)


def _calc_scene_count(target_minutes: int) -> int:
    """목표 분량별 씬(이미지) 수 계산 — 5~6초/씬 기준
    
    1.3x 배속 TTS 기준:
    - 1분(60초) / 5.5초 = 약 11씬
    - 5분(300초) / 5.5초 = 약 55씬
    - 10분(600초) / 5.5초 = 약 109씬
    - 15분(900초) / 5.5초 = 약 164씬
    - 20분(1200초) / 5.5초 = 약 218씬
    """
    secs_per_scene = SCENE_DURATION_SEC
    total_seconds = target_minutes * 60
    return max(1, round(total_seconds / secs_per_scene))


def get_character_pose_from_text(text: str) -> str:
    # worried
    if any(k in text for k in ["위험", "폭락", "급락", "우려", "손실", "적자", "하락", "부담", "리스크", "경고", "피해", "하락세", "부진", "타격", "악재", "부정"]):
        return "worried"
    # surprised
    if any(k in text for k in ["충격", "경악", "놀라운", "믿기 힘든", "사상 최대", "역대급", "이례적", "깜짝", "기습", "돌발"]):
        return "surprised"
    # happy / success
    if any(k in text for k in ["폭등", "급등", "상승", "호재", "이익", "성장", "성공", "기회", "긍정", "수익", "돌파", "반등", "급등세", "최고치"]):
        return "happy"
    # highlight / emphasis
    if any(k in text for k in ["핵심", "중요", "주목", "기억", "강조", "포인트", "집중", "특별", "바로", "이것", "목표"]):
        return "pointing"
    # neutral
    return "neutral"


def clean_script_commas_and_pct(text: str) -> str:
    if not text:
        return ""
    # % is a percentage, never an index point change.
    text = re.sub(r'(\d+(?:\.\d+)?)\s*%', r'\1퍼센트', text)
    # Remove all grouped thousands separators, including 29,800,000.
    while re.search(r'\d,\d{3}', text):
        text = re.sub(r'(\d),(\d{3})', r'\1\2', text)
    return text


def _split_sections_for_visual_pacing(sections: list, max_chars: int = _SENTENCE_HARD_CAP_CHARS) -> list:
    """Cap each generated sentence at the short-sentence hard limit.

    2026-08-05: sentences are now generated short (15-20 visible chars) on
    purpose, so this mostly passes them through unchanged; it only combines
    or caps the rare case where the LLM still wrote something longer. The
    actual 5-6 second on-screen grouping happens later in
    pace_sections_for_runtime, which buckets these short sentences by real
    character-per-second rate regardless of how short each one is.
    """
    expanded: list[dict] = []
    for source in sections:
        text = re.sub(r"\s+", " ", str(source.get("content") or "")).strip()
        if not text:
            continue
        sentences = [piece.strip() for piece in re.split(r"(?<=[.!?])\s+", text) if piece.strip()]
        if not sentences:
            sentences = [text]

        units: list[str] = []
        current = ""
        for sentence in sentences:
            # 대사·TTS·자막은 완결 문장을 공유한다. 화면 수를 맞춘다는 이유로
            # 문장을 단어 경계에서 자르면 의미와 싱크가 모두 깨지므로 금지한다.
            candidate = sentence
            proposed = f"{current} {candidate}".strip()
            if current and len(proposed.replace(" ", "")) > max_chars:
                units.append(current)
                current = candidate
            else:
                current = proposed
        if current:
            units.append(current)

        for part_index, unit in enumerate(units, start=1):
            scene = dict(source)
            scene["content"] = unit
            scene["text"] = unit
            scene["char_count"] = len(unit)
            if len(units) > 1:
                scene["title"] = f"{source.get('title', 'Scene')} · {part_index}"
            expanded.append(scene)

    total = len(expanded)
    for index, scene in enumerate(expanded):
        scene["section"] = _assign_section_type(index, total)
    return expanded


def _minimum_scene_count(target_scene_count: int) -> int:
    """5~6초 장면 계약의 최소 허용 장면 수를 반환한다.

    2026-08-04, job 147에서 반복 재현: target=55일 때 Claude가 49, 52, 52로
    거듭 undershoot했다. 이전에는 고정 "-2"(target 대비 96%)를 요구했는데,
    이 고정치는 영상 길이가 길수록 상대적으로 훨씬 빡빡해진다(target=55일
    때 -2=96%지만 target=218인 20분 영상에서는 -2=99%). 실측 undershoot가
    관측된 지금, 목표치의 90%로 완화한다 — 이 최소치에서도 평균 장면 길이는
    5~6초 계약의 상한(6.0초) 안에 머문다(300초/50장면=6.0초). 문장을 억지로
    잘라 장면 수를 채우지 않는다는 규칙(_split_sections_for_visual_pacing)은
    그대로 유지되며, 이 함수는 LLM이 실제로 써낸 완결 문장 수를 얼마나
    관대하게 받아들일지만 조정한다.
    """
    return max(1, round(target_scene_count * 0.90))


def _validate_scene_delivery(sections: list[dict], target_scene_count: int) -> None:
    """짧은 완결 문장 기준의 목표 문장 수와 길이를 생성 단계에서 강제한다."""
    minimum_scene_count = _minimum_scene_count(target_scene_count)
    if len(sections) < minimum_scene_count:
        raise ValueError(
            f"장면 수가 목표에 부족합니다: actual={len(sections)}, "
            f"minimum={minimum_scene_count}, target={target_scene_count}"
        )
    overlong = [
        len(re.sub(r"\s+", "", str(scene.get("content") or "")))
        for scene in sections
        if len(re.sub(r"\s+", "", str(scene.get("content") or ""))) > _SENTENCE_HARD_CAP_CHARS
    ]
    if overlong:
        raise ValueError(f"완결 문장 길이가 {_SENTENCE_HARD_CAP_CHARS}자를 초과합니다: max={max(overlong)}")


def _parse_sections(full_text: str, evidence: dict | None = None) -> list:
    """## 씬 제목 또는 ## 섹션명 기준으로 분리하고, 대사/한국어 설명/영어 프롬프트/감정 포즈를 추출합니다."""
    parts = re.split(r'(?m)^##\s*(.+)$', full_text)
    raw_sections = []

    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            title = parts[i].strip()
            if any(k in title for k in ["메타데이터", "추천", "유튜브", "Shorts", "쇼츠"]):
                continue
            raw_content = parts[i + 1].strip()
            
            # [대사] 추출
            content_match = re.search(r'\[대사\]\s*(.*?)(?=\[비주얼 설명|$|\[비주얼 프롬프트|\[감정)', raw_content, re.DOTALL)
            content = content_match.group(1).strip() if content_match else ""
            if not content:
                content = re.sub(r'\[비주얼 설명.*$', '', raw_content, flags=re.DOTALL).strip()
                content = re.sub(r'\[비주얼 프롬프트.*$', '', content, flags=re.DOTALL).strip()
                content = re.sub(r'\[감정.*$', '', content, flags=re.DOTALL).strip()
                content = re.sub(r'\[대사\]', '', content).strip()
            
            # 대사와 수치 가공 (콤마 제거, % -> 포인트)
            content = clean_script_commas_and_pct(content)
            
            # [비주얼 설명 (한국어)] 추출
            prompt_ko_match = re.search(r'\[비주얼 설명\s*(?:\(한국어\))?\]\s*(.*?)(?=\[비주얼 프롬프트|$|\[감정|\[대사)', raw_content, re.DOTALL)
            prompt_ko = prompt_ko_match.group(1).strip() if prompt_ko_match else ""
            
            # [비주얼 프롬프트 (영어)] 추출
            prompt_en_match = re.search(r'\[비주얼 프롬프트\s*(?:\(영어\))?\]\s*(.*?)(?=\[감정|$|\[대사|\[비주얼 설명)', raw_content, re.DOTALL)
            prompt_en = prompt_en_match.group(1).strip() if prompt_en_match else ""
            
            # [감정] 추출
            pose_match = re.search(r'\[감정\]\s*(.*?)(?=\[대사|$|\[비주얼 설명|\[비주얼 프롬프트|\[모션|\[말풍선)', raw_content, re.DOTALL)
            pose = pose_match.group(1).strip() if pose_match else "neutral"
            pose = re.sub(r'[^a-zA-Z]', '', pose).lower()
            if pose not in ["happy", "worried", "surprised", "pointing", "thinking", "explaining", "neutral"]:
                # Fallback to keyword matching from narration if LLM gave invalid pose
                pose = get_character_pose_from_text(content)

            # [모션] 추출
            motion_match = re.search(r'\[모션\]\s*(.*?)(?=\[대사|$|\[비주얼 설명|\[비주얼 프롬프트|\[감정|\[말풍선)', raw_content, re.DOTALL)
            motion_type = motion_match.group(1).strip().lower() if motion_match else ""
            if motion_type not in ["chart_shock", "pointing_explain", "thinking_desk", "walking_intro", "celebration"]:
                motion_type = ""

            # [말풍선] 추출
            bubble_match = re.search(r'\[말풍선\]\s*(.*?)(?=\[대사|$|\[비주얼 설명|\[비주얼 프롬프트|\[감정|\[모션)', raw_content, re.DOTALL)
            bubble_text = bubble_match.group(1).strip() if bubble_match else ""
            bubble_validation = validate_verbatim(bubble_text, evidence)
            scene_rejected = bool(bubble_text and not bubble_validation.passed)
            if scene_rejected:
                logger.warning(
                    "scene '%s' rejected: bubble text is not evidence-grounded (%s)",
                    title, ", ".join(bubble_validation.reasons),
                )

            raw_sections.append({
                "title": title,
                "content": content,
                "prompt_ko": prompt_ko or content,
                "prompt_en": prompt_en,
                "pose": pose,
                "motion_type": motion_type,
                "bubble_text": bubble_text,
                "bubble_validation": {
                    "passed": bubble_validation.passed,
                    "reasons": bubble_validation.reasons,
                    "matched_sources": bubble_validation.matched_sources,
                    "numeric_tokens": bubble_validation.numeric_tokens,
                },
                "scene_rejected": scene_rejected,
            })

    if not raw_sections:
        raw_sections.append({
            "title": "인트로",
            "content": full_text.strip(),
            "prompt_ko": full_text.strip(),
            "prompt_en": "Abstract financial chart background, professional finance news studio, dark navy blue background",
            "pose": "neutral",
            "motion_type": "walking_intro",
            "bubble_text": "",
            "bubble_validation": {"passed": True, "reasons": [], "matched_sources": [], "numeric_tokens": []},
            "scene_rejected": False,
        })

    total = len(raw_sections)
    sections = []
    for idx, s in enumerate(raw_sections):
        section_type = _assign_section_type(idx, total)
        prompt_en = s["prompt_en"]
        if not prompt_en:
            prompt_en = f"Financial editorial scene representing {s['title']}, dark navy tone, original 2D Korean comic, bold ink outlines, cel shading"

        section = {
            "title": s["title"],
            "content": s["content"],
            "prompt_ko": s["prompt_ko"],
            "prompt_en": prompt_en,
            "prompt": prompt_en,  # Backward compatibility
            "pose": s["pose"],
            "motion_type": s["motion_type"],
            "bubble_text": s["bubble_text"],
            "bubble_validation": s.get("bubble_validation", {"passed": True}),
            "scene_rejected": bool(s.get("scene_rejected")),
            "section": section_type,
            "char_count": len(s["content"]),
        }
        # 대본 문구는 TTS·ASS 자막의 단일 원본으로만 쓴다. 영상 위 요약칩과
        # 말풍선은 프레임 밖 UI처럼 보이고 자막과 중복되므로 계획하지 않는다.
        bubble = str(s.get("bubble_text") or "").strip()
        if bubble:
            section["editorial_decision"] = {
                "selected": False,
                "reason": "script_caption_only_policy",
                "suppressed_non_subtitle_overlay": True,
            }
        sections.append(section)

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


SCENE_TYPES = {"general", "metric", "graph", "diagram", "text"}

# 장면 유형은 검증된 대본과 이미 작성된 시각 의도만 보고 결정한다. 이 규칙은
# 수치·등락률을 만들거나 사실 여부를 판단하지 않으며, 이후 단계가 어떤 무대를
# 선택해야 하는지 설명 가능한 신호만 남긴다.
_GRAPH_SIGNALS = (
    "차트", "그래프", "추이", "타임라인", "그래프", "막대", "선 그래프",
    "chart", "graph", "trend", "timeline", "bar chart", "line chart",
)
_DIAGRAM_SIGNALS = (
    "공급망", "흐름도", "구조", "단계", "과정", "경로", "인과", "연결",
    "supply chain", "flow", "process", "structure", "diagram", "causal",
)
_METRIC_SIGNALS = (
    "지수", "종가", "고점", "저점", "시가총액", "등락", "변동률", "낙폭", "비율", "규모",
    "index", "close", "high", "low", "market cap", "change", "percent", "rate",
)
_TEXT_SIGNALS = (
    "뜻", "의미", "정의", "용어", "핵심 문구", "한마디", "요약",
    "definition", "meaning", "term", "key phrase", "quote", "summary",
)


def _scene_type_source_text(scene: dict) -> str:
    """분류 근거가 된 기존 대본·시각 의도 텍스트만 합친다."""
    fields = ("title", "content", "text", "prompt_ko", "prompt_en", "visual_intent")
    return "\n".join(str(scene.get(field) or "") for field in fields).lower()


def _has_any_signal(text: str, signals: tuple[str, ...]) -> bool:
    return any(signal in text for signal in signals)


def _classify_scene_type(scene: dict) -> tuple[str, str]:
    """한 장면의 표현 목적과 사람이 읽을 수 있는 선택 근거를 반환한다."""
    text = _scene_type_source_text(scene)
    section = str(scene.get("section") or "").lower()

    # 이 페이로드는 수집기에서 확인된 시계열·비교 데이터만 담는다. 원고의
    # 표현 문구와 무관하게 렌더링될 실제 그래프가 있으므로 그래프형이 우선이다.
    if isinstance(scene.get("market_chart"), dict) and scene["market_chart"]:
        return "graph", "검증된 market_chart 페이로드가 있어 그래프형으로 분류"
    if _has_any_signal(text, _GRAPH_SIGNALS):
        return "graph", "대본 또는 기존 시각 의도에 차트·추이·시간축 표현이 있어 그래프형으로 분류"
    if _has_any_signal(text, _DIAGRAM_SIGNALS):
        return "diagram", "대본 또는 기존 시각 의도에 흐름·구조·단계 관계가 있어 다이어그램형으로 분류"
    if re.search(r"\d", text) or _has_any_signal(text, _METRIC_SIGNALS) or section == "data":
        return "metric", "대본에 검증 대상 수치·등락·규모 표현이 있어 지표형으로 분류"
    if _has_any_signal(text, _TEXT_SIGNALS):
        return "text", "대본에 정의·핵심 문구 중심 설명이 있어 텍스트형으로 분류"
    return "general", "수치·그래프·구조·핵심 문구 신호가 없어 일반 설명형으로 분류"


def _classify_scene_types(sections: list[dict]) -> list[dict]:
    """모든 씬에 표준 scene_type과 근거를 기록한다.

    이 단계는 이미지 프롬프트, V5 archetype, 오버레이 또는 영상 조립을 바꾸지
    않는다. 다음 설계 단계에서 동일한 계약을 소비할 수 있도록 대본 메타데이터에
    분류 결과만 남긴다.
    """
    classified: list[dict] = []
    for original in sections:
        scene = dict(original)
        scene_type, selection_reason = _classify_scene_type(scene)
        if scene_type not in SCENE_TYPES:
            raise ValueError(f"지원하지 않는 scene_type: {scene_type}")
        scene["scene_type"] = scene_type
        scene["selection_reason"] = selection_reason
        classified.append(scene)
    return _rebalance_scene_type_distribution(classified)


def _rebalance_scene_type_distribution(scenes: list[dict]) -> list[dict]:
    """장문 대본에서 지표형 장면이 과도하게 연속되는 것을 막는다.

    숫자가 포함된 문장은 금융 대본에 매우 흔하다. 숫자 유무만으로 분류하면
    계기판·차트 같은 정보형 화면이 대부분을 차지해 시청 경험이 단조로워진다.
    사실·대본 문구는 수정하지 않고, 지표형으로 남길 장면만 시간축에 고르게
    배치한다. 나머지는 동일 문장을 상황·비유 중심의 일반 장면으로 렌더한다.
    """
    def _keep_evenly(indices: list[int], limit: int) -> set[int]:
        """같은 정보형 화면이 한 구간에 몰리지 않도록 시간축에 분산한다."""
        if len(indices) <= limit:
            return set(indices)
        return {
            indices[round(position * (len(indices) - 1) / (limit - 1))]
            for position in range(limit)
        }

    metric_indices = [index for index, scene in enumerate(scenes)
                      if scene.get("scene_type") == "metric"]
    # 지표형은 최대 18%, 장문에서도 12장을 넘기지 않는다. 최소 두 장은 남겨
    # 실제 수치·지표를 설명해야 하는 구간을 보존한다.
    metric_limit = min(12, max(2, round(len(scenes) * 0.18)))
    kept_metric_indices = _keep_evenly(metric_indices, metric_limit)
    for index in metric_indices:
        if index in kept_metric_indices:
            continue
        scenes[index]["scene_type"] = "general"
        scenes[index]["selection_reason"] = (
            "수치가 포함돼 있으나 장문 지표형 비중 상한을 적용해 "
            "상황·비유 중심 일반 장면으로 분류"
        )

    # 관계·단계를 설명하는 장면도 과도하면 칠판이나 프로세스 도식이 연속된다.
    # 정보형은 전체의 10%(최대 8장)만 남기고, 나머지는 기사·상황·비유 장면으로
    # 전환한다. 원문과 검증 사실은 그대로 보존한다.
    diagram_indices = [index for index, scene in enumerate(scenes)
                       if scene.get("scene_type") == "diagram"]
    diagram_limit = min(8, max(2, round(len(scenes) * 0.10)))
    kept_diagram_indices = _keep_evenly(diagram_indices, diagram_limit)
    for index in diagram_indices:
        if index in kept_diagram_indices:
            continue
        scenes[index]["scene_type"] = "general"
        scenes[index]["selection_reason"] = (
            "관계 설명이 포함돼 있으나 장문 다이어그램형 비중 상한을 적용해 "
            "기사·상황 중심 일반 장면으로 분류"
        )
    return scenes


def _attach_verified_index_overlays(sections: list[dict], market_data: dict) -> list[dict]:
    """Attach cards only to data scenes backed by a collected market snapshot."""
    if not isinstance(market_data, dict):
        return sections
    kr_index = ((market_data.get("kr") or {}).get("index") or {})
    us_index = ((market_data.get("us") or {}).get("index") or {})
    for scene in sections:
        if str(scene.get("section") or "").lower() != "data":
            continue
        text = str(scene.get("content") or scene.get("text") or "").lower()
        candidates = []
        if any(token in text for token in ("kosdaq", "코스닥")):
            candidates.append(("코스닥", kr_index.get("kosdaq"), "kr"))
        if any(token in text for token in ("sp500", "s&p", "s&p500")):
            candidates.append(("S&P 500", us_index.get("sp500"), "us"))
        if any(token in text for token in ("nasdaq", "나스닥")):
            candidates.append(("NASDAQ", us_index.get("nasdaq"), "us"))
        candidates.extend([("코스피", kr_index.get("kospi"), "kr"), ("S&P 500", us_index.get("sp500"), "us")])
        for label, raw, market in candidates:
            if not isinstance(raw, dict) or raw.get("close") is None or raw.get("change_pct") is None:
                continue
            close = float(raw["close"])
            change_pct = float(raw["change_pct"])
            change = float(raw.get("change", close * change_pct / 100.0))
            scene["index_data"] = {
                "name": label,
                "value": close,
                "change": change,
                "change_pct": change_pct,
                "market": market,
                "verified": True,
                "source": "market_snapshot",
            }
            scene["overlay_placement"] = {"mode": "anchor", "anchor": "top_right", "margin": 40}
            direction = dict(scene.get("art_direction") or {})
            direction["overlay_strategy"] = "index_card"
            scene["art_direction"] = direction
            break
    return sections


def _validate_info_scene_payloads(sections: list[dict]) -> list[dict]:
    """v4 다이어그램 입력을 검증 사실과 출처가 있는 항목으로만 제한한다."""
    limits = {"stage_items": (2, 4), "causal_nodes": (2, 5), "structure_items": (2, 3)}
    for scene in sections:
        chart = scene.get("market_chart") or {}
        source_ref = str(chart.get("source_ref") or chart.get("source") or "")
        for key, (minimum, maximum) in limits.items():
            cleaned = []
            for raw in list(scene.get(key) or [])[:maximum]:
                if not isinstance(raw, dict) or not str(raw.get("label") or "").strip():
                    continue
                refs = [str(value) for value in raw.get("source_refs") or [] if str(value)] or ([source_ref] if source_ref else [])
                if not refs:
                    continue
                cleaned.append({"label": str(raw["label"])[:24], "value": raw.get("value"), "state": raw.get("state"), "emphasis": bool(raw.get("emphasis")), "source_refs": refs})
            if cleaned:
                if not minimum <= len(cleaned) <= maximum:
                    raise ValueError(f"{key} 항목 수가 v4 계약 범위를 벗어났습니다")
                scene[key] = cleaned
        rates = []
        for raw in list(chart.get("external_rates") or [])[:3]:
            if not isinstance(raw, dict) or not raw.get("label") or raw.get("value") is None:
                continue
            refs = [str(value) for value in raw.get("source_refs") or [] if str(value)] or ([source_ref] if source_ref else [])
            if refs:
                rates.append({"label": str(raw["label"])[:24], "value": str(raw["value"])[:18], "emphasis": bool(raw.get("emphasis")), "source_refs": refs})
        if rates:
            chart["external_rates"] = rates
            scene["market_chart"] = chart
    return sections


def _attach_verified_market_charts(sections: list[dict], max_charts: int = 12) -> list[dict]:
    """Attach a small, evenly-spaced set of narrative data visuals only.

    The illustration model never receives exact chart values.  A chart payload
    is created solely from the collector's closing-price series and is later
    rendered by matplotlib/FFmpeg.  Keeping the chart budget bounded protects
    long-form assembly throughput while still placing evidence throughout a
    20-minute video.
    """
    candidates: list[tuple[int, int, dict]] = []
    for index, scene in enumerate(sections):
        chart = extract_market_chart(scene)
        if chart:
            text = str(scene.get("content") or scene.get("text") or "")
            lower = text.lower()
            # Prefer scenes that make a concrete claim, while still keeping
            # selections distributed through the finished video.
            score = 10 + (25 if any(char.isdigit() for char in text) else 0)
            score += 15 if any(token in lower for token in ("상승", "하락", "급등", "급락", "등락", "비교", "대비", "비중", "점유", "계약", "순위")) else 0
            candidates.append((index, score, chart))
    if not candidates:
        return sections

    # Roughly one data-rich visual per 18 scenes (about 90 seconds), with a
    # hard cap of 12.  A 17-minute video therefore receives about 10, while
    # a 20-minute video receives at most 12 rather than 200+ slow data scenes.
    proportional_budget = max(1, round(len(sections) / 18))
    budget = min(int(max_charts), proportional_budget, len(candidates))
    if budget == len(candidates):
        selected = candidates
    else:
        selected = []
        for bucket in range(budget):
            start = round(bucket * len(candidates) / budget)
            end = round((bucket + 1) * len(candidates) / budget)
            selected.append(max(candidates[start:max(start + 1, end)], key=lambda item: item[1]))

    for index, _, chart in selected:
        chart = dict(chart)
        text = str(sections[index].get("content") or sections[index].get("text") or "").lower()
        authored_kind = str(chart.get("visual_kind") or "")
        if authored_kind in {"supply_flow", "stock_movers"}:
            chart["visual_kind"] = authored_kind
        elif any(token in text for token in ("상승", "하락", "급등", "급락", "등락")):
            chart["visual_kind"] = "change_arrow"
        elif any(token in text for token in ("비중", "점유", "구성")) and chart.get("market_cap_pie"):
            chart["visual_kind"] = "composition_pie"
        elif any(token in text for token in ("비교", "대비", "vs")):
            chart["visual_kind"] = "comparison"
        else:
            chart["visual_kind"] = "trend_dashboard"
        direction = dict(sections[index].get("art_direction") or {})
        family = str(direction.get("family") or "")
        # The data renderer inherits the physical prop chosen by the art
        # director.  A monitor can use a dark panel, but clipboards, map
        # clouds, tags and desk reports are paper-like.  This prevents every
        # factual scene from collapsing into the former fixed chalkboard.
        surface_kind = str(direction.get("data_surface_kind") or "")
        theme_by_surface = {
            "monitor": "factory_panel",
            "trading_ticket": "factory_panel",
            "inspection_clipboard": "paper_poster",
            "ledger_card": "paper_poster",
            "desk_report": "paper_poster",
            "map_cloud": "paper_poster",
            "product_label": "paper_poster",
            "scene_card": "paper_poster",
        }
        if chart["visual_kind"] == "supply_flow":
            chart["visual_theme"] = "paper_poster"
        elif chart["visual_kind"] == "stock_movers":
            chart["visual_theme"] = "factory_panel"
        elif surface_kind:
            chart["visual_theme"] = theme_by_surface.get(surface_kind, "paper_poster")
        elif family in {"industry_environment", "factory_dashboard"}:
            chart["visual_theme"] = "factory_panel"
        else:
            chart["visual_theme"] = "paper_poster"
        # Phase 2 F6: a data scene that naturally uses a chalkboard receives
        # one full deterministic explainer board, never model-generated marks.
        if chart["visual_theme"] == "chalkboard" and chart["visual_kind"] == "trend_dashboard":
            chart["visual_kind"] = "chalkboard_explainer"
        chart.update({"verified": True, "source": "market_snapshot.chart_series"})
        # Image copy is planned from the same verified payload as TTS, but it
        # is not narration duplicated onto a board. The renderer receives one
        # bounded hero fact plus its provenance before any image is generated.
        chart["hero_stat"] = hero_stat_from_chart(chart).model_dump()
        sections[index]["embedded_copy"] = [{
            "text": chart["hero_stat"]["meaning_line"],
            "claim_type": "derived_hook",
            "source_refs": list(chart["hero_stat"]["source_refs"]),
        }]
        # A chart emphasis is opt-in from the semantic claim, then its exact
        # screen position is derived by longform_worker from the final chart
        # surface and verified data coordinates.  No LLM emits pixel values.
        chart["focus"] = {
            "enabled": chart["visual_kind"] not in {"supply_flow", "stock_movers"} and any(token in text for token in ("상승", "하락", "급등", "급락", "등락", "돌파", "최고", "최저", "반등")),
            "target": "latest_verified_point",
        }
        source_ref = str(chart.get("source_ref") or f"market_snapshot.chart_series.{chart['series_key']}")
        plan_kind = chart_kind_from_visual_kind(chart["visual_kind"])
        data_plan = DataOverlayPlan(
            chart_kind=plan_kind,
            primary_metric=str(chart["label"]),
            unit=("원" if chart["visual_kind"] == "supply_flow" else "%" if chart["visual_kind"] == "stock_movers" else "pt"),
            source_refs=[source_ref],
            comparison_basis="동일 수집 기준일" if plan_kind == "comparison" else None,
            focus_target=(
                "largest_slice" if plan_kind == "composition"
                else "larger_bar" if plan_kind == "comparison"
                else "latest_point"
            ),
            callout=CopyClaim(
                text="이 흐름이 핵심",
                claim_type="derived_hook",
                source_refs=[source_ref],
            ),
            subtitle_emphasis_ref=source_ref,
            date_stamp_ref="market_chart.source_date",
        )
        sections[index]["data_overlay_plan"] = data_plan.model_dump()
        sections[index]["market_chart"] = chart
        # The old KOSPI corner card is a HUD, not part of the cartoon scene.
        # An integrated display replaces it for these selected key scenes.
        sections[index].pop("index_data", None)
        # The image prompt and FFmpeg compositor share this semantic anchor.
        # Prefer the selected in-world prop; the legacy theme rect is only a
        # fallback for older scene plans that predate surface selection.
        surfaces = {
            "factory_panel": {
                "anchor": "right_factory_panel",
                "x": 1010, "y": 155, "width": 720, "height": 500,
            },
            "paper_poster": {
                "anchor": "right_paper_poster",
                "x": 1130, "y": 175, "width": 590, "height": 570,
            },
            "chalkboard": {
                "anchor": "right_chalkboard",
                "x": 980, "y": 150, "width": 760, "height": 520,
            },
        }
        direction["data_surface"] = direction.get("data_surface") or surfaces.get(chart["visual_theme"], surfaces["paper_poster"])
        direction["overlay_strategy"] = "integrated_verified_data_visual"
        sections[index]["art_direction"] = direction
    return sections


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
