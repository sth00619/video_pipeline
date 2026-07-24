"""Scene-backed thumbnail renderer.

All visible words, numbers, badges and emphasis are rendered locally.  The
normal path does not ask an image model for a second, unrelated thumbnail.
"""
from __future__ import annotations

import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

from app import runtime_config
from .person_compositor import paste_person, validate_photo

LONGFORM_SIZE = (1280, 720)
SHORTS_SIZE = (1080, 1920)
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/app/assets/fonts/NanumGothicBold.ttf",
)


class ThumbnailRenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    scene: dict[str, Any]
    score: float


def output_size(format_name: str) -> tuple[int, int]:
    return SHORTS_SIZE if str(format_name).lower() == "shorts" else LONGFORM_SIZE


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _cover(path: str, size: tuple[int, int]) -> Image.Image:
    try:
        with Image.open(path) as source:
            return ImageOps.fit(source.convert("RGB"), size, method=Image.Resampling.LANCZOS).convert("RGBA")
    except OSError as exc:
        raise ThumbnailRenderError(f"THUMBNAIL_SOURCE_INVALID: {path}") from exc


def _score_scene(scene: dict[str, Any], requested_ids: set[str]) -> float:
    path = Path(str(scene.get("image_path") or scene.get("path") or ""))
    if not path.is_file() or path.stat().st_size < 1024:
        return float("-inf")
    try:
        with Image.open(path) as source:
            image = source.convert("L").resize((160, 90))
            contrast = ImageStat.Stat(image).var[0]
            mean = ImageStat.Stat(image).mean[0]
            edge = ImageStat.Stat(image.filter(ImageFilter.FIND_EDGES)).var[0]
    except OSError:
        return float("-inf")
    scene_id = str(scene.get("scene_id") or scene.get("id") or scene.get("index") or "")
    requested_bonus = 90.0 if scene_id in requested_ids else 0.0
    article_penalty = -18.0 if str(scene.get("generation_method")) == "article_evidence" else 0.0
    # Reward readable, non-black image surfaces; do not infer financial facts.
    exposure = max(0.0, 45.0 - abs(mean - 128.0) * .35)
    return requested_bonus + min(contrast, 110.0) * .35 + min(edge, 2200.0) / 45.0 + exposure + article_penalty


def _clean_line(raw: str) -> str:
    return re.sub(r"\{[yr]:([^{}]+)\}", r"\1", raw or "")


def _segments(raw: str) -> list[tuple[str, tuple[int, int, int, int]]]:
    colors = {"y": (255, 226, 58, 255), "r": (255, 63, 55, 255)}
    out: list[tuple[str, tuple[int, int, int, int]]] = []
    cursor = 0
    for match in re.finditer(r"\{([yr]):([^{}]+)\}", raw or ""):
        if match.start() > cursor:
            out.append((raw[cursor:match.start()], (255, 255, 255, 255)))
        out.append((match.group(2), colors[match.group(1)]))
        cursor = match.end()
    if cursor < len(raw or ""):
        out.append((raw[cursor:], (255, 255, 255, 255)))
    return out or [(raw or "", (255, 255, 255, 255))]


