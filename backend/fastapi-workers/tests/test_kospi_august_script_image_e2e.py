import importlib.util
from pathlib import Path

import pytest

from app.workers.script_worker import _classify_scene_type


def _module():
    path = Path(__file__).resolve().parent.parent / "scripts" / "run_kospi_august_script_image_e2e.py"
    spec = importlib.util.spec_from_file_location("kospi_august_script_image_e2e", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_selects_exactly_two_real_script_scenes_per_required_type():
    module = _module()
    sections = []
    for scene_type in module.REQUIRED_SCENE_TYPES:
        sections.extend([
            {"scene_type": scene_type, "title": f"{scene_type}-first"},
            {"scene_type": scene_type, "title": f"{scene_type}-second"},
            {"scene_type": scene_type, "title": f"{scene_type}-third"},
        ])

    selected = module.select_two_per_scene_type({"sections": sections})

    assert len(selected) == 6
    assert [scene["e2e_test_scene_type"] for scene in selected] == [
        "graph", "graph", "diagram", "diagram", "metric", "metric",
    ]
    assert [scene["title"] for scene in selected] == [
        "graph-first", "graph-second", "diagram-first", "diagram-second", "metric-first", "metric-second",
    ]


def test_refuses_to_fill_missing_scene_types_with_unrelated_scenes():
    module = _module()

    with pytest.raises(ValueError, match="diagram"):
        module.select_two_per_scene_type({"sections": [
            {"scene_type": "graph"}, {"scene_type": "graph"},
            {"scene_type": "metric"}, {"scene_type": "metric"},
        ]})


def test_verified_market_chart_is_classified_as_graph_before_numeric_metric():
    scene_type, reason = _classify_scene_type({
        "content": "지수는 100포인트입니다.",
        "market_chart": {"verified": True, "points": [{"close": 100}, {"close": 110}]},
    })

    assert scene_type == "graph"
    assert "market_chart" in reason


def test_prefers_scenes_with_script_numbers_for_overlay_verification():
    module = _module()
    selected = module.select_two_per_scene_type({"sections": [
        {"scene_type": "graph", "title": "graph-no-number"},
        {"scene_type": "graph", "title": "graph-1", "content": "VIX 15.99"},
        {"scene_type": "graph", "title": "graph-2", "content": "VIX 20.66"},
        {"scene_type": "diagram", "title": "diagram-no-number"},
        {"scene_type": "diagram", "title": "diagram-1", "content": "KOSPI 6,023.66p"},
        {"scene_type": "diagram", "title": "diagram-2", "content": "KOSPI 5,593.56p"},
        {"scene_type": "metric", "title": "metric-no-number"},
        {"scene_type": "metric", "title": "metric-1", "content": "stocks 70%"},
        {"scene_type": "metric", "title": "metric-2", "content": "fall 38.21%"},
    ]})

    assert [scene["title"] for scene in selected] == [
        "graph-no-number", "graph-1", "diagram-no-number", "diagram-1", "metric-no-number", "metric-1",
    ]
