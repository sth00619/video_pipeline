from app.services.overlay.editorial_director import direct_editorial_overlays
from app.workers.longform_worker import _assign_editorial_overlay_timing


def _scene(section, bubble, **extra):
    return {
        "section": section,
        "title": "장면",
        "content": "경제 흐름을 설명합니다.",
        "bubble_text": bubble,
        "bubble_validation": {"passed": True, "matched_sources": ["facts[0]"]},
        **extra,
    }


def test_director_prioritises_verified_data_and_limits_dense_bubbles():
    scenes = [
        _scene("intro", "왜 지금일까?", pose="thinking"),
        _scene("background", "원인을 보자", pose="explaining"),
        _scene("data", "15% 상승", data_overlay_plan={"chart_kind": "trend"}),
        _scene("scenario", "위험 신호", pose="worried"),
        _scene("action", "비교해 보자", pose="pointing"),
        _scene("conclusion", "핵심을 기억하세요", pose="neutral"),
    ]

    result = direct_editorial_overlays(scenes)

    assert result[2]["editorial_decision"]["reason"] == "verified_data_visual_priority"
    assert "editorial_overlay_plan" not in result[2]
    selected = [scene for scene in result if scene["editorial_decision"]["selected"]]
    assert len(selected) <= 2
    assert result[0]["editorial_overlay_plan"]["overlay"]["kind"] == "burst"


def test_tts_scene_timing_places_overlay_inside_the_scene():
    scenes = [
        {"duration": 4.0, "editorial_overlay_plan": {"overlay": {"text": "질문"}}},
        {"duration": 2.0, "data_overlay_plan": {"chart_kind": "trend"}},
    ]
    _assign_editorial_overlay_timing(scenes)
    for scene in scenes:
        timing = scene["overlay_timing"]
        assert 0 <= timing["start"] < timing["end"] <= scene["duration"]
        assert timing["source"] == "tts_scene_duration"


def test_classroom_explanation_uses_a_board_bound_chalk_note():
    scene = _scene(
        "background", "상승의 이유는?", pose="explaining",
        art_direction={
            "family": "history_classroom",
            "editorial_text_surface": {"x": .10, "y": .16, "width": .55, "height": .42},
        },
    )
    result = direct_editorial_overlays([scene])[0]
    overlay = result["editorial_overlay_plan"]["overlay"]
    assert overlay["kind"] == "chalk_note"
    assert overlay["target_bbox"] == (.10, .16, .55, .42)


def test_cause_explanation_uses_a_target_bound_cloud():
    scene = _scene(
        "scenario", "왜 중요한가?", pose="explaining",
        art_direction={"editorial_overlay_target": {"x": .53, "y": .16, "width": .36, "height": .25}},
    )
    result = direct_editorial_overlays([scene])[0]
    overlay = result["editorial_overlay_plan"]["overlay"]
    assert overlay["kind"] == "cloud"
    assert overlay["target_bbox"] == (.53, .16, .36, .25)
