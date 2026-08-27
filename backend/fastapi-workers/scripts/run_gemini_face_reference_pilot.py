#!/usr/bin/env python3
"""WO-IMG-01-D 얼굴 v2 3장 파일럿을 장면당 실제 POST 1회로 실행한다."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_gemini_eight_scene_pilot import (  # noqa: E402
    _measure_generated_labels,
    _read_prices,
    _remove_historical_unbound_commodity_prompt,
    _sha,
    _write_json,
    prepare_pilot_scene,
)


EXPECTED_INDICES = {2, 7, 35}
EXPECTED_SCENE_KEYS = {"face-v2:2", "face-v2:7", "face-v2:35"}
AUTHORIZED_TOTAL_KRW = 4800
RESERVED_PER_SCENE_KRW = 1600


def validate_spec(spec: dict) -> None:
    """사용자가 승인한 3장·1회·₩4,800 계약 이외의 실행을 차단한다."""
    authorization = spec.get("authorization") or {}
    scenes = spec.get("scenes") or []
    indices = {int(item.get("index", -1)) for item in scenes}
    scene_keys = {str(item.get("scene_key") or "") for item in scenes}
    if spec.get("paid_execution_authorized") is not True:
        raise RuntimeError("유료 실행 승인이 명세에 고정되지 않았습니다.")
    if authorization.get("approved_total_reserved_krw") != AUTHORIZED_TOTAL_KRW:
        raise RuntimeError("총 예약 상한은 ₩4,800이어야 합니다.")
    if authorization.get("reserved_per_scene_krw") != RESERVED_PER_SCENE_KRW:
        raise RuntimeError("장면당 예약액은 ₩1,600이어야 합니다.")
    if len(scenes) != 3 or indices != EXPECTED_INDICES or scene_keys != EXPECTED_SCENE_KEYS:
        raise RuntimeError("파일럿은 새 scene key를 가진 scene 02·07·35 세 장이어야 합니다.")
    if 42 in indices or spec.get("scene42_frozen_and_excluded") is not True:
        raise RuntimeError("scene42 동결 계약이 지켜지지 않았습니다.")
    if spec.get("face_reference", {}).get("name") != "channel_character_face_range_v2.png":
        raise RuntimeError("얼굴 v2 참조 이름이 다릅니다.")


def prepare_rows(spec: dict, source_scenes: list[dict]) -> list[dict]:
    """기존 텍스트 게이트를 유지한 채 얼굴 v2 참조가 첫 입력인지 검증한다."""
    from app.v5.providers.gemini_provider import select_contextual_reference_paths
    from app.workers.images_worker import _bounded_text_generation_prompt

    by_index = {int(item["index"]): item for item in source_scenes}
    expected_face_sha256 = spec["face_reference"]["sha256"]
    prepared = []
    for item in spec["scenes"]:
        scene = prepare_pilot_scene(by_index[int(item["index"])], item)
        narration = str(scene.get("content") or scene.get("text") or "")
        source_prompt = _remove_historical_unbound_commodity_prompt(scene["prompt_en"], narration)
        prompt = _bounded_text_generation_prompt(
            f"{source_prompt}\n\nSCENE MEANING CONTRACT: {item['visual_contract']}",
            audit_target=scene,
        )
        references = select_contextual_reference_paths(prompt)
        reference_rows = [
            {"name": Path(path).name, "sha256": _sha(Path(path).read_bytes())}
            for path in references
        ]
        if not reference_rows or reference_rows[0] != {
            "name": spec["face_reference"]["name"], "sha256": expected_face_sha256,
        }:
            raise RuntimeError(f"scene {item['index']}의 첫 참조가 승인 얼굴 v2가 아닙니다.")
        if any(row["name"] == "channel_character_face_range_v1.png" for row in reference_rows):
            raise RuntimeError("롤백용 v1이 실제 요청 참조에 다시 포함됐습니다.")
        prepared.append({
            "index": int(item["index"]), "scene_key": item["scene_key"],
            "lane": item["lane"], "scene": scene, "prompt": prompt,
            "prompt_sha256": _sha(prompt.encode()),
            "narration_sha256": scene["screen_text_validation"]["narration_sha256"],
            "references": reference_rows, "reference_paths": references,
        })
    return prepared


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--pricing-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    spec_bytes = args.spec.read_bytes()
    spec = json.loads(spec_bytes)
    validate_spec(spec)
    source_path = REPO / spec["source"]["path"]
    source_bytes = source_path.read_bytes()
    if _sha(source_bytes) != spec["source"]["sha256"]:
        raise RuntimeError("Job52 보존 입력 해시가 바뀌었습니다.")
    source_scenes = json.loads(source_bytes)
    _, usd_krw = _read_prices(args.pricing_config)

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["GEMINI_REQUEST_STATE_PATH"] = str(output / "request_state.sqlite3")
    os.environ["GEMINI_PROJECT_SCOPE"] = f"wo-img01-d-{_sha(spec_bytes)[:12]}"

    from app import runtime_config
    from app.utils.budget import ProviderRequestAudit
    from app.utils.image_request_control import ImageRequestHeld
    from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider

    runtime_config.update(gemini_scene_request_limit=1)
    prepared = prepare_rows(spec, source_scenes)
    manifest_path = output / "pilot_manifest.json"
    manifest = {
        "version": spec["version"], "status": "preflight_only",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "spec_sha256": _sha(spec_bytes), "source_sha256": _sha(source_bytes),
        "model": GeminiModel.PRO.value, "service_tier": spec["service_tier"],
        "image_size": spec["image_size"],
        "authorized_total_reserved_krw": AUTHORIZED_TOTAL_KRW,
        "reserved_per_scene_krw": RESERVED_PER_SCENE_KRW,
        "attempt_policy": "one_external_post_per_scene_no_retry",
        "reservation_interpretation": "보수적 요청 예약 상한이며 예상 비용 또는 확정 지출이 아님",
        "actual_paid_calls_other_providers": 0, "scene42_frozen_and_excluded": True,
        "scenes": [
            {key: value for key, value in row.items() if key not in {"scene", "prompt", "reference_paths"}}
            | {"status": "pending"}
            for row in prepared
        ],
    }
    if not args.execute:
        _write_json(output / "preflight.json", manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY 미설정. 유료 실행을 시작하지 않습니다.")
    claim = output / "execute_once.claim"
    if claim.exists() or (output / "request_ledger.json").exists():
        raise RuntimeError("이 파일럿은 이미 실행됐거나 시작됐습니다. 추가 POST를 차단합니다.")
    claim.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    manifest["status"] = "running"
    _write_json(manifest_path, manifest)

    first_usage = None
    for position, row in enumerate(prepared):
        scene_result = manifest["scenes"][position]
        index = row["index"]
        print(f"[face-v2-pilot] scene {index:02d} 시작", flush=True)
        audit = ProviderRequestAudit.for_path(
            path=output / "request_ledger.json", scene_key=row["scene_key"],
            model=GeminiModel.PRO.value, unit_usd=float(Decimal(RESERVED_PER_SCENE_KRW) / usd_krw),
            usd_krw=float(usd_krw), budget_limit_krw=AUTHORIZED_TOTAL_KRW,
            request_metadata={
                "pilot_id": output.name, "run_id": output.name,
                "contract_fingerprint": _sha(json.dumps(row["scene"], ensure_ascii=False, sort_keys=True).encode()),
                "attempt_policy": "one_external_post_no_retry",
                "face_reference_sha256": spec["face_reference"]["sha256"],
            },
        )
        try:
            result = GeminiProvider(use_batch=False).generate(
                row["prompt"], reference_image_paths=row["reference_paths"], request_audit=audit,
            )
            raw_path = output / f"scene_{index:02d}_raw.png"
            raw_path.write_bytes(result.image_bytes)
            scene_result.update(status="generated", raw_path=str(raw_path), raw_sha256=_sha(result.image_bytes))
            if row["lane"] == "deterministic_information":
                from app.services.semantic_surface_text import render_semantic_surface_text
                final_path = output / f"scene_{index:02d}_final.png"
                final_path.write_bytes(result.image_bytes)
                try:
                    render_semantic_surface_text(row["scene"], str(final_path))
                    scene_result.update(
                        status="deterministic_render_verified", final_path=str(final_path),
                        final_sha256=_sha(final_path.read_bytes()),
                        surface_binding=row["scene"].get("surface_bindings"),
                        final_frame_text_integrity=row["scene"].get("final_frame_text_integrity"),
                    )
                except Exception as render_error:
                    scene_result.update(
                        status="needs_review_deterministic_surface",
                        deterministic_error_type=type(render_error).__name__,
                    )
            else:
                measurement = _measure_generated_labels(raw_path, row["scene"]["screen_texts"])
                measurement_path = output / f"scene_{index:02d}_label_measurement.json"
                _write_json(measurement_path, measurement)
                scene_result.update(
                    status="generated_label_measured", measurement_path=str(measurement_path),
                    generated_label_measurement=measurement,
                )
        except Exception as exc:
            scene_result.update(
                status="needs_review_request_failed", error_type=type(exc).__name__,
                held_status=exc.status if isinstance(exc, ImageRequestHeld) else None,
                next_allowed_at=exc.next_allowed_at if isinstance(exc, ImageRequestHeld) else None,
            )
        summary = audit.summary()
        scene_result["request_summary"] = summary
        entries = summary.get("entries") or []
        if len(entries) > 1:
            raise RuntimeError(f"scene {index}에서 외부 요청 원장 항목이 1개를 넘었습니다.")
        if entries:
            usage = entries[-1].get("usage_metadata")
            if first_usage is None and entries[-1].get("usage_metadata_status") == "present" and usage is not None:
                first_usage = {"scene_index": index, "attempt_id": entries[-1].get("attempt_id"), "usageMetadata": usage}
                _write_json(output / "first_success_usageMetadata.json", first_usage)
            deadline = float((entries[-1].get("request_control") or {}).get("next_allowed_at") or 0)
            remaining = deadline - time.time()
            if remaining > 0 and position + 1 < len(prepared):
                print(f"[face-v2-pilot] 공유 냉각 {remaining:.1f}초 준수", flush=True)
                time.sleep(remaining + .25)
        manifest["first_success_usage_metadata"] = first_usage
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(manifest_path, manifest)
        print(f"[face-v2-pilot] scene {index:02d} 종료: {scene_result['status']}", flush=True)

    manifest["status"] = "completed_with_review" if any(
        str(item["status"]).startswith("needs_review") for item in manifest["scenes"]
    ) else "completed"
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(manifest_path, manifest)
    print(json.dumps({
        "status": manifest["status"], "output_dir": str(output),
        "first_success_usage_metadata": first_usage,
        "scenes": [{"index": item["index"], "status": item["status"]} for item in manifest["scenes"]],
    }, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
