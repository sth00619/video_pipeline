#!/usr/bin/env python3
"""문자 프롬프트 연쇄 훼손 수정 뒤 scene07 한 장만 새 계보로 검증한다."""
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


SCENE_INDEX = 7
SCENE_KEY = "face-v2-promptfix:7"
INCREMENTAL_RESERVED_KRW = 1600
PRIOR_LEDGER_EXPOSURE_KRW = 8000
CUMULATIVE_EXPOSURE_CAP_KRW = 9600


def validate_spec(spec: dict) -> None:
    """사용자의 상시 허가와 한 장·한 번·누적 예산 계약만 허용한다."""
    auth = spec.get("authorization") or {}
    scene = spec.get("scene") or {}
    status = spec.get("provider_status_check") or {}
    if spec.get("paid_execution_authorized") is not True or auth.get("standing_authorization") is not True:
        raise RuntimeError("Gemini 이미지 재도전 상시 허가가 없습니다.")
    if auth.get("incremental_reserved_krw") != INCREMENTAL_RESERVED_KRW:
        raise RuntimeError("신규 canary 예약액은 ₩1,600이어야 합니다.")
    if auth.get("prior_ledger_exposure_krw") != PRIOR_LEDGER_EXPOSURE_KRW:
        raise RuntimeError("기존 예약 노출 ₩8,000을 보존해야 합니다.")
    if auth.get("cumulative_exposure_cap_krw") != CUMULATIVE_EXPOSURE_CAP_KRW:
        raise RuntimeError("누적 예약 노출 상한은 ₩9,600이어야 합니다.")
    if auth.get("external_post_limit") != 1 or auth.get("continuation") != "stop_after_one_for_review":
        raise RuntimeError("scene07 한 장을 한 번 호출한 뒤 반드시 멈춰야 합니다.")
    if int(scene.get("index", -1)) != SCENE_INDEX or scene.get("scene_key") != SCENE_KEY:
        raise RuntimeError("새 canary는 scene07 promptfix 계보만 허용합니다.")
    if spec.get("model") != "gemini-3-pro-image" or spec.get("service_tier") != "standard":
        raise RuntimeError("고정 모델 또는 service tier가 다릅니다.")
    if spec.get("scene42_frozen_and_excluded") is not True:
        raise RuntimeError("scene42 동결 계약이 없습니다.")
    if status.get("source") != "https://status.cloud.google.com/":
        raise RuntimeError("공식 공급자 상태 확인이 없습니다.")
    if status.get("result") != "no_broad_severe_incidents_model_capacity_unverified":
        raise RuntimeError("상태판의 범위를 과장하지 않은 판정이 필요합니다.")


