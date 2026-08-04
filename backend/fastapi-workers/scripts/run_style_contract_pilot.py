"""승인된 V5 화풍 계약을 3개 대표 장면으로만 검증하는 유료 파일럿 실행기."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import requests


PILOT_SCENES: tuple[dict[str, str], ...] = (
    {
        "scene_id": "scene_000",
        "scene_type": "graph",
        "visual_archetype": "briefing_podium",
        "title": "공포 지수가 식었다",
        "content": "공포가 식고 시장의 긴장이 완화되는 흐름을 설명합니다.",
    },
    {
        "scene_id": "scene_001",
        "scene_type": "graph",
        "visual_archetype": "trade_calculator",
        "title": "달러가 흔들렸다",
        "content": "달러가 압박을 받는 시장 흐름을 설명합니다.",
    },
    {
        "scene_id": "scene_003",
        "scene_type": "metric",
        "visual_archetype": "risk_control_room",
        "title": "7월의 공포",
        "content": "시장 공포와 위험 신호를 설명합니다.",
    },
)


def _write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--execute-images", action="store_true")
    args = parser.parse_args()

    scenes = [dict(scene) for scene in PILOT_SCENES]
    _write_json(args.output_dir / "selected_scenes.json", scenes)
    if not args.execute_images:
        print(json.dumps({"mode": "preflight", "scene_count": len(scenes)}, ensure_ascii=False))
        return 0

    payload = {
        "job_id": args.job_id,
        "tts_meta": json.dumps({"target_seconds": 30}, ensure_ascii=False),
        "script_meta": json.dumps({"still_image_pilot": True, "sections": scenes, "scenes": scenes}, ensure_ascii=False),
        "budget_limit_krw": 620,
        "budget_policy_version": "style-contract-pilot-3x188-2026-08-02",
    }
    response = requests.post(f"{args.base_url.rstrip('/')}/workers/images/generate", json=payload, timeout=900)
    if response.status_code >= 400:
        raise RuntimeError(f"이미지 파일럿 호출 실패 (HTTP {response.status_code}): {response.text[:2000]}")
    result = response.json()
    _write_json(args.output_dir / "images_result.json", result)
    if int(result.get("scene_count") or 0) != len(scenes):
        raise RuntimeError(f"파일럿 장면 수 불일치: {result.get('scene_count')}")
    methods = {str(scene.get("generation_method") or "") for scene in result.get("scenes", [])}
    if methods - {"pro_gemini", "composite"}:
        raise RuntimeError(f"허용되지 않은 생성 방식: {sorted(methods)}")
    print(json.dumps({"mode": "completed", "scene_count": len(scenes), "methods": sorted(methods)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
