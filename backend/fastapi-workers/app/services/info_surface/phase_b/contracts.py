"""Immutable contracts for the optional Phase B style-only pass."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BarSpec(BaseModel):
    bbox: tuple[int, int, int, int]
    value: float
    fill_rgb: tuple[int, int, int]


class ExpectedText(BaseModel):
    text: str = Field(min_length=1)
    numeric_critical: bool = True


class HarmonizeRequest(BaseModel):
    scene_id: str
    surface_kind: Literal["chalkboard", "paper", "clipboard", "monitor", "signboard", "ledger_card"]
    crop_bbox_in_frame: tuple[int, int, int, int]
    expected_texts: list[ExpectedText]
    bars: list[BarSpec] = Field(default_factory=list)
    palette_rgb: list[tuple[int, int, int]]
    style_prompt: str
    strength: float = Field(default=.38, ge=.15, le=.6)
    provider: Literal["fal_canny", "gemini_edit"] = "fal_canny"


class GateReport(BaseModel):
    name: Literal["text_integrity", "bar_geometry", "palette", "edge_iou"]
    passed: bool
    detail: str = ""
    metric: float | None = None


class HarmonizeResult(BaseModel):
    scene_id: str
    provider: str
    accepted: bool
    gates: list[GateReport]
    fallback_reason: str = ""
    latency_ms: int = 0
    cost_estimate_krw: float = 0.0
    output_path: str | None = None
