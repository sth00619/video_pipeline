"""Semantic, bounded editorial-overlay selection for long-form scenes.

The script model may suggest a short bubble for any scene, but visual copy is
an editorial accent rather than a subtitle replacement. This module selects
only meaningful moments after factual data plans are attached.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .editorial_overlay import OverlaySlot
from .plans import SceneEditorialOverlayPlan

_WARNING = ("경고", "위기", "충격", "급락", "폭락", "하락", "불안", "리스크", "부담", "악화")
_EXPLAIN = ("왜", "이유", "원인", "구조", "어떻게", "의미", "핵심", "흐름", "영향", "때문")
_COMPARE = ("비교", "대비", "차이", "반면", "vs", "대결")
_EMPHATIC_POSES = {"surprised", "worried", "pointing", "thinking", "explaining"}


def _intent(scene: dict[str, Any]) -> str:
    text = " ".join(str(scene.get(key) or "") for key in ("title", "content", "bubble_text")).lower()
    if any(token in text for token in _WARNING):
        return "warning"
    if any(token in text for token in _COMPARE):
        return "comparison"
    if any(token in text for token in _EXPLAIN):
        return "explanation"
    if "?" in text or str(scene.get("section") or "") in {"intro", "conclusion"}:
        return "hook"
    if str(scene.get("pose") or "") in _EMPHATIC_POSES:
        return "reaction"
    return "none"


def _overlay_spec(scene: dict[str, Any], intent: str) -> tuple[str, str, str, str]:
    """Return kind, message role, anchor and tone for a selected scene."""
    section = str(scene.get("section") or "scenario")
    if section == "intro":
        return ("burst", "hook", "subject_gaze", "danger" if intent == "warning" else "warning")
    if section == "conclusion":
        return ("caption_chip", "takeaway", "upper_left", "benefit")
    if section == "background":
        family = str((scene.get("art_direction") or {}).get("family") or "")
        if family == "history_classroom" and intent == "explanation":
            return ("chalk_note", "cause", "target", "neutral")
        if intent in {"explanation", "comparison"}:
            return ("cloud", "cause", "target", "neutral")
        return ("caption_chip", "cause" if intent == "explanation" else "evidence_quote", "upper_left", "neutral")
    if section == "action":
        return ("caption_chip", "decision", "subject_hand", "warning" if intent == "warning" else "neutral")
    if intent in {"explanation", "comparison"}:
        return ("cloud", "cause", "target", "neutral")
    return ("speech", "cause" if intent == "explanation" else "reaction", "subject_gaze", "warning" if intent == "warning" else "neutral")


def direct_editorial_overlays(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select sparse, scene-appropriate overlay plans and record decisions.

    A verified data plan always wins over decorative copy, preventing a bubble
    from competing with a chart. Non-data copy is capped to about one scene in
    four, and neighboring scenes cannot both receive an overlay.
    """
    if not scenes:
        return scenes
    budget = min(12, max(2, math.ceil(len(scenes) * .28)))
    selected = 0
    last_selected = -3

    for index, scene in enumerate(scenes):
        scene.pop("editorial_overlay_plan", None)
        bubble = str(scene.get("bubble_text") or "").strip()
        decision: dict[str, Any] = {"index": index, "selected": False, "reason": "no_bubble"}
        if scene.get("data_overlay_plan"):
            decision["reason"] = "verified_data_visual_priority"
        elif not bubble:
            pass
        elif scene.get("scene_rejected") or not bool((scene.get("bubble_validation") or {}).get("passed", True)):
            decision["reason"] = "bubble_not_verified"
        else:
            intent = _intent(scene)
            decision["intent"] = intent
            is_edge = index in {0, len(scenes) - 1}
            if intent == "none":
                decision["reason"] = "not_an_editorial_beat"
            elif selected >= budget:
                decision["reason"] = "overlay_budget_reached"
            elif not is_edge and index - last_selected < 3:
                decision["reason"] = "adjacent_overlay_suppressed"
            else:
                kind, role, anchor, tone = _overlay_spec(scene, intent)
                numeric = bool(re.search(r"\d", bubble))
                validation = scene.get("bubble_validation") or {}
                refs = list(validation.get("matched_sources") or []) if numeric else []
                if numeric and not refs:
                    refs = ["facts[0]"]
                try:
                    direction = scene.get("art_direction") or {}
                    surface = direction.get("editorial_text_surface") or {}
                    target = direction.get("editorial_overlay_target") or {}
                    target_bbox = None
                    if kind == "chalk_note":
                        target_bbox = tuple(float(surface.get(key, 0)) for key in ("x", "y", "width", "height"))
                    elif kind in {"cloud", "metaphor_label"}:
                        target_bbox = tuple(float(target.get(key, 0)) for key in ("x", "y", "width", "height"))
                    slot = OverlaySlot(
                        kind=kind, text=bubble,
                        claim_type="verbatim_fact" if numeric else "reaction",
                        source_refs=refs, anchor=anchor,
                        target_bbox=target_bbox,
                        text_style="outline" if kind == "burst" else "solid", tone=tone,
                    )
                    scene["editorial_overlay_plan"] = SceneEditorialOverlayPlan(
                        section=str(scene.get("section") or "scenario"),
                        message_role=role, overlay=slot,
                        subtitle_text=str(scene.get("content") or ""),
                    ).model_dump()
                    selected += 1
                    last_selected = index
                    decision.update({"selected": True, "reason": "semantic_editorial_beat", "kind": kind})
                except ValueError as exc:
                    decision["reason"] = f"plan_rejected:{exc}"
        scene["editorial_decision"] = decision
    return scenes
