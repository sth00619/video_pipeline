"""V5 무문자 프롬프트 계약이 다시 라벨 요구를 넣지 않게 막는다."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.scene.prompt_builder import ARCHETYPES, BENCHMARK_SCENES, build_prompt


def test_all_benchmark_prompts_request_a_textless_image():
    forbidden_positive_hints = ("short english labels", "sample figures", "simple equations", "chart ticks")
    for scene in BENCHMARK_SCENES:
        prompt = build_prompt(scene, visual_text_policy="strict_textless").lower()
        assert "no writing-like strokes anywhere" in prompt
        assert "roman letters such as x or x" in prompt
        assert "equation fragments" in prompt
        assert "do not make a split screen, comic panels, inset images" in prompt
        assert "comic panels" in prompt
        # 금지 대상은 exclusions에서 언급되어야 하므로, 장식 텍스트를 긍정적으로
        # 요구하는 문구만 없는지 확인한다.
        assert not any(hint in prompt for hint in forbidden_positive_hints), scene.scene_id


def test_default_prompt_requests_reference_like_decorative_information():
    prompt = build_prompt(BENCHMARK_SCENES[0]).lower()
    assert "short english labels" in prompt
    assert "sample figures" in prompt
    assert "never leave an empty screen" in prompt
    assert "atmospheric decoration only" in prompt
    assert "all writing must be painted" in prompt
    assert "detached rectangular ui widget" in prompt
    assert "broad flat front panel" in prompt
    assert "never on its side wall" in prompt
    assert "only anthropomorphic character" in prompt
    assert "exact same round coin silhouette" in prompt


def test_weather_and_risk_text_are_required_to_be_scene_native_props():
    weather = build_prompt(BENCHMARK_SCENES[4]).lower()
    risk = build_prompt(BENCHMARK_SCENES[5]).lower()
    assert "integrate them with map contours, cloud icons, and directional arrows" in weather
    assert "brass-and-red control plaques" in risk
    assert "free-floating data card" in weather
    assert "free-floating data card" in risk


def test_retail_prompt_has_no_positive_secondary_character_request():
    props = ARCHETYPES["retail_shock"].props.lower()
    assert "robot" not in props
    assert "cashier" not in props


def test_data_lab_prompt_requires_full_body_wide_control_room_composition():
    prompt = build_prompt(BENCHMARK_SCENES[-1]).lower()
    assert "same full-body scale" in prompt
    assert "do not use a close portrait crop" in prompt
