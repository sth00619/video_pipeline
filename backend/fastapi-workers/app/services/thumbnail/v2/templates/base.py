from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from ..brief import ThumbnailBriefV2
from ..text_panel import Zone, draw

# Render long-form masters at Full HD.  YouTube re-encodes uploads, so local
# type and cutout edges need more source pixels than a 1280px preview.
SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920)}
TEMPLATE_REGISTRY: dict[str, type["BaseTemplate"]] = {}


class CleanPlateRequiredError(ValueError):
    """A cutout-led layout may only use a pre-character background plate."""

    code = "CLEAN_PLATE_REQUIRED"


def register(cls: type["BaseTemplate"]) -> type["BaseTemplate"]:
    TEMPLATE_REGISTRY[cls.template_id] = cls
    return cls


@dataclass
class AssetBundle:
    source: dict[str, Any]
    sources: list[dict[str, Any]]
    person_photos: list[dict[str, Any]]
    mascot_path: str | None
    watermark_path: str | None
    layout_plan: Any | None = None


class BaseTemplate:
    template_id: ClassVar[str]
    panel_ratio: ClassVar[float] = .38

    @staticmethod
    def _overlaps(left: dict[str, int], right: tuple[int, int, int, int]) -> bool:
        return not (
            left["x"] + left["width"] <= right[0]
            or left["x"] >= right[2]
            or left["y"] + left["height"] <= right[1]
            or left["y"] >= right[3]
        )

    def text_zone(self, size: tuple[int, int]) -> Zone:
        width, height = size
        panel_h = int(height * self.panel_ratio)
        return Zone(int(width * .04), height - panel_h, int(width * .92), panel_h, int(width * .03))

    def background(self, source: dict[str, Any], size: tuple[int, int]) -> Image.Image:
        path = Path(str(source.get("image_path") or source.get("path") or ""))
        if not path.is_file():
            raise FileNotFoundError("THUMBNAIL_SOURCE_NOT_IN_VIDEO")
        with Image.open(path) as loaded:
            return ImageOps.fit(loaded.convert("RGBA"), size, Image.Resampling.LANCZOS)

    @staticmethod
    def _normalised_region(raw: Any) -> tuple[float, float, float, float] | None:
        """Read the scene-compositor's normalised character keep-out region."""
        if not isinstance(raw, dict):
            return None
        try:
            x = float(raw.get("x", raw.get("left", 0)))
            y = float(raw.get("y", raw.get("top", 0)))
            width = float(raw.get("width", 0))
            height = float(raw.get("height", 0))
        except (TypeError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        return (
            max(0.0, min(1.0, x)),
            max(0.0, min(1.0, y)),
            max(0.0, min(1.0 - x, width)),
            max(0.0, min(1.0 - y, height)),
        )

    def character_free_background(
        self,
        source: dict[str, Any],
        size: tuple[int, int],
    ) -> tuple[Image.Image, dict[str, Any]]:
        """Return a single clean plate for a cutout-led thumbnail.

        A scene can already contain an integrated channel mascot.  Painting a
        second selected mascot or a licensed person on top of that scene makes
        the thumbnail look like an accidental collage.  New composite scenes
        retain a real background-only plate; for older integrated scenes we
        deterministically crop the larger side outside ``character_regions``.
        The crop remains derived from an in-video scene and is recorded in
        provenance, rather than generating a separate poster image.
        """
        # ``clean_plate_path`` is created by the image worker before character
        # compositing.  Earlier jobs only have a finished scene, which can
        # already contain a mascot; those jobs must use a non-cutout template
        # until they are regenerated rather than silently duplicating it.
        for key in ("clean_plate_path",):
            clean_path = Path(str(source.get(key) or ""))
            if clean_path.is_file():
                with Image.open(clean_path) as loaded:
                    return (
                        ImageOps.fit(loaded.convert("RGBA"), size, Image.Resampling.LANCZOS),
                        {"kind": "background_plate", "path_key": key},
                    )

        if self.template_id in {"person_headline", "mascot_headline"}:
            raise CleanPlateRequiredError(
                "CLEAN_PLATE_REQUIRED: cutout-led thumbnails require a scene clean_plate_path"
            )
        source_path = Path(str(source.get("image_path") or source.get("path") or ""))
        if not source_path.is_file():
            raise FileNotFoundError("THUMBNAIL_SOURCE_NOT_IN_VIDEO")
        regions = [
            region for region in (
                self._normalised_region(value)
                for value in (source.get("character_regions") or [])
            ) if region is not None
        ]
        with Image.open(source_path) as loaded:
            image = loaded.convert("RGBA")
            if not regions:
                return (
                    ImageOps.fit(image, size, Image.Resampling.LANCZOS),
                    {"kind": "scene_no_character_region"},
                )
            # Use the largest estimated character area. The image worker uses
            # a broad conservative region, which is exactly what we need here.
            x, _y, width, _height = max(regions, key=lambda value: value[2] * value[3])
            gap = .025
            left_end = max(0.0, x - gap)
            right_start = min(1.0, x + width + gap)
            left_width = left_end
            right_width = 1.0 - right_start
            if max(left_width, right_width) < .40:
                return (
                    ImageOps.fit(image, size, Image.Resampling.LANCZOS),
                    {"kind": "scene_region_too_wide"},
                )
            if right_width >= left_width:
                crop_left, crop_right, side = right_start, 1.0, "right"
            else:
                crop_left, crop_right, side = 0.0, left_end, "left"
            cropped = image.crop((
                round(crop_left * image.width), 0,
                round(crop_right * image.width), image.height,
            ))
            return (
                ImageOps.fit(cropped, size, Image.Resampling.LANCZOS),
                {
                    "kind": "cropped_around_embedded_character",
                    "kept_side": side,
                    "crop": [round(crop_left, 4), 0.0, round(crop_right - crop_left, 4), 1.0],
                },
            )

    def collage_background(self, assets: AssetBundle, size: tuple[int, int]) -> Image.Image:
        """Build a dense montage from scenes proven to exist in the final video."""
        primary = self.background(assets.source, size)
        if len(assets.sources) < 2:
            return primary
        width, height = size
        top_h = int(height * .67)
        canvas = Image.new("RGBA", size, (8, 10, 14, 255))
        canvas.alpha_composite(
            ImageOps.fit(primary, (width, top_h), Image.Resampling.LANCZOS),
            (0, 0),
        )
        support_path = Path(str(
            assets.sources[1].get("image_path")
            or assets.sources[1].get("path")
            or ""
        ))
        if support_path.is_file():
            with Image.open(support_path) as loaded:
                support = ImageOps.fit(
                    loaded.convert("RGBA"),
                    (int(width * .42), int(top_h * .72)),
                    Image.Resampling.LANCZOS,
                )
            alpha = Image.new("L", support.size, 255)
            alpha_draw = ImageDraw.Draw(alpha)
            fade = max(16, support.width // 10)
            for x in range(fade):
                alpha_draw.line((x, 0, x, support.height), fill=round(255 * x / fade))
            support.putalpha(alpha.filter(ImageFilter.GaussianBlur(max(2, fade // 5))))
            support_x = (
                width - support.width
                if getattr(assets.layout_plan, "layout_variant", "default") == "mirrored"
                else 0
            )
            canvas.alpha_composite(support, (support_x, int(top_h * .08)))
        return canvas

    @staticmethod
    def cinematic_grade(canvas: Image.Image, top_ratio: float = .68) -> None:
        """Add the dark edge contrast and lower fade of a manual thumbnail."""
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw_ctx = ImageDraw.Draw(overlay)
        top_h = int(canvas.height * top_ratio)
        draw_ctx.rectangle((0, 0, canvas.width, top_h), fill=(4, 8, 16, 26))
        fade_start = max(0, top_h - 150)
        for y in range(fade_start, top_h):
            alpha = round(190 * (y - fade_start) / max(1, top_h - fade_start))
            draw_ctx.line((0, y, canvas.width, y), fill=(0, 0, 0, alpha))
        for inset in range(0, 42, 3):
            alpha = max(0, 34 - inset)
            draw_ctx.rounded_rectangle(
                (inset, inset, canvas.width - inset - 1, canvas.height - inset - 1),
                radius=24,
                outline=(0, 0, 0, alpha),
                width=4,
            )
        canvas.alpha_composite(overlay)

    def draw_panel(self, canvas: Image.Image, zone: Zone) -> None:
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw_ctx = ImageDraw.Draw(overlay)
        draw_ctx.rectangle((0, zone.top, canvas.width, canvas.height), fill=(0, 0, 0, 238))
        draw_ctx.rectangle((0, max(0, zone.top - 18), canvas.width, zone.top), fill=(0, 0, 0, 96))
        canvas.alpha_composite(overlay)

    def overlay_badge(self, canvas: Image.Image, brief: ThumbnailBriefV2) -> None:
        if not brief.badge:
            return
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle((canvas.width - 300, 34, canvas.width - 34, 108), radius=18, fill=(0, 0, 0, 210), outline=(229, 36, 29), width=3)
        from ..text_panel import _font
        d.text((canvas.width - 278, 50), f"{brief.badge.label} {brief.badge.value}", font=_font(30), fill=(255, 214, 0))

    def watermark(self, canvas: Image.Image, path: str | None) -> None:
        if not path or not Path(path).is_file():
            return
        with Image.open(path) as source:
            mark = source.convert("RGBA")
        mark.thumbnail((int(canvas.width * .18), int(canvas.height * .10)), Image.Resampling.LANCZOS)
        canvas.alpha_composite(mark, (canvas.width - mark.width - int(canvas.width * .04), int(canvas.height * .035)))

    def render(self, brief: ThumbnailBriefV2, assets: AssetBundle, aspect: str) -> Image.Image:
        size = SIZES[aspect]
        self.last_protected_regions: list[dict[str, int]] = []
        self.last_subject_area = max(.16, 1 - self.panel_ratio)
        self.last_bubble_area_ratio = 0.0
        self.last_semantic_marks: list[dict[str, object]] = []
        canvas = self.collage_background(assets, size)
        self.place_subjects(canvas, brief, assets)
        self.cinematic_grade(canvas, 1 - self.panel_ratio)
        zone = self.text_zone(size)
        copy_box = (zone.left, zone.top, zone.left + zone.width, zone.top + zone.height)
        self.last_overlap_count = sum(
            1 for region in self.last_protected_regions if self._overlaps(region, copy_box)
        )
        self.draw_panel(canvas, zone)
        self.last_text_metrics = draw(canvas, brief, zone)
        self.overlay_badge(canvas, brief)
        self.watermark(canvas, assets.watermark_path)
        return canvas

    def place_subjects(self, canvas: Image.Image, brief: ThumbnailBriefV2, assets: AssetBundle) -> None:
        return None
