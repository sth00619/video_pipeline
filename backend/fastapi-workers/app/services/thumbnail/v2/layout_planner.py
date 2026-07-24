"""Role-based thumbnail layout planning and deterministic QA."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageFilter, ImageStat
from pydantic import BaseModel, ConfigDict, Field

from .brief import HeadlineLine, ThumbnailBriefV2


class PlateSpec(BaseModel):
    asset_id: str
    darkness: float = Field(default=.80, ge=.35, le=1)
    vignette: float = Field(default=.18, ge=0, le=.6)


class SubjectSpec(BaseModel):
    kind: Literal["person", "chart", "article", "product"]
    side: Literal["left", "right"] = "right"
    area_target: float = Field(default=.32, ge=.16, le=.60)


class MascotSpec(BaseModel):
    enabled: bool = False
    # The mascot-only preset deliberately makes the chosen character a
    # primary subject.  The older .26 ceiling was suitable only for a small
    # supporting sticker and could never reach a reference-size focal pose.
    height_ratio: float = Field(default=.54, ge=.10, le=.58)
    side: Literal["left", "right"] = "right"
    emotion: Literal["neutral", "highlight", "surprised", "worried", "happy"] = "worried"


class BubbleSpec(BaseModel):
    enabled: bool = False
    side: Literal["left", "right"] = "left"


class CopySpec(BaseModel):
    lines: list[HeadlineLine] = Field(min_length=2, max_length=3)
    min_fill_ratio: float = Field(default=.88, ge=.5, le=1)


class LayerPlan(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    preset: Literal["person_led", "chart_led", "mascot_led"]
    background_plate: PlateSpec
    subject: SubjectSpec
    mascot: MascotSpec | None = None
    bubble: BubbleSpec | None = None
    copy_spec: CopySpec = Field(alias="copy", serialization_alias="copy")
    layout_variant: Literal["default", "mirrored"] = "default"
    source_index: int = 0


class ThumbQA(BaseModel):
    face_sharpness: float = 0
    subject_area: float = 0
    copy_fill: float = 0
    minimum_copy_fill: float = 0
    text_scale: float = 1
    mobile_font_px: float = 0
    contrast: float = 21
    overlaps: int = 0
    requires_face: bool = False
    passed: bool = False
    failures: list[str] = Field(default_factory=list)
    editorial: "EditorialQA" = Field(default_factory=lambda: EditorialQA())


class EditorialQA(BaseModel):
    """Human-reviewable constraints that visual quality scores cannot infer."""
    text_safe_bottom: bool = False
    font_profile_id: str = ""
    emphasis_target_valid: bool = True
    direction_claim_verified: bool = True
    subject_script_match: float = 1.0
    duplicate_character_count: int = 0
    bubble_dominance_ratio: float = 0.0
    visual_hierarchy_score: float = 1.0
    clean_plate_present: bool = True
    semantic_marks: list[dict[str, Any]] = Field(default_factory=list)


def _variance(image: Image.Image) -> float:
    gray = image.convert("L")
    gray.thumbnail((640, 640), Image.Resampling.LANCZOS)
    response = gray.filter(ImageFilter.Kernel(
        (3, 3),
        (0, 1, 0, 1, -4, 1, 0, 1, 0),
        scale=1,
        offset=128,
    ))
    # Offset 128 represents zero response; variance is unchanged.
    return round(float(ImageStat.Stat(response).var[0]), 3)


def laplacian_variance(path: str | Path) -> float:
    """Compute local Laplacian variance without adding a network/AI runtime."""
    source = Path(path)
    if not source.is_file():
        return 0.0
    try:
        with Image.open(source) as loaded:
            return _variance(loaded)
    except OSError:
        return 0.0


def face_laplacian_variance(path: str | Path) -> float:
    """Measure the likely face zone, not sharp clothing or a transparent edge."""
    source = Path(path)
    if not source.is_file():
        return 0.0
    try:
        with Image.open(source) as loaded:
            rgba = loaded.convert("RGBA")
            content = rgba.getchannel("A").getbbox() or (0, 0, rgba.width, rgba.height)
            left, top, right, bottom = content
            face_bottom = top + max(1, round((bottom - top) * .48))
            return _variance(rgba.crop((left, top, right, face_bottom)))
    except OSError:
        return 0.0


def alpha_area_ratio(path: str | Path) -> float:
    source = Path(path)
    if not source.is_file():
        return 0.0
    try:
        with Image.open(source) as loaded:
            rgba = loaded.convert("RGBA")
            alpha = rgba.getchannel("A")
            histogram = alpha.histogram()
            opaque = sum(histogram[16:])
            return opaque / max(1, rgba.width * rgba.height)
    except OSError:
        return 0.0


def assess(
    *,
    image_path: str,
    subject_kind: str,
    subject_area: float,
    copy_fill: float,
    minimum_copy_fill: float = 0,
    text_scale: float = 1,
    mobile_font_px: float = 0,
    overlaps: int,
    person_path: str | None = None,
    editorial: EditorialQA | dict[str, Any] | None = None,
) -> ThumbQA:
    requires_face = subject_kind == "person"
    face_sharpness = face_laplacian_variance(person_path or image_path) if requires_face else 0.0
    failures: list[str] = []
    if requires_face and face_sharpness < 120:
        failures.append("face_sharpness")
    if subject_area < .16:
        failures.append("subject_area")
    if copy_fill < .58:
        failures.append("copy_fill")
    if minimum_copy_fill < .34:
        failures.append("short_copy_line")
    if text_scale < .74:
        failures.append("text_distortion")
    if mobile_font_px < 18:
        failures.append("mobile_legibility")
    contrast = 21.0  # white/yellow/red on the deterministic black shelf.
    if contrast < 4.5:
        failures.append("contrast")
    if overlaps:
        failures.append("overlaps")
    editorial = EditorialQA.model_validate(editorial or {})
    if not editorial.text_safe_bottom:
        failures.append("editorial_text_safe_bottom")
    if editorial.font_profile_id != "black_han_sans_v1":
        failures.append("editorial_font_profile")
    if not editorial.emphasis_target_valid:
        failures.append("editorial_emphasis_target")
    if not editorial.direction_claim_verified:
        failures.append("editorial_direction_claim")
    if requires_face and editorial.subject_script_match < 1.0:
        failures.append("editorial_subject_script_match")
    if editorial.duplicate_character_count > 0:
        failures.append("editorial_duplicate_character")
    if editorial.bubble_dominance_ratio > .12:
        failures.append("editorial_bubble_dominance")
    if editorial.visual_hierarchy_score < .60:
        failures.append("editorial_visual_hierarchy")
    if not editorial.clean_plate_present:
        failures.append("editorial_clean_plate")
    return ThumbQA(
        face_sharpness=face_sharpness,
        subject_area=round(subject_area, 4),
        copy_fill=round(copy_fill, 4),
        minimum_copy_fill=round(minimum_copy_fill, 4),
        text_scale=round(text_scale, 4),
        mobile_font_px=round(mobile_font_px, 2),
        contrast=contrast,
        overlaps=overlaps,
        requires_face=requires_face,
        passed=not failures,
        failures=failures,
        editorial=editorial,
    )


def _role_copy(lines: list[HeadlineLine], *, keyword_index: int = 1) -> list[HeadlineLine]:
    output = [line.model_copy(deep=True) for line in lines]
    if not output:
        return output
    for index, line in enumerate(output):
        line.text = line.text.strip("'\"")
        line.tone = "white" if index == 0 else "yellow"
        if index > 0 and any(character.isdigit() for character in line.text):
            line.tone = "red"
    # Exactly one editorial keyword carries quotation marks. This is local
    # typography over approved copy, not an LLM rewrite.
    keyword_index = min(keyword_index, len(output) - 1)
    text = output[keyword_index].text
    if len(text) <= 14:
        output[keyword_index].text = f"'{text}'"
    output[keyword_index].tone = "yellow"
    return output


class ThumbnailLayoutPlanner:
    def plan(
        self,
        *,
        brief: ThumbnailBriefV2,
        sources: list[dict[str, Any]],
        person_photos: list[dict[str, Any]],
        mascot_path: str | None,
    ) -> list[LayerPlan]:
        if not sources:
            return []
        # Cutout-led presets only use a pre-composite plate. This forces old
        # jobs to keep a chart/article layout until their scene is regenerated.
        clean_sources = [source for source in sources if Path(str(source.get("clean_plate_path") or "")).is_file()]
        has_person = bool(person_photos and clean_sources)
        has_mascot = bool(mascot_path and Path(mascot_path).is_file())
        has_mascot = has_mascot and bool(clean_sources)
        if clean_sources:
            sources = clean_sources
        if has_person:
            preset = "person_led"
            kind = "person"
        elif has_mascot:
            preset = "mascot_led"
            kind = brief.primary_subject.kind
        else:
            preset = "chart_led"
            kind = brief.primary_subject.kind

        # The reference format is a two-line poster, not a transcript card.
        # When the editorial brief carries a third verified line, use it as a
        # distinct A/B candidate rather than shrinking all three lines into
        # every thumbnail.
        role_copy = _role_copy(brief.headline[:2])
        alternate_source = (
            [brief.headline[0], brief.headline[-1]]
            if len(brief.headline) >= 3
            else list(brief.headline[:2])
        )
        alternate_copy = _role_copy(
            alternate_source,
            keyword_index=1,
        )
        negative_space = ((sources[0].get("asset_layout_metadata") or {}).get("negative_space"))
        bubble_enabled = bool(brief.speech_bubble and has_mascot and negative_space)
        plans = [
            LayerPlan(
                preset=preset,
                background_plate=PlateSpec(asset_id=str(brief.primary_subject.asset_id)),
                subject=SubjectSpec(kind=kind, side="right"),
                mascot=MascotSpec(enabled=has_mascot and not has_person, side="right", emotion="worried") if has_mascot else None,
                bubble=BubbleSpec(enabled=bubble_enabled, side="left") if has_mascot else None,
                copy=CopySpec(lines=role_copy),
                source_index=0,
            ),
            LayerPlan(
                preset=preset,
                background_plate=PlateSpec(asset_id=str(brief.primary_subject.asset_id), darkness=.74),
                subject=SubjectSpec(kind=kind, side="right"),
                mascot=MascotSpec(enabled=has_mascot and not has_person, side="right", emotion="neutral") if has_mascot else None,
                bubble=BubbleSpec(enabled=bubble_enabled, side="left") if has_mascot else None,
                copy=CopySpec(lines=alternate_copy),
                source_index=0,
            ),
            LayerPlan(
                preset=preset,
                background_plate=PlateSpec(asset_id=str(brief.primary_subject.asset_id), darkness=.78),
                subject=SubjectSpec(kind=kind, side="left"),
                mascot=MascotSpec(enabled=has_mascot and not has_person, side="left", emotion="happy") if has_mascot else None,
                bubble=BubbleSpec(enabled=bool(bubble_enabled and not has_person), side="right") if has_mascot else None,
                copy=CopySpec(lines=[line.model_copy(deep=True) for line in role_copy]),
                layout_variant="mirrored",
                source_index=1 if len(sources) > 1 else 0,
            ),
        ]
        # When the job has both a rights-cleared real-person photograph and a
        # channel-owned mascot, the recommendation surface must not blend the
        # two treatments into one busy image.  Keep two portrait-led options
        # and reserve the third for a genuinely mascot-only alternative. This
        # mirrors an editor's A/B choice: a human-reaction poster versus a
        # branded explainer poster.
        if has_person and has_mascot:
            plans[2] = LayerPlan(
                preset="mascot_led",
                background_plate=PlateSpec(asset_id=str(brief.primary_subject.asset_id), darkness=.78),
                subject=SubjectSpec(kind="chart", side="right"),
                mascot=MascotSpec(enabled=True, height_ratio=.54, side="right", emotion="worried"),
                bubble=BubbleSpec(enabled=bubble_enabled, side="left"),
                copy=CopySpec(lines=[line.model_copy(deep=True) for line in role_copy]),
                source_index=1 if len(sources) > 1 else 0,
            )
        return plans
