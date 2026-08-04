from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "run_visual_mix_nine_scene_preflight.py"
SPEC = importlib.util.spec_from_file_location("visual_mix_preflight", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _payload() -> dict:
    article = [{"scene_id": f"article-{index}", "visual_mode": "article_evidence", "article_capture_json": ""} for index in range(3)]
    semantic = [
        {"scene_id": f"semantic-{index}", "visual_mode": "semantic_illustration", "scene_type": "general", "content": "시장 상황 설명"}
        for index in range(3)
    ]
    information = [
        {"scene_id": f"info-{index}", "visual_mode": "archetype_explainer", "scene_type": "graph", "content": "시장 그래프 설명"}
        for index in range(3)
    ]
    return {"scenes": article + semantic + information}


def test_visual_mix_preflight_requires_three_modes_and_rotates_generated_archetypes(monkeypatch):
    observed = {}

    def fake_preflight(*args, **kwargs):
        observed.update(kwargs)
        return {"allowed": True, "estimated_cost_krw": 0}

    monkeypatch.setattr(MODULE, "plan_preflight", fake_preflight)
    result = MODULE.build_preflight(_payload())

    assert result["status"] == "article_assets_required"
    assert result["mode_counts"] == {
        "article_evidence": 3,
        "semantic_illustration": 3,
        "archetype_explainer": 3,
    }
    archetypes = [scene["archetype"] for scene in result["generated_scenes"]]
    assert all(left != right for left, right in zip(archetypes, archetypes[1:]))
    assert all(scene["numeric_visual_policy"] == "prohibited" for scene in result["generated_scenes"])
    assert all(scene["overlay_policy"] == "ass_subtitle_only" for scene in result["generated_scenes"])
    assert all(scene["overlay_policy"] == "underline_highlight_and_source_credit_only" for scene in result["article_scenes"])
    assert result["motion_preflight"]["external_request_started"] is False
    assert result["motion_preflight"]["requires_explicit_editor_selection"] is True
    assert len(result["motion_preflight"]["eligible_scene_ids"]) == 3
    assert len(result["motion_preflight"]["blocked_scene_ids"]) == 6
    assert observed["budget_limit_krw"] == 5_000
    assert observed["include_thumbnail"] is False


def test_visual_mix_preflight_rejects_an_unbalanced_mix():
    payload = _payload()
    payload["scenes"][0]["visual_mode"] = "semantic_illustration"

    try:
        MODULE.build_preflight(payload)
    except ValueError as exc:
        assert "각각 정확히 3개" in str(exc)
    else:
        raise AssertionError("불균형한 장면 혼합은 통과하면 안 됩니다.")
