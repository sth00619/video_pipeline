from app.utils.info_surface_motion import (
    max_inverse_anchor_delta,
    max_inverse_relative_anchor_delta,
    max_normalized_anchor_delta,
)


def test_inverse_motion_check_accepts_one_shared_transform():
    # The same in-world point after three different crop/scale transforms.
    samples = [((200, 180), {"scale": 1, "tx": 0, "ty": 0}), ((260, 225), {"scale": 1.25, "tx": 10, "ty": 0}), ((320, 270), {"scale": 1.5, "tx": 20, "ty": 0})]
    assert max_inverse_anchor_delta(samples) <= 1.0


def test_normalized_motion_fallback_detects_overlay_leakage():
    stable = [((120, 110), (100, 100), 500), ((145, 130), (125, 120), 500), ((170, 150), (150, 140), 500)]
    leaking = [((120, 110), (100, 100), 500), ((120, 110), (125, 120), 500)]
    assert max_normalized_anchor_delta(stable) <= .002
    assert max_normalized_anchor_delta(leaking) > .002


def test_inverse_motion_check_compares_text_to_surface_in_source_space():
    # The screen-space gap changes because every frame is cropped/scaled, but
    # after inverse mapping the chart glyph and its paper anchor stay together.
    stable = [
        ((220, 210), (180, 160), {"scale": 1, "tx": 0, "ty": 0}),
        ((285, 270), (235, 207.5), {"scale": 1.25, "tx": 10, "ty": 10}),
        ((350, 330), (290, 255), {"scale": 1.5, "tx": 20, "ty": 30}),
    ]
    leaking = [
        ((220, 210), (180, 160), {"scale": 1, "tx": 0, "ty": 0}),
        ((220, 210), (235, 207.5), {"scale": 1.25, "tx": 10, "ty": 10}),
    ]
    assert max_inverse_relative_anchor_delta(stable) <= 1.0
    assert max_inverse_relative_anchor_delta(leaking) > 1.0
