"""검증된 단일 지표를 V5 물리 표면에 합성하는 무과금 검증 도구."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.services.info_surface.contracts import plan_from_scene
from app.services.info_surface.detector import detection_from_normalized_region
from app.services.info_surface.warp_compositor import composite_planar


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archetype", required=True)
    parser.add_argument("--region", required=True, help="x,y,width,height 정규화 좌표")
    parser.add_argument("--label", required=True)
    parser.add_argument("--value", required=True)
    parser.add_argument("--meaning", required=True)
    parser.add_argument("--direction", choices=("up", "down", "flat"), required=True)
    parser.add_argument("--basis", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-url", required=True)
    return parser.parse_args()


def main() -> None:
    args = _args()
    region = tuple(float(value) for value in args.region.split(","))
    if len(region) != 4:
        raise ValueError("region은 x,y,width,height 네 값이어야 합니다.")
    chart = {
        "verified": True,
        "source_ref": args.source_ref,
        "source_url": args.source_url,
        "visual_kind": "verified_fact",
        "label": args.label,
        "hero_stat": {
            "headline_value": args.value,
            "headline_unit_label": args.label,
            "direction": args.direction,
            "meaning_line": args.meaning,
            "support_marks": [],
            "comparison_basis": args.basis,
            "source_refs": [args.source_ref],
        },
    }
    scene = {
        "scene_id": args.output.stem,
        "scene_type": "metric",
        "market_chart": chart,
        "v5_render_contract": {
            "scene_type": "metric",
            "selection": {"archetype": args.archetype},
            "primary_surface_region": region,
        },
    }
    plan = plan_from_scene(scene)
    if plan is None or plan.render_mode != "DIEGETIC_WARP" or plan.surface is None:
        raise RuntimeError("V5 물리 표면 합성 계획을 만들지 못했습니다.")
    base = Image.open(args.input).convert("RGBA")
    bgr = cv2.cvtColor(np.asarray(base.convert("RGB")), cv2.COLOR_RGB2BGR)
    detection = detection_from_normalized_region(bgr, region)
    result = composite_planar(base, chart, plan, detection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.convert("RGB").save(args.output, "PNG")
    manifest = {
        "input_background": str(args.input),
        "output_image": str(args.output),
        "source_url": args.source_url,
        "source_ref": args.source_ref,
        "verified_values": {args.label: args.value, "meaning": args.meaning},
        "render_mode": plan.render_mode,
        "surface_kind": plan.surface.surface_kind,
        "primary_surface_region": region,
        "floating_card_used": False,
        "image_generation_api_calls": 0,
    }
    manifest_path = args.output.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    print(manifest_path)


if __name__ == "__main__":
    main()
