from __future__ import annotations

from .base import BaseTemplate, AssetBundle, register
from ..semantic_emphasis import draw_semantic_emphasis


@register
class ProductEarningsTemplate(BaseTemplate):
    template_id = "product_earnings"

    def place_subjects(self, canvas, brief, assets: AssetBundle) -> None:
        self.last_semantic_marks = draw_semantic_emphasis(canvas, brief.semantic_emphasis)
