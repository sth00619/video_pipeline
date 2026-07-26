import pytest

from app.services.overlay.editorial_overlay import OverlaySlot
from app.services.overlay.plans import SceneEditorialOverlayPlan


def test_scene_plan_rejects_category_violation_and_subtitle_duplicate():
    with pytest.raises(ValueError, match="not allowed"):
        SceneEditorialOverlayPlan(
            section="intro", message_role="hook", overlay=OverlaySlot(kind="caption_chip", text="핵심입니다"),
        )
    with pytest.raises(ValueError, match="duplicates subtitle"):
        SceneEditorialOverlayPlan(
            section="action", message_role="decision", overlay=OverlaySlot(kind="speech", text="이 흐름을 지금 확인하세요"),
            subtitle_text="이 흐름을 지금 확인하세요 반드시",
        )


def test_scene_plan_requires_target_for_background_cloud():
    with pytest.raises(ValueError, match="target-bound"):
        OverlaySlot(kind="cloud", text="정책 변수", claim_type="reaction")
