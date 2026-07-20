from app.utils.intro_motion import select_intro_motion_scene_indices
from app.workers.longform_worker import _build_kling_motion_prompt


def _scenes(count: int, duration: float = 5.0):
    return [{"duration": duration} for _ in range(count)]


def test_ten_minute_video_uses_contiguous_40_second_opening_budget():
    indices, target, actual = select_intro_motion_scene_indices(
        _scenes(120), 600,
        short_seconds=40,
        long_seconds=60,
        short_threshold=660,
        max_clips=12,
    )
    assert indices == set(range(8))
    assert target == 40
    assert actual == 40


def test_long_video_uses_contiguous_60_second_opening_budget():
    indices, target, actual = select_intro_motion_scene_indices(
        _scenes(240), 1200,
        short_seconds=40,
        long_seconds=60,
        short_threshold=660,
        max_clips=12,
    )
    assert indices == set(range(12))
    assert target == 60
    assert actual == 60


def test_budget_cap_never_selects_later_scenes_or_exceeds_fal_limit():
    indices, target, actual = select_intro_motion_scene_indices(
        _scenes(120), 600,
        short_seconds=40,
        long_seconds=60,
        short_threshold=660,
        max_clips=6,
    )
    assert indices == set(range(6))
    assert target == 40
    assert actual == 30


def test_motion_prompt_uses_delivery_metadata_and_locks_camera_and_layout():
    prompt = _build_kling_motion_prompt({
        "character_action": "pointer_up",
        "emotion_tag": "worried",
        "edit_marker": "data_overlay",
    }).lower()
    assert "pointer prop" in prompt
    assert "worried expression" in prompt
    assert "every number and label remains perfectly static" in prompt
    assert "no camera motion" in prompt
    assert "no zoom" in prompt
    assert "no pan" in prompt
    assert "no transition" in prompt
