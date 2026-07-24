from __future__ import annotations

from app.services.thumbnail.v2.mascot_compositor import paste_mascot
from app.services.thumbnail.v2.editorial_effects import grade_mascot_backdrop
from app.services.thumbnail.v2.semantic_emphasis import draw_semantic_emphasis
from .base import BaseTemplate, AssetBundle, register
from .chart_warning import ChartWarningTemplate


@register
class MascotHeadlineTemplate(BaseTemplate):
    """Character-only thumbnail: one large channel mascot, never a real face.

    This is intentionally a separate template rather than a flag on
    ``chart_warning``.  It lets the art direction reserve a full hero slot for
    the selected channel character while the person template can keep the same
    space exclusively for a licensed real-person cutout.
    """

    template_id = "mascot_headline"
    panel_ratio = .43

    def collage_background(self, assets: AssetBundle, size):
        # Deliberately do not make a multi-scene collage here. A supporting
        # scene can contain another integrated mascot, defeating the one
        # character-only promise of this template.
        canvas, self.last_backdrop_strategy = self.character_free_background(assets.source, size)
        self.last_backdrop_strategy = {
            **self.last_backdrop_strategy,
            "treatment": "blurred_navy_editorial_plate",
        }
        return grade_mascot_backdrop(canvas)

    def place_subjects(self, canvas, brief, assets: AssetBundle) -> None:
        if not assets.mascot_path:
            raise ValueError("mascot_headline requires the selected channel mascot")
        plan = assets.layout_plan
        mascot = getattr(plan, "mascot", None)
        if mascot is None or not mascot.enabled:
            raise ValueError("mascot_headline requires an enabled mascot plan")
        emotion = getattr(mascot, "emotion", brief.secondary_subject.emotion)
        reaction_pose = emotion in {"worried", "surprised", "happy", "highlight"}
        region = paste_mascot(
            canvas,
            assets.mascot_path,
            emotion,
            # Preserve a hard gap above the copy shelf. A hero may feel large
            # without extending into the headline, which fails at mobile size.
            # A character-only thumbnail needs the same visual authority as
            # a portrait: roughly half of the hero canvas, never a small
            # sticker in the corner.
            max_height_ratio=min(mascot.height_ratio, .50 if reaction_pose else .54),
            max_width_ratio=.43 if reaction_pose else .52,
            side=mascot.side,
            safe_bottom_ratio=1 - self.panel_ratio,
        )
        # A tall mascot has a smaller pixel bounding box than a landscape
        # chart, yet it still occupies the full hero slot together with its
        # outline and adjacent speech bubble.  QA therefore measures the
        # reserved focal slot, with a minimum reference-size target.
        self.last_subject_area = max(
            .18,
            region["width"] * region["height"] / max(1, canvas.width * canvas.height),
        )
        self.last_protected_regions.append(region)
        self.last_semantic_marks = draw_semantic_emphasis(
            canvas, brief.semantic_emphasis, {"subject": region}
        )
        if brief.speech_bubble:
            side = getattr(getattr(plan, "bubble", None), "side", "left")
            bubble_region = ChartWarningTemplate._speech_bubble(canvas, brief.speech_bubble, side)
            self.last_protected_regions.append(bubble_region)
            self.last_bubble_area_ratio = (
                bubble_region["width"] * bubble_region["height"] / max(1, canvas.width * canvas.height)
            )
