import importlib.util
import io
import json
from pathlib import Path

import pytest
from PIL import Image


def _load_script_module():
    path = Path(__file__).resolve().parent.parent / "scripts" / "run_three_goals_images_e2e.py"
    spec = importlib.util.spec_from_file_location("three_goals_images_e2e", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dry_run_validates_four_scene_contract_without_external_call(tmp_path):
    input_path = tmp_path / "pilot.json"
    input_path.write_text(json.dumps({"scenes": [
        {"scene_id": "graph", "scene_type": "graph", "content": "항만 물동량 추세를 설명한다.",
         "verified_facts": [{"figure": "15%", "fact": "물동량은 15% 증가했다."}],
         "v5_verified_overlays": [{"label": "증가율", "value": "15%", "source_ref": "verified_facts[0]", "anchor": {"x": .20, "y": .20, "width": .20, "height": .15, "kind": "monitor"}}]},
        {"scene_id": "diagram", "scene_type": "diagram", "content": "공급망 단계를 설명한다.",
         "verified_facts": [{"figure": "3단계", "fact": "공급망은 3단계다."}],
         "v5_verified_overlays": [{"label": "단계", "value": "3단계", "source_ref": "verified_facts[0]", "anchor": {"x": .15, "y": .15, "width": .20, "height": .15, "kind": "placard"}}]},
        {"scene_id": "metric", "scene_type": "metric", "content": "물가 변동을 설명한다.",
         "verified_facts": [{"figure": "2.4%", "fact": "물가는 2.4% 변동했다."}],
         "v5_verified_overlays": [{"label": "변동", "value": "2.4%", "source_ref": "verified_facts[0]", "anchor": {"x": .40, "y": .30, "width": .20, "height": .15, "kind": "gauge_caption"}}]},
        {"scene_id": "general", "scene_type": "general", "content": "마스코트가 항구를 걷는다."},
    ]}, ensure_ascii=False), encoding="utf-8")

    module = _load_script_module()
    plan = module.build_plan(input_path)

    assert plan["mode"] == "dry_run"
    assert plan["model"] == "gemini-3-pro-image"
    assert [scene["scene_type"] for scene in plan["scenes"]] == ["graph", "diagram", "metric", "general"]
    assert all(scene["prompt_guard"] == "passed" for scene in plan["scenes"])
    assert plan["character_reference"]["file_name"] == "goldie_sheet_v1.png"
    assert plan["character_reference"]["attached_to_every_gemini_request"] is True
    assert plan["review_contract"]["automatic_regeneration"] is False


def test_rate_rise_diagram_selects_a_data_lab_chart_wall():
    module = _load_script_module()
    input_path = Path(__file__).resolve().parent.parent / "pilot-inputs" / "bok_monetary_policy_2026_07.json"

    plan = module.build_plan(input_path)

    diagram = next(scene for scene in plan["_planned_scenes"] if scene["scene_id"] == "policy_transmission_diagram")
    assert diagram["v5_render_contract"]["selection"]["archetype"] == "data_lab"
    fact = diagram["v5_verified_overlays"][0]
    assert fact["visualization"] == "upward_trend"
    assert fact["start_value"] == "2.50%"
    assert fact["end_value"] == "2.75%"


def test_regeneration_requires_a_manual_reason(tmp_path):
    module = _load_script_module()
    decisions = tmp_path / "review-decisions.json"
    decisions.write_text(json.dumps({"decisions": [
        {"scene_id": "graph", "decision": "REGENERATE", "reason": "소품 표면이 장면 의도와 다릅니다."},
    ]}, ensure_ascii=False), encoding="utf-8")

    module._require_regeneration_decisions(decisions, {"graph"})
    with pytest.raises(ValueError, match="명시적 재생성 승인"):
        module._require_regeneration_decisions(decisions, {"metric"})


def test_regeneration_requires_the_reviewed_candidate_attempt(tmp_path):
    module = _load_script_module()
    decisions = tmp_path / "review-decisions.json"
    decisions.write_text(json.dumps({"decisions": [
        {"scene_id": "graph", "decision": "REGENERATE", "reason": "문자 오염", "reviewed_attempt": 1},
    ]}, ensure_ascii=False), encoding="utf-8")
    dossier = {"scenes": [{"scene_id": "graph", "current_attempt": 1}]}

    module._require_regeneration_decisions(decisions, {"graph"}, dossier)

    dossier["scenes"][0]["current_attempt"] = 2
    with pytest.raises(ValueError, match="reviewed_attempt"):
        module._require_regeneration_decisions(decisions, {"graph"}, dossier)


def test_high_resolution_near_16_by_9_background_is_normalized_for_final_png():
    module = _load_script_module()
    source = io.BytesIO()
    Image.new("RGB", (2752, 1536), "navy").save(source, format="PNG")

    normalized, metadata = module._normalize_to_target_canvas(source.getvalue())

    with Image.open(io.BytesIO(normalized)) as result:
        assert result.size == (1920, 1080)
    assert metadata["source_size"] == [2752, 1536]
    assert metadata["target_size"] == [1920, 1080]


def test_manual_review_requires_every_current_candidate_and_marks_dossier_approved(tmp_path):
    module = _load_script_module()
    decisions = tmp_path / "final-review.json"
    decisions.write_text(json.dumps({"decisions": [
        {"scene_id": "graph", "decision": "APPROVE", "reviewed_attempt": 2, "reason": "통과"},
        {"scene_id": "metric", "decision": "APPROVE", "reviewed_attempt": 1, "reason": "통과"},
    ]}, ensure_ascii=False), encoding="utf-8")
    dossier = {"status": "PENDING_MANUAL_REVIEW", "scenes": [
        {"scene_id": "graph", "current_attempt": 2, "decision": "PENDING"},
        {"scene_id": "metric", "current_attempt": 1, "decision": "PENDING"},
    ]}

    recorded = module._record_manual_review(dossier, decisions)

    assert recorded["status"] == "APPROVED"
    assert all(scene["decision"] == "APPROVE" for scene in recorded["scenes"])
