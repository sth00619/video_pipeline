from app.utils.scene_accuracy_metrics import aggregate_scene_accuracy
from app.utils.visual_quality_checklist import (
    VISUAL_QUALITY_ITEMS,
    aggregate_visual_quality_checklists,
    build_visual_quality_checklist,
)


def test_checklist_keeps_automatic_failures_and_visual_pending_separate() -> None:
    checklist = build_visual_quality_checklist(
        "scene:00",
        automated={
            "text_integrity": "pass",
            "physical_text_surface": "fail",
        },
    )

    assert tuple(checklist["items"]) == VISUAL_QUALITY_ITEMS
    assert checklist["items"]["text_integrity"] == "pass"
    assert checklist["items"]["physical_text_surface"] == "fail"
    assert checklist["items"]["scene_meaning"] == "pending"
    assert checklist["approval_blocked"] is True


def test_accuracy_reports_each_item_and_complete_scene_rate_together() -> None:
    result = aggregate_visual_quality_checklists([
        build_visual_quality_checklist(
            "scene:00",
            automated={
                "text_integrity": "pass",
                "physical_text_surface": "fail",
            },
        )
    ])

    assert result["item_accuracy"] == 0.5
    assert result["fully_accurate_scene_rate"] == 0.0
    assert result["per_item"]["text_integrity"]["passed_count"] == 1
    assert result["per_item"]["physical_text_surface"]["failed_count"] == 1
    assert result["per_item"]["scene_meaning"]["pending_count"] == 1


def test_generic_accuracy_metrics_include_per_item_counts() -> None:
    result = aggregate_scene_accuracy([
        {"scene_key": "scene:00", "items": {"text": "pass", "surface": "fail"}},
        {"scene_key": "scene:01", "items": {"text": "pass", "surface": "pending"}},
    ])

    assert result["per_item"]["text"]["accuracy"] == 1.0
    assert result["per_item"]["surface"]["accuracy"] == 0.0
    assert result["per_item"]["surface"]["pending_count"] == 1

