from app import runtime_config
from app.utils.budget import plan_preflight


def test_template_reserve_is_recorded_when_affordable():
    old = runtime_config.value("max_budget_per_video_krw")
    try:
        runtime_config.update(max_budget_per_video_krw=70000)
        plan = plan_preflight(3, "flash", 0, 0, template_scene_count=2)
        assert plan["budget_limit_krw"] == 70000
        assert plan["template_regeneration_enabled"] is True
        assert plan["template_retry_reserve_krw"] > 0
    finally:
        runtime_config.update(max_budget_per_video_krw=old)


def test_template_regeneration_is_disabled_above_70000_limit():
    old = runtime_config.value("max_budget_per_video_krw")
    try:
        runtime_config.update(max_budget_per_video_krw=70000)
        plan = plan_preflight(300, "pro", 0, 0, template_scene_count=300)
        assert plan["template_regeneration_enabled"] is False
        assert plan["template_retry_reserve_krw"] == 0
        assert "template_regeneration:disabled_budget_reserve" in plan["actions"]
    finally:
        runtime_config.update(max_budget_per_video_krw=old)
