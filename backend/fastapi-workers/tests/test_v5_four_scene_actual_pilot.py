from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "run_v5_four_scene_actual_pilot.py"
SPEC = importlib.util.spec_from_file_location("v5_four_scene_actual_pilot", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _scene(scene_id: str, scene_type: str, narration: str) -> dict:
    return {
        "scene_id": scene_id,
        "scene_type": scene_type,
        "narration": narration,
        "visual_intent": narration,
    }


def test_actual_four_scene_pilot_uses_script_caption_contract_without_numeric_overlays():
    scenes = MODULE._planned_scenes({
        "scenes": [
            {**_scene("semiconductor", "graph", "반도체 주가가 약세일 가능성을 살펴봅니다."), "visual_intent": "A graph."},
            {**_scene("dollar", "graph", "달러와 환율의 압박으로 시장 흐름이 약세입니다."), "visual_intent": "A graph."},
            {**_scene("fear", "metric", "시장의 공포는 진정되지만 변동성 위험은 남아 있습니다."), "visual_intent": "A market risk index gauge."},
        ]
    })

    assert [scene["v5_render_contract"]["scene_type"] for scene in scenes] == ["graph", "graph", "metric", "general"]
    assert all(not scene.get("verified_facts") for scene in scenes)
    assert all(not scene.get("v5_verified_overlays") for scene in scenes)
    assert all(
        scene["v5_render_contract"]["visual_text_policy"] in {"deterministic_surface_text", "strict_textless"}
        for scene in scenes
    )


def test_actual_four_scene_pilot_rejects_numeric_overlay_payload():
    payload = {
        "scenes": [
            {**_scene("one", "graph", "시장 약세"), "verified_facts": [{"figure": "12%"}]},
            _scene("two", "graph", "달러 압박"),
            _scene("three", "metric", "공포 진정"),
        ]
    }

    try:
        MODULE._planned_scenes(payload)
    except ValueError as exc:
        assert "수치·사실 오버레이" in str(exc)
    else:
        raise AssertionError("수치 오버레이가 파일럿 계획에 들어가면 안 됩니다.")
