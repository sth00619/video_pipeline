"""V5 레이아웃 스케치는 사람 검토용이고 모델 입력 래스터가 아님을 검증한다."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.scene.layout_sketcher import LayoutSketcher
from app.v5.scene.prompt_builder import BENCHMARK_SCENES, build_prompt


def test_right_mascot_layout_keeps_subtitle_and_logo_clear():
    plan = LayoutSketcher.for_right_mascot("scene-01", occupancy=0.42)
    plan.validate()
    assert plan.mascot.y + plan.mascot.height <= plan.subtitle.y
    assert plan.mascot.y >= plan.logo.y + plan.logo.height


def test_scene_layouts_intentionally_use_left_center_and_right_positions():
    positions = {scene.character_position for scene in BENCHMARK_SCENES}
    assert positions == {"left", "center", "right"}
    for scene in BENCHMARK_SCENES:
        plan = LayoutSketcher.for_mascot_position(
            scene.scene_id, occupancy=scene.frame_occupancy, position=scene.character_position,
        )
        plan.validate()
        assert plan.mascot_position == scene.character_position
        assert plan.mascot.y + plan.mascot.height <= plan.subtitle.y
        assert plan.mascot.y >= plan.logo.y + plan.logo.height


def test_svg_is_textless_review_artifact_and_not_a_model_reference(tmp_path: Path):
    plan = LayoutSketcher.for_right_mascot("scene-01", occupancy=0.42)
    target = tmp_path / "layout.svg"
    plan.write_svg(target)
    svg = target.read_text(encoding="utf-8")
    assert "<text" not in svg
    assert "scene-01" not in svg


def test_prompt_uses_text_only_layout_contract_without_guide_frame_request():
    instruction = LayoutSketcher.for_right_mascot("scene-01", occupancy=0.42).prompt_instruction()
    prompt = build_prompt(BENCHMARK_SCENES[-1], layout_instruction=instruction).lower()
    assert "layout contract" in prompt
    assert "do not draw any layout guide" in prompt
    assert "short english labels" in prompt
