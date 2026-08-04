"""승인 대본·TTS·자막·장면의 동일 원문 계약을 검증한다."""

from __future__ import annotations

import hashlib
import re
from typing import Any


class NarrationContractError(ValueError):
    """승인된 내레이션 계보가 다음 단계에서 달라졌을 때 발생한다."""


CONTRACT_VERSION = "narration-source-v1"


def compact_text(value: str) -> str:
    """자막 줄바꿈만 무시하고 의미 있는 원문 차이는 유지한다."""
    return re.sub(r"\s+", "", str(value or ""))


def canonical_narration_text(value: str) -> str:
    """낭독·자막·장면 계약에서 공유할 공백 정규화 원문을 만든다."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def text_sha256(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def narration_from_sections(sections: list[dict[str, Any]]) -> str:
    """장면 순서를 보존해 승인 내레이션을 재구성한다."""
    return "\n\n".join(
        str(section.get("text_for_tts") or section.get("content") or section.get("text") or "").strip()
        for section in sections
        if str(section.get("text_for_tts") or section.get("content") or section.get("text") or "").strip()
    )


def build_script_contract(script: str, sections: list[dict[str, Any]]) -> dict[str, Any]:
    """대본 원문과 이미지 장면 원문이 같은지 확인해 계보를 만든다."""
    # TTS는 낭독을 위해 줄바꿈을 단일 공백으로 정규화한다. 이 계약도 같은
    # 원문 표현을 해시해야 줄바꿈만 다른 동일 대본을 거짓 불일치로 막지 않는다.
    canonical_text = canonical_narration_text(script)
    section_text = narration_from_sections(sections)
    if not canonical_text:
        raise NarrationContractError("승인 대본 원문이 비어 있습니다.")
    if compact_text(canonical_text) != compact_text(section_text):
        raise NarrationContractError(
            "승인 대본 원문과 장면 내레이션이 다릅니다. 대본 또는 장면을 다시 확정하세요."
        )

    scene_sources: list[dict[str, Any]] = []
    for index, section in enumerate(sections, start=1):
        text = str(section.get("text_for_tts") or section.get("content") or section.get("text") or "").strip()
        if not text:
            raise NarrationContractError(f"{index}번 장면의 내레이션이 비어 있습니다.")
        scene_sources.append({
            "scene_id": str(section.get("scene_id") or f"script_scene_{index:03d}"),
            "text_sha256": text_sha256(text),
        })
    return {
        "version": CONTRACT_VERSION,
        "canonical_text_sha256": text_sha256(canonical_text),
        "section_count": len(scene_sources),
        "scene_sources": scene_sources,
    }


def verify_tts_against_script_contract(
    tts_meta: dict[str, Any], script_contract: dict[str, Any],
) -> dict[str, Any]:
    """TTS 메타데이터가 승인 대본·자막 청크를 그대로 사용했는지 확인한다."""
    canonical_text = canonical_narration_text(tts_meta.get("canonical_text") or "")
    canonical_sha256 = str(tts_meta.get("canonical_sha256") or "").strip()
    expected_sha256 = str(script_contract.get("canonical_text_sha256") or "").strip()
    chunks = list(tts_meta.get("chunks") or [])
    subtitle_text = "".join(str(chunk.get("text") or "") for chunk in chunks)

    if not canonical_text or not canonical_sha256 or not expected_sha256:
        raise NarrationContractError("TTS 또는 승인 대본의 원문 계약이 없습니다.")
    if text_sha256(canonical_text) != canonical_sha256:
        raise NarrationContractError("TTS 원문 해시가 실제 TTS 원문과 다릅니다.")
    if canonical_sha256 != expected_sha256:
        raise NarrationContractError("TTS 원문이 승인 대본과 다릅니다.")
    if compact_text(canonical_text) != compact_text(subtitle_text):
        raise NarrationContractError("TTS 자막 청크가 승인 대본 원문과 다릅니다.")

    return {
        "passed": True,
        "version": CONTRACT_VERSION,
        "canonical_text_sha256": canonical_sha256,
        "subtitle_cue_count": len(chunks),
        "subtitle_text_match": True,
    }
