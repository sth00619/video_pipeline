from app.services.overlay.style_profile import load_channel_overlay_style


def test_profile_is_channel_resolved_and_never_environment_driven():
    style = load_channel_overlay_style("black_han_sans_v1")
    assert style.danger_color == "#FF5148"
    assert style.benefit_color == "#FFD230"
    assert style.speech_max_width_ratio == .42
    assert style.font_display.is_file()


def test_unknown_profile_fails_closed():
    try:
        load_channel_overlay_style("unreviewed_theme")
        raise AssertionError("unreviewed profile must not use host assets")
    except ValueError as exc:
        assert str(exc) == "UNSUPPORTED_REFERENCE_STYLE_PROFILE"
