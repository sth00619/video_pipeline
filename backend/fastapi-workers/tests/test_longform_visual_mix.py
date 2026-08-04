import pytest

from app.utils.narration_contract import compact_text
from app.utils.script_delivery import pace_sections_for_runtime
from app.workers.script_worker import (
    _minimum_scene_count,
    _parse_dialogue_sentence_array,
    _split_sections_for_visual_pacing,
    _structured_script_from_dialogue_lines,
    _validate_scene_delivery,
)
from app.v5.scene.longform_visual_mix import apply_longform_visual_mix
from app.v5.scene.runtime_contract import attach_v5_scene_contracts


def _scene(index: int, text: str, scene_type: str = "general") -> dict:
    return {
        "scene_id": f"scene-{index:03d}",
        "scene_type": scene_type,
        "content": text,
        "text": text,
        "visual_intent": text,
    }


def test_runtime_pacing_preserves_narration_and_targets_five_to_six_seconds():
    source = [_scene(index, "시장 흐름을 차분하게 살펴봅니다.") for index in range(120)]
    paced = pace_sections_for_runtime(source, 300)

    assert compact_text(" ".join(scene["content"] for scene in source)) == compact_text(
        " ".join(scene["content"] for scene in paced)
    )
    assert 45 <= len(paced) <= 60
    assert all(scene["runtime_pacing"]["visible_char_count"] > 0 for scene in paced)


def test_visual_pacing_never_splits_a_sentence_at_a_word_boundary():
    source = [_scene(0, "이 문장은 공백을 제외하면 매우 길지만 마침표 하나로 끝나는 완결 문장이어서 중간을 자르면 안 됩니다.")]
    scenes = _split_sections_for_visual_pacing(source)

    assert len(scenes) == 1
    assert scenes[0]["content"] == source[0]["content"]
    with pytest.raises(ValueError, match="26자"):
        _validate_scene_delivery(scenes, target_scene_count=1)


def test_minimum_scene_count_tolerates_the_undershoot_observed_in_job_147():
    # job 147 (2026-08-04): target=55 scenes for a 5-minute video, Claude
    # repeatedly wrote 49-52 complete sentences. The old flat "target-2"
    # tolerance (53) rejected all of these and failed the whole job after
    # 3 retries. The 90%-of-target floor accepts 52 while still requiring a
    # real majority of the target, and keeps average scene length at the
    # 5~6-second contract's own upper bound (300s / 50 scenes = 6.0s).
    assert _minimum_scene_count(55) == 50
    assert 50 <= 52  # the actual undershoot that kept failing


def test_minimum_scene_count_scales_with_target_instead_of_a_flat_offset():
    # A flat "-2" tolerance is far tighter, relatively, for a long video
    # (216/218 = 99%) than a short one (53/55 = 96%) -- backwards from what
    # sampling noise would suggest. A percentage floor treats both the same.
    assert _minimum_scene_count(11) == 10
    assert _minimum_scene_count(218) == 196


def test_structured_dialogue_rewrite_requires_json_array_and_preserves_lines():
    lines = _parse_dialogue_sentence_array('["첫 번째 완결 문장입니다.", "두 번째 완결 문장입니다."]')
    structured = _structured_script_from_dialogue_lines(lines)

    assert lines == ["첫 번째 완결 문장입니다.", "두 번째 완결 문장입니다."]
    assert "[대사]" in structured
    assert "첫 번째 완결 문장입니다." in structured
    assert _parse_dialogue_sentence_array("1. 문장") == []
    assert _parse_dialogue_sentence_array("결과입니다.\n[\"한 문장입니다.\"]") == ["한 문장입니다."]


def test_longform_mix_preserves_article_evidence_and_assigns_other_two_modes():
    source = [
        _scene(0, "기사 근거를 설명합니다.", "graph"),
        *[_scene(index, "반도체와 환율 흐름의 영향을 살펴봅니다.", "metric") for index in range(1, 31)],
    ]
    source[0].update({
        "visual_kind": "article_scene",
        "article_capture": {"local_path": "/tmp/article.png"},
    })

    mixed, audit = apply_longform_visual_mix(source)
    contracted = attach_v5_scene_contracts(mixed)

    assert compact_text(" ".join(scene["content"] for scene in source)) == compact_text(
        " ".join(scene["content"] for scene in mixed)
    )
    assert audit["counts"]["article_evidence"] == 1
    assert audit["counts"]["semantic_illustration"] > 0
    assert audit["counts"]["archetype_explainer"] > 0
    assert contracted[0]["v5_render_contract"]["visual_mode"] == "article_evidence"
    assert all(
        scene["v5_render_contract"]["visual_text_policy"] == "strict_textless"
        for scene in contracted if scene["visual_mode"] == "semantic_illustration"
    )
    assert all(
        scene["v5_render_contract"]["visual_text_policy"] == "script_captioned"
        for scene in contracted if scene["visual_mode"] == "archetype_explainer"
    )
