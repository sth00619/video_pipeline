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
from app.utils.quality_gate import enrich_scene_plans, assess_scene_plan
from app.utils.art_direction import direct_scenes, assess_art_diversity
from app.utils.market_charts import extract_market_chart
from app.utils.script_style import (
    DEFAULT_SCRIPT_STYLE_PROFILE,
    assess_storytelling,
    get_script_style_guide,
)

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
SCRIPT_SYSTEM_PROMPT = """당신은 한국 금융 콘텐츠를 위한 오리지널 대본 작가입니다.

특정 채널·작가의 고유한 말투, 반복 문구, 문장 구조를 모방하지 않습니다. 아래의
편집 원칙과 별도로 제공되는 오리지널 스토리텔링 프로필을 사용합니다.

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
- 숫자와 기호는 천단위 콤마(,)를 절대 사용하지 말고(예: 2783포인트, 6806포인트), 퍼센트(%) 기호는 스크립트 대사에서 반드시 '퍼센트' 또는 '포인트'라는 한글 단어로 풀어서 작성하세요(예: 1.2퍼센트, 1.2포인트, 2억 5800만 주).
- 문장 중간에 쉼표로 끊지 말고, 마침표로 완전히 종결하세요

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
- 배경 이미지들이 전체적으로 일관성을 갖도록 "professional 3D render, vibrant colors, comic art style, no text, no letters, no words, no UI elements" 키워드를 프롬프트 끝에 항상 포함하세요.
- 각 헤더 아래에는 다음 네 개의 태그를 사용해 내용을 채우세요:
  1. [대사] : 실제 한국어로 낭독할 대사 텍스트
  2. [비주얼 설명 (한국어)] : 화면에 보여줄 구체적인 상황과 은유적 배경에 대한 설명 (한국어)
  3. [비주얼 프롬프트 (영어)] : AI 이미지 생성기용 영어 프롬프트 (오직 배경/분위기/객체만 묘사, 캐릭터 묘사 금지 + 공통 스타일/네거티브 키워드 추가)
  4. [감정] : 상황에 맞는 캐릭터 표정/포즈 (happy / worried / surprised / pointing / thinking / explaining / neutral 중 하나)

예시:
## 씬 1: 실적 발표와 주가 하락

[대사]
실적이 사상 최대인데도 주가는 떨어집니다. 투자자들은 당황스럽죠.

[비주얼 설명 (한국어)]
'사상 최대 실적'이라 적힌 모니터 화면 밖으로 붉은색 하락 화살표가 모니터를 깨고 튀어나오는 상황. 

[비주얼 프롬프트 (영어)]
giant red downward arrow smashing out of a glowing computer monitor that displays high green numbers, high-tech trading room environment, shattered glass, dynamic lighting, professional 3D render, vibrant colors, comic art style

[감정]
surprised

절대 금지사항:
- 확정적 미래 예측 ("반드시 오릅니다" 등) 금지
- 특정 종목에 대한 직접적인 매수/매도 지시 금지
- <verified_facts>에 없는 수치나 날짜 창작 금지

🎯 영상 메타데이터 (대본 작성이 모두 끝난 후 마지막에 딱 1번만 작성):
## 메타데이터
[추천 제목]: 클릭을 유도하는 매력적인 유튜브 제목 (30자 내외)
[추천 썸네일]: 썸네일용 비주얼 프롬프트 (영어, 극적이고 시선을 끄는 상황 묘사, professional 3D render)
[더보기 설명]: 영상 하단에 들어갈 3줄 요약과 해시태그"""


