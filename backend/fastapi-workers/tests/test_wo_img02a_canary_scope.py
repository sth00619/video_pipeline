from scripts.run_wo_img02a_before_after_canary import _validate_spec


def _spec(scenes: list[int]) -> dict:
    return {
        "paid_execution_authorized": True,
        "authorization": {
            "approved_total_reserved_krw": 1600 * len(scenes),
            "reserved_per_attempt_krw": 1600,
            "external_image_post_limit": len(scenes),
            "attempts_per_scene": 1,
            "retry_on_failure": False,
        },
        "model": "gemini-3-pro-image",
        "service_tier": "priority",
        "scenes": scenes,
        "scene42_frozen_and_excluded": True,
    }


def test_scene00_canary_one_request_is_allowed() -> None:
    assert _validate_spec(_spec([0])) == (0,)


def test_remaining_three_scenes_can_follow_successful_canary() -> None:
    assert _validate_spec(_spec([7, 15, 28])) == (7, 15, 28)


def test_canary_cannot_expand_beyond_reviewed_four_scenes() -> None:
    spec = _spec([0, 1])
    try:
        _validate_spec(spec)
    except RuntimeError as exc:
        assert "부분집합" in str(exc)
    else:
        raise AssertionError("허용되지 않은 장면이 canary 범위를 우회했습니다.")

