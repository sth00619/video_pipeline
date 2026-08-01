from app.v5.providers.router import RENDER_BLOCKED_ARCHETYPES
from app.v5.scene.runtime_contract import (
    attach_v5_scene_contracts,
    plan_v5_scene_contract,
    prompt_for_scene,
    v5_provider_options,
)
from app.v5.scene.scene_type_archetypes import TYPE_CANDIDATES


def _scene(scene_id: str, scene_type: str, content: str) -> dict:
    return {
        "scene_id": scene_id,
        "scene_type": scene_type,
        "content": content,
        "visual_intent": content,
    }


def test_runtime_contract_uses_gemini_for_general_and_information_scenes():
    scenes = attach_v5_scene_contracts([
        _scene("general-01", "general", "항만 물류 차질의 배경을 설명합니다."),
        _scene("metric-01", "metric", "코스피 하락폭과 위험 지표를 설명합니다."),
        _scene("graph-01", "graph", "시장 추이 막대그래프를 비교합니다."),
    ])

    general, metric, graph = [scene["v5_render_contract"] for scene in scenes]
    assert general["provider"] == metric["provider"] == graph["provider"] == "gemini_pro"
    assert general["tier"] == "body"
    assert metric["tier"] == graph["tier"] == "hero"
    assert general["visual_text_policy"] == "strict_textless"
    assert metric["visual_text_policy"] == graph["visual_text_policy"] == "diegetic_decorative"
    assert general["style_contract_version"] == "2026-08-02-cinematic-cartoon-recovery"
    assert metric["style_contract_version"] == general["style_contract_version"]
    assert general["verified_overlay_mode"] == "not_applicable"
    assert metric["verified_overlay_mode"] == "apply_verified_values_after_generation"
    assert v5_provider_options(scenes[0]) == {
        "image_provider": "gemini",
        "gemini_model": "gemini-3-pro-image",
        "gemini_image_size": "2K",
        "gemini_service_tier": "standard",
        "gemini_max_attempts": 1,
        "suppress_legacy_style_lock": True,
        "style_locked": True,
        "gemini_reference_contract_declared": True,
    }
    assert scenes[0]["image_profile"]["v5_final_lane"] is True


def test_runtime_contract_preserves_primary_surface_and_does_not_invent_verified_values():
    source = _scene("metric-01", "metric", "코스피 하락폭과 위험 지표를 설명합니다.")
    planned = attach_v5_scene_contracts([source])[0]
    contract = planned["v5_render_contract"]

    assert planned["scene_type"] == "metric"
    assert contract["selection"]["archetype"] == "risk_control_room"
    assert len(contract["primary_surface_region"]) == 4
    assert contract["verified_overlay_present"] is False
    assert "v5_verified_overlays" not in planned
    assert "exact verified facts are composited later by deterministic rendering" in prompt_for_scene(planned).lower()


def test_runtime_contract_keeps_verified_overlay_input_unchanged_when_present():
    source = _scene("graph-01", "graph", "시장 추이 막대그래프를 비교합니다.")
    source["verified_facts"] = [{"fact": "종가 100.0", "figure": "100.0"}]
    source["v5_verified_overlays"] = [{
        "label": "종가",
        "value": "100.0",
        "source_ref": "facts[0]",
        "anchor": {"x": .12, "y": .12, "width": .25, "height": .12, "kind": "embedded_monitor"},
    }]

    planned = attach_v5_scene_contracts([source])[0]
    assert planned["v5_verified_overlays"] == source["v5_verified_overlays"]
    assert planned["v5_render_contract"]["verified_overlay_present"] is True


def test_earnings_stage_is_not_an_automatic_candidate_and_remains_blocked():
    assert "earnings_stage" in RENDER_BLOCKED_ARCHETYPES
    assert all("earnings_stage" not in candidates for candidates in TYPE_CANDIDATES.values())


def test_runtime_contract_rejects_missing_scene_type():
    try:
        plan_v5_scene_contract({"scene_id": "missing", "content": "내용"}, 0)
    except ValueError as exc:
        assert "scene_type" in str(exc)
    else:
        raise AssertionError("scene_type 누락은 차단되어야 합니다.")
