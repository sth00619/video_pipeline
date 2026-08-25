import numpy as np

from app.services.motion_locality import assess_motion_frames


def test_local_character_motion_is_accepted():
    first = np.zeros((90, 160), dtype=np.uint8)
    second = first.copy()
    third = first.copy()
    second[28:72, 62:102] = 180
    third[25:69, 70:110] = 210

    result = assess_motion_frames([first, second, third])

    assert result["passed"] is True
    assert result["changed_pixel_ratio"] < 0.55
    assert result["border_changed_ratio"] == 0


def test_whole_frame_shimmer_is_rejected():
    first = np.zeros((90, 160), dtype=np.uint8)
    second = np.full((90, 160), 35, dtype=np.uint8)
    third = np.full((90, 160), 70, dtype=np.uint8)

    result = assess_motion_frames([first, second, third])

    assert result["passed"] is False
    assert "whole_frame_change" in result["reasons"]
    assert "global_motion_coverage" in result["reasons"]
    assert "camera_or_border_jitter" in result["reasons"]


def test_nearly_static_fal_clip_is_rejected_instead_of_claiming_motion():
    frame = np.zeros((90, 160), dtype=np.uint8)
    result = assess_motion_frames([frame, frame.copy(), frame.copy()])

    assert result["passed"] is False
    assert result["reasons"] == ["motion_not_detected"]
