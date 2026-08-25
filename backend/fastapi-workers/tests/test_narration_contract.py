import pytest
import json

from app.utils.narration_contract import (
    NarrationContractError,
    bind_caption_chunks_to_scenes,
    build_script_contract,
    canonical_narration_text,
    compact_text,
    normalize_scene_sentence_boundaries,
    text_sha256,
    verify_tts_against_script_contract,
)
from app.workers.images_worker import ImagesWorker
from app.workers.longform_worker import LongformWorker, _assign_scene_durations_from_chunks


def test_script_contract_keeps_tts_and_scene_source_identical():
    script = "첫 문장입니다.\n\n둘째 문장입니다."
    sections = [
        {"scene_id": "article_001", "content": "첫 문장입니다."},
        {"scene_id": "semantic_002", "content": "둘째 문장입니다."},
    ]

    contract = build_script_contract(script, sections)
    tts_meta = {
        "canonical_text": canonical_narration_text(script),
        "canonical_sha256": text_sha256(canonical_narration_text(script)),
        "chunks": [
            {"text": "첫 문장입니다."},
            {"text": "둘째 문장입니다."},
        ],
    }

    result = verify_tts_against_script_contract(tts_meta, contract)

    assert result["passed"] is True
    assert [item["scene_id"] for item in contract["scene_sources"]] == ["article_001", "semantic_002"]


def test_caption_chunks_are_bound_to_complete_image_scene_units():
    sections = [
        {"scene_id": "scene_001", "content": "첫 문장입니다. 둘째 설명입니다."},
        {"scene_id": "scene_002", "content": "마지막 문장입니다."},
    ]
    chunks = [
        {"index": 1, "text": "첫 문장입니다.", "start": 0.0, "end": 1.4},
        {"index": 2, "text": "둘째 설명입니다.", "start": 1.4, "end": 3.7},
        {"index": 3, "text": "마지막 문장입니다.", "start": 3.7, "end": 6.0},
    ]

    result = bind_caption_chunks_to_scenes(sections, chunks)

    assert result["all_scene_boundaries_on_caption_boundaries"] is True
    assert result["mappings"][0]["chunk_indexes"] == [1, 2]
    assert result["mappings"][0]["chunk_end_index"] == 1
    assert result["mappings"][1]["chunk_start_index"] == 2


def test_caption_chunk_must_not_straddle_two_image_scenes():
    sections = [
        {"content": "첫 문장입니다."},
        {"content": "둘째 문장입니다."},
    ]
    chunks = [
        {"text": "첫 문장입니다. 둘째", "start": 0.0, "end": 2.0},
        {"text": "문장입니다.", "start": 2.0, "end": 3.0},
    ]

    with pytest.raises(NarrationContractError, match="자막 청크 1 중간"):
        bind_caption_chunks_to_scenes(sections, chunks)


def test_incomplete_scene_tail_moves_to_next_scene_without_rewriting_narration():
    sections = [
        {"scene_id": "scene_001", "content": "첫 문장입니다. 반대로 실망스러운 가이던스가 나오면", "prompt": "stale"},
        {"scene_id": "scene_002", "content": "하락 압력이 더 이어질 수 있습니다."},
    ]

    normalized, audit = normalize_scene_sentence_boundaries(sections)

    assert [scene["content"] for scene in normalized] == [
        "첫 문장입니다.",
        "반대로 실망스러운 가이던스가 나오면 하락 압력이 더 이어질 수 있습니다.",
    ]
    assert "prompt" not in normalized[0]
    assert audit["repair_count"] == 1
    assert compact_text("".join(scene["content"] for scene in normalized)) == compact_text(
        "".join(scene["content"] for scene in sections)
    )


def test_normalized_scene_boundaries_bind_to_complete_caption_chunks():
    sections = [
        {"content": "첫 문장입니다. 두 회사가 같은 방향을 향하면서도"},
        {"content": "서로 다른 경로를 선택한 셈이죠."},
    ]
    chunks = [
        {"index": 1, "text": "첫 문장입니다.", "start": 0.0, "end": 1.0},
        {"index": 2, "text": "두 회사가 같은 방향을 향하면서도", "start": 1.0, "end": 2.0},
        {"index": 3, "text": "서로 다른 경로를 선택한 셈이죠.", "start": 2.0, "end": 3.0},
    ]

    normalized, _ = normalize_scene_sentence_boundaries(sections)
    binding = bind_caption_chunks_to_scenes(normalized, chunks)

    assert binding["passed"] is True
    assert binding["mappings"][0]["chunk_indexes"] == [1]
    assert binding["mappings"][1]["chunk_indexes"] == [2, 3]


