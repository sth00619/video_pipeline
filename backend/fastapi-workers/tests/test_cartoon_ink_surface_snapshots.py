import hashlib

from app.services.info_surface.channel_chart_style import render_chart_content
from app.services.info_surface.material_fx import apply_material_fx


def test_four_surface_material_snapshots_are_deterministic():
    chart = {
        "verified": True, "source_ref": "fixture", "label": "Cost index",
        "visual_kind": "indexed_comparison", "comparison_baseline": 100,
        "comparison_basis": "2026-07-21 = 100",
        "comparison_values": [{"label": "Base", "value": 100}, {"label": "After", "value": 107}],
    }
    raw = render_chart_content(chart, (720, 405))
    snapshots = {}
    for surface in ("chalkboard", "paper", "monitor", "signboard"):
        first = apply_material_fx(raw, surface, "golden-fixture")
        second = apply_material_fx(raw, surface, "golden-fixture")
        assert first.tobytes() == second.tobytes()
        snapshots[surface] = hashlib.sha256(first.tobytes()).hexdigest()
    assert len(set(snapshots.values())) >= 3
