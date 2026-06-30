"""
Phase 3-2 — 주식 영상 스크립트 워커

특징:
  - 6섹션 구조: 도입 / 시장배경 / 핵심데이터 / 시나리오 / 실행가이드 / 결론
  - 분량 유동성: target_minutes (15/20/30 등)
  - 한국어 분당 300자 기준
  - 시점 명시 + 면책 조항
"""
import logging
from datetime import datetime
from app.providers.factory import get_llm_provider

logger = logging.getLogger(__name__)

KO_CHARS_PER_MINUTE = 300


STOCK_SCRIPT_SYSTEM_PROMPT = """당신은 한국어 주식 유튜브 채널의 베테랑 작가입니다.
시청자의 매매 판단에 실질적으로 도움이 되는 스크립트를 작성합니다.

구조:
  1. 도입 (Hook): 시청자가 가장 궁금해할 질문 직격
  2. 시장 배경: 지금 이 주제가 왜 중요한지, 거시 흐름
  3. 핵심 데이터: 구체적 수치, 차트 포인트, 펀더멘털
  4. 시나리오 분석: 상승/박스권/하락 3가지 + 근거
  5. 실행 가이드: 개인 투자자가 지금 할 수 있는 구체적 행동
  6. 결론 + CTA: 핵심 요약 + 면책 + 구독 요청

원칙:
  - 단호하지 않은 표현 사용 (가능성, 시나리오)
  - 시점 명시 + 투자 권유 아님 면책
  - 섹션마다 호기심 유발 문장
"""

SYNOPSIS_SYSTEM_PROMPT = "주식 영상 시놉시스를 2~3문장으로 작성합니다."


class ScriptWorker:

    def __init__(self):
        self.llm = get_llm_provider()

    def generate(self, keyword: str, target_minutes: int = 20,
                 category: str = "CUSTOM", job_id: int = 0) -> dict:

        target_chars = target_minutes * KO_CHARS_PER_MINUTE
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        logger.info(f"스크립트 생성: keyword={keyword}, target={target_minutes}분 "
                    f"({target_chars}자), category={category}")

        # 시놉시스
        synopsis = self.llm.generate(
            SYNOPSIS_SYSTEM_PROMPT,
            f"키워드: {keyword}\n카테고리: {category}\n시놉시스를 작성해주세요."
        )

        # 스크립트
        user_prompt = (
            f"키워드: {keyword}\n"
            f"카테고리: {category}\n"
            f"목표 분량: 약 {target_minutes}분 (한국어 {target_chars}자 내외)\n"
            f"작성 시점: {timestamp}\n"
            f"주식 영상 스크립트를 6섹션 구조로 작성해주세요."
        )
        script = self.llm.generate(STOCK_SCRIPT_SYSTEM_PROMPT, user_prompt)

        # 시점 표기 추가 (스크립트 맨 앞)
        prefix = f"[본 영상은 {timestamp} 기준으로 작성되었습니다.] "
        script = prefix + script

        char_count = len(script)
        estimated_minutes = round(char_count / KO_CHARS_PER_MINUTE, 1)

        # 섹션 메타 (Phase 3-4 이미지 매칭 + 3-5 자막 동기화에 활용)
        sections = self._build_section_meta(target_chars)

        logger.info(f"스크립트 완료: {char_count}자, 약 {estimated_minutes}분")

        return {
            "job_id": job_id,
            "synopsis": synopsis,
            "script": script,
            "estimated_minutes": estimated_minutes,
            "char_count": char_count,
            "sections": sections,
            "generated_at": timestamp,
            "category": category,
        }

    @staticmethod
    def _build_section_meta(target_chars: int) -> list[dict]:
        weights = {
            "intro": 0.10,
            "background": 0.15,
            "data": 0.25,
            "scenario": 0.25,
            "action": 0.15,
            "conclusion": 0.10,
        }
        sections = []
        cursor = 0
        for name, weight in weights.items():
            section_chars = int(target_chars * weight)
            sections.append({
                "name": name,
                "expected_chars": section_chars,
                "start_offset_chars": cursor,
            })
            cursor += section_chars
        return sections
