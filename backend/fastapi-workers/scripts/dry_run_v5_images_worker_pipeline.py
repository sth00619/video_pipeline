#!/usr/bin/env python3
"""ScriptWorker 분류 결과를 ImagesWorker용 V5 계약까지 무료로 점검한다.

이 도구는 이미지·LLM API를 호출하지 않는다. 실제 ImagesWorker가 소비하는
``v5_render_contract``와 같은 생성 함수를 사용해, 프롬프트/라우팅/오버레이
준비 상태만 JSON과 Markdown으로 남긴다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.scene.runtime_contract import attach_v5_scene_contracts
from app.workers.script_worker import _classify_scene_types


def _worker_scene(raw: dict) -> dict:
    narration = str(raw.get("narration") or raw.get("content") or raw.get("text") or "")
    return {
        "scene_id": str(raw.get("scene_id") or raw.get("id") or ""),
        # scene_id의 순번 숫자는 금융 지표가 아니다. 제목이 없을 때 ID를
        # 제목으로 복사하면 scene_type 분류기가 이를 metric 신호로 오인할 수 있다.
        "title": str(raw.get("title") or ""),
        "content": narration,
        "text": narration,
        "visual_intent": str(raw.get("visual_intent") or ""),
        "verified_facts": raw.get("verified_facts") or [],
        "v5_verified_overlays": raw.get("v5_verified_overlays") or [],
    }


def _summary(scene: dict) -> dict:
    contract = scene["v5_render_contract"]
    return {
        "scene_id": contract["scene_id"],
        "scene_type": contract["scene_type"],
        "archetype": contract["selection"]["archetype"],
        "selection_reason": contract["selection"]["selection_reason"],
        "primary_physical_surface": contract["selection"]["primary_physical_surface"],
        "primary_surface_region": contract["primary_surface_region"],
        "provider": contract["provider"],
        "tier": contract["tier"],
        "visual_text_policy": contract["visual_text_policy"],
        "verified_overlay_mode": contract["verified_overlay_mode"],
        "verified_overlay_present": contract["verified_overlay_present"],
        "prompt_en": contract["prompt_en"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="V5 ImagesWorker 무료 드라이런")
    parser.add_argument("--input", type=Path, default=ROOT / "out/v5_pilot/kospi_july_2026/v5_pilot_input.json")
    parser.add_argument("--output", type=Path, default=ROOT / "out/v5_pilot/kospi_july_2026/images_worker_v5_dry_run.json")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    raw_scenes = list(payload.get("scenes") or [])[:5]
    classified = _classify_scene_types([_worker_scene(scene) for scene in raw_scenes])
    planned = attach_v5_scene_contracts(classified)
    report = {
        "mode": "dry_run_no_image_or_llm_api_calls",
        "source": str(args.input),
        "scene_count": len(planned),
        "images_worker_prompt_source": "v5_render_contract.prompt_en",
        "facts_policy": "v5_verified_overlays are preserved and rendered only after generation by Pillow",
        "scenes": [_summary(scene) for scene in planned],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown = [
        "# V5 ImagesWorker 무료 드라이런",
        "",
        "이미지 API와 LLM API를 호출하지 않았다. ScriptWorker의 scene_type 분류와 ImagesWorker가 사용하는 V5 계약 생성만 실행했다.",
        "",
    ]
    for item in report["scenes"]:
        markdown.extend([
            f"## {item['scene_id']}",
            "",
            f"- scene_type: `{item['scene_type']}`",
            f"- archetype: `{item['archetype']}`",
            f"- provider / tier: `{item['provider']}` / `{item['tier']}`",
            f"- primary surface: {item['primary_physical_surface']}",
            f"- deterministic verified overlay: `{item['verified_overlay_mode']}` (input present: `{item['verified_overlay_present']}`)",
            f"- selection reason: {item['selection_reason']}",
            "",
        ])
    args.output.with_suffix(".md").write_text("\n".join(markdown), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
