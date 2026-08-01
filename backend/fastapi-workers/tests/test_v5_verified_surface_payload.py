from __future__ import annotations

import pytest

from app.services.info_surface.contracts import plan_from_scene
from app.v5.overlay.verified_surface_payload import market_chart_from_verified_scene


def _scene(value: str = "-3.16%") -> dict:
    return {
        "scene_id": "verified-surface",
        "scene_type": "metric",
        "verified_facts": [{
            "fact": f"SK HYNIX 주가는 {value} 하락했다.",
            "figure": value,
            "published_at": "2026-08-02T09:00:00+09:00",
            "source_url": "https://example.test/verified",
        }],
        "v5_verified_overlays": [{
            "label": "SK HYNIX",
            "value": value,
            "source_ref": "facts[0]",
            "anchor": {"x": .34, "y": .28, "width": .20, "height": .14, "kind": "embedded_monitor"},
        }],
        "v5_render_contract": {
            "scene_type": "metric",
            "selection": {"archetype": "risk_control_room"},
            "primary_surface_region": (.33, .23, .34, .38),
        },
    }


def test_verified_fact_becomes_exact_physical_surface_payload_without_new_number():
    chart = market_chart_from_verified_scene(_scene())
    assert chart is not None
    assert chart["verified"] is True
    assert chart["hero_stat"]["headline_value"] == "-3.16%"
    assert chart["hero_stat"]["headline_unit_label"] == "SK HYNIX"
    assert chart["hero_stat"]["direction"] == "down"
    assert chart["hero_stat"]["source_refs"] == ["facts[0]"]


def test_verified_surface_copy_can_change_the_scene_wording_without_inventing_a_number():
    scene = _scene()
    scene["v5_verified_overlays"][0]["surface_title"] = "SEMICONDUCTOR STOCK"
    scene["v5_verified_overlays"][0]["surface_meaning"] = "SK HYNIX GOES DOWN"
    chart = market_chart_from_verified_scene(scene)
    assert chart is not None
    assert chart["label"] == "SEMICONDUCTOR STOCK"
    assert chart["hero_stat"]["headline_value"] == "-3.16%"
    assert chart["hero_stat"]["headline_unit_label"] == "SK HYNIX"
    assert chart["hero_stat"]["meaning_line"] == "SK HYNIX GOES DOWN"


def test_verified_surface_copy_rejects_a_number_missing_from_the_evidence():
    scene = _scene()
    scene["v5_verified_overlays"][0]["surface_meaning"] = "SK HYNIX DOWN -9.99%"
    with pytest.raises(ValueError, match="검증 원문에 없는 숫자"):
        market_chart_from_verified_scene(scene)


def test_v5_plan_uses_the_archetype_primary_surface_instead_of_a_hud_card():
    scene = _scene()
    scene["market_chart"] = market_chart_from_verified_scene(scene)
    plan = plan_from_scene(scene)
    assert plan is not None
    assert plan.render_mode == "DIEGETIC_WARP"
    assert plan.surface is not None
    assert plan.surface.surface_kind == "analog_gauge"
    assert plan.surface.preferred_region == {"x": .33, "y": .23, "width": .34, "height": .38}
    assert plan.items[0].role == "metric"


def test_unverified_existing_market_chart_fails_closed():
    scene = _scene()
    scene["market_chart"] = {"verified": False, "latest": 123}
    with pytest.raises(ValueError, match="verified=true"):
        market_chart_from_verified_scene(scene)
