from app.services.overlay.editorial_director import direct_editorial_overlays
from app.workers.longform_worker import _assign_editorial_overlay_timing


def test_director_suppresses_all_non_subtitle_copy_and_records_the_reason():
    scenes = [
        {
            "section": "intro",
            "content": "시장 흐름을 설명합니다.",
            "bubble_text": "왜 지금일까?",
            "data_overlay_plan": {"chart_kind": "trend"},
            "editorial_overlay_plan": {"overlay": {"text": "기존 카드"}},
        }
    ]

    result = direct_editorial_overlays(scenes)[0]

    assert "editorial_overlay_plan" not in result
    assert result["editorial_decision"] == {
        "index": 0,
        "selected": False,
        "reason": "script_caption_only_policy",
        "policy_version": "v5-script-caption-only-20260803",
        "suppressed_non_subtitle_overlay": True,
    }


def test_tts_scene_timing_still_uses_each_scene_duration():
    scenes = [
        {"duration": 4.0, "editorial_overlay_plan": {"overlay": {"text": "질문"}}},
        {"duration": 2.0, "data_overlay_plan": {"chart_kind": "trend"}},
    ]
    _assign_editorial_overlay_timing(scenes)
    for scene in scenes:
        timing = scene["overlay_timing"]
        assert 0 <= timing["start"] < timing["end"] <= scene["duration"]
        assert timing["source"] == "tts_scene_duration"