def _split_for_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if draw.textlength(_clean_line(candidate), font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    # Korean headlines may have a long token without whitespace. Split only
    # those oversized tokens so the exact local-font copy remains readable.
    normalized: list[str] = []
    for line in lines:
        if draw.textlength(_clean_line(line), font=font) <= max_width:
            normalized.append(line)
            continue
        fragment = ""
        for char in line:
            proposal = fragment + char
            if fragment and draw.textlength(_clean_line(proposal), font=font) > max_width:
                normalized.append(fragment)
                fragment = char
            else:
                fragment = proposal
        if fragment:
            normalized.append(fragment)
    return normalized


def _draw_markup(draw: ImageDraw.ImageDraw, xy: tuple[int, int], line: str, font: ImageFont.ImageFont, stroke: int) -> int:
    x, y = xy
    for text, color in _segments(line):
        if not text:
            continue
        draw.text((x, y), text, font=font, fill=color, stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        x += int(draw.textlength(text, font=font))
    return x


class ThumbnailGenerator:
    """Generate 1–3 deterministic variants from images proven to be in a video."""

    def render(self, *, job_id: int, format_name: str, output_path: str,
               candidates: list[dict[str, Any]], brief: dict[str, Any] | None = None,
               character_asset_path: str | None = None, character_identity: dict[str, Any] | None = None,
               person_photos: list[dict[str, Any]] | None = None,
               watermark_path: str | None = None, variants: int = 3,
               reference_style_profile: str = "black_han_sans_v1",
               forced_preset: str | None = None) -> dict[str, Any]:
        brief = brief or {}
        # V2 is opt-in and requires an explicit contract.  Old in-flight jobs
        # retain the scene renderer even after the feature flag is enabled.
        if bool(runtime_config.value("thumbnail_v2_enabled")) and brief.get("template"):
            from .v2.compose import ThumbnailV2Composer
            # Asset choice is not cosmetic: an approved real person becomes
            # the primary subject, while a user-selected channel mascot is
            # only enabled for the chart template.  This prevents accidental
            # mint/default characters from mixing into a selected identity.
            v2_brief = dict(brief)
            if person_photos:
                v2_brief.update({
                    "template": "person_headline",
                    "primary_subject": {"kind": "person", "asset_id": str(person_photos[0].get("photo_id") or "approved_person")},
                    "secondary_subject": {"allowed": False},
                })
            elif (character_asset_path and Path(character_asset_path).is_file()
                  and v2_brief.get("template") in {"chart_warning", "mascot_headline"}):
                secondary = dict(v2_brief.get("secondary_subject") or {})
                secondary.update({"allowed": True, "emotion": str(secondary.get("emotion") or "worried")})
                # Character-led and real-person-led thumbnails are separate
                # creative modes.  Never inject the mascot into a real-person
                # layout merely because a channel profile happens to exist.
                v2_brief["template"] = "mascot_headline"
                v2_brief["secondary_subject"] = secondary
            return ThumbnailV2Composer().render(
                output_path=output_path, format_name=format_name, candidates=candidates,
                brief=v2_brief, person_photos=person_photos,
                mascot_path=character_asset_path, watermark_path=watermark_path,
                verified_facts=brief.get("verified_facts") if isinstance(brief.get("verified_facts"), list) else [],
                narration=str(brief.get("narration") or ""),
                variants=variants,
                reference_style_profile=reference_style_profile,
                forced_preset=forced_preset,
            )
        requested_ids = {str(value) for value in brief.get("source_scene_ids", [])}
        ranked = [Candidate(scene=scene, score=_score_scene(scene, requested_ids)) for scene in candidates]
        ranked = [candidate for candidate in ranked if math.isfinite(candidate.score)]
        ranked.sort(key=lambda candidate: candidate.score, reverse=True)
        if not ranked:
            raise ThumbnailRenderError("THUMBNAIL_SOURCE_NOT_IN_VIDEO: usable scene candidate is required")
        selected = ranked[:max(1, min(int(variants or 1), 3, len(ranked)))]
        target_size = output_size(format_name)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        variant_results: list[dict[str, Any]] = []
        approved_people = list(person_photos or [])[:2]
        for photo in approved_people:
            validate_photo(photo)
        for variant_index, candidate in enumerate(selected):
            rendered = self._render_one(
                source=candidate.scene,
                size=target_size,
                brief=brief,
                character_asset_path=character_asset_path,
                character_identity=character_identity or {},
                person_photos=approved_people,
                watermark_path=watermark_path,
            )
            variant_path = output if variant_index == 0 else output.with_name(f"{output.stem}_v{variant_index + 1}{output.suffix or '.png'}")
            rendered[0].convert("RGB").save(variant_path, "PNG", optimize=True)
            metadata = rendered[1]
            metadata.update({"variant_index": variant_index, "output_path": str(variant_path), "candidate_score": round(candidate.score, 3)})
            variant_results.append(metadata)
        # Always retain the legacy requested path as the selected primary.
        if Path(variant_results[0]["output_path"]) != output:
            shutil.copy2(variant_results[0]["output_path"], output)
        return {
            "status": "ok", "mode": "scene", "output_path": str(output),
            "variants": variant_results, "selected_variant": 0,
            "character_identity_hash": str((character_identity or {}).get("identity_hash") or ""),
        }

    def _render_one(self, *, source: dict[str, Any], size: tuple[int, int], brief: dict[str, Any],
                    character_asset_path: str | None, character_identity: dict[str, Any],
                    person_photos: list[dict[str, Any]], watermark_path: str | None) -> tuple[Image.Image, dict[str, Any]]:
        source_path = str(source.get("image_path") or source.get("path") or "")
        canvas = _cover(source_path, size)
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        shade = ImageDraw.Draw(overlay)
        reference_layout = str(brief.get("layout") or "reference_headline").lower() != "legacy"
        text_on_left = str(brief.get("text_side") or "left").lower() != "right"
        if reference_layout:
            # Reference-channel pattern: primary visual above, then a solid
            # black headline shelf. Korean copy is always local-font text.
            shelf_start = int(size[1] * (.59 if size == LONGFORM_SIZE else .64))
            shade.rectangle((0, shelf_start, size[0], size[1]), fill=(0, 0, 0, 238))
            shade.rectangle((0, shelf_start - int(size[1] * .06), size[0], shelf_start), fill=(0, 0, 0, 105))
        elif text_on_left:
            shade.rectangle((0, 0, int(size[0] * .62), size[1]), fill=(0, 0, 0, 110))
        else:
            shade.rectangle((int(size[0] * .38), 0, size[0], size[1]), fill=(0, 0, 0, 110))
        if not reference_layout:
            shade.rectangle((0, int(size[1] * .72), size[0], size[1]), fill=(0, 0, 0, 72))
        canvas = Image.alpha_composite(canvas, overlay)
        subject_regions: list[dict[str, Any]] = []
        # A registered real photo wins over the mascot. Mixed layouts need an
        # explicit preset, preventing the accidental double-character issue.
        if person_photos:
            for index, photo in enumerate(person_photos):
                subject_regions.append(paste_person(canvas, photo, side="right" if index == 0 else "left", height_ratio=.68))
        elif character_asset_path and Path(character_asset_path).is_file():
            with Image.open(character_asset_path) as source_character:
                character = source_character.convert("RGBA")
            max_h = int(size[1] * (.47 if reference_layout else .58))
            scale = min(max_h / max(character.height, 1), (size[0] * .32) / max(character.width, 1))
            character = character.resize((max(1, round(character.width * scale)), max(1, round(character.height * scale))), Image.Resampling.LANCZOS)
            x = size[0] - character.width - int(size[0] * .035)
            y = int(size[1] * .08) if reference_layout else size[1] - character.height - int(size[1] * .04)
            canvas.alpha_composite(character, (x, y))
            subject_regions.append({"x": x, "y": y, "width": character.width, "height": character.height, "type": "selected_character"})

        draw = ImageDraw.Draw(canvas)
        margin = int(size[0] * .045)
        max_text_width = int(size[0] * (.92 if reference_layout else (.55 if text_on_left else .50)))
        base_size = int(size[1] * (.096 if size == LONGFORM_SIZE else .052))
        font = _font(max(24, base_size))
        line_height = int(base_size * 1.08)
        y = int(size[1] * (.64 if reference_layout else (.49 if size == LONGFORM_SIZE else .57)))
        x = margin if (reference_layout or text_on_left) else int(size[0] * .47)
        for raw in (str(brief.get("hook_line") or ""), str(brief.get("punch_line") or "")):
            for line in _split_for_width(draw, raw, font, max_text_width):
                _draw_markup(draw, (x, y), line, font, max(2, base_size // 16))
                y += line_height

        badge = brief.get("badge") if isinstance(brief.get("badge"), dict) else {}
        if badge and badge.get("value") and badge.get("source_ref"):
            value = str(badge.get("value"))
            color = (238, 61, 60, 255) if value.strip().startswith("+") else (51, 116, 255, 255)
            badge_font = _font(max(20, base_size // 2))
            box = (margin, int(size[1] * .08), margin + int(size[0] * .28), int(size[1] * .17))
            draw.rounded_rectangle(box, radius=16, fill=(8, 16, 30, 220), outline=color, width=3)
            draw.text((box[0] + 16, box[1] + 10), value, font=badge_font, fill=(255, 255, 255, 255))

        focus = brief.get("focus") if isinstance(brief.get("focus"), dict) else {}
        if focus:
            cx = int(float(focus.get("x", .72)) * size[0])
            cy = int(float(focus.get("y", .38)) * size[1])
            radius = int(float(focus.get("radius", .11)) * min(size))
            self._dashed_ellipse(draw, (cx - radius, cy - radius, cx + radius, cy + radius))
        if watermark_path and Path(watermark_path).is_file():
            with Image.open(watermark_path) as watermark_source:
                watermark = watermark_source.convert("RGBA")
            watermark.thumbnail((int(size[0] * .18), int(size[1] * .10)), Image.Resampling.LANCZOS)
            canvas.alpha_composite(watermark, (size[0] - watermark.width - margin, margin))
        return canvas, {
            "source_scene_id": str(source.get("scene_id") or source.get("id") or source.get("index") or ""),
            "source_path": source_path,
            "used_in_final_video": bool(source.get("used_in_final_video", True)),
            "subject_regions": subject_regions,
            "character_identity_hash": str(character_identity.get("identity_hash") or ""),
            "credits": [str(photo.get("credit_text") or "") for photo in person_photos if photo.get("credit_text")],
        }

    @staticmethod
    def _dashed_ellipse(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
        # Pillow does not provide dashed ellipses, so compose short arc strokes.
        for start in range(0, 360, 30):
            draw.arc(box, start=start, end=start + 17, fill=(235, 0, 55, 255), width=7)
