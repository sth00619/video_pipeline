from app.services.overlay.editorial_overlay import OverlaySlot, render_editorial_overlay


def test_every_overlay_kind_renders_or_fail_closes_with_target_contract():
    target = (.35, .22, .20, .14)
    for kind in ("speech", "shout", "burst", "cloud", "caption_chip", "article_callout", "badge", "title_card", "date_stamp", "chalk_note", "metaphor_label"):
        slot = OverlaySlot(
            kind=kind,
            text="핵심 확인",
            claim_type="derived_hook" if kind == "burst" else "reaction",
            source_refs=["facts[0]"] if kind == "burst" else [],
            target_bbox=target if kind in {"cloud", "article_callout", "chalk_note", "metaphor_label"} else None,
            text_style="gradient" if kind == "burst" else "solid",
        )
        result = render_editorial_overlay(slot)
        assert result is not None
        assert result.skipped_reason is None
        assert result.image.getbbox() is not None


def test_overlay_rejects_invalid_gradient_and_protected_watermark_collision():
    try:
        OverlaySlot(kind="speech", text="질문", claim_type="reaction", text_style="gradient")
        raise AssertionError("gradient must be rejected outside question burst")
    except ValueError:
        pass
    result = render_editorial_overlay(
        OverlaySlot(kind="speech", text="보호 영역", anchor="upper_left"),
        subject_regions=[{"x": 0, "y": 0, "width": 1, "height": .79}],
    )
    assert result is not None
    assert result.skipped_reason == "protected_region_collision"


def test_chalk_note_writes_inside_its_board_without_a_white_card():
    result = render_editorial_overlay(
        OverlaySlot(
            kind="chalk_note", text="상승 이유", claim_type="reaction",
            target_bbox=(.10, .16, .55, .42), anchor="target",
        ),
        canvas_size=(960, 540),
    )
    assert result and not result.skipped_reason
    # A chalk note begins inside the authored board, rather than above it.
    assert result.bbox["x"] > 96
    assert result.bbox["y"] > 86
