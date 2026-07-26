from PIL import Image

from app.services.overlay.editorial_overlay import OverlaySlot, render_editorial_overlay


def test_overlay_grammar_remains_visible_at_mobile_width():
    slots = [
        OverlaySlot(kind="speech", text="CHECK", claim_type="reaction", anchor="upper_left"),
        OverlaySlot(kind="burst", text="WHY?", claim_type="derived_hook", source_refs=["scene:1"], text_style="gradient"),
        OverlaySlot(kind="metaphor_label", text="12.5%", claim_type="verbatim_fact", source_refs=["facts[0]"], target_bbox=(.5, .2, .25, .18)),
    ]
    for slot in slots:
        rendered = render_editorial_overlay(slot, canvas_size=(1920, 1080))
        assert rendered and rendered.bbox
        mobile = rendered.image.resize((320, 180), Image.Resampling.LANCZOS)
        assert mobile.getbbox() is not None
