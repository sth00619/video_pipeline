"""
Phase 3-2 — 스크립트 생성 워커

한국어 기준 분당 약 300자 (보통 350~400자, 약간 보수적으로 300)
20분 목표 → 약 6000자 분량 생성
"""
import logging
from app.providers.factory import get_llm_provider

logger = logging.getLogger(__name__)

KO_CHARS_PER_MINUTE = 300


SCRIPT_SYSTEM_PROMPT = """당신은 한국어 유튜브 롱폼 영상 스크립트 작가입니다.
주어진 키워드를 주제로 자연스럽고 흥미로운 한국어 나레이션 스크립트를 작성합니다.
도입 → 본론(3~5개 섹션) → 결론(요약 + CTA) 구조를 따르고,
시청자 이탈을 막기 위해 중간중간 호기심을 자극하는 문장을 포함합니다.
"""

SYNOPSIS_SYSTEM_PROMPT = """주어진 영상 키워드에 대한 핵심 시놉시스(synopsis)를 2~3문장으로 작성합니다."""


class ScriptWorker:
    def __init__(self):
        self.llm = get_llm_provider()

    def generate(self, keyword: str, target_minutes: int = 20, job_id: int = 0) -> dict:
        logger.info(f"스크립트 생성 시작: keyword={keyword}, target={target_minutes}분, job_id={job_id}")

        target_chars = target_minutes * KO_CHARS_PER_MINUTE

        # 1) 시놉시스
        synopsis = self.llm.generate(
            SYNOPSIS_SYSTEM_PROMPT,
            f"키워드: {keyword}\n시놉시스를 작성해주세요."
        )

        # 2) 스크립트
        user_prompt = (
            f"키워드: {keyword}\n"
            f"목표 분량: 약 {target_minutes}분 (한국어 {target_chars}자 내외)\n"
            f"스크립트를 작성해주세요."
        )
        script_raw = self.llm.generate(SCRIPT_SYSTEM_PROMPT, user_prompt)

        # 3) 분량 보정 — Mock은 분량을 정확히 못 맞추므로 잘라내거나 패딩
        script = self._adjust_length(script_raw, target_chars)
        char_count = len(script)
        estimated_minutes = round(char_count / KO_CHARS_PER_MINUTE, 1)

        logger.info(f"스크립트 생성 완료: {char_count}자, 약 {estimated_minutes}분")

        return {
            "job_id": job_id,
            "synopsis": synopsis,
            "script": script,
            "estimated_minutes": estimated_minutes,
            "char_count": char_count,
        }

    @staticmethod
    def _adjust_length(text: str, target_chars: int) -> str:
        if len(text) >= target_chars:
            return text[:target_chars]
        # 부족하면 반복으로 채움 (Mock 전용)
        padding_needed = target_chars - len(text)
        if padding_needed > 0 and text:
            repeats = (padding_needed // len(text)) + 1
            return (text + " " + text * repeats)[:target_chars]
        return text
