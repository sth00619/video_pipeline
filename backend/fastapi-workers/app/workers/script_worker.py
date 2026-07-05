"""
스크립트 생성 워커 v2 — 실제 Claude API 연동

핵심 변경:
  Mock LLM → 실제 Anthropic API (claude-sonnet-4-6)
  한국어 주식 유튜브 스크립트 (경제사냥꾼 스타일) 프롬프트 엔지니어링
  6섹션 구조 유지: 인트로/시장배경/핵심데이터/시나리오/실행가이드/결론
  ANTHROPIC_API_KEY 환경변수 필요

주식 콘텐츠 특화:
  - 프롬프트에 코스피/코스닥/미국 주식 톤앤매너 명시
  - 숫자/수치 표현 방식 지정 (예: "코스피 2,650포인트", "+3.2%")
  - 실제 경제 유튜버 화법 반영 (친근하지만 전문적)
"""
import os
import logging
import re

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

SYSTEM_PROMPT = """당신은 한국의 인기 경제 유튜브 채널 "경제사냥꾼" 스타일의 대본 작가입니다.

작성 원칙:
- 친근하지만 전문적인 톤 (반말 아닌 존댓말, "~습니다/~해요" 혼용)
- 수치는 반드시 구체적으로: "코스피 2,650포인트", "외국인 순매수 +3,200억원"
- 각 섹션은 자연스럽게 다음 섹션으로 연결
- 과장된 클릭베이트 표현 지양, 신뢰도 있는 분석 어조
- 시청자에게 직접 말하는 듯한 구어체 (예: "여러분", "지금 보시는 것처럼")
- 투자 조언이 아닌 정보 제공 관점 유지 (예: "매수를 권유하는 것이 아니라")

절대 금지사항:
- 확정적 미래 예측 ("반드시 오릅니다" 등) 금지, "가능성이 높습니다" 등으로 표현
- 특정 종목에 대한 직접적인 매수/매도 지시 금지
"""


class ScriptWorker:

    def generate(self, keyword: str, category: str, target_minutes: int, job_id: int = 0) -> dict:
        category_label = CATEGORY_LABELS.get(category, "주식시장")
        target_chars = target_minutes * 300  # 한국어 분당 300자 기준

        logger.info(f"스크립트 생성 시작: job_id={job_id}, keyword={keyword}, "
                    f"category={category}, target={target_minutes}분")

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY 미설정 — Mock 스크립트로 폴백")
            return self._mock_generate(keyword, category_label, target_minutes, job_id)

        try:
            script_text, sections = self._generate_with_claude(
                keyword, category_label, target_minutes, target_chars, api_key
            )
            used_real_llm = True
        except Exception as e:
            logger.error(f"Claude API 호출 실패: {e} — Mock으로 폴백")
            script_text, sections = self._mock_script(keyword, category_label, target_minutes)
            used_real_llm = False

        logger.info(f"스크립트 생성 완료: {len(script_text)}자, real_llm={used_real_llm}")

        return {
            "job_id": job_id,
            "keyword": keyword,
            "script": script_text,
            "sections": sections,
            "char_count": len(script_text),
            "used_real_llm": used_real_llm,
        }

    def _generate_with_claude(self, keyword, category_label, target_minutes, target_chars, api_key):
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)

        user_prompt = f"""다음 조건으로 한국어 주식 유튜브 대본을 작성해주세요.

카테고리: {category_label}
핵심 키워드/주제: {keyword}
목표 분량: 약 {target_chars}자 (약 {target_minutes}분 분량)

구조 (6개 섹션, 각 섹션 앞에 "## 섹션명"으로 표시):
## 인트로
시청자의 관심을 끄는 도입부. 오늘 다룰 핵심 질문 제시.

## 시장 배경
현재 {category_label} 시장 상황 설명. 최근 지수/가격 동향.

## 핵심 데이터
구체적인 수치와 지표 (거래량, 외국인/기관 매매 동향, 주요 경제지표 등).

## 시나리오 분석
상승 시나리오와 하락 시나리오를 균형있게 제시.

## 실행 가이드
투자자가 참고할 수 있는 체크포인트 (매수/매도 권유가 아닌 관찰 포인트).

## 결론
핵심 3가지 요약 및 다음 영상 예고.

각 섹션은 자연스러운 구어체로 작성하고, 전체 분량이 {target_chars}자에 최대한 맞도록 작성해주세요."""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        full_text = "".join(
            block.text for block in response.content if block.type == "text"
        )

        sections = self._parse_sections(full_text)
        # 마크다운 헤더 제거한 순수 낭독용 텍스트
        clean_text = re.sub(r'^##\s*.+$', '', full_text, flags=re.MULTILINE).strip()
        clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)

        return clean_text, sections

    def _parse_sections(self, full_text: str) -> list:
        """## 섹션명 기준으로 분리"""
        parts = re.split(r'^##\s*(.+)$', full_text, flags=re.MULTILINE)
        sections = []
        # parts[0]은 헤더 이전 텍스트(보통 빈 문자열), 이후 [제목, 내용, 제목, 내용...]
        for i in range(1, len(parts), 2):
            if i + 1 < len(parts):
                title = parts[i].strip()
                content = parts[i + 1].strip()
                sections.append({"title": title, "content": content, "char_count": len(content)})
        return sections

    # ============================
    # Mock 폴백 (API 키 없거나 실패 시)
    # ============================
    def _mock_generate(self, keyword, category_label, target_minutes, job_id):
        script_text, sections = self._mock_script(keyword, category_label, target_minutes)
        return {
            "job_id": job_id,
            "keyword": keyword,
            "script": script_text,
            "sections": sections,
            "char_count": len(script_text),
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
            sections.append({"title": name, "content": padded[:chars_per_section], "char_count": chars_per_section})

        full_script = "\n\n".join(s["content"] for s in sections)
        return full_script, sections
