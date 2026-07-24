"""v2 composition entry point and inspectable provenance output."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .asset_selector import choose_many, scene_kind
from .brief import Subject, ThumbnailBriefV2, validate_brief
from .templates import TEMPLATE_REGISTRY
from .templates.base import AssetBundle
from .layout_planner import EditorialQA, ThumbnailLayoutPlanner, assess, face_laplacian_variance


def _person_path(photo: dict[str, Any]) -> str:
    return str(photo.get("cutout_path") or photo.get("original_path") or "")


def _direction_claim_verified(emphasis, verified_facts: list[dict] | None) -> bool:
    """Directional graphics are allowed only when the referenced fact agrees."""
    if not emphasis or not emphasis.direction_claim:
        return True
    ref = str(emphasis.reason_ref)
    index = None
    for token in ref.replace("[", ".").replace("]", "").split("."):
        if token.isdigit():
            index = int(token)
            break
    if index is None or not verified_facts or index >= len(verified_facts):
        return False
    direction = str((verified_facts[index] or {}).get("direction") or "").lower()
    return direction == emphasis.direction_claim


class ThumbnailV2Composer:
    def render(self, *, output_path: str, format_name: str, candidates: list[dict[str, Any]], brief: dict[str, Any], person_photos: list[dict[str, Any]] | None = None, mascot_path: str | None = None, watermark_path: str | None = None, verified_facts: list[dict] | None = None, narration: str = "", variants: int = 3, reference_style_profile: str = "black_han_sans_v1", forced_preset: str | None = None) -> dict[str, Any]:
        if reference_style_profile != "black_han_sans_v1":
            raise ValueError("UNSUPPORTED_REFERENCE_STYLE_PROFILE")
        contract = ThumbnailBriefV2.model_validate(brief)
        errors = validate_brief(contract, verified_facts, narration)
        if errors:
            raise ValueError("BRIEF_VALIDATION_FAILED: " + "; ".join(errors))
        preferred = {str(value) for value in brief.get("source_scene_ids", [])}
        sources = choose_many(
            candidates,
            contract.template,
            limit=3,
            preferred_scene_ids=preferred,
        )
        if not sources:
            raise ValueError("THUMBNAIL_SOURCE_NOT_IN_VIDEO")
        aspect = "9:16" if str(format_name).lower() == "shorts" else "16:9"
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        ranked_people = sorted(
            list(person_photos or []),
            key=lambda photo: face_laplacian_variance(_person_path(photo)),
            reverse=True,
        )
        rejected_people = [
            {
                "photo_id": str(photo.get("photo_id") or ""),
                "path": _person_path(photo),
                "reason": "face_sharpness",
                "score": face_laplacian_variance(_person_path(photo)),
            }
            for photo in ranked_people
            if face_laplacian_variance(_person_path(photo)) < 120
        ]
        accepted_people = [
            photo for photo in ranked_people
            if face_laplacian_variance(_person_path(photo)) >= 120
        ]
        # Person-led output is permitted only for the named entity resolver's
        # contextual matches; a generic stock photo must never become a face
        # just because it is sharp.
        render_people = [
            photo for photo in accepted_people
            if str(photo.get("match_source") or "") in {"script_context", "thumbnail_brief"}
        ][:2]
        plans = ThumbnailLayoutPlanner().plan(
            brief=contract,
            sources=sources,
            person_photos=render_people,
            mascot_path=mascot_path,
        )[: max(1, min(int(variants or 1), 3))]
        if forced_preset:
            plans = [plan for plan in plans if plan.preset == forced_preset]
        if not plans:
            raise ValueError("THUMBNAIL_LAYOUT_UNAVAILABLE")

        rendered_variants = []
        for variant_index, plan in enumerate(plans):
            source = sources[min(plan.source_index, len(sources) - 1)]
            ordered_sources = [source, *[item for item in sources if item is not source]]
            # A reference-style recommendation uses one unmistakable face as
            # the focal subject.  When two approved people are available the
            # third recommendation rotates to the second person instead of
            # shrinking both faces into every candidate.
            variant_people: list[dict[str, Any]] = []
            if render_people and plan.preset == "person_led":
                person_index = 1 if variant_index == 2 and len(render_people) > 1 else 0
                variant_people = [render_people[person_index]]
            variant_contract = contract.model_copy(deep=True)
            variant_contract.headline = [line.model_copy(deep=True) for line in plan.copy_spec.lines]
            # A mascot recommendation is an independent visual mode, even if
            # the original brief selected a real person.  It receives no
            # person pixels and is validated as a mascot template before the
            # renderer begins.  This avoids the accidental character/person
            # collages that made the prior recommendations feel generic.
            if plan.preset == "mascot_led":
                variant_contract.template = "mascot_headline"
                variant_contract.primary_subject = Subject(
                    kind="chart",
                    asset_id=str(source.get("scene_id") or source.get("id") or "scene_backdrop"),
                    source_ref=contract.primary_subject.source_ref,
                )
                variant_contract.secondary_subject.allowed = True
                if plan.mascot:
                    variant_contract.secondary_subject.emotion = plan.mascot.emotion
            elif plan.preset == "person_led":
                variant_contract.template = "person_headline"
            else:
                # A legacy job with no clean plate is still eligible for a
                # proven chart/article frame, never for a second cutout.
                variant_contract.template = "chart_warning"
                variant_contract.primary_subject = Subject(
                    kind="chart",
                    asset_id=str(source.get("scene_id") or source.get("id") or "scene_backdrop"),
                    source_ref=contract.primary_subject.source_ref,
                )
            if variant_contract.secondary_subject:
                variant_contract.secondary_subject.allowed = bool(plan.mascot and plan.mascot.enabled)
            if not plan.bubble or not plan.bubble.enabled:
                variant_contract.speech_bubble = None
            template = TEMPLATE_REGISTRY[variant_contract.template]()
            image = template.render(
                variant_contract,
                AssetBundle(
                    source,
                    ordered_sources,
                    variant_people,
                    mascot_path,
                    watermark_path,
                    plan,
                ),
                aspect,
            )
            variant_path = target.with_name(f"{target.stem}_v{variant_index + 1}{target.suffix or '.png'}")
            image.convert("RGB").save(variant_path, "PNG", optimize=True)
            person_path = None
            if variant_people:
                person_path = _person_path(variant_people[0])
            metrics = getattr(template, "last_text_metrics", None)
            semantic = variant_contract.semantic_emphasis
            semantic_verified = not semantic or bool(semantic.reason_ref and semantic.target_asset_id)
            direction_verified = _direction_claim_verified(semantic, verified_facts)
            person_match = (
                not variant_people
                or str(variant_people[0].get("match_source") or "") in {"script_context", "thumbnail_brief"}
            )
            clean_plate_present = (
                plan.preset not in {"person_led", "mascot_led"}
                or bool(source.get("clean_plate_path"))
            )
            duplicate_character_count = int((source.get("asset_layout_metadata") or {}).get("duplicate_character_count") or 0)
            bubble_ratio = float(getattr(template, "last_bubble_area_ratio", 0.0))
            subject_area = float(getattr(template, "last_subject_area", plan.subject.area_target))
            # A bubble is a supporting cue, never the focal subject.
            visual_hierarchy = min(1.0, subject_area / max(.01, bubble_ratio * 1.5))
            qa = assess(
                image_path=str(variant_path),
                subject_kind=plan.subject.kind,
                subject_area=subject_area,
                copy_fill=float(getattr(metrics, "copy_fill", 0)),
                minimum_copy_fill=float(getattr(metrics, "minimum_fill", 0)),
                text_scale=float(getattr(metrics, "minimum_scale", 1)),
                mobile_font_px=float(getattr(metrics, "mobile_font_px", 0)),
                overlaps=int(getattr(template, "last_overlap_count", 0)),
                person_path=person_path,
                editorial=EditorialQA(
                    text_safe_bottom=bool(getattr(metrics, "text_safe_bottom", False)),
                    font_profile_id=str(getattr(metrics, "profile_id", "")),
                    emphasis_target_valid=semantic_verified,
                    direction_claim_verified=direction_verified,
                    subject_script_match=1.0 if person_match else 0.0,
                    duplicate_character_count=duplicate_character_count,
                    bubble_dominance_ratio=round(bubble_ratio, 4),
                    visual_hierarchy_score=round(visual_hierarchy, 4),
                    clean_plate_present=clean_plate_present,
                    semantic_marks=list(getattr(template, "last_semantic_marks", [])),
                ),
            )
            rendered_variants.append({
                "template_id": variant_contract.template,
                "preset": plan.preset,
                "creative_mode": (
                    "real_person" if variant_people
                    else "mascot_only" if plan.mascot and plan.mascot.enabled
                    else "chart_only"
                ),
                "layout_variant": plan.layout_variant,
                "source_scene_id": str(source.get("scene_id") or source.get("id") or source.get("index") or ""),
                "scene_kind": scene_kind(source),
                "backdrop": getattr(template, "last_backdrop_strategy", {"kind": "scene_collage"}),
                "supporting_scene_ids": [
                    str(item.get("scene_id") or item.get("id") or item.get("index") or "")
                    for item in ordered_sources[1:]
                ],
                "source_ref": [
                    value for value in [
                        variant_contract.primary_subject.source_ref,
                        variant_contract.badge.source_ref if variant_contract.badge else None,
                        variant_contract.evidence.source_ref if variant_contract.evidence else None,
                    ] if value
                ],
                "font": "BlackHanSans-Regular (OFL-1.1)",
                "output_path": str(variant_path),
                "variant_index": variant_index,
                "headline": [line.model_dump() for line in variant_contract.headline],
                "person": ({
                    "person_id": str(variant_people[0].get("person_id") or ""),
                    "person_name": str(variant_people[0].get("person_name") or ""),
                    "photo_id": str(variant_people[0].get("photo_id") or ""),
                    "match_term": str(variant_people[0].get("match_term") or ""),
                    "match_source": str(variant_people[0].get("match_source") or ""),
                    "rights": {
                        "license_type": variant_people[0].get("license_type"),
                        "license_ref": variant_people[0].get("license_ref"),
                        "credit_text": variant_people[0].get("credit_text"),
                        "author_name": variant_people[0].get("author_name"),
                        "approved": variant_people[0].get("approved"),
                        "rights_review_status": variant_people[0].get(
                            "rights_review_status"
                        ),
                    },
                    "rendering": {
                        "source": "approved_licensed_photo",
                        "effects": list(getattr(template, "last_person_treatment", [])),
                        "generative_face_edit": False,
                    },
                } if variant_people else None),
                "qa": qa.model_dump(),
            })
        selected = next(
            (index for index, item in enumerate(rendered_variants) if item["qa"]["passed"]),
            0,
        )
        shutil.copy2(rendered_variants[selected]["output_path"], target)
        provenance = {
            "schema_version": 3,
            "selected_variant": selected,
            "variants": rendered_variants,
            "output_path": str(target),
            "asset_rejections": rejected_people,
        }
        provenance_path = target.with_name("provenance.json")
        provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "status": "ok",
            "mode": "v2_template",
            "output_path": str(target),
            "variants": rendered_variants,
            "selected_variant": selected,
            "provenance_path": str(provenance_path),
            "asset_rejections": rejected_people,
        }
