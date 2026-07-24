from __future__ import annotations

from PIL import Image, ImageDraw, ImageEnhance

from .base import BaseTemplate, AssetBundle, register
from ..mascot_compositor import paste_mascot
from ..text_panel import _font
from ..semantic_emphasis import draw_semantic_emphasis


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
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        font = _font(max(34, round(canvas.width * .034)))
        max_width = int(canvas.width * .47)
        while getattr(font, "size", 26) > 26 and draw.textlength(text, font=font) > max_width:
            font = _font(font.size - 2)
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=2)
        width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        left = (
            int(canvas.width * .035)
            if side == "left"
            else canvas.width - width - 48 - int(canvas.width * .035)
        )
        # The channel watermark owns the top-right corner. A mirrored bubble
        # moves below that reserved zone instead of being painted underneath it.
        top = int(canvas.height * (.14 if side == "right" else .035))
        bubble = (left, top, left + width + 48, top + height + 34)
        draw.rounded_rectangle(
            bubble, radius=24, fill=(255, 255, 255, 246),
            outline=(16, 16, 16, 255), width=5,
        )
        draw.polygon(
            [
                (bubble[2] - 70, bubble[3] - 2),
                (bubble[2] - 20, bubble[3] - 2),
                (bubble[2] - 28, bubble[3] + 38),
            ],
            fill=(255, 255, 255, 246),
            outline=(16, 16, 16, 255),
        )
        draw.text(
            (left + 24, top + 12 - bbox[1]),
            text,
            font=font,
            fill=(255, 211, 42, 255),
            stroke_width=4,
            stroke_fill=(10, 10, 10, 255),
        )
        canvas.alpha_composite(layer)
        return {
            "x": bubble[0],
            "y": bubble[1],
            "width": bubble[2] - bubble[0],
            "height": bubble[3] - bubble[1] + 38,
        }
