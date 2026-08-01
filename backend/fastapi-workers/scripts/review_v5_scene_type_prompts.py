#!/usr/bin/env python3
"""씬 타입 매핑이 반영된 V5 프롬프트를 이미지 호출 없이 검토용으로 출력한다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.scene.prompt_builder import SceneSpec, build_prompt
from app.v5.scene.scene_type_archetypes import recommend_v5_archetype
from app.workers.script_worker import _classify_scene_types


PRESENTATION_BY_ARCHETYPE = {
    "port_emergency": ("alarm", "safety_vest", "alarmed_run", "right"),
    "retail_shock": ("surprise", "analyst", "calculator_hold", "left"),
    "classroom": ("explain", "professor", "point_left", "right"),
    "weather_map": ("explain", "reporter", "present", "right"),
    "risk_control_room": ("concern", "formal", "present", "center"),
    "trade_calculator": ("confidence", "vest", "think", "left"),
    "data_lab": ("explain", "reporter", "present", "right"),
}


def _source_scene(raw: dict) -> dict:
    return {
        "title": raw.get("scene_id", ""),
        "content": raw.get("narration", ""),
        "visual_intent": raw.get("visual_intent", ""),
        "section": "data",
    }


def build_review(input_path: Path, output_path: Path) -> None:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    scenes = _classify_scene_types([_source_scene(raw) for raw in payload["scenes"]])
    lines = [
        "# V5 씬 타입 프롬프트 검토 출력",
        "",
        f"입력: `{input_path.as_posix()}`",
        "",
        "이 파일은 프롬프트 문자열 검토용이다. 이미지 API를 호출하지 않으며, 정확한 검증 수치는 AI에 넣지 않는다.",
        "",
    ]
    for raw, scene in zip(payload["scenes"], scenes):
        selection = recommend_v5_archetype(scene)
        emotion, costume, pose, position = PRESENTATION_BY_ARCHETYPE[selection.archetype]
        spec = SceneSpec(raw["scene_id"], selection.archetype, emotion, costume, pose, character_position=position)
        prompt = build_prompt(spec, scene_type_selection=selection, visual_text_policy="diegetic_decorative")
        lines.extend([
            f"## {raw['scene_id']}",
            "",
            f"- `scene_type`: `{scene['scene_type']}`",
            f"- 추천 `archetype`: `{selection.archetype}`",
            f"- 매핑 근거: {selection.selection_reason}",
            f"- 허용 물리 표면: {', '.join(selection.physical_surfaces)}",
            f"- 자동 고정 primary 물리 표면: `{selection.primary_physical_surface}`",
            "",
            "```text",
            prompt,
            "```",
            "",
        ])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def build_single_archetype_review(archetype: str, scene_type: str, output_path: Path) -> None:
    """한 archetype의 실제 프롬프트 계약만 비용 없이 검토 파일로 만든다."""
    raw_scene = {
        "scene_type": scene_type,
        "content": (
            "지도와 지역별 추이를 설명하는 그래프" if archetype == "weather_map"
            else "공급망의 단계와 인과 관계를 설명하는 흐름도" if archetype == "classroom"
            else "항만 물류의 핵심 경고 문구를 설명하는 장면" if archetype == "port_emergency"
            else "매장 가격과 소비 지표를 설명하는 장면" if archetype == "retail_shock"
            else "검증용 정보 장면"
        ),
    }
    selection = recommend_v5_archetype(raw_scene)
    if selection.archetype != archetype:
        raise ValueError(f"입력 scene_type이 {archetype}을 선택하지 않았습니다: {selection.archetype}")
    emotion, costume, pose, position = PRESENTATION_BY_ARCHETYPE[archetype]
    spec = SceneSpec(f"review_{archetype}", archetype, emotion, costume, pose, character_position=position)
    prompt = build_prompt(spec, scene_type_selection=selection, visual_text_policy="diegetic_decorative")
    lines = [
        f"# V5 {archetype} primary-surface 프롬프트 검토",
        "",
        "이 파일은 프롬프트 문자열 검토용이다. 이미지 API를 호출하지 않으며, 정확한 검증 수치를 AI에 넣지 않는다.",
        "",
        f"- `scene_type`: `{selection.scene_type}`",
        f"- 추천 `archetype`: `{selection.archetype}`",
        f"- 매핑 근거: {selection.selection_reason}",
        f"- 허용 물리 표면: {', '.join(selection.physical_surfaces)}",
        f"- 자동 고정 primary 물리 표면: `{selection.primary_physical_surface}`",
        "",
        "```text",
        prompt,
        "```",
        "",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="V5 씬 타입 프롬프트 검토 출력")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "out/v5_pilot/kospi_july_2026/v5_pilot_input.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "out/v5_pilot/kospi_july_2026/scene_type_prompt_review.md",
    )
    parser.add_argument("--single-archetype", choices=tuple(PRESENTATION_BY_ARCHETYPE))
    parser.add_argument("--scene-type", choices=("general", "metric", "graph", "diagram", "text"))
    args = parser.parse_args()
    if args.single_archetype:
        if not args.scene_type:
            parser.error("--single-archetype 사용 시 --scene-type이 필요합니다.")
        build_single_archetype_review(args.single_archetype, args.scene_type, args.output)
    else:
        build_review(args.input, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
