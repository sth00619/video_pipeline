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
    assert metric["visual_text_policy"] == graph["visual_text_policy"] == "script_captioned"
    assert general["style_contract_version"] == "2026-08-03-r4-korean-nonnumeric-three-mode-v1"
    assert metric["style_contract_version"] == general["style_contract_version"]
    assert general["verified_overlay_mode"] == "not_applicable"
    assert metric["verified_overlay_mode"] == "non_numeric_prompt_embedded_script_caption"
    assert general["visual_mode_contract"]["overlay_policy"] == "ass_subtitle_only"
    assert metric["visual_mode_contract"]["numeric_visual_policy"] == "prohibited"
    assert v5_provider_options(scenes[0]) == {
        "image_provider": "gemini",
        "gemini_model": "gemini-3-pro-image",
        "gemini_image_size": "2K",
        "gemini_service_tier": "standard",
        "gemini_max_attempts": 2,
        "suppress_legacy_style_lock": True,
        "style_locked": True,
        "gemini_reference_contract_declared": True,
    }
    assert scenes[0]["image_profile"]["v5_final_lane"] is True


def test_runtime_contract_rotates_consecutive_archetypes_and_records_visual_modes():
    scenes = attach_v5_scene_contracts([
        _scene("graph-01", "graph", "반도체 하락 그래프를 설명합니다."),
        _scene("graph-02", "graph", "달러 압박 그래프를 설명합니다."),
        _scene("general-01", "general", "항만의 상황을 보여 줍니다."),
    ])

    first, second, general = [scene["v5_render_contract"] for scene in scenes]
    assert first["selection"]["archetype"] == "data_lab"
    assert second["selection"]["archetype"] == "weather_map"
    assert scenes[1]["visual_mix_adjustment"]["reason"] == "consecutive_archetype_avoidance"
    assert first["visual_mode"] == second["visual_mode"] == "archetype_explainer"
    assert general["visual_mode"] == "semantic_illustration"


def test_runtime_contract_marks_captured_article_as_article_evidence_mode():
    scene = _scene("article-01", "graph", "미국 증시 뉴스를 설명합니다.")
    scene["visual_type"] = "article_evidence"
    scene["article_capture"] = {"local_path": "/tmp/article.png"}

    contract = plan_v5_scene_contract(scene, 0)

    assert contract["visual_mode"] == "article_evidence"
    assert contract["visual_mode_contract"] == {
        "asset_source": "verified_article_capture",
        "text_policy": "source_capture_only",
        "overlay_policy": "underline_highlight_and_source_credit_only",
        "numeric_visual_policy": "source_document_only",
        "character_policy": "no_generated_mascot",
    }


def test_runtime_contract_preserves_primary_surface_and_does_not_invent_verified_values():
    source = _scene("metric-01", "metric", "코스피 하락폭과 위험 지표를 설명합니다.")
    planned = attach_v5_scene_contracts([source])[0]
    contract = planned["v5_render_contract"]

    assert planned["scene_type"] == "metric"
    assert contract["selection"]["archetype"] == "risk_control_room"
    assert len(contract["primary_surface_region"]) == 4
    assert contract["verified_overlay_present"] is False
    assert "caption" in contract["semantic_visual_plan"]
    assert "prop_visuals" in contract["semantic_visual_plan"]
    assert "v5_verified_overlays" not in planned
    assert "physically part of that prop" in prompt_for_scene(planned).lower()


def test_runtime_contract_does_not_confuse_style_contract_numbers_with_verified_facts():
    source = _scene("metric-three", "metric", "시장 심리를 설명합니다.")
    source["verified_facts"] = [{"figure": "3"}]

    planned = attach_v5_scene_contracts([source])[0]

    prompt = prompt_for_scene(planned)
    assert prompt is not None
    assert "3-5px" not in prompt
    assert "SCENE VARIATION SEED" not in prompt


def test_runtime_contract_restores_text_only_layout_contract_for_general_and_information_scenes():
    general = plan_v5_scene_contract(
        _scene("general-layout", "general", "항만 물류 차질의 배경을 설명합니다."),
        0,
    )
    information = plan_v5_scene_contract(
        _scene("graph-layout", "graph", "시장 추이 막대그래프를 비교합니다."),
        1,
    )

    for contract in (general, information):
        prompt = contract["prompt_en"]
        assert "<layout_contract>" in prompt
        assert "Do not draw any layout guide, safe-area outline, placeholder, or empty display." in prompt


