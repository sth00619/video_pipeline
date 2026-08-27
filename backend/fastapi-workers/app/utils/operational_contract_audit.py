"""영상 생성 버튼의 공통 운영 계약을 모든 단계 산출물에 기록한다.

개별 Job과 장면은 회귀 fixture일 뿐이다. 이 감사 객체는 2026-08-20 이후
검증된 결론이 SCRIPT→TTS→IMAGES→LONGFORM 운영 경로에서 실제로 적용된
코드 버전을 DB 자산과 결과 manifest에 남긴다.
"""
from __future__ import annotations

from typing import Any


PIPELINE_OPERATIONAL_CONTRACT_VERSION = "video-button-global-v1-20260828"
_VALID_STAGES = {"script", "tts", "images", "single_scene", "longform"}


def build_operational_contract_audit(
    stage: str,
    *,
    checks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """현재 단계가 사용하는 전역 계약과 실행 판정을 직렬화한다."""
    normalized_stage = str(stage or "").strip().lower()
    if normalized_stage not in _VALID_STAGES:
        raise ValueError(f"알 수 없는 운영 계약 단계: {stage}")
    return {
        "version": PIPELINE_OPERATIONAL_CONTRACT_VERSION,
        "scope": "all_jobs_all_topics",
        "entrypoint": "video_generation_button",
        "job_specific_patch": False,
        "stage": normalized_stage,
        "stage_sequence": ["script", "tts", "images", "longform"],
        "contracts": {
            "research_and_script": {
                "policy": "verified_evidence_and_claude_sonnet_4_6",
                "reason": "검증 근거와 승인 대본을 이후 모든 단계의 단일 의미 원천으로 사용",
            },
            "timing_and_caption": {
                "policy": "measured_voice_duration_and_caption_scene_hash",
                "reason": "실제 음성 시간·완결 문장·자막 청크 경계에 이미지 전환을 결박",
            },
            "image_semantics_and_style": {
                "policy": "scene_local_semantics_with_channel_reference_range",
                "reason": "참조 화풍은 보존하되 현재 대본의 주제·구도·의상·소품을 우선",
            },
            "text_and_fact_integrity": {
                "policy": "scene_local_exact_text_and_deterministic_financial_values",
                "reason": "승인 문자열은 정확 대조하고 금융 수치는 Pillow/FFmpeg로 결정론 렌더",
            },
            "character_integrity": {
                "policy": "face_range_scene_specific_costume_two_arm_anatomy",
                "reason": "캐릭터 종과 얼굴 조형을 유지하면서 표정·의상·행동 다양성 보존",
            },
            "provider_request_control": {
                "policy": "single_owner_persistent_retry_budget_and_cooldown",
                "reason": "503 중첩 재시도·중복 과금·검수 상태 우회를 차단",
            },
            "motion_and_assembly": {
                "policy": "text_locked_local_motion_and_lineage_recheck",
                "reason": "문자·수치 표면은 고정하고 승인된 캐릭터·사물·배경만 국소 모션",
            },
        },
        "checks": dict(checks or {}),
    }
