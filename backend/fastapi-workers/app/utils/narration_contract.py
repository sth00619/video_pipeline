"""승인 대본·TTS·자막·장면의 동일 원문 계약을 검증한다."""

from __future__ import annotations

import hashlib
import re
from typing import Any


class NarrationContractError(ValueError):
    """승인된 내레이션 계보가 다음 단계에서 달라졌을 때 발생한다."""


CONTRACT_VERSION = "narration-source-v1"
CAPTION_SCENE_CONTRACT_VERSION = "caption-scene-v1"
SCENE_SENTENCE_BOUNDARY_VERSION = "scene-sentence-boundary-v1"


_SENTENCE_END_RE = re.compile(r"[.!?。！？]+[\"'”’)]*")
_ENDS_WITH_SENTENCE_RE = re.compile(r"[.!?。！？]+[\"'”’)]*$")


def _scene_narration(scene: dict[str, Any]) -> str:
    return str(
        scene.get("text_for_tts") or scene.get("content") or scene.get("text") or ""
    ).strip()


def _replace_scene_narration(scene: dict[str, Any], text: str) -> dict[str, Any]:
    """문장 경계만 바꾼 장면의 파생 메타데이터를 무효화한다."""
    updated = dict(scene)
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    updated["content"] = clean
    updated["text"] = clean
    updated["text_for_tts"] = clean
    updated["char_count"] = len(clean)
    for key in (
        "caption_chunk_plan",
        "caption_chunk_contract",
        "caption_image_contract",
        "subtitle_text",
        "prompt",
        "prompt_en",
        "prompt_ko",
        "screen_texts",
        "screen_text_contract",
        "scene_spec",
        "headline",
    ):
        updated.pop(key, None)
    return updated


