#!/usr/bin/env python3
"""기존 대본 산출물의 장면 유형만 최신 분포 정책으로 다시 계산한다.

Claude 대본·검증 사실·수치·출처는 그대로 두며, 이미지 프롬프트 선택에 쓰이는
``scene_type``과 ``selection_reason``만 갱신한다.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from app.workers.script_worker import _classify_scene_types


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="기존 script_result.json")
    parser.add_argument("--output", type=Path, required=True, help="보정된 JSON 저장 경로")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    sections = payload.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("sections가 있는 실제 대본 산출물이 필요합니다.")

    payload["sections"] = _classify_scene_types(sections)
    payload["scene_type_distribution"] = dict(
        Counter(str(scene.get("scene_type") or "") for scene in payload["sections"])
    )
    payload["scene_type_policy"] = "longform-metric-cap-18pct-v1"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "completed",
        "input": str(args.input),
        "output": str(args.output),
        "scene_type_distribution": payload["scene_type_distribution"],
        "scene_type_policy": payload["scene_type_policy"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
