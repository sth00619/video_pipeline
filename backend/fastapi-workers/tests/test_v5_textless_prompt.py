"""V5 무문자 프롬프트 계약이 다시 라벨 요구를 넣지 않게 막는다."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.scene.prompt_builder import BENCHMARK_SCENES, build_prompt


def test_all_benchmark_prompts_request_a_textless_image():
    forbidden_positive_hints = ("english", "percentage", "label", "subtitle", "logo", "korean", "16:9", "%")
    for scene in BENCHMARK_SCENES:
        prompt = build_prompt(scene).lower()
        assert "no writing-like strokes anywhere" in prompt
        assert not any(hint in prompt for hint in forbidden_positive_hints), scene.scene_id
