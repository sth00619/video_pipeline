"""정지 이미지 승인 전에 만드는 Fal 국소 동작 사전 계획.

이 모듈은 Fal을 호출하지 않는다. 장면 의미에서 움직일 사물 하나와 보조 반응만
고르고, 카메라·텍스트 표면·나머지 배경을 고정해 전 화면 지글링을 예방한다.
"""
from __future__ import annotations

from typing import Any

from app.services.fal_motion_safety import fal_motion_metadata_block_reasons


def _source(scene: dict[str, Any]) -> str:
    return " ".join(
        str(scene.get(key) or "")
        for key in ("text_for_tts", "content", "text", "prompt_en", "prompt")
    ).casefold()


def scene_motion_intent(scene: dict[str, Any], *, selected: bool) -> dict[str, Any]:
    source = _source(scene)
    reasons = fal_motion_metadata_block_reasons(scene)
    if any(token in source for token in ("폭락", "급락", "하락", "crash", "plummet", "falling arrow")):
        primary = "하락선이나 붉은 방향 화살표 한 개만 짧게 아래로 이동"
        secondary = "마스코트의 눈·눈썹 반응과 한쪽 팔 동작만 작게 연결"
    elif any(token in source for token in ("반도체", "웨이퍼", "칩", "semiconductor", "wafer", "chip")):
        primary = "웨이퍼 컨베이어나 회로의 빛 흐름 한 개만 천천히 이동"
        secondary = "연구 도구 또는 마스코트의 한쪽 손만 짧게 반응"
    elif any(token in source for token in ("환율", "외국인", "currency", "exchange")):
        primary = "환율 게이지 바늘 또는 통화 흐름 표식 한 개만 이동"
        secondary = "배경의 무문자 신호등 한 개만 한 번 점멸"
    elif any(token in source for token in ("선물", "발표", "reveal", "curtain", "gift")):
        primary = "커튼·리본·선물 상자 중 핵심 소품 하나만 짧게 열리거나 흔들림"
        secondary = "마스코트의 고개 또는 한쪽 팔만 자연스럽게 반응"
    else:
        primary = "대본의 핵심 물리 소품 한 개만 3~5초 동안 작게 움직임"
        secondary = "마스코트가 있으면 얼굴과 한쪽 팔만 최소 반응"

    eligible = bool(selected and not reasons)
    return {
        "selected_candidate": bool(selected),
        "eligible_before_image_ocr": eligible,
        "block_reasons": reasons,
        "primary_motion": primary,
        "secondary_motion": secondary,
        "locked_elements": [
            "카메라 위치와 줌",
            "화면 가장자리와 전체 배경",
            "모든 문자·숫자·차트 표면",
            "캐릭터 얼굴 구조와 사지 개수",
        ],
        "forbidden_motion": [
            "전 화면 지글링 또는 노이즈",
            "전역 카메라 흔들림",
            "글자·숫자 재그리기",
            "배경 전체의 물결 왜곡",
            "추가 손·팔·캐릭터 생성",
        ],
        "post_generation_gate": "motion_locality_v1_and_final_frame_text_integrity",
    }


def build_fal_motion_preflight(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    entries = []
    for index, scene in enumerate(scenes or []):
        entries.append({
            "scene_index": index,
            "scene_id": str(scene.get("scene_id") or scene.get("id") or index),
            **scene_motion_intent(scene, selected=bool(scene.get("use_kling"))),
        })
    return {
        "version": "fal-local-object-motion-preflight-v1",
        "fal_called": False,
        "scene_count": len(entries),
        "selected_count": sum(bool(item["selected_candidate"]) for item in entries),
        "eligible_count": sum(bool(item["eligible_before_image_ocr"]) for item in entries),
        "scenes": entries,
    }
