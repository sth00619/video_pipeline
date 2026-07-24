from app.services.bubble_overlay import render_speech_bubble_overlay


def test_every_bubble_style_renders_large_deterministic_text():
    for style in ("round", "burst", "warning", "positive", "cloud", "shout"):
        one = render_speech_bubble_overlay("15%로 싹!", style=style)
        two = render_speech_bubble_overlay("15%로 싹!", style=style)
        assert one is not None, style
        assert one.tobytes() == two.tobytes(), style
        assert one.getbbox() is not None


def test_bubble_avoids_subtitle_and_annotation_region():
    image = render_speech_bubble_overlay(
        "핵심 구간입니다!",
        character_side="right",
        avoid_regions=[{"x": .03, "y": .04, "width": .45, "height": .40}],
        subtitle_safe_area_pct=21,
    )
    assert image is not None
    # The hard subtitle safe area must be transparent in the bubble layer.
    alpha = image.getchannel("A")
    assert alpha.crop((0, int(image.height * .80), image.width, image.height)).getbbox() is None


def test_bubble_returns_none_when_all_candidates_are_obscured():
    assert render_speech_bubble_overlay(
        "피할 수 없어요", avoid_regions=[{"x": 0, "y": 0, "width": 1, "height": .8}],
    ) is None

