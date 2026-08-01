#!/usr/bin/env python3
"""업로드 기사 캡처 엔드포인트를 로컬 HTTP 요청으로 한 번 검증한다.

이 스크립트의 좌표는 이미 DOM 캡처로 검증된 연합뉴스 코스피 문장의 좌표를
재사용한다. OCR이나 모델은 호출하지 않으며, 실제 기사 사실은 새로 만들지 않는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import main
from app.services import evidence_capture
from app.services.evidence_capture import EvidenceCaptureService


SOURCE_IMAGE = ROOT / "out" / "article_capture_pilot_v4" / "jobs" / "20260802" / "evidence" / "article_d557e25890a6480c.png"
OUT = ROOT / "out" / "article_capture_upload_endpoint_pilot"


def main_entry() -> int:
    if not SOURCE_IMAGE.is_file():
        raise SystemExit(f"테스트 입력 이미지를 찾을 수 없습니다: {SOURCE_IMAGE}")
    OUT.mkdir(parents=True, exist_ok=True)
    # 이 실증은 MinIO가 아니라 로컬 증거 파일과 HTTP 입력 계약을 검증한다.
    evidence_capture.DATA_DIR = OUT
    EvidenceCaptureService._upload_minio = staticmethod(lambda *_: None)
    main.evidence_capture_service = None

    quote_boxes = [
        {"x": 0.1522491349480969, "y": 0.40200293624161076, "width": 0.695393598615917, "height": 0.07046979865771812},
        {"x": 0.1522491349480969, "y": 0.49260696308724833, "width": 0.1882136678200692, "height": 0.07046979865771812},
    ]
    with SOURCE_IMAGE.open("rb") as image_file, TestClient(main.app) as client:
        response = client.post(
            "/workers/evidence/capture-upload",
            files={"image": ("yonhap_kospi_capture.png", image_file, "image/png")},
            data={
                "job_id": "20260802",
                "source_url": "https://www.yna.co.kr/view/AKR20260723141400008",
                "source_title": "코스피 5거래일 만에 7천피 회복",
                "publisher": "연합뉴스",
                "published_at": "2026-07-23T15:36:05+09:00",
                "quote": "한국거래소에 따르면 이날 코스피는 전장보다 299.19포인트(4.40%) 오른 7,096.89로 마쳤다.",
                "target_bbox_json": json.dumps({"x": 0.1522491349480969, "y": 0.40200293624161076, "width": 0.695393598615917, "height": 0.1610738255033557}),
                "quote_bboxes_json": json.dumps(quote_boxes),
                "key_phrase": "7,096.89",
                "key_phrase_bboxes_json": json.dumps([quote_boxes[1] | {"width": 0.09282006920415226}]),
            },
        )
    if response.status_code != 200:
        raise SystemExit(f"업로드 엔드포인트 실패: {response.status_code} {response.text}")
    result = response.json()
    result_path = OUT / "endpoint_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "passed",
        "capture_mode": result["capture_mode"],
        "bbox_source": result["bbox_source"],
        "original": result["local_path"],
        "annotation_preview": result["annotation_preview_path"],
        "result": str(result_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
