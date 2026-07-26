from __future__ import annotations

from PIL import Image, ImageEnhance

from .base import BaseTemplate, AssetBundle, register
from ..mascot_compositor import paste_mascot
from ..semantic_emphasis import draw_semantic_emphasis
from app.services.overlay.editorial_overlay import OverlaySlot, render_editorial_overlay


@register
class ChartWarningTemplate(BaseTemplate):
    template_id = "chart_warning"
    panel_ratio = .46

    def place_subjects(self, canvas, brief, assets: AssetBundle) -> None:
        # Charts are deliberately darkened so locally-rendered copy is the
        # dominant reading order.  The focus ring is renderer-owned, never OCR.
        muted = ImageEnhance.Brightness(canvas.convert("RGB")).enhance(.80).convert("RGBA")
        canvas.paste(muted)
        if brief.secondary_subject.allowed and assets.mascot_path:
            plan = assets.layout_plan
            mascot = getattr(plan, "mascot", None)
            region = paste_mascot(
                canvas,
                assets.mascot_path,
                brief.secondary_subject.emotion,
                max_height_ratio=getattr(mascot, "height_ratio", .26),
                side=getattr(mascot, "side", "right"),
                safe_bottom_ratio=1 - self.panel_ratio,
            )
            self.last_protected_regions.append(region)
        self.last_semantic_marks = draw_semantic_emphasis(
            canvas, brief.semantic_emphasis, {"chart": {"x": 0, "y": 0, "width": canvas.width, "height": int(canvas.height * .54)}}
        )
        if brief.speech_bubble:
            bubble = getattr(getattr(assets.layout_plan, "bubble", None), "side", "left")
            bubble_region = self._speech_bubble(canvas, brief.speech_bubble, bubble)
            self.last_protected_regions.append(bubble_region)
            self.last_bubble_area_ratio = (
                bubble_region["width"] * bubble_region["height"] / max(1, canvas.width * canvas.height)
            )

    @staticmethod
    def _speech_bubble(canvas: Image.Image, text: str, side: str = "left") -> dict[str, int]:
        result = render_editorial_overlay(
            OverlaySlot(
                kind="speech",
                text=text,
                anchor="upper_left" if side == "left" else "upper_right",
            ),
            canvas_size=canvas.size,
        )
        if result and result.bbox:
            canvas.alpha_composite(result.image)
            return result.bbox
        return {"x": 0, "y": 0, "width": 0, "height": 0}
