#!/usr/bin/env python3
"""공개 기사 한 건의 DOM 캡처와 결정론적 강조를 실증한다.

기사 URL과 원문 인용구는 호출자가 제공한다. 이 스크립트는 수치나
인용구를 생성하지 않으며, 로그인·구독·paywall 우회를 시도하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models.article_evidence import ArticleSource, EvidenceAnnotation, EvidenceCaptureRequest
from app.services import evidence_capture
from app.services.annotate import render_annotations
from app.services.evidence_capture import EvidenceCaptureService


def main() -> int:
    parser = argparse.ArgumentParser(description="공개 기사 DOM 캡처 Playwright 실증")
    parser.add_argument("--url", required=True, help="허용된 공개 기사 URL")
    parser.add_argument("--quote", required=True, help="기사 DOM에 그대로 존재하는 원문 인용구")
    parser.add_argument("--key-phrase", default="", help="선택: 별도 강조할 원문 구절")
    parser.add_argument("--publisher", required=True, help="검토된 기사 발행사명")
    parser.add_argument("--job-id", type=int, default=20260801)
    parser.add_argument("--out", type=Path, default=ROOT / "out" / "article_capture_pilot")
    args = parser.parse_args()

    # 파일 시스템 산출물만 검증한다. 운영 저장소 업로드는 이 파일럿의 범위가 아니다.
    evidence_capture.DATA_DIR = args.out
    EvidenceCaptureService._upload_minio = staticmethod(lambda *_: None)

    request = EvidenceCaptureRequest(
        job_id=args.job_id,
        source_url=args.url,
        quote=args.quote,
        key_phrase=args.key_phrase or None,
        publisher=args.publisher,
        source=ArticleSource(url=args.url, publisher=args.publisher),
    )
    service = EvidenceCaptureService()
    try:
        capture = service.capture_dom(request)
    finally:
        EvidenceCaptureService.shutdown()

    source_path = Path(str(capture.local_path))
    base = Image.open(source_path).convert("RGBA")
    annotations = [
        EvidenceAnnotation(type="highlighter", bbox=box, color="#FFE146")
        for box in capture.quote_bboxes
    ] + [
        EvidenceAnnotation(type="underline", bboxes=capture.quote_bboxes, color="#E60023", stroke_width=8)
    ]
    if capture.key_phrase_bboxes:
        annotations.extend(
            EvidenceAnnotation(type="ellipse", bbox=box, color="#E60023", stroke_width=6)
            for box in capture.key_phrase_bboxes
        )
    overlay = render_annotations(base.size, annotations)
    emphasized = Image.alpha_composite(base, overlay)
    emphasized_path = source_path.with_name(source_path.stem + "_emphasized.png")
    emphasized.save(emphasized_path)

    report = {
        "status": "passed",
        "capture_mode": capture.capture_mode,
        "source_url": capture.source_url,
        "publisher": capture.publisher,
        "capture_png": str(source_path),
        "emphasized_png": str(emphasized_path),
        "image_sha256": capture.image_sha256,
        "bbox_source": capture.bbox_source,
        "quote_bbox_count": len(capture.quote_bboxes),
        "key_phrase_bbox_count": len(capture.key_phrase_bboxes),
        "annotations": [item.model_dump(mode="json") for item in annotations],
        "storage": "local_artifact_only",
    }
    report_path = source_path.with_name(source_path.stem + "_pilot_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