class ScriptWorker:

    def __init__(self):
        self.collector = MarketDataCollector()

    def _call_llm_with_fallback(self, system_prompt: str, messages: list, max_tokens: int = 4000) -> str:
        """Claude API를 먼저 호출하고, 크레딧 부족 등 실패 시 Gemini API로 자동 폴백합니다."""
        # 1. Claude 시도
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            try:
                from anthropic import Anthropic
                from app.utils.anthropic_cache import cached_system, log_cache_usage
                client = Anthropic(api_key=anthropic_key)
                response = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=max_tokens,
                    system=cached_system(system_prompt),
                    messages=messages
                )
                log_cache_usage(response, "script_worker")
                content_text = "".join(block.text for block in response.content if hasattr(block, "text"))
                if content_text:
                    logger.info(f"Claude API 호출 성공 ({len(content_text)}자)")
                    return content_text
            except Exception as e:
                logger.error(f"Claude API 호출 실패: {e}. Gemini 폴백 시도합니다.")
        
        # 2. Gemini 폴백
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            raise RuntimeError("Claude 호출 실패 및 GEMINI_API_KEY가 설정되지 않아 진행할 수 없습니다.")
        
        logger.info("Gemini API 호출 시작 (모델: gemini-2.5-flash)...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        
        # convert messages list to gemini contents
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            content_text = msg["content"]
            if isinstance(content_text, list):
                content_text = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content_text)
            
            contents.append({
                "role": role,
                "parts": [{"text": str(content_text)}]
            })
            
        payload = {
            "contents": contents,
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.2
            }
        }
        
        try:
            import requests
            resp = requests.post(url, json=payload, timeout=90)
            if resp.status_code == 200:
                res_json = resp.json()
                candidates = res_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        gemini_content = parts[0].get("text", "")
                        logger.info(f"Gemini API 호출 성공 ({len(gemini_content)}자)")
                        return gemini_content
                raise RuntimeError(f"Gemini 응답 구조 분석 실패: {res_json}")
            else:
                raise RuntimeError(f"Gemini API 오류 (status: {resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"Gemini API 호출 예외: {e}")
            raise e

    def generate(self, keyword: str, category: str, target_minutes: int,
                 market_data: Optional[dict] = None, job_id: int = 0,
                 data_visuals_enabled: bool = True,
                 storytelling_profile: str = DEFAULT_SCRIPT_STYLE_PROFILE) -> dict:
        category_label = CATEGORY_LABELS.get(category, "주식시장")
        # Use the measured spoken-narration rate rather than the rich script's
        # total character count (which also includes prompts and metadata).
        target_chars = target_minutes * int(runtime_config.value("chars_per_minute"))

        logger.info(f"스크립트 생성 v3: job_id={job_id}, keyword={keyword}, "
                    f"category={category}, target={target_minutes}분")

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if not api_key and not gemini_key:
            logger.warning("ANTHROPIC_API_KEY 및 GEMINI_API_KEY 모두 미설정 — Mock 스크립트로 폴백")
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
                keyword, category_label, market_data
            )

            # 검증된 사실 기반 스크립트 생성
            full_script, sections, meta_title, meta_thumb, meta_desc, meta_shorts = self._generate_with_verified_facts(
                keyword, category_label, target_minutes, target_chars,
                verified_facts, market_data, storytelling_profile
            )
            sections = direct_scenes(enrich_scene_plans(sections))
            if data_visuals_enabled:
                sections = _attach_verified_index_overlays(sections, market_data)
                sections = _attach_verified_market_charts(sections)
            used_real_llm = True

        except Exception as e:
            logger.error(f"LLM API 호출 실패: {e} — Mock으로 폴백")
            full_script, sections = self._mock_script(keyword, category_label, target_minutes)
            sections = direct_scenes(enrich_scene_plans(sections))
            if data_visuals_enabled:
                sections = _attach_verified_index_overlays(sections, market_data)
                sections = _attach_verified_market_charts(sections)
            verified_facts = []
            fact_check_log = [f"오류: {str(e)}"]
            used_real_llm = False
            meta_title = "제목 자동 생성 실패"
            meta_thumb = "Stock market background"
            meta_desc = "상세 설명이 없습니다."
            meta_shorts = "쇼츠 대본 자동 생성 실패"

        logger.info(f"스크립트 생성 완료: {len(full_script)}자, job_id={job_id}")

        scene_quality = assess_scene_plan(sections)
        art_quality = assess_art_diversity(sections)
        storytelling_quality = assess_storytelling(sections, full_script)

        return {
            "job_id": job_id,
            "keyword": keyword,
            "script": full_script,
            "sections": sections,
            "char_count": sum(s["char_count"] for s in sections),
            "verified_facts": verified_facts,
            "fact_check_rounds": len(fact_check_log),
            "fact_check_log": fact_check_log,
            "market_snapshot_used": market_data is not None,
            "market_snapshot": market_data or {},
            "used_real_llm": used_real_llm,
            "storytelling_profile": DEFAULT_SCRIPT_STYLE_PROFILE,
            "quality_report": {
                "scene_plan": scene_quality,
                "art_direction": art_quality,
                "storytelling": storytelling_quality,
            },
            "youtube_metadata": {
                "title": meta_title,
                "thumbnail_prompt": meta_thumb,
                "description": meta_desc,
                "shorts_script": meta_shorts
            }
        }

    def _multi_round_fact_check(self, keyword: str, category_label: str,
                                 market_data: dict) -> tuple[list, list]:
        messages = []
        fact_check_log = []
        market_json = json.dumps(market_data, ensure_ascii=False, indent=2)

        r1_content = f"""<market_data>
{market_json}
</market_data>

<task>
위 실제 시장 데이터에서 '{keyword}' 관련 핵심 사실들을 가능한 많이 추출하세요.
1. 수치, 뉴스, 매크로 동향 등 신뢰성 있는 정보 포함.
2. 데이터 내 출처 필드명 명시.
3. 데이터에 없는 내용 절대 금지.
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
                                       storytelling_profile: str = DEFAULT_SCRIPT_STYLE_PROFILE):
        facts_text = "\n".join(f"- {f['fact']} (상세 정보: {f.get('figure', 'N/A')}, 출처: {f.get('source_field', 'N/A')}, 신뢰도: {f.get('confidence', 0):.2f})" for f in verified_facts)
        market_summary = _build_market_summary_for_script(market_data)
        num_scenes = _calc_scene_count(target_minutes)
        chars_per_scene = target_chars // num_scenes if num_scenes > 0 else 60

        user_prompt = f"""<verified_facts>{facts_text}</verified_facts>
