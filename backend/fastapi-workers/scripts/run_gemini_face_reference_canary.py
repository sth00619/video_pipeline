#!/usr/bin/env python3
"""scene07을 기존 실패 계보에서 한 번만 재시도하는 얼굴 v2 canary 실행기."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_gemini_eight_scene_pilot import _read_prices, _sha, _write_json  # noqa: E402
from scripts.run_gemini_face_reference_pilot import prepare_rows  # noqa: E402


INCREMENTAL_RESERVED_KRW = 1600
CUMULATIVE_EXPOSURE_CAP_KRW = 6400
PRIOR_EXPOSURE_KRW = 4800
SCENE_INDEX = 7
SCENE_KEY = "face-v2:7"


def validate_canary_spec(spec: dict) -> None:
    """승인된 scene07 한 장과 중단 조건 이외의 실행을 거절한다."""
    auth = spec.get("authorization") or {}
    scene = spec.get("scene") or {}
    state = spec.get("request_state") or {}
    if spec.get("paid_execution_authorized") is not True:
        raise RuntimeError("scene07 유료 canary 승인이 명세에 없습니다.")
    if auth.get("approved_incremental_reserved_krw") != INCREMENTAL_RESERVED_KRW:
        raise RuntimeError("이번 신규 예약 상한은 ₩1,600이어야 합니다.")
    if auth.get("cumulative_ledger_exposure_cap_krw") != CUMULATIVE_EXPOSURE_CAP_KRW:
        raise RuntimeError("기존 노출을 포함한 원장 상한은 ₩6,400이어야 합니다.")
    if auth.get("on_http_failure") != "stop_without_scene02_or_scene35":
        raise RuntimeError("HTTP 실패 뒤 다른 장면 호출을 허용할 수 없습니다.")
    if auth.get("on_http_200") != "stop_and_review_face_before_scene02_or_scene35":
        raise RuntimeError("HTTP 200 뒤 얼굴 판정 전에 다른 장면을 호출할 수 없습니다.")
    if int(scene.get("index", -1)) != SCENE_INDEX or scene.get("scene_key") != SCENE_KEY:
        raise RuntimeError("canary 대상은 기존 key의 scene07 한 장이어야 합니다.")
    if state.get("scene_key") != SCENE_KEY or state.get("approved_retry_prior_count") != 1:
        raise RuntimeError("기존 scene07 실패 계보를 이어받지 못했습니다.")
    if state.get("approved_retry_failure_n") != 1 or state.get("prior_status") != "http_503":
        raise RuntimeError("승인 재시도의 직전 실패 상태가 다릅니다.")
    if spec.get("scene42_frozen_and_excluded") is not True:
        raise RuntimeError("scene42 동결 계약이 지켜지지 않았습니다.")
    if spec.get("face_reference", {}).get("name") != "channel_character_face_range_v2.png":
        raise RuntimeError("얼굴 v2 이외 참조로 canary를 실행할 수 없습니다.")
    if spec.get("model") != "gemini-3-pro-image" or spec.get("service_tier") != "standard":
        raise RuntimeError("승인 모델 또는 service tier가 다릅니다.")


def validate_prior_state(spec: dict, ledger: dict) -> dict:
    """직전 503·payload·계약·실패 카운터와 예약 노출을 정확히 대조한다."""
    state = spec["request_state"]
    prior = [
        item for item in ledger.get("items", [])
        if item.get("provider") == "gemini" and item.get("scene_key") == SCENE_KEY
    ]
    if len(prior) != state["approved_retry_prior_count"]:
        raise RuntimeError("scene07 기존 요청 수가 승인 시점과 다릅니다.")
    previous = prior[-1]
    checks = {
        "attempt_id": state["approved_retry_of"],
        "status": state["prior_status"],
        "status_code": state["prior_status_code"],
        "model": spec["model"],
        "contract_fingerprint": state["prior_contract_fingerprint"],
    }
    for key, expected in checks.items():
        if previous.get(key) != expected:
            raise RuntimeError(f"scene07 직전 원장의 {key}가 승인 계보와 다릅니다.")
    if (previous.get("request_evidence") or {}).get("payload_sha256") != state["prior_payload_sha256"]:
        raise RuntimeError("scene07 직전 payload 해시가 승인 계보와 다릅니다.")
    if (previous.get("request_control") or {}).get("failure_n") != state["approved_retry_failure_n"]:
        raise RuntimeError("scene07 직전 실패 카운터가 승인 계보와 다릅니다.")
    if int(ledger.get("reserved_exposure_krw", -1)) != PRIOR_EXPOSURE_KRW:
        raise RuntimeError("기존 ₩4,800 예약 노출을 삭제하거나 축소할 수 없습니다.")
    return previous


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--pricing-config", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    spec_bytes = args.spec.read_bytes()
    spec = json.loads(spec_bytes)
    validate_canary_spec(spec)
    output = (REPO / spec["original_output_dir"]).resolve()
    ledger_path = output / "request_ledger.json"
    state_path = output / "request_state.sqlite3"
    original_spec_path = REPO / spec["original_three_scene_spec"]["path"]
    source_path = REPO / spec["source"]["path"]
    scene42_path = REPO / spec["scene42_frozen_ledger"]["path"]

    for path, expected, label in (
        (original_spec_path, spec["original_three_scene_spec"]["sha256"], "원본 3장 명세"),
        (source_path, spec["source"]["sha256"], "Job52 보존 입력"),
        (ledger_path, spec["original_ledger_sha256_before_canary"], "3장 실패 원장"),
        (scene42_path, spec["scene42_frozen_ledger"]["sha256"], "scene42 동결 원장"),
    ):
        if not path.is_file() or _sha(path.read_bytes()) != expected:
            raise RuntimeError(f"{label} 해시가 승인 시점과 다릅니다.")
    scene42 = json.loads(scene42_path.read_text(encoding="utf-8"))
    if (scene42.get("items") or [{}])[0].get("attempt_id") != spec["scene42_frozen_ledger"]["attempt_id"]:
        raise RuntimeError("scene42 attempt ID가 바뀌었습니다.")

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    previous = validate_prior_state(spec, ledger)
    # prepare_rows가 images_worker를 가져오면서 runtime_config를 먼저 로드할 수
    # 있다. 환경변수만 늦게 바꾸지 말고, 승인된 기존 DB·scope를 준비 전에
    # 런타임에도 직접 반영해 다른 상태 저장소로 새 요청이 새는 일을 막는다.
    os.environ["GEMINI_REQUEST_STATE_PATH"] = str(state_path)
    os.environ["GEMINI_PROJECT_SCOPE"] = spec["request_state"]["project_scope"]
    from app import runtime_config
    runtime_config.update(
        gemini_scene_request_limit=2,
        gemini_request_state_path=str(state_path),
        gemini_project_scope=spec["request_state"]["project_scope"],
    )
    original_spec = json.loads(original_spec_path.read_text(encoding="utf-8"))
    original_scene = next(item for item in original_spec["scenes"] if int(item["index"]) == SCENE_INDEX)
    if original_scene != spec["scene"]:
        raise RuntimeError("scene07 시각 계약이 첫 3장 요청과 달라졌습니다.")
    source_scenes = json.loads(source_path.read_text(encoding="utf-8"))
    row = prepare_rows({**original_spec, "scenes": [original_scene]}, source_scenes)[0]
    contract_fingerprint = _sha(json.dumps(row["scene"], ensure_ascii=False, sort_keys=True).encode())
    if contract_fingerprint != spec["request_state"]["prior_contract_fingerprint"]:
        raise RuntimeError("scene07 계약 fingerprint가 직전 요청과 다릅니다.")

    preflight = {
        "version": spec["version"],
        "status": "authorized_preflight",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "spec_sha256": _sha(spec_bytes),
        "scene_index": SCENE_INDEX,
        "scene_key": SCENE_KEY,
        "incremental_reserved_cap_krw": INCREMENTAL_RESERVED_KRW,
        "prior_reserved_exposure_krw": PRIOR_EXPOSURE_KRW,
        "cumulative_ledger_exposure_cap_krw": CUMULATIVE_EXPOSURE_CAP_KRW,
        "approved_retry_of": previous["attempt_id"],
        "approved_retry_failure_n": previous["request_control"]["failure_n"],
        "prior_payload_sha256": previous["request_evidence"]["payload_sha256"],
        "contract_fingerprint": contract_fingerprint,
        "first_reference": row["references"][0],
        "scene42_frozen_and_excluded": True,
        "continuation_policy": "HTTP와 얼굴/텍스트 판정을 분리하고 어떤 결과에서도 scene02·35를 호출하지 않음",
    }
    preflight_path = output / "scene_07_canary_preflight.json"
    _write_json(preflight_path, preflight)
    if not args.execute:
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return 0
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY 미설정. 유료 canary를 시작하지 않습니다.")
    claim = output / "scene_07_canary_execute_once.claim"
    manifest_path = output / "scene_07_canary_manifest.json"
    if claim.exists() or manifest_path.exists():
        raise RuntimeError("scene07 canary는 이미 시작됐습니다. 추가 POST를 차단합니다.")
    claim.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    from app.utils.budget import ProviderRequestAudit
    from app.utils.image_request_control import ImageRequestHeld
    from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider

    _, usd_krw = _read_prices(args.pricing_config)
    audit = ProviderRequestAudit.for_path(
        path=ledger_path,
        scene_key=SCENE_KEY,
        model=GeminiModel.PRO.value,
        unit_usd=float(Decimal(INCREMENTAL_RESERVED_KRW) / usd_krw),
        usd_krw=float(usd_krw),
        budget_limit_krw=CUMULATIVE_EXPOSURE_CAP_KRW,
        request_metadata={
            "pilot_id": "wo_img01_d_face_scene07_canary_20260828",
            "run_id": "wo_img01_d_face_scene07_canary_20260828",
            "contract_fingerprint": contract_fingerprint,
            "attempt_policy": "one_approved_retry_then_stop_for_face_review",
            "face_reference_sha256": spec["face_reference"]["sha256"],
            "approved_retry_of": spec["request_state"]["approved_retry_of"],
            "approved_retry_prior_count": spec["request_state"]["approved_retry_prior_count"],
            "approved_retry_failure_n": spec["request_state"]["approved_retry_failure_n"],
        },
    )
    manifest = {**preflight, "status": "running", "started_at": datetime.now(timezone.utc).isoformat()}
    _write_json(manifest_path, manifest)
    try:
        result = GeminiProvider(use_batch=False).generate(
            row["prompt"], reference_image_paths=row["reference_paths"], request_audit=audit,
        )
        raw_path = output / "scene_07_canary_raw.png"
        raw_path.write_bytes(result.image_bytes)
        final_path = output / "scene_07_canary_final.png"
        final_path.write_bytes(result.image_bytes)
        manifest.update(
            provider_status="http_200",
            raw_path=str(raw_path),
            raw_sha256=_sha(result.image_bytes),
            face_contract_status="awaiting_manual_and_quantitative_review",
            continuation_allowed=False,
        )
        try:
            from app.services.semantic_surface_text import render_semantic_surface_text
            render_semantic_surface_text(row["scene"], str(final_path))
            manifest.update(
                status="http_200_awaiting_face_review",
                text_gate_status="deterministic_render_verified",
                final_path=str(final_path),
                final_sha256=_sha(final_path.read_bytes()),
                final_frame_text_integrity=row["scene"].get("final_frame_text_integrity"),
            )
        except Exception as exc:
            manifest.update(
                status="http_200_text_gate_needs_review",
                text_gate_status="needs_review",
                text_gate_error_type=type(exc).__name__,
            )
    except Exception as exc:
        manifest.update(
            status="provider_request_failed",
            provider_status="held" if isinstance(exc, ImageRequestHeld) else "error",
            error_type=type(exc).__name__,
            held_status=exc.status if isinstance(exc, ImageRequestHeld) else None,
            next_allowed_at=exc.next_allowed_at if isinstance(exc, ImageRequestHeld) else None,
            face_contract_status="not_evaluable_provider_failure_before_image",
            text_gate_status="not_evaluable_provider_failure_before_image",
            continuation_allowed=False,
        )
    summary = audit.summary()
    if len(summary.get("entries") or []) == 1:
        # before_attempt가 차단한 경우 POST도 예약도 없으므로 원래 오류를
        # 가리지 않고 증거를 남긴다. 이 상태는 유료 canary 소진이 아니다.
        manifest.update(
            status="predispatch_blocked_no_external_post",
            provider_status="not_dispatched",
            external_post_count=0,
            incremental_reserved_exposure_krw=0,
        )
    elif len(summary.get("entries") or []) != 2:
        manifest.update(status="ledger_lineage_mismatch", continuation_allowed=False)
        _write_json(manifest_path, manifest)
        raise RuntimeError("scene07 원장은 기존 1건과 canary 1건만 가져야 합니다.")
    else:
        manifest["external_post_count"] = 1
        manifest["incremental_reserved_exposure_krw"] = INCREMENTAL_RESERVED_KRW
    manifest["request_summary"] = summary
    latest = summary["entries"][-1]
    manifest["latest_attempt_id"] = latest.get("attempt_id")
    manifest["latest_usage_metadata"] = latest.get("usage_metadata")
    manifest["latest_usage_metadata_status"] = latest.get("usage_metadata_status")
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(manifest_path, manifest)
    print(json.dumps({
        "status": manifest["status"],
        "provider_status": manifest.get("provider_status"),
        "face_contract_status": manifest["face_contract_status"],
        "text_gate_status": manifest["text_gate_status"],
        "continuation_allowed": False,
        "latest_attempt_id": manifest["latest_attempt_id"],
        "usageMetadata": manifest["latest_usage_metadata"],
    }, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