def prepare_row(spec: dict, *, verify_expected_hash: bool = True) -> dict:
    """Job52 보존 장면에서 현재 코드가 만드는 새 payload 입력을 재구성한다."""
    # 실행 시 GEMINI_REQUEST_STATE_PATH가 먼저 정해진 뒤에만 이미지 worker를
    # 불러와야 runtime_config가 다른 상태 DB 경로로 조기에 고정되지 않는다.
    from scripts.run_gemini_face_reference_pilot import prepare_rows

    source_path = REPO / spec["source"]["path"]
    original_spec_path = REPO / spec["original_three_scene_spec"]["path"]
    source_scenes = json.loads(source_path.read_text(encoding="utf-8"))
    original_spec = json.loads(original_spec_path.read_text(encoding="utf-8"))
    original_scene = next(item for item in original_spec["scenes"] if int(item["index"]) == SCENE_INDEX)
    scene = {**original_scene, "scene_key": SCENE_KEY}
    row = prepare_rows({**original_spec, "scenes": [scene]}, source_scenes)[0]
    prompt = row["prompt"]
    for forbidden in ("shapesinguistic", "bold digits", "Samsung Electronics", "SK Hynix"):
        if forbidden in prompt:
            raise RuntimeError(f"수정된 프롬프트에 금지 잔여물이 있습니다: {forbidden}")
    if "Two unlettered containers" not in prompt:
        raise RuntimeError("두 제외 기업을 뜻하는 소품 수량이 보존되지 않았습니다.")
    if verify_expected_hash and row["prompt_sha256"] != spec["expected_prompt_sha256"]:
        raise RuntimeError("검증한 새 프롬프트 해시와 현재 코드 출력이 다릅니다.")
    return row


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
    immutable = (
        (REPO / spec["source"]["path"], spec["source"]["sha256"], "Job52 보존 입력"),
        (REPO / spec["original_three_scene_spec"]["path"], spec["original_three_scene_spec"]["sha256"], "원본 3장 명세"),
        (REPO / spec["prior_ledger"]["path"], spec["prior_ledger"]["sha256"], "기존 scene07 원장"),
        (REPO / spec["scene42_frozen_ledger"]["path"], spec["scene42_frozen_ledger"]["sha256"], "scene42 동결 원장"),
    )
    for path, expected, label in immutable:
        if not path.is_file() or _sha(path.read_bytes()) != expected:
            raise RuntimeError(f"{label} 해시가 실행 명세와 다릅니다.")
    prior = json.loads((REPO / spec["prior_ledger"]["path"]).read_text(encoding="utf-8"))
    if int(prior.get("reserved_exposure_krw", -1)) != PRIOR_LEDGER_EXPOSURE_KRW:
        raise RuntimeError("기존 원장의 예약 노출 합계가 다릅니다.")
    if (prior.get("items") or [{}])[-1].get("attempt_id") != spec["prior_ledger"]["latest_attempt_id"]:
        raise RuntimeError("직전 scene07 성공 attempt 계보가 다릅니다.")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["GEMINI_REQUEST_STATE_PATH"] = str(output / "request_state.sqlite3")
    os.environ["GEMINI_PROJECT_SCOPE"] = f"wo-scene07-promptfix-{_sha(spec_bytes)[:12]}"
    row = prepare_row(spec)
    # 가격 계약도 execute claim보다 먼저 검증해 로컬 경로 오류를 유료 호출
    # 시도로 오인하거나 재실행을 막는 빈 claim으로 남기지 않는다.
    _, usd_krw = _read_prices(args.pricing_config)
    preflight = {
        "version": spec["version"],
        "status": "authorized_preflight",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "spec_sha256": _sha(spec_bytes),
        "scene_index": SCENE_INDEX,
        "scene_key": SCENE_KEY,
        "prompt_sha256": row["prompt_sha256"],
        "references": row["references"],
        "provider_status_check": spec["provider_status_check"],
        "incremental_reserved_krw": INCREMENTAL_RESERVED_KRW,
        "prior_ledger_exposure_krw": PRIOR_LEDGER_EXPOSURE_KRW,
        "cumulative_exposure_cap_krw": CUMULATIVE_EXPOSURE_CAP_KRW,
        "scene42_frozen_and_excluded": True,
        "continuation_allowed": False,
    }
    _write_json(output / "preflight.json", preflight)
    if not args.execute:
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return 0
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY 미설정. 유료 호출을 시작하지 않습니다.")
    claim = output / "execute_once.claim"
    ledger_path = output / "request_ledger.json"
    manifest_path = output / "manifest.json"
    if claim.exists() or ledger_path.exists() or manifest_path.exists():
        raise RuntimeError("promptfix canary는 이미 시작됐습니다. 중복 POST를 차단합니다.")
    claim.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    from app import runtime_config
    from app.utils.budget import ProviderRequestAudit
    from app.utils.canary_visual_review import build_canary_visual_review_packet
    from app.utils.image_request_control import ImageRequestHeld
    from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider

    runtime_config.update(gemini_scene_request_limit=1)
    contract_fingerprint = _sha(json.dumps(row["scene"], ensure_ascii=False, sort_keys=True).encode())
    audit = ProviderRequestAudit.for_path(
        path=ledger_path,
        scene_key=SCENE_KEY,
        model=GeminiModel.PRO.value,
        unit_usd=float(Decimal(INCREMENTAL_RESERVED_KRW) / usd_krw),
        usd_krw=float(usd_krw),
        budget_limit_krw=INCREMENTAL_RESERVED_KRW,
        request_metadata={
            "pilot_id": output.name,
            "run_id": output.name,
            "contract_fingerprint": contract_fingerprint,
            "attempt_policy": "one_standing_authorized_promptfix_canary_then_stop",
            "prior_ledger_sha256": spec["prior_ledger"]["sha256"],
            "prior_attempt_id": spec["prior_ledger"]["latest_attempt_id"],
            "prior_ledger_exposure_krw": PRIOR_LEDGER_EXPOSURE_KRW,
            "cumulative_exposure_cap_krw": CUMULATIVE_EXPOSURE_CAP_KRW,
            "provider_status_check": spec["provider_status_check"],
            "standing_authorization_basis": spec["authorization"]["basis"],
        },
    )
    manifest = {**preflight, "status": "running", "started_at": datetime.now(timezone.utc).isoformat()}
    _write_json(manifest_path, manifest)
    try:
        result = GeminiProvider(use_batch=False).generate(
            row["prompt"], reference_image_paths=row["reference_paths"], request_audit=audit,
        )
        raw_path = output / "scene_07_raw.png"
        final_path = output / "scene_07_final.png"
        raw_path.write_bytes(result.image_bytes)
        final_path.write_bytes(result.image_bytes)
        raw_sha256 = _sha(result.image_bytes)
        visual_review = build_canary_visual_review_packet(
            raw_path,
            raw_sha256,
            automated_findings={
                "face_contract": "awaiting_quantitative_review",
                "text_gate": "awaiting_deterministic_render",
                "production_holistic_visual_qa": "not_executed_by_canary_user_review_required",
            },
        )
        manifest.update(
            status="pending_user_visual_review",
            provider_status="http_200",
            raw_path=str(raw_path),
            raw_sha256=raw_sha256,
            final_path=str(final_path),
            face_contract_status="awaiting_manual_and_quantitative_review",
            holistic_visual_review=visual_review,
            approval_blocked=True,
            continuation_allowed=False,
        )
        try:
            from app.services.semantic_surface_text import render_semantic_surface_text
            render_semantic_surface_text(row["scene"], str(final_path))
            manifest.update(
                text_gate_status="deterministic_render_verified",
                final_sha256=_sha(final_path.read_bytes()),
                final_frame_text_integrity=row["scene"].get("final_frame_text_integrity"),
            )
        except Exception as exc:
            manifest.update(
                automated_quality_status="http_200_text_gate_needs_review",
                text_gate_status="needs_review",
                text_gate_error_type=type(exc).__name__,
                text_gate_error=str(exc),
            )
    except Exception as exc:
        manifest.update(
            status="provider_request_failed",
            provider_status="held" if isinstance(exc, ImageRequestHeld) else "error",
            error_type=type(exc).__name__,
            error=str(exc),
            continuation_allowed=False,
        )
    summary = audit.summary()
    entries = summary.get("entries") or []
    if len(entries) != 1:
        raise RuntimeError("새 canary 외부 요청 원장은 정확히 한 건이어야 합니다.")
    latest = entries[0]
    manifest.update(
        request_summary=summary,
        external_post_count=1,
        latest_attempt_id=latest.get("attempt_id"),
        latest_usage_metadata=latest.get("usage_metadata"),
        latest_usage_metadata_status=latest.get("usage_metadata_status"),
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    _write_json(manifest_path, manifest)
    print(json.dumps({
        "status": manifest["status"],
        "provider_status": manifest.get("provider_status"),
        "external_post_count": 1,
        "latest_attempt_id": manifest.get("latest_attempt_id"),
        "latest_usage_metadata": manifest.get("latest_usage_metadata"),
        "text_gate_error": manifest.get("text_gate_error"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