<market_context>{market_summary}</market_context>
작성 규칙:
- [대사], [비주얼 설명 (한국어)], [비주얼 프롬프트 (영어)], [감정] 포함
- [대사] 블록만 합산해 공백 제외 약 {target_chars}자(±8%)로 작성. 비주얼 설명·영문 프롬프트·메타데이터는 이 분량에 포함하지 않음
- 각 씬의 대사는 공백 제외 약 {chars_per_scene}자 내외의 짧고 완결된 생각 단위로 작성해 5~7초마다 시각 전환이 가능하게 구성
- 마지막에 ## 메타데이터 섹션 추가 ([추천 제목], [추천 썸네일], [더보기 설명], [쇼츠 대본])
- 쇼츠 대본은 본 영상의 핵심만 30초 내외로 요약한 강렬한 문장으로 작성
목표 씬 수: 총 {num_scenes}개 내외"""

        full_text = self._call_llm_with_fallback(
            f"{SCRIPT_SYSTEM_PROMPT}\n\n{get_script_style_guide(storytelling_profile)}",
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

        # LLM instructions can occasionally be exceeded. Keep the spoken text
        # within the requested video duration without touching visual prompts or
        # metadata, so a 5-minute job cannot silently become a 9-minute TTS.
        script_body = _cap_dialogue_to_target(script_body, target_chars)

        # The LLM often returns a valid but too-coarse outline (for example,
        # twenty 20-second scenes in a five-minute video).  Split the spoken
        # content into short, complete thought units before images are planned.
        sections = _split_sections_for_visual_pacing(_parse_sections(script_body))
        return script_body, sections, meta_title, meta_thumb, meta_desc, meta_shorts

    def _mock_generate(self, keyword, category_label, target_minutes, job_id):
        script_text, sections = self._mock_script(keyword, category_label, target_minutes)
        return {
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
            prompt_ko = f"거대한 폭풍우가 몰아치는 바다 한가운데, 튼튼한 닻을 내리고 흔들리지 않는 황금 배."
            prompt_en = "large golden ship anchoring firmly in the middle of a massive stormy ocean, huge waves, dark clouds, professional 3D render, vibrant colors, comic art style"
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

    def char_count(value: str) -> int:
        return len(re.sub(r"\s+", "", value))

    original_counts = [char_count(match.group(2)) for match in matches]
    total = sum(original_counts)
    # Keep the narration budget exact.  The previous sentence-only truncation
    # could leave most of each scene's allowance unused, producing a 38-second
    # TTS for a one-minute request.
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
        if char_count(text) <= limit:
            return text
        kept: list[str] = []
        for sentence in re.split(r"(?<=[.!?。])\s*", text):
            sentence = sentence.strip()
            if not sentence:
                continue
            candidate = " ".join([*kept, sentence]).strip()
            if char_count(candidate) <= limit:
                kept.append(sentence)
            elif not kept:
                visible = 0
                cut_at = 0
                for char_index, char in enumerate(sentence):
                    if not char.isspace():
                        visible += 1
                    if visible > max(1, limit - 1):
                        break
                    cut_at = char_index + 1
                shortened = sentence[:cut_at].rstrip(" ,;:")
                return (shortened + ".") if shortened else sentence[:1]
            else:
                remaining = limit - char_count(" ".join(kept))
                if remaining > 0:
                    visible = 0
                    cut_at = 0
                    for char_index, char in enumerate(sentence):
                        if not char.isspace():
                            visible += 1
                        if visible > remaining:
                            break
                        cut_at = char_index + 1
                    tail = sentence[:cut_at].rstrip(" ,;:")
                    if tail:
                        kept.append(tail)
                break
        return " ".join(kept).strip() or text[:max(1, limit)]

    cap_iter = iter(caps)

    def replace(match: re.Match) -> str:
        return match.group(1) + shorten_dialogue(match.group(2), next(cap_iter)) + "\n"

    compacted = pattern.sub(replace, script_body)
    compacted_total = sum(char_count(match.group(2)) for match in pattern.finditer(compacted))
    logger.warning(
        "Narration capped for target duration: %s -> %s chars (target=%s, budget=%s)",
        total, compacted_total, target_chars, compaction_budget,
    )
    return compacted


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
    # 1. 퍼센트 기호나 단어('%' 또는 '퍼센트')를 '포인트'로 일괄 치환
    text = re.sub(r'(\d+(?:\.\d+)?)\s*%', r'\1포인트', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*퍼센트', r'\1포인트', text)
    # 2. 천단위 콤마 제거 (예: 6,806 -> 6806)
    text = re.sub(r'(\d{1,3}),(\d{3})', r'\1\2', text)
    return text


def _split_sections_for_visual_pacing(sections: list, max_chars: int = 34) -> list:
    """Split long narration into 5-7 second thought units for image direction.

    We retain each source scene's topic and prompt as context, but every output
    unit receives its own scene director pass later in the image worker.  This
    prevents one illustration from being asked to explain an entire paragraph.
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
            candidates = [sentence]
            if len(sentence.replace(" ", "")) > max_chars:
                candidates = [part.strip() for part in re.split(r"(?<=,)\s+|(?<=; )\s+|(?<=그리고)\s+", sentence) if part.strip()]
            for candidate in candidates:
                words = candidate.split()
                # Preserve word boundaries when an individual sentence remains long.
                fragments: list[str] = []
                fragment = ""
                for word in words:
                    proposed = f"{fragment} {word}".strip()
                    if fragment and len(proposed.replace(" ", "")) > max_chars:
                        fragments.append(fragment)
                        fragment = word
                    else:
                        fragment = proposed
                if fragment:
                    fragments.append(fragment)
                for fragment in fragments or [candidate]:
                    proposed = f"{current} {fragment}".strip()
                    if current and len(proposed.replace(" ", "")) > max_chars:
                        units.append(current)
                        current = fragment
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


