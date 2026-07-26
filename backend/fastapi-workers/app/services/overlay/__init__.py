"""Deterministic editorial overlays shared by longform and thumbnails."""

from .editorial_overlay import (
    OverlayKind,
    OverlayRenderResult,
    OverlaySlot,
    render_editorial_overlay,
)
from .plans import CopyClaim, DataOverlayPlan, DiegeticNumberPlan, SceneEditorialOverlayPlan

__all__ = [
    "OverlayKind", "OverlayRenderResult", "OverlaySlot", "render_editorial_overlay",
    "CopyClaim", "DataOverlayPlan", "DiegeticNumberPlan", "SceneEditorialOverlayPlan",
]
