#!/usr/bin/env python3
"""서로 다른 세 장면에서 공통 이미지 품질 하한선을 장면당 1회로 실증한다."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
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


EXPECTED_INDICES = [7, 28, 36]
EXPECTED_SCENE_KEYS = ["quality-floor-v1:7", "quality-floor-v1:28", "quality-floor-v1:36"]
AUTHORIZED_TOTAL_KRW = 4800
RESERVED_PER_SCENE_KRW = 1600


def _canonical_sha(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_spec(spec: dict) -> None:
    """승인된 세 장면·순차 1회·실패 즉시 중단 계약 외의 실행을 차단한다."""
    auth = spec.get("authorization") or {}
    scenes = spec.get("scenes") or []
    if spec.get("paid_execution_authorized") is not True:
        raise RuntimeError("세 장면 유료 canary 승인이 명세에 없습니다.")
    if auth.get("approved_total_reserved_krw") != AUTHORIZED_TOTAL_KRW:
        raise RuntimeError("총 예약 상한은 ₩4,800이어야 합니다.")
    if auth.get("reserved_per_scene_krw") != RESERVED_PER_SCENE_KRW:
        raise RuntimeError("장면당 예약액은 ₩1,600이어야 합니다.")
    if auth.get("external_image_post_limit") != 3 or auth.get("attempts_per_scene") != 1:
        raise RuntimeError("외부 이미지 POST는 장면당 1회, 최대 3회여야 합니다.")
    if auth.get("retry_on_failure") is not False or auth.get("stop_remaining_after_provider_failure") is not True:
        raise RuntimeError("공급자 실패 시 재시도 없이 나머지를 중단해야 합니다.")
    if [int(item.get("index", -1)) for item in scenes] != EXPECTED_INDICES:
        raise RuntimeError("승인된 장면 순서는 scene07·28·36이어야 합니다.")
    if [str(item.get("scene_key") or "") for item in scenes] != EXPECTED_SCENE_KEYS:
        raise RuntimeError("세 장면의 신규 계보 키가 다릅니다.")
    if len({item.get("scene_type_group") for item in scenes}) != 3:
        raise RuntimeError("서로 다른 장면 유형 세 개가 필요합니다.")
    if spec.get("model") != "gemini-3-pro-image" or spec.get("service_tier") != "standard":
        raise RuntimeError("고정 이미지 모델 또는 service tier가 다릅니다.")
    if spec.get("scene42_frozen_and_excluded") is not True or 42 in EXPECTED_INDICES:
        raise RuntimeError("scene42 동결 계약이 지켜지지 않았습니다.")
    status = spec.get("provider_status_check") or {}
    if status.get("source") != "https://status.cloud.google.com/":
        raise RuntimeError("공식 공급자 상태 확인 기록이 없습니다.")
    if status.get("result") != "no_broad_severe_incidents_model_capacity_unverified":
        raise RuntimeError("상태 대시보드의 범위를 과장하지 않은 판정이 필요합니다.")


def prepare_rows(spec: dict, source_scenes: list[dict]) -> list[dict]:
    """승인 대본→장면 역할→공통 프롬프트→실제 참조→최종 POST 계보를 만든다."""
    from app.v5.providers.gemini_provider import (
        ensure_gemini_reference_contract,
        select_contextual_reference_paths,
    )
    from app.workers.images_worker import _bounded_text_generation_prompt

    by_index = {int(item["index"]): item for item in source_scenes}
    prepared: list[dict] = []
    for item in spec["scenes"]:
        scene = prepare_pilot_scene(by_index[int(item["index"])], item)
        # Job52 보존 자료의 오래된 art_direction은 당시 prompt_en과 의상 역할이
        # 어긋난 장면이 있다. 현재 운영 경로가 SceneDirector의 scene_spec을
        # 단일 기준으로 쓰는 것과 동일하게, 이 canary도 승인 명세를 우선한다.
        scene["scene_spec"] = copy.deepcopy(item["scene_spec_override"])
        scene["scene_key"] = item["scene_key"]
        narration = str(scene.get("content") or scene.get("text") or "")
        source_prompt = _remove_historical_unbound_commodity_prompt(
            scene["prompt_en"], narration
        )
        bounded_prompt = _bounded_text_generation_prompt(
            f"{source_prompt}\n\nSCENE MEANING CONTRACT: {item['visual_contract']}",
            audit_target=scene,
        )
        reference_paths = select_contextual_reference_paths(bounded_prompt)
        references = [
            {"name": Path(path).name, "sha256": _sha(Path(path).read_bytes())}
            for path in reference_paths
        ]
        if not references or references[0] != spec["face_reference"]:
            raise RuntimeError(f"scene {item['index']}의 첫 참조가 승인 얼굴 v2가 아닙니다.")
        final_prompt = ensure_gemini_reference_contract(
            bounded_prompt, reference_paths
        )
        quality = scene["scene_visual_quality_contract"]
        expected_ratio = 0.22 if int(item["index"]) == 7 else 0.16
        if quality["deterministic_surface"]["max_single_surface_frame_ratio"] != expected_ratio:
            raise RuntimeError(f"scene {item['index']}의 표면 예산이 다릅니다.")
        variables = quality["scene_variables"]
        override = item["scene_spec_override"]
        if variables["wardrobe"] != override["character_costume"]:
            raise RuntimeError(f"scene {item['index']}의 의상 기준이 둘로 갈라졌습니다.")
        if variables["emotion"] != override["character_emotion"]:
            raise RuntimeError(f"scene {item['index']}의 표정 기준이 둘로 갈라졌습니다.")
        if variables["action"] != override["character_action"]:
            raise RuntimeError(f"scene {item['index']}의 행동 기준이 둘로 갈라졌습니다.")
        legacy_prefix = bounded_prompt.split(" FINAL SCENE-LOCAL TEXT CONTRACT:", 1)[0]
        if re.search(
            r"\b(?:massive|giant|oversized|huge|enormous|large)\s+"
            r"(?:central\s+|wall(?:-mounted)?\s+)?(?:monitor|screen|display|board|panel)(?:\s+wall)?\b",
            legacy_prefix,
            flags=re.IGNORECASE,
        ):
            raise RuntimeError(f"scene {item['index']}에 거대 문자 표면 지시가 남았습니다.")
        if int(item["index"]) == 36 and "Silver" in bounded_prompt:
            raise RuntimeError("scene36의 조사 `은` 유래 Silver 오염이 재발했습니다.")
        prepared.append({
            "index": int(item["index"]),
            "scene_key": item["scene_key"],
            "scene_type_group": item["scene_type_group"],
            "lane": item["lane"],
            "scene": scene,
            "narration": narration,
            "narration_sha256": _sha(narration.encode("utf-8")),
            "source_prompt_sha256": _sha(source_prompt.encode("utf-8")),
            "bounded_prompt": bounded_prompt,
            "bounded_prompt_sha256": _sha(bounded_prompt.encode("utf-8")),
            "final_prompt": final_prompt,
            "final_prompt_sha256": _sha(final_prompt.encode("utf-8")),
            "scene_contract_sha256": _canonical_sha(scene),
            "references": references,
            "reference_paths": reference_paths,
            "quality_contract": quality,
            "surface_plan": scene.get("screen_text_plan") or [],
        })
    return prepared


def _public_row(row: dict) -> dict:
    hidden = {
        "scene", "narration", "bounded_prompt", "final_prompt", "reference_paths"
    }
    return {key: value for key, value in row.items() if key not in hidden}


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
    prepared = prepare_rows(spec, source_scenes)
    _, usd_krw = _read_prices(args.pricing_config)

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["GEMINI_REQUEST_STATE_PATH"] = str(output / "request_state.sqlite3")
    os.environ["GEMINI_PROJECT_SCOPE"] = f"quality-floor-{_sha(spec_bytes)[:12]}"
    for row in prepared:
        (output / f"scene_{row['index']:02d}_bounded_prompt.txt").write_text(
            row["bounded_prompt"], encoding="utf-8"
        )
        (output / f"scene_{row['index']:02d}_final_prompt.txt").write_text(
            row["final_prompt"], encoding="utf-8"
        )
    manifest = {
        "version": spec["version"],
        "status": "authorized_preflight",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "spec_sha256": _sha(spec_bytes),
        "source_sha256": _sha(source_bytes),
        "model": spec["model"],
        "service_tier": spec["service_tier"],
        "image_size": spec["image_size"],
        "authorized_total_reserved_krw": AUTHORIZED_TOTAL_KRW,
        "reserved_per_scene_krw": RESERVED_PER_SCENE_KRW,
        "attempt_policy": "sequential_one_post_each_stop_on_provider_failure",
        "reservation_interpretation": "보수적 요청 노출 상한이며 예상 비용 또는 확정 지출이 아님",
        "scene42_frozen_and_excluded": True,
        "provider_status_check": spec["provider_status_check"],
        "scenes": [_public_row(row) | {"status": "pending"} for row in prepared],
    }
    _write_json(output / "preflight.json", manifest)
    if not args.execute:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY 미설정. 유료 실행을 시작하지 않습니다.")
    claim = output / "execute_once.claim"
    ledger_path = output / "request_ledger.json"
    manifest_path = output / "manifest.json"
    if claim.exists() or ledger_path.exists() or manifest_path.exists():
        raise RuntimeError("이 canary는 이미 시작됐습니다. 중복 POST를 차단합니다.")
    claim.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    from app import runtime_config
    from app.utils.budget import ProviderRequestAudit
    from app.utils.canary_visual_review import build_canary_visual_review_packet
    from app.utils.image_request_control import ImageRequestHeld
    from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider

    runtime_config.update(gemini_scene_request_limit=1)
    manifest["status"] = "running"
    manifest["started_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(manifest_path, manifest)
    first_usage = None
    provider_failure = False
    for position, row in enumerate(prepared):
        target = manifest["scenes"][position]
        if provider_failure:
            target["status"] = "skipped_after_provider_failure"
            continue
        index = row["index"]
        print(f"[quality-floor-canary] scene {index:02d} 시작", flush=True)
        audit = ProviderRequestAudit.for_path(
            path=ledger_path,
            scene_key=row["scene_key"],
            model=GeminiModel.PRO.value,
            unit_usd=float(Decimal(RESERVED_PER_SCENE_KRW) / usd_krw),
            usd_krw=float(usd_krw),
            budget_limit_krw=AUTHORIZED_TOTAL_KRW,
            request_metadata={
                "pilot_id": output.name,
                "run_id": output.name,
                "contract_fingerprint": row["scene_contract_sha256"],
                "attempt_policy": "sequential_one_post_stop_on_provider_failure",
                "provider_status_check": spec["provider_status_check"],
            },
        )
        try:
            result = GeminiProvider(use_batch=False).generate(
                row["bounded_prompt"],
                reference_image_paths=row["reference_paths"],
                request_audit=audit,
            )
            raw_path = output / f"scene_{index:02d}_raw.png"
            raw_path.write_bytes(result.image_bytes)
            raw_sha256 = _sha(result.image_bytes)
            target.update(
                status="pending_user_visual_review",
                provider_status="http_200",
                raw_path=str(raw_path),
                raw_sha256=raw_sha256,
                approval_blocked=True,
            )
            if row["lane"] == "deterministic_information":
                preview_path = output / f"scene_{index:02d}_deterministic_preview.png"
                preview_path.write_bytes(result.image_bytes)
                try:
                    from app.services.semantic_surface_text import render_semantic_surface_text

                    render_semantic_surface_text(row["scene"], str(preview_path))
                    target.update(
                        deterministic_preview_status="rendered_not_approval",
                        deterministic_preview_path=str(preview_path),
                        deterministic_preview_sha256=_sha(preview_path.read_bytes()),
                        deterministic_preview_text_integrity=row["scene"].get("final_frame_text_integrity"),
                    )
                except Exception as exc:
                    target.update(
                        deterministic_preview_status="needs_review",
                        deterministic_preview_error_type=type(exc).__name__,
                        deterministic_preview_error=str(exc),
                    )
            else:
                measurement = _measure_generated_labels(
                    raw_path, row["scene"]["screen_texts"]
                )
                measurement_path = output / f"scene_{index:02d}_label_measurement.json"
                _write_json(measurement_path, measurement)
                target.update(
                    generated_label_measurement=measurement,
                    generated_label_measurement_path=str(measurement_path),
                )
            target["holistic_visual_review"] = build_canary_visual_review_packet(
                raw_path,
                raw_sha256,
                automated_findings={
                    "common_quality_floor": "awaiting_user_full_frame_review",
                    "text_lane": row["lane"],
                    "production_approval": "blocked_until_user_visual_review",
                },
            )
        except Exception as exc:
            provider_failure = True
            target.update(
                status="provider_request_failed",
                provider_status="held" if isinstance(exc, ImageRequestHeld) else "error",
                error_type=type(exc).__name__,
                error=str(exc),
                approval_blocked=True,
            )
        summary = audit.summary()
        target["request_summary"] = summary
        entries = summary.get("entries") or []
        if len(entries) > 1:
            raise RuntimeError(f"scene {index}의 외부 요청 원장 항목이 1개를 넘었습니다.")
        if entries:
            usage = entries[-1].get("usage_metadata")
            if first_usage is None and entries[-1].get("usage_metadata_status") == "present" and usage is not None:
                first_usage = {
                    "scene_index": index,
                    "attempt_id": entries[-1].get("attempt_id"),
                    "usageMetadata": usage,
                }
                _write_json(output / "first_success_usageMetadata.json", first_usage)
            deadline = float(
                (entries[-1].get("request_control") or {}).get("next_allowed_at") or 0
            )
            remaining = deadline - time.time()
            if remaining > 0 and position + 1 < len(prepared) and not provider_failure:
                print(f"[quality-floor-canary] 공유 냉각 {remaining:.1f}초 준수", flush=True)
                time.sleep(remaining + 0.25)
        manifest["first_success_usage_metadata"] = first_usage
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(manifest_path, manifest)
        print(f"[quality-floor-canary] scene {index:02d} 종료: {target['status']}", flush=True)

    manifest["status"] = (
        "stopped_after_provider_failure" if provider_failure else "pending_user_visual_review"
    )
    manifest["approval_blocked"] = True
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["external_image_post_count"] = sum(
        len((item.get("request_summary") or {}).get("entries") or [])
        for item in manifest["scenes"]
    )
    _write_json(manifest_path, manifest)
    print(json.dumps({
        "status": manifest["status"],
        "external_image_post_count": manifest["external_image_post_count"],
        "first_success_usage_metadata": first_usage,
        "scenes": [
            {"index": item["index"], "status": item["status"]}
            for item in manifest["scenes"]
        ],
    }, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
