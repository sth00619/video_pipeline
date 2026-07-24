from __future__ import annotations

from PIL import ImageDraw

from .base import BaseTemplate, AssetBundle, register


@register
class ArticleEvidenceTemplate(BaseTemplate):
    template_id = "article_evidence"
    panel_ratio = .38

    def place_subjects(self, canvas, brief, assets: AssetBundle) -> None:
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle((42, 34, 265, 78), radius=14, fill=(255, 255, 255, 230))
        from ..text_panel import _font
        d.text((58, 43), f"출처: {brief.evidence.publisher}", font=_font(22), fill=(25, 25, 25))
