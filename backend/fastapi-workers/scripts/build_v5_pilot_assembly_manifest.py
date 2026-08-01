#!/usr/bin/env python3
"""검증된 V5 이미지·대본·출처를 영상 조립기가 바로 읽을 순서 계약으로 묶는다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.validate_v5_pilot_input import validate_payload


def build_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    validate_payload(payload)
    scenes: list[dict[str, Any]] = []
    for index, scene in enumerate(payload["scenes"], start=1):
        facts = scene["verified_facts"]
        scenes.append({
            "order": index,
            "scene_id": scene["scene_id"],
            "image_path": scene["background_path"],
            "narration": scene.get("narration", ""),
            "visual_intent": scene.get("visual_intent", ""),
            "verified_overlays": scene["v5_verified_overlays"],
            "evidence": [
                {
                    "fact": fact.get("fact"),
                    "figure": fact.get("figure"),
                    "source_url": fact.get("source_url"),
                    "source_title": fact.get("source_title"),
                    "published_at": fact.get("published_at"),
                }
                for fact in facts
            ],
            # 실제 영상 길이는 TTS WAV의 실측 길이가 들어온 뒤 확정한다. 임의 초 수를
            # 넣지 않아 영상 조립 단계에서 내레이션과 화면이 어긋나는 일을 막는다.
            "duration_seconds": None,
            "duration_status": "pending_verified_tts_audio",
        })
    return {
        "contract": "v5_verified_pilot_assembly_v1",
        "topic": payload.get("topic"),
        "scene_count": len(scenes),
        "requires_image_generation": False,
        "image_cost_status": "no_additional_image_api_call_for_assembly",
        "scenes": scenes,
        "assembly_gate": {
            "requires_verified_tts_audio": True,
            "requires_human_visual_review": True,
            "forbids_unproven_overlay_values": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="V5 파일럿 영상 조립 매니페스트 생성")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    manifest = build_manifest(payload)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "assembly_manifest_created", "output": str(output), "scene_count": len(manifest["scenes"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
