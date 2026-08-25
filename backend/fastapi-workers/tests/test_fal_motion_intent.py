from app.services.fal_motion_intent import build_fal_motion_preflight, scene_motion_intent


def test_downturn_scene_moves_one_object_and_forbids_global_jitter():
    result = scene_motion_intent(
        {"content": "주가는 오히려 폭락했습니다.", "scene_type": "general"},
        selected=True,
    )
    assert result["eligible_before_image_ocr"] is True
    assert "하락선" in result["primary_motion"]
    assert "전 화면 지글링 또는 노이즈" in result["forbidden_motion"]


def test_text_or_metric_scene_is_recorded_but_not_fal_eligible():
    result = scene_motion_intent(
        {"content": "코스피 6696포인트", "scene_type": "metric", "core_figures": [{"raw": "6696포인트"}]},
        selected=True,
    )
    assert result["eligible_before_image_ocr"] is False
    assert "information_scene_type:metric" in result["block_reasons"]


def test_preflight_never_claims_that_fal_was_called():
    plan = build_fal_motion_preflight([{"scene_id": "s1", "use_kling": True}])
    assert plan["fal_called"] is False
    assert plan["scene_count"] == 1
