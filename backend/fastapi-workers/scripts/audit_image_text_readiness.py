#!/usr/bin/env python3
"""네트워크 없이 현재 텍스트 계약을 재현한다. 운영 정책/입력/이미지는 변경하지 않는다."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def deny_network(*args, **kwargs):
    raise RuntimeError("오프라인 준비 감사에서는 네트워크 사용을 금지합니다.")


def build_report(source_path: Path) -> dict:
    from app.utils.image_text_contract import build_scene_text_contract, visible_text_contract_result
    from app.utils.scene_screen_text_planner import attach_scene_screen_texts
    from app.services.final_frame_text_integrity import inspect_final_frame_text_integrity

    original = source_path.read_bytes()
    source = json.loads(original)
    before = json.dumps(source, ensure_ascii=False, sort_keys=True)
    planned = attach_scene_screen_texts(source)
    rows = []
    for old, scene in zip(source, planned):
        narration = str(old.get("text_for_tts") or old.get("content") or old.get("text") or old.get("narration") or "")
        current = str(scene.get("text_for_tts") or scene.get("content") or scene.get("text") or scene.get("narration") or "")
        contract = build_scene_text_contract(scene)
        rows.append({
            "source_scene_index": old["index"], "narration": narration,
            "narration_sha256_before": sha(narration.encode()), "narration_sha256_after": sha(current.encode()),
            "narration_unchanged": narration == current,
            "source_prompt_sha256": sha(str(old.get("prompt_en") or "").encode()),
            "original_screen_texts": old.get("screen_texts"),
            "derived_screen_texts": scene.get("screen_texts"),
            "current_generated_texts": contract["generated_texts"],
            "current_deterministic_texts": contract["deterministic_texts"],
            "current_surface_plan": contract["surface_plan"],
            "note": "과거 승인 내레이션 추출 재현; 새 사실 확인/표면 계획 승인/이미지 생성 아님",
        })

    routing = []
    for text, category in [("삼성전자", "회사명"), ("KOSPI", "지수명"), ("현재 전망", "정보성 라벨"),
                           ("143조 원", "수치"), ("와!", "실측 전 장식 문구")]:
        result = build_scene_text_contract({"screen_texts": [text], "screen_text_validation": {"passed": True}})
        routing.append({"text": text, "category": category, "observed_generated": result["generated_texts"],
                        "observed_deterministic": result["deterministic_texts"],
                        "wo_img01_expected_route": "deterministic", "matches_wo_img01": result["deterministic_texts"] == [text]})

    raw_ocr = []
    for expected, recognized in [("삼성전자", ["삼성전자오탈"]), ("삼성전자", ["SK 하이느"]), ("삼성전자", [])]:
        result = visible_text_contract_result(recognized, {"screen_texts": [expected]})
        raw_ocr.append({"approved": expected, "recognized_fixture": recognized, "observed": result,
                        "scope": "OCR 중간 함수만 호출; 후속 멀티모달 QA의 최종 승인 여부는 검증하지 않음"})

    final_ocr = []
    for expected, recognized, should_pass in [("4배", "14배", False), ("영업이익", "비영업이익", False),
                                             ("PER", "per", False), ("현재 전망", "현력 토공", False),
                                             ("143조 원", "143조\n원", True)]:
        scene = {"v5_render_contract": {"visual_text_policy": "deterministic_surface_text", "surface_caption": {"texts": [expected]}}}
        # 가짜 OCR 행만 주입한다. 새 이미지/실제 OCR/공급자 호출은 없고 픽셀 계보 예외도 사용하지 않는다.
        result = inspect_final_frame_text_integrity("unused-fixture.png", scene, ocr_rows=[{"text": recognized, "conf": "99"}])
        final_ocr.append({"expected": expected, "recognized_fixture": recognized, "expected_passed": should_pass,
                          "observed": result, "matches_expected": result["passed"] == should_pass})

    source_files = ["app/utils/image_text_contract.py", "app/utils/scene_screen_text_planner.py",
                    "app/services/final_frame_text_integrity.py", "app/v5/scene/runtime_contract.py",
                    "app/workers/images_worker.py", "app/utils/visual_qa.py", "app/postprocess/text_overlay.py"]
    return {
        "scope": "WO-IMG-01 오프라인 준비 상태 감사. 유료 실행 승인/완료 선언 아님",
        "source_sha256": sha(original), "source_bytes_unchanged": source_path.read_bytes() == original,
        "source_object_unchanged": json.dumps(source, ensure_ascii=False, sort_keys=True) == before,
        "source_count": len(rows), "all_narrations_unchanged": all(r["narration_unchanged"] for r in rows),
        "empty_derived_text_scene_indices": [r["source_scene_index"] for r in rows if not r["derived_screen_texts"]],
        "scenes_with_generated_strings": sum(bool(r["current_generated_texts"]) for r in rows),
        "scenes_with_deterministic_strings": sum(bool(r["current_deterministic_texts"]) for r in rows),
        "scenes_with_surface_plan": sum(bool(r["current_surface_plan"]) for r in rows),
        "routing_probes": routing, "raw_ocr_probes": raw_ocr, "final_ocr_probes": final_ocr,
        "source_files_sha256": {p: sha((ROOT / p).read_bytes()) for p in source_files},
        "scenes": rows, "paid_execution_ready": False,
        "ready_reason": "정보성/장식성 분기·정확 일치 및 장식 크기 게이트·8장 실행 명세/예산 검증 미완료",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-scenes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    socket.create_connection = deny_network
    socket.socket.connect = deny_network
    report = build_report(args.source_scenes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # 역사 증거를 우연히 덮어쓰지 않는다.
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({k: report[k] for k in ("source_count", "source_bytes_unchanged", "all_narrations_unchanged",
        "empty_derived_text_scene_indices", "scenes_with_generated_strings", "scenes_with_deterministic_strings",
        "scenes_with_surface_plan", "routing_probes", "final_ocr_probes", "paid_execution_ready")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
