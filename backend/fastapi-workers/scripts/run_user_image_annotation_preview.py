#!/usr/bin/env python3
"""사용자 제공 스크린샷에 검증자가 지정한 좌표 강조만 합성하는 시안 도구.

브라우저·OCR·AI를 호출하지 않는다. 좌표는 검증 단계에서 사람이 확정한
정규화 좌표여야 하며, 이 도구는 그 좌표가 화면 크기와 무관하게 정확히
렌더되는지만 확인한다. 운영 업로드 API를 대신하지 않는 로컬 검증 도구다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models.article_evidence import EvidenceAnnotation, NormalizedBBox
from app.services.annotate import render_annotations


def _bbox(value: str) -> NormalizedBBox:
    try:
        parts = [float(item.strip()) for item in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("좌표는 x,y,width,height 형식의 숫자여야 합니다.") from exc
    try:
        return NormalizedBBox.from_list(parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="사용자 스크린샷 결정론적 강조 시안")
    parser.add_argument("--image", type=Path, required=True, help="사용자가 제공한 원본 이미지 경로")
    parser.add_argument("--bbox", type=_bbox, required=True, help="검증자가 확정한 x,y,width,height 정규화 좌표")
    parser.add_argument("--label", required=True, help="감사 로그용 대상 설명이며 이미지에 새 텍스트를 그리지 않습니다.")
    parser.add_argument("--out", type=Path, required=True, help="출력 PNG 및 감사 JSON 경로의 상위 폴더")
    args = parser.parse_args()

    if not args.image.is_file():
        raise SystemExit(f"원본 이미지를 찾을 수 없습니다: {args.image}")

    base = Image.open(args.image).convert("RGBA")
    annotations = [
        EvidenceAnnotation(type="highlighter", bbox=args.bbox, color="#FFE146"),
        EvidenceAnnotation(type="underline", bbox=args.bbox, color="#E60023", stroke_width=8),
        EvidenceAnnotation(type="ellipse", bbox=args.bbox, color="#E60023", stroke_width=6),
    ]
    result = Image.alpha_composite(base, render_annotations(base.size, annotations))
    args.out.mkdir(parents=True, exist_ok=True)
    output_path = args.out / f"{args.image.stem}_annotated.png"
    result.save(output_path)
    report_path = output_path.with_suffix(".json")
    report_path.write_text(json.dumps({
        "status": "preview_only",
        "source_image": str(args.image),
        "source_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        "source_size": {"width": base.width, "height": base.height},
        "target_label": args.label,
        "target_bbox": args.bbox.model_dump(),
        "coordinate_source": "pilot_human_demo_not_verified_fact",
        "annotations": [item.model_dump(mode="json") for item in annotations],
        "output_image": str(output_path),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_image": str(output_path), "report": str(report_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
