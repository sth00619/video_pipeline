import pytest

from app.services.info_surface.cartoon_ink_qc import CartoonInkValidationError, require_panel_palette, require_type_minima, ui_likeness_warnings
from app.services.info_surface.channel_typography import DISPLAY_FONT, DISPLAY_LICENSE, ensure_display_font_license
from app.services.info_surface.channel_chart_style import render_chart_content


def test_font_bundle_license_and_1080p_role_minima_are_required():
    assert DISPLAY_FONT.is_file() and DISPLAY_LICENSE.is_file()
    assert ensure_display_font_license() == DISPLAY_FONT
    require_type_minima({"hero": 66, "title": 44, "meaning": 30})
    with pytest.raises(CartoonInkValidationError, match="TYPE_SIZE"):
        require_type_minima({"hero": 65, "title": 44, "meaning": 30})


def test_renderer_fails_when_declared_final_type_scale_is_below_minimum():
    chart = {"verified": True, "source_ref": "fixture", "label": "Metric", "latest": 100, "change_pct": 1, "source_date": "2026-07-21", "final_output_scale": .9}
    with pytest.raises(CartoonInkValidationError, match="TYPE_SIZE"):
        render_chart_content(chart, (720, 405))


def test_palette_and_ui_widget_gate_fail_closed():
    require_panel_palette(["#071A3A", "#FFF4D6", "#F6BE28"])
    with pytest.raises(CartoonInkValidationError, match="PALETTE"):
        require_panel_palette(["#071A3A", "#00FFCC"])
    assert ui_likeness_warnings(rounded_rectangles=1, thin_grid_lines=4, axis_labels=5) == ["rounded_widget", "dense_grid", "dashboard_axis_density"]
