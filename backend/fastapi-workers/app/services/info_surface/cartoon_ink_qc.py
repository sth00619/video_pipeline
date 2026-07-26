"""Fail-closed P0 checks for deterministic cartoon information panels."""
from __future__ import annotations


ROLE_MINIMUM_PX = {"hero": 66, "title": 44, "meaning": 30}
CHANNEL_ACCENTS = {"#F6BE28", "#C94B3C"}
CHANNEL_NEUTRALS = {"#071A3A", "#FFF4D6", "#A99F8A", "#FFFFFF"}


class CartoonInkValidationError(ValueError): pass


def require_type_minima(role_pixels: dict[str, float]) -> None:
    missing = {role: (role_pixels.get(role, 0), minimum) for role, minimum in ROLE_MINIMUM_PX.items() if role_pixels.get(role, 0) < minimum}
    if missing:
        raise CartoonInkValidationError(f"TYPE_SIZE_BELOW_1080P_MINIMUM:{missing}")


def require_panel_palette(colours: list[str]) -> None:
    normalized = {colour.upper() for colour in colours}
    unknown = normalized - CHANNEL_ACCENTS - CHANNEL_NEUTRALS
    accents = normalized & CHANNEL_ACCENTS
    if unknown or len(accents) > 2:
        raise CartoonInkValidationError(f"PALETTE_GATE_FAILED: unknown={sorted(unknown)}, accents={sorted(accents)}")


def ui_likeness_warnings(*, rounded_rectangles: int, thin_grid_lines: int, axis_labels: int) -> list[str]:
    """A compact heuristic for accidental mobile-widget grammar."""
    warnings = []
    if rounded_rectangles > 0: warnings.append("rounded_widget")
    if thin_grid_lines > 2: warnings.append("dense_grid")
    if axis_labels > 3: warnings.append("dashboard_axis_density")
    return warnings
