"""분리된 구조화 값·단위가 생성기와 최종 어댑터를 모두 통과하는 긍정 증거."""
import pytest

from app.v5.overlay.diegetic_fact_overlay import facts_from_verified_scene
from app.v5.scene.runtime_contract import _build_v5_verified_overlays


@pytest.mark.parametrize("value", ["2,650", "6,597"])
def test_split_unit_passes_planner_and_final_adapter(value):
    scene = {
        "narration": f"코스피가 {value}포인트를 기록했습니다.",
        "verified_facts": [{"indicator": "KOSPI", "value": value, "unit": "pt",
                            "figure": f"{value}pt", "fact": f"코스피 {value}포인트 기록"}],
    }
    scene["v5_verified_overlays"] = _build_v5_verified_overlays(
        scene["verified_facts"], "classroom", (.1, .1, .5, .5), scene=scene,
    )
    assert scene["v5_verified_overlays"][0]["value"] == value
    assert facts_from_verified_scene(scene)[0].value == value
    scene["v5_verified_overlays"][0]["value"] = value[:-1]
    with pytest.raises(ValueError, match="원문"):
        facts_from_verified_scene(scene)