def _parse_sections(full_text: str) -> list:
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
            pose_match = re.search(r'\[감정\]\s*(.*?)(?=\[대사|$|\[비주얼 설명|\[비주얼 프롬프트)', raw_content, re.DOTALL)
            pose = pose_match.group(1).strip() if pose_match else "neutral"
            pose = re.sub(r'[^a-zA-Z]', '', pose).lower()
            if pose not in ["happy", "worried", "surprised", "pointing", "thinking", "explaining", "neutral"]:
                # Fallback to keyword matching from narration if LLM gave invalid pose
                pose = get_character_pose_from_text(content)

            raw_sections.append({
                "title": title,
                "content": content,
                "prompt_ko": prompt_ko or content,
                "prompt_en": prompt_en,
                "pose": pose
            })

    if not raw_sections:
        raw_sections.append({
            "title": "인트로",
            "content": full_text.strip(),
            "prompt_ko": full_text.strip(),
            "prompt_en": "Abstract financial chart background, professional finance news studio, dark navy blue background",
            "pose": "neutral"
        })

    total = len(raw_sections)
    sections = []
    for idx, s in enumerate(raw_sections):
        section_type = _assign_section_type(idx, total)
        prompt_en = s["prompt_en"]
        if not prompt_en:
            prompt_en = f"Abstract financial background representing {s['title']}, dark navy tone, professional 3D style"

        sections.append({
            "title": s["title"],
            "content": s["content"],
            "prompt_ko": s["prompt_ko"],
            "prompt_en": prompt_en,
            "prompt": prompt_en,  # Backward compatibility
            "pose": s["pose"],
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
        if any(token in text for token in ("상승", "하락", "급등", "급락", "등락")):
            chart["visual_kind"] = "change_arrow"
        elif any(token in text for token in ("비중", "점유", "구성")) and chart.get("market_cap_pie"):
            chart["visual_kind"] = "composition_pie"
        elif any(token in text for token in ("비교", "대비", "vs")):
            chart["visual_kind"] = "comparison"
        else:
            chart["visual_kind"] = "trend_dashboard"
        family = str((sections[index].get("art_direction") or {}).get("family") or "")
        if family in {"industry_environment", "factory_dashboard"}:
            chart["visual_theme"] = "factory_panel"
        elif family in {"news_headline", "news_context", "comparison_board"}:
            chart["visual_theme"] = "paper_poster"
        else:
            chart["visual_theme"] = "chalkboard"
        chart.update({"verified": True, "source": "market_snapshot.chart_series"})
        sections[index]["market_chart"] = chart
        # The old KOSPI corner card is a HUD, not part of the cartoon scene.
        # An integrated display replaces it for these selected key scenes.
        sections[index].pop("index_data", None)
        direction = dict(sections[index].get("art_direction") or {})
        # The image prompt and FFmpeg compositor share this semantic anchor.
        # It replaces the previous one-size-fits-all (880,120) rectangle,
        # which could land outside a generated paper prop.
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
        direction["data_surface"] = surfaces.get(chart["visual_theme"], surfaces["chalkboard"])
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
