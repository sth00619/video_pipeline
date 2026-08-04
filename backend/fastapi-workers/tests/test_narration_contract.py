import pytest
import json

from app.utils.narration_contract import (
    NarrationContractError,
    build_script_contract,
    canonical_narration_text,
    text_sha256,
    verify_tts_against_script_contract,
)
from app.workers.images_worker import ImagesWorker
from app.workers.longform_worker import LongformWorker


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
