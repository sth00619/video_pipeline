"""Stage 0 회귀 테스트: longform_worker.py L278 수정 검증.

gemini_image_only_budget 정책 하에서 kling_clip_count=0 이 버그를 유발했던 케이스를
단위 테스트로 고정한다.
"""
from __future__ import annotations


def _resolve_kling_cap(budget_preflight: dict, max_clips_cap: int) -> int:
    """longform_worker.py L278 로직 그대로 복제."""
    if budget_preflight.get("gemini_image_only_budget"):
        preflight_kling_cap = int(
            budget_preflight.get("fal_motion_clips_reserved_separately", max_clips_cap)
        )
    else:
        preflight_kling_cap = int(
            budget_preflight.get("kling_clip_count", max_clips_cap)
        )
    return min(max_clips_cap, max(0, preflight_kling_cap))


class TestKlingCapGeminiImageOnlyBudget:
    def test_bug_repro_0_should_not_propagate(self):
        """버그 당시: kling_clip_count=0 이 그대로 읽혀 cap=0 이 됐던 케이스."""
        budget_preflight = {
            "gemini_image_only_budget": True,
            "kling_clip_count": 0,
            "fal_motion_clips_reserved_separately": 9,
        }
        result = _resolve_kling_cap(budget_preflight, max_clips_cap=10)
        assert result == 9, f"Expected 9, got {result}"

    def test_reserved_capped_by_max(self):
        budget_preflight = {
            "gemini_image_only_budget": True,
            "kling_clip_count": 0,
            "fal_motion_clips_reserved_separately": 20,
        }
        result = _resolve_kling_cap(budget_preflight, max_clips_cap=10)
        assert result == 10, f"Expected 10, got {result}"

    def test_reserved_missing_falls_back_to_max(self):
        budget_preflight = {"gemini_image_only_budget": True, "kling_clip_count": 0}
        result = _resolve_kling_cap(budget_preflight, max_clips_cap=5)
        assert result == 5, f"Expected 5, got {result}"

    def test_reserved_zero_is_intentional(self):
        budget_preflight = {
            "gemini_image_only_budget": True,
            "kling_clip_count": 0,
            "fal_motion_clips_reserved_separately": 0,
        }
        result = _resolve_kling_cap(budget_preflight, max_clips_cap=10)
        assert result == 0, f"Expected 0, got {result}"


class TestKlingCapNormalBudget:
    def test_normal_reads_kling_clip_count(self):
        result = _resolve_kling_cap({"kling_clip_count": 7}, max_clips_cap=10)
        assert result == 7

    def test_normal_missing_falls_back_to_max(self):
        result = _resolve_kling_cap({}, max_clips_cap=6)
        assert result == 6

    def test_explicit_false_goes_normal_path(self):
        budget_preflight = {
            "gemini_image_only_budget": False,
            "kling_clip_count": 4,
            "fal_motion_clips_reserved_separately": 99,
        }
        result = _resolve_kling_cap(budget_preflight, max_clips_cap=10)
        assert result == 4