def test_general_scene_can_explicitly_use_an_environment_only_composition():
    source = _scene("general-environment", "general", "빅테크 실적과 AI 투자 부담을 상황으로 설명합니다.")
    source.update({
        "character_required": False,
        "visual_archetype": "data_lab",
        "visual_intent": "A processor pipeline feeds an uncertain profit turbine, no text and no numbers.",
    })

    contract = plan_v5_scene_contract(source, 0)
    prompt = contract["prompt_en"]

    assert contract["scene_spec"]["character_required"] is False
    assert "NO mascot and NO anthropomorphic character" in prompt
    assert "processor pipeline feeds an uncertain profit turbine" in prompt
    assert "<layout_contract>" not in prompt


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
    assert planned["v5_render_contract"]["verified_overlay_present"] is False
    assert planned["v5_render_contract"]["visual_text_policy"] == "script_captioned"
    assert "no floating text anywhere" in planned["v5_render_contract"]["prompt_en"].lower()


def test_runtime_contract_derives_chart_overlay_only_from_matching_verified_fact():
    source = _scene("vix-graph", "graph", "VIX 지수가 15.99포인트로 진정됐습니다.")
    source["market_chart"] = {
        "verified": True,
        "label": "VIX",
        "latest": 15.99,
        "source_ref": "market_snapshot.chart_series.vix",
    }
    source["verified_facts"] = [{
        "fact": "VIX 지수는 진정됐다.",
        "figure": "15.99포인트",
        "source_field": "market_snapshot.chart_series.vix",
    }]

    planned = attach_v5_scene_contracts([source])[0]

    assert "v5_verified_overlays" not in planned


def test_runtime_contract_matches_chart_source_by_indicator_tail_and_derives_script_number():
    graph = _scene("vix-graph", "graph", "VIX는 7월 29일 20.66포인트까지 올랐습니다.")
    graph["market_chart"] = {
        "verified": True,
        "label": "VIX",
        "latest": 15.99,
        "source_ref": "market_snapshot.chart_series.vix",
    }
    graph["verified_facts"] = [{
        "fact": "VIX 지수는 7월 말 진정됐다.",
        "figure": "20.66포인트",
        "source_field": "us.chart_series.vix(2026-07-29, 2026-07-31)",
    }]
    diagram = _scene("kospi-diagram", "diagram", "28일 6023포인트였던 코스피가 하락했습니다.")
    diagram["verified_facts"] = [{
        "fact": "코스피는 7월 28일부터 30일까지 하락했다.",
        "figure": "6023포인트",
        "source_field": "kr.chart_series.kospi",
    }]

    planned_graph, planned_diagram = attach_v5_scene_contracts([graph, diagram])

    assert "v5_verified_overlays" not in planned_graph
    assert "v5_verified_overlays" not in planned_diagram


def test_runtime_contract_uses_korean_context_without_numeric_or_floating_ui():
    contract = plan_v5_scene_contract(
        _scene("retail-korea", "metric", "홈플러스와 하림 인수 이슈가 유통주에 미칠 영향을 설명합니다."),
        0,
    )

    prompt = contract["prompt_en"].lower()
    assert "recognizably korean hypermarket" in prompt
    assert "no real brand logo" in prompt
    assert "speech bubbles, comic balloons, caption chips" in prompt
    assert "numeric_visual_policy" in contract["visual_mode_contract"]


def test_earnings_stage_is_not_an_automatic_candidate_and_remains_blocked():
    assert "earnings_stage" not in RENDER_BLOCKED_ARCHETYPES
    assert all("earnings_stage" not in candidates for candidates in TYPE_CANDIDATES.values())


def test_runtime_contract_rejects_missing_scene_type():
    try:
        plan_v5_scene_contract({"scene_id": "missing", "content": "내용"}, 0)
    except ValueError as exc:
        assert "scene_type" in str(exc)
    else:
        raise AssertionError("scene_type 누락은 차단되어야 합니다.")
