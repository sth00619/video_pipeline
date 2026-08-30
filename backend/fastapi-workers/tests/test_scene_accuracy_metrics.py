from app.utils.scene_accuracy_metrics import (
    aggregate_scene_accuracy,
    visual_qa_item_results,
)


def test_accuracy_separates_item_accuracy_from_fully_accurate_scene_rate():
    result = aggregate_scene_accuracy([
        {
            "scene_key": "scene:00",
            "items": {"text": "pass", "meaning": "pass", "style": "pass"},
        },
        {
            "scene_key": "scene:01",
            "items": {"text": "pass", "meaning": "fail", "style": "pass"},
        },
    ])

    assert result["evaluated_item_count"] == 6
    assert result["passed_item_count"] == 5
    assert result["item_accuracy"] == 5 / 6
    assert result["fully_accurate_scene_count"] == 1
    assert result["fully_accurate_scene_rate"] == 0.5


def test_pending_blocks_scene_accuracy_without_becoming_a_pass_or_fail_item():
    result = aggregate_scene_accuracy([
        {
            "scene_key": "scene:07",
            "items": {"text": "pass", "user_visual_review": "pending", "fal": "not_applicable"},
        }
    ])

    assert result["evaluated_item_count"] == 1
    assert result["pending_item_count"] == 1
    assert result["not_applicable_item_count"] == 1
    assert result["fully_accurate_scene_count"] == 0


def test_visual_qa_failure_categories_become_shared_pipeline_items():
    items = visual_qa_item_results([
        "text_missing_approved_numeric",
        "scene_semantic_underexplained",
        "unexpected_or_ambiguous_prop",
    ])

    assert items["text_integrity"] == "fail"
    assert items["scene_meaning"] == "fail"
    assert items["unexpected_visual_anomaly"] == "fail"
    assert items["style_fidelity"] == "pass"