def normalize_scene_sentence_boundaries(
    sections: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """문장 중간에서 나뉜 장면 경계를 다음 완결문 경계로 이동한다.

    승인 대본의 단어·숫자·순서는 바꾸지 않고 장면 소유 범위만
    다시 나눈다. 이미 생성된 프롬프트와 자막 계약은 바뀐 장면에서
    재생성하여 이전 의미가 남지 않게 한다.
    """
    normalized = [dict(section) for section in sections]
    original_compact = compact_text("".join(_scene_narration(item) for item in normalized))
    repairs: list[dict[str, Any]] = []
    index = 0
    while index < len(normalized) - 1:
        current_text = _scene_narration(normalized[index])
        if not current_text or _ENDS_WITH_SENTENCE_RE.search(current_text.rstrip()):
            index += 1
            continue

        endings = list(_SENTENCE_END_RE.finditer(current_text))
        if endings:
            split_at = endings[-1].end()
            completed = current_text[:split_at].strip()
            trailing = current_text[split_at:].strip()
            if completed and trailing:
                next_text = _scene_narration(normalized[index + 1])
                normalized[index] = _replace_scene_narration(normalized[index], completed)
                normalized[index + 1] = _replace_scene_narration(
                    normalized[index + 1], f"{trailing} {next_text}".strip(),
                )
                repairs.append({
                    "scene_index": index,
                    "next_scene_index": index + 1,
                    "moved_text": trailing,
                    "action": "move_incomplete_tail_to_next_scene",
                })
                index += 1
                continue

        # 완결문이 하나도 없는 조각은 다음 장면에 합쳐 문장을 복원한다.
        next_text = _scene_narration(normalized[index + 1])
        normalized[index + 1] = _replace_scene_narration(
            normalized[index + 1], f"{current_text} {next_text}".strip(),
        )
        repairs.append({
            "scene_index": index,
            "next_scene_index": index + 1,
            "moved_text": current_text,
            "action": "merge_incomplete_scene_into_next_scene",
        })
        normalized.pop(index)

    normalized_compact = compact_text("".join(_scene_narration(item) for item in normalized))
    if normalized_compact != original_compact:
        raise NarrationContractError("문장 경계 보정 중 승인 대본 원문이 변경됐습니다.")
    return normalized, {
        "version": SCENE_SENTENCE_BOUNDARY_VERSION,
        "passed": True,
        "repair_count": len(repairs),
        "repairs": repairs,
        "source_scene_count": len(sections),
        "normalized_scene_count": len(normalized),
        "canonical_compact_sha256": text_sha256(normalized_compact),
    }


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


def bind_caption_chunks_to_scenes(
    sections: list[dict[str, Any]], chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    """자막 청크를 이미지 장면에 원문 순서대로 정확히 결박한다.

    한 장면은 하나 이상의 *완전한* 자막 청크만 소유할 수 있다. 장면 끝이
    자막 청크 중간에 걸리거나, 한 청크가 두 장면의 문장을 함께 포함하면
    비율 추정으로 덮지 않고 다음 비용 단계 전에 실패한다.
    """
    if not sections:
        raise NarrationContractError("자막과 연결할 이미지 장면이 없습니다.")
    if not chunks:
        raise NarrationContractError("이미지 장면과 연결할 자막 청크가 없습니다.")

    scene_texts = [
        str(section.get("text_for_tts") or section.get("content") or section.get("text") or "").strip()
        for section in sections
    ]
    chunk_texts = [str(chunk.get("text") or "").strip() for chunk in chunks]
    if any(not compact_text(text) for text in scene_texts):
        raise NarrationContractError("내레이션 원문이 비어 있는 이미지 장면이 있습니다.")
    if any(not compact_text(text) for text in chunk_texts):
        raise NarrationContractError("원문이 비어 있는 자막 청크가 있습니다.")
    if compact_text("".join(scene_texts)) != compact_text("".join(chunk_texts)):
        raise NarrationContractError("이미지 장면 원문과 자막 청크 원문 전체가 일치하지 않습니다.")

    timed = any(
        chunk.get("start") is not None or chunk.get("end") is not None or chunk.get("duration") is not None
        for chunk in chunks
    )
    previous_end = 0.0
    if timed:
        for index, chunk in enumerate(chunks, start=1):
            if chunk.get("start") is None:
                raise NarrationContractError(f"자막 청크 {index}에 시작 시각이 없습니다.")
            start = float(chunk.get("start") or 0.0)
            end = float(
                chunk.get("end")
                if chunk.get("end") is not None
                else start + float(chunk.get("duration") or 0.0)
            )
            if end <= start:
                raise NarrationContractError(f"자막 청크 {index}의 재생 시간이 올바르지 않습니다.")
            if start + 0.001 < previous_end:
                raise NarrationContractError(f"자막 청크 {index}의 시간이 이전 청크와 겹칩니다.")
            previous_end = end

    mappings: list[dict[str, Any]] = []
    chunk_cursor = 0
    for scene_index, (section, scene_text) in enumerate(zip(sections, scene_texts)):
        target = compact_text(scene_text)
        accumulated = ""
        chunk_start = chunk_cursor
        while len(accumulated) < len(target):
            if chunk_cursor >= len(chunks):
                raise NarrationContractError(
                    f"이미지 장면 {scene_index + 1}의 원문을 채울 자막 청크가 부족합니다."
                )
            candidate = accumulated + compact_text(chunk_texts[chunk_cursor])
            if not target.startswith(candidate):
                raise NarrationContractError(
                    f"이미지 장면 {scene_index + 1} 경계가 자막 청크 {chunk_cursor + 1} 중간에 놓입니다."
                )
            accumulated = candidate
            chunk_cursor += 1
        if accumulated != target:
            raise NarrationContractError(
                f"이미지 장면 {scene_index + 1}과 자막 청크의 의미 단위가 일치하지 않습니다."
            )

        owned = chunks[chunk_start:chunk_cursor]
        mapping = {
            "version": CAPTION_SCENE_CONTRACT_VERSION,
            "scene_index": scene_index,
            "scene_id": str(section.get("scene_id") or f"script_scene_{scene_index + 1:03d}"),
            "chunk_start_index": chunk_start,
            "chunk_end_index": chunk_cursor - 1,
            "chunk_indexes": [
                int(chunk.get("index")) if str(chunk.get("index", "")).isdigit() else index + 1
                for index, chunk in enumerate(owned, start=chunk_start)
            ],
            "caption_chunk_count": len(owned),
            "scene_text_sha256": text_sha256(scene_text),
            "scene_compact_sha256": text_sha256(target),
            "caption_compact_sha256": text_sha256("".join(compact_text(text) for text in chunk_texts[chunk_start:chunk_cursor])),
            "boundary_match": True,
            "image_transition_after_chunk": chunk_cursor - 1,
        }
        if timed:
            first = owned[0]
            last = owned[-1]
            start = float(first.get("start") or 0.0)
            end = float(
                last.get("end")
                if last.get("end") is not None
                else float(last.get("start") or 0.0) + float(last.get("duration") or 0.0)
            )
            mapping.update({
                "start": round(start, 6),
                "end": round(end, 6),
                "duration": round(end - start, 6),
            })
        mappings.append(mapping)

    if chunk_cursor != len(chunks):
        raise NarrationContractError("어떤 이미지 장면에도 연결되지 않은 자막 청크가 남았습니다.")

    return {
        "passed": True,
        "version": CAPTION_SCENE_CONTRACT_VERSION,
        "scene_count": len(sections),
        "subtitle_cue_count": len(chunks),
        "all_scene_boundaries_on_caption_boundaries": True,
        "mappings": mappings,
    }