def test_scene_with_multiple_complete_sentences_is_not_merged():
    sections = [
        {"content": "첫 문장입니다. 둘째 문장입니다."},
        {"content": "마지막 문장입니다."},
    ]

    normalized, audit = normalize_scene_sentence_boundaries(sections)

    assert normalized == sections
    assert audit["repair_count"] == 0


def test_longform_image_transition_uses_bound_caption_end_not_character_ratio():
    scenes = [
        {"scene_id": "scene_001", "content": "첫 문장입니다. 둘째 설명입니다."},
        {"scene_id": "scene_002", "content": "마지막 문장입니다."},
    ]
    chunks = [
        {"index": 1, "text": "첫 문장입니다.", "start": 0.0, "end": 1.4},
        {"index": 2, "text": "둘째 설명입니다.", "start": 1.4, "end": 3.7},
        {"index": 3, "text": "마지막 문장입니다.", "start": 3.7, "end": 10.0},
    ]
    binding = bind_caption_chunks_to_scenes(scenes, chunks)
    for scene, mapping in zip(scenes, binding["mappings"]):
        scene["caption_chunk_contract"] = mapping

    _assign_scene_durations_from_chunks(scenes, chunks, total_duration=10.0)

    assert scenes[0]["end_time"] == 3.7
    assert scenes[0]["image_transition_after_caption_chunk"] == 1
    assert scenes[1]["start_time"] == 3.7


def test_script_contract_uses_text_for_tts_when_a_scene_has_an_editorial_content_field():
    spoken = "실제로 읽을 문장입니다."
    contract = build_script_contract(
        spoken,
        [{"content": "편집용 장면 설명", "text_for_tts": spoken}],
    )

    assert contract["scene_sources"][0]["text_sha256"] == text_sha256(spoken)


def test_script_contract_accepts_tts_whitespace_normalization_without_rewriting_words():
    script = "첫 문장입니다.\n\n둘째 문장입니다."
    sections = [
        {"content": "첫 문장입니다."},
        {"content": "둘째 문장입니다."},
    ]
    contract = build_script_contract(script, sections)
    canonical = canonical_narration_text(script)

    result = verify_tts_against_script_contract(
        {
            "canonical_text": canonical,
            "canonical_sha256": text_sha256(canonical),
            "chunks": [{"text": "첫 문장입니다."}, {"text": "둘째 문장입니다."}],
        },
        contract,
    )

    assert result["passed"] is True


def test_script_contract_rejects_a_section_that_does_not_match_approved_script():
    with pytest.raises(NarrationContractError, match="장면 내레이션"):
        build_script_contract(
            "승인된 문장입니다.",
            [{"content": "다른 문장입니다."}],
        )


def test_tts_contract_rejects_a_subtitle_rewrite_even_when_the_audio_hash_is_valid():
    script = "승인된 원문입니다."
    contract = build_script_contract(script, [{"content": script}])
    tts_meta = {
        "canonical_text": script,
        "canonical_sha256": text_sha256(script),
        "chunks": [{"text": "요약된 자막입니다."}],
    }

    with pytest.raises(NarrationContractError, match="자막 청크"):
        verify_tts_against_script_contract(tts_meta, contract)


def test_image_stage_rejects_tts_from_a_different_approved_script():
    script = "승인된 원문입니다."
    script_meta = {
        "script": script,
        "sections": [{"scene_id": "script_scene_001", "content": script}],
        "narration_contract": build_script_contract(script, [{"content": script}]),
    }
    tts_meta = {
        "canonical_text": "다른 원문입니다.",
        "canonical_sha256": text_sha256("다른 원문입니다."),
        "chunks": [{"text": "다른 원문입니다."}],
    }

    with pytest.raises(RuntimeError, match="이미지 단계 대본·TTS·자막 계보 검증 실패"):
        ImagesWorker()._generate(
            scenes_meta=script_meta["sections"],
            script_meta_json=json.dumps(script_meta, ensure_ascii=False),
            tts_meta_json=json.dumps(tts_meta, ensure_ascii=False),
        )


def test_assembly_rejects_a_scene_rewrite_before_mp4_work_starts():
    script = "승인된 원문입니다."
    tts_meta = {
        "canonical_text": script,
        "canonical_sha256": text_sha256(script),
        "chunks": [{"text": script, "start": 0.0, "duration": 1.0}],
        "quality_report": {"subtitles": {"passed": True}},
    }

    with pytest.raises(RuntimeError, match="조립 전 대본·TTS·자막·장면 계보 검증 실패"):
        LongformWorker().assemble(
            json.dumps(tts_meta, ensure_ascii=False),
            json.dumps([{"content": "변경된 장면 원문입니다."}], ensure_ascii=False),
            "[]",
        )
