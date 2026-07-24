from PIL import Image

from app.services.annotate import render_annotations
from app.workers.longform_worker import _default_capture_annotations


def _has_red_near(image: Image.Image, x: int, y: int) -> bool:
    for px in range(max(0, x - 4), min(image.width, x + 5)):
        for py in range(max(0, y - 4), min(image.height, y + 5)):
            r, g, b, a = image.getpixel((px, py))
            if a and r > 180 and g < 80 and b < 100:
                return True
    return False


def test_normalized_underline_maps_to_landscape_and_portrait():
    annotation = {"type": "underline", "bboxes": [{"x": .1, "y": .3, "width": .5, "height": .08}]}
    landscape = render_annotations((1920, 1080), [annotation])
    portrait = render_annotations((1080, 1920), [annotation])
    assert _has_red_near(landscape, int(1920 * .35), int(1080 * .38))
    assert _has_red_near(portrait, int(1080 * .35), int(1920 * .38))


def test_annotation_renderer_is_pixel_deterministic():
    annotations = [
        {"type": "ellipse", "bbox": {"x": .2, "y": .2, "width": .2, "height": .2}},
        {"type": "arrow", "from_xy": [.1, .1], "to_xy": [.6, .6]},
    ]
    one = render_annotations((960, 540), annotations)
    two = render_annotations((960, 540), annotations)
    assert one.tobytes() == two.tobytes()


def test_legacy_dom_capture_migrates_to_allowed_highlight_underline_policy():
    result = _default_capture_annotations({
        "quote_bboxes": [{"x": .1, "y": .2, "width": .4, "height": .08}],
        "target_bbox": {"x": .1, "y": .2, "width": .4, "height": .08},
    })
    assert [item["type"] for item in result] == ["highlighter", "underline"]
    assert all(item["origin"] == "dom_quote_default_v3" for item in result)
