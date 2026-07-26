"""Validated plans linking scene meaning to deterministic overlays."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .editorial_overlay import OverlayKind, OverlaySlot


class CopyClaim(BaseModel):
    text: str = Field(min_length=2, max_length=24)
    claim_type: Literal["reaction", "derived_hook", "verbatim_fact"]
    source_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def requires_source_when_grounded(self):
        if self.claim_type != "reaction" and not self.source_refs:
            raise ValueError("grounded copy requires source_refs")
        return self


class DiegeticNumberPlan(BaseModel):
    schema_version: Literal[1] = 1
    surface_kind: Literal["device_screen", "signboard", "clock_display", "prop_panel", "board"]
    value_ref: str = Field(min_length=3)
    format: Literal["numeral_grouped", "korean_compact", "percent", "point", "date_ym"]
    render_style: Literal["lcd", "led", "print", "chalk", "paint"]
    quad: tuple[tuple[float, float], ...] | None = None
    detection_confidence: float = Field(default=0, ge=0, le=1)


class DataOverlayPlan(BaseModel):
    chart_kind: Literal["trend", "change", "composition", "comparison"]
    primary_metric: str = Field(min_length=1)
    unit: str = Field(min_length=1, max_length=12)
    source_refs: list[str] = Field(min_length=1)
    comparison_basis: str | None = None
    focus_target: Literal["latest_point", "largest_slice", "larger_bar"]
    callout: CopyClaim | None = None
    callout_anchor: Literal["target", "upper_left", "lower_right"] = "target"
    diegetic: list[DiegeticNumberPlan] = Field(default_factory=list, max_length=2)
    subtitle_emphasis_ref: str | None = None
    date_stamp_ref: str | None = None

    @model_validator(mode="after")
    def no_repeated_metric_in_callout(self):
        if self.callout and re.search(r"\d", self.callout.text):
            raise ValueError("data callout must not restate a numeric value")
        if self.chart_kind == "comparison" and not self.comparison_basis:
            raise ValueError("comparison requires a common comparison_basis")
        return self


_ALLOWED_BY_SECTION: dict[str, set[str]] = {
    "intro": {"burst", "speech"},
    "background": {"cloud", "chalk_note", "caption_chip", "date_stamp"},
    "scenario": {"speech", "cloud", "metaphor_label", "title_card"},
    "action": {"speech", "caption_chip"},
    "conclusion": {"burst", "caption_chip"},
}


class SceneEditorialOverlayPlan(BaseModel):
    section: Literal["intro", "background", "scenario", "action", "conclusion"]
    message_role: Literal["hook", "reaction", "cause", "decision", "takeaway", "evidence_quote"]
    overlay: OverlaySlot
    target_id: str | None = None
    subtitle_text: str = ""

    @model_validator(mode="after")
    def section_kind_and_duplicate_rules(self):
        if self.overlay.kind not in _ALLOWED_BY_SECTION[self.section]:
            raise ValueError("overlay kind is not allowed for this scene section")
        words = {item for item in re.findall(r"[0-9A-Za-z가-힣]+", self.overlay.text) if len(item) >= 2}
        subtitle_words = {item for item in re.findall(r"[0-9A-Za-z가-힣]+", self.subtitle_text) if len(item) >= 2}
        if len(words & subtitle_words) >= 3:
            raise ValueError("overlay duplicates subtitle")
        return self


def chart_kind_from_visual_kind(value: str) -> Literal["trend", "change", "composition", "comparison"]:
    return {
        "change_arrow": "change", "composition_pie": "composition", "comparison": "comparison",
    }.get(value, "trend")
