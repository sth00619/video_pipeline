"""승인 대본·TTS·자막·장면의 동일 원문 계약을 검증한다."""

from __future__ import annotations

import hashlib
import re
from typing import Any


class NarrationContractError(ValueError):
    """승인된 내레이션 계보가 다음 단계에서 달라졌을 때 발생한다."""


CONTRACT_VERSION = "narration-source-v1"


def compact_text(value: str) -> str:
    """자막 줄바꿈 및 쉼표 표기 무시, 의미 있는 원문 차이는 유지한다."""
    cleaned = re.sub(r"##\s*장면\s*\d*", "", str(value or ""))
    cleaned = re.sub(r"(?<=\d),(?=\d)", "", cleaned)
    return re.sub(r"\s+", "", cleaned)


def canonical_narration_text(value: str) -> str:
    """낭독·자막·장면 계약에서 공유할 공백 정규화 원문을 만든다."""
    try:
        from app.utils.quality_gate import extract_narration
        clean = extract_narration(value) if value and ("##" in value or "[" in value) else value
    except Exception:
        clean = value
    return re.sub(r"\s+", " ", str(clean or value or "")).strip()


def text_sha256(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def narration_from_sections(sections: list[dict[str, Any]]) -> str:
    """장면 순서를 보존해 승인 내레이션을 재구성한다."""
    extracted = []
    for section in sections:
        val = str(section.get("text_for_tts") or section.get("content") or section.get("text") or "").strip()
        if not val:
            continue
        try:
            from app.utils.quality_gate import extract_narration
            clean_val = extract_narration(val) if ("[" in val or "##" in val) else val
            extracted.append(clean_val or val)
        except Exception:
            extracted.append(val)
    return "\n\n".join(extracted)


def build_script_contract(script: str, sections: list[dict[str, Any]]) -> dict[str, Any]:
    """대본 원문과 이미지 장면 원문이 같은지 확인해 계보를 만든다."""
    import logging
    logger = logging.getLogger(__name__)

    canonical_text = canonical_narration_text(script)
    section_text = narration_from_sections(sections)
    if not canonical_text:
        canonical_text = section_text or "내레이션 원문"

    if sections and section_text and compact_text(canonical_text) != compact_text(section_text):
        raise NarrationContractError(
            "승인 대본 원문과 장면 내레이션에 차이가 있습니다."
        )

    scene_sources: list[dict[str, Any]] = []
    for index, section in enumerate(sections, start=1):
        text = str(section.get("text_for_tts") or section.get("content") or section.get("text") or "").strip()
        if not text:
            text = f"장면 {index}"
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
    import logging
    logger = logging.getLogger(__name__)

    canonical_text = canonical_narration_text(tts_meta.get("canonical_text") or "")
    canonical_sha256 = str(tts_meta.get("canonical_sha256") or "").strip()
    expected_sha256 = str(script_contract.get("canonical_text_sha256") or "").strip()
    chunks = list(tts_meta.get("chunks") or [])
    chunks_text = compact_text("".join(str(c.get("text", "")) for c in chunks))

    if canonical_sha256 != expected_sha256:
        raise NarrationContractError("자막 청크 또는 TTS 원문 해시가 대본 계약과 다릅니다.")

    if chunks_text and compact_text(canonical_text) != chunks_text:
        raise NarrationContractError("자막 청크 원문이 대본 계약과 다릅니다.")

    return {
        "passed": True,
        "version": CONTRACT_VERSION,
        "canonical_text_sha256": canonical_sha256 or expected_sha256,
        "subtitle_cue_count": len(chunks),
        "subtitle_text_match": True,
    }
