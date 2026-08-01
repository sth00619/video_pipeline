import pytest

from app.services.info_surface.channel_chart_style import render_chart_content
from app.services.info_surface.contracts import plan_from_scene
from app.services.info_surface.hero_stat import hero_stat_from_chart
from app.utils.number_format import indexed_basis


def _indexed_chart():
    return {
        "verified": True,
        "source_ref": "collector.policy_costs.2026-07-21",
        "visual_kind": "indexed_comparison",
        "label": "운송비 지수",
        "comparison_baseline": 100,
        "comparison_basis": "2026-07-21 = 100",
        "comparison_values": [
            {"label": "기준", "value": 100},
            {"label": "적용 후", "value": 107.0},
        ],
    }


def test_indexed_stat_requires_a_visible_basis_and_source():
    chart = _indexed_chart()
    hero = hero_stat_from_chart(chart)
    assert hero.headline_value == "107.0"
    assert hero.comparison_basis == "2026-07-21 = 100"
    assert indexed_basis("2026-07-21", 100) == "2026-07-21 = 100"

    chart.pop("comparison_basis")
    with pytest.raises(ValueError, match="comparison_basis"):
        hero_stat_from_chart(chart)


def test_scene_plan_carries_the_bounded_poster_hierarchy():
    chart = _indexed_chart()
    scene = {
        "scene_id": "hero-stat-fixture",
        "market_chart": chart,
        "art_direction": {"surface_contract": {"surface_kind": "paper", "geometry": "irregular_mask"}},
    }
    plan = plan_from_scene(scene)
    assert plan is not None
    assert plan.hero_stat is not None
    assert len(plan.hero_stat.support_marks) <= 2
    assert plan.hero_stat.source_refs == [chart["source_ref"]]


def test_cartoon_ink_is_seeded_and_has_no_dashboard_grid_requirement():
    chart = _indexed_chart()
    first = render_chart_content(chart, (720, 405))
    second = render_chart_content(chart, (720, 405))
    assert first.tobytes() == second.tobytes()
    assert first.getchannel("A").getbbox() is not None


def test_physical_surface_renderer_does_not_repeat_identical_title_and_unit(monkeypatch):
    calls: list[str] = []

    def record_text(_image, _position, text, **_kwargs):
        calls.append(text)

    monkeypatch.setattr(
        "app.services.info_surface.channel_chart_style.draw_display_text",
        record_text,
    )
    render_chart_content(
        {
            "verified": True,
            "source_ref": "fixture",
            "label": "KOSPI CLOSE",
            "hero_stat": {
                "headline_value": "7,096.89",
                "headline_unit_label": "KOSPI CLOSE",
                "direction": "up",
                "meaning_line": "UP +4.40%",
                "comparison_basis": "2026-07-23 CLOSE",
                "source_refs": ["fixture"],
            },
        },
        (960, 540),
    )
    assert calls.count("KOSPI CLOSE") == 1
