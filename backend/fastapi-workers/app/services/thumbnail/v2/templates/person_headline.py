from __future__ import annotations

from app.services.thumbnail.person_compositor import paste_person, validate_photo
from app.services.thumbnail.v2.editorial_effects import grade_photo_backdrop
from app.services.thumbnail.v2.semantic_emphasis import draw_semantic_emphasis
from .base import BaseTemplate, AssetBundle, register


@register
class PersonHeadlineTemplate(BaseTemplate):
    template_id = "person_headline"
    panel_ratio = .39

    def collage_background(self, assets: AssetBundle, size):
        # A real-person recommendation is an independent mode: never retain
        # an already-integrated mascot from a source scene behind the licensed
        # portrait.  This produces one unmistakable human focal subject.
        canvas, self.last_backdrop_strategy = self.character_free_background(assets.source, size)
        mirrored = getattr(assets.layout_plan, "layout_variant", "default") == "mirrored"
        return grade_photo_backdrop(canvas, subject_side="left" if mirrored else "right")

    def place_subjects(self, canvas, brief, assets: AssetBundle) -> None:
        if not assets.person_photos:
            raise ValueError("person_headline requires an approved person asset")
        mirrored = getattr(assets.layout_plan, "layout_variant", "default") == "mirrored"
        # One large, recognisable approved face is more legible at YouTube
        # card size than two small portraits.  Multi-person jobs rotate the
        # second approved person into another recommendation in the composer.
        photo = assets.person_photos[0]
        validate_photo(photo)
        region = paste_person(
            canvas,
            photo,
            side="left" if mirrored else "right",
            # Portrait options are intentionally cropped large.  At feed size
            # the eyes and expression must remain recognisable before any
            # supporting graphic is noticed.
            height_ratio=.94,
            width_ratio=.58,
            outline_px=10,
        )
        self.last_semantic_marks = draw_semantic_emphasis(
            canvas, brief.semantic_emphasis, {"subject": region}
        )
        self.last_subject_area = (
            region["width"] * region["height"] / max(1, canvas.width * canvas.height)
        )
        # Protect the face rather than the full cutout. A shoulder can
        # intentionally enter the headline shelf; eyes and mouth cannot.
        self.last_protected_regions.append({
            "x": region["x"],
            "y": region["y"],
            "width": region["width"],
            "height": max(1, round(region["height"] * .48)),
        })
        self.last_person_treatment = list(region.get("visual_treatment") or [])
