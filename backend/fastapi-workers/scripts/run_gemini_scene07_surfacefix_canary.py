#!/usr/bin/env python3
"""최근 두 수정만 격리한 scene07 Gemini canary를 외부 POST 한 번으로 실행한다."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_gemini_eight_scene_pilot import _read_prices, _sha, _write_json  # noqa: E402


SCENE_INDEX = 7
SCENE_KEY = "wo-img01-g-surfacefix:7"
INCREMENTAL_RESERVED_KRW = 1600
PRIOR_LEDGER_EXPOSURE_KRW = 9600
CUMULATIVE_EXPOSURE_CAP_KRW = 11200


def _canonical_sha(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_spec(spec: dict) -> None:
    """한 장·한 번·변수 격리·사용자 육안 보류 계약 이외의 실행을 막는다."""
    auth = spec.get("authorization") or {}
    scene = spec.get("scene") or {}
    isolation = spec.get("causal_isolation") or {}
    status = spec.get("provider_status_check") or {}
    if spec.get("paid_execution_authorized") is not True or auth.get("standing_authorization") is not True:
        raise RuntimeError("Gemini 이미지 재도전 상시 허가가 없습니다.")
    if auth.get("incremental_reserved_krw") != INCREMENTAL_RESERVED_KRW:
        raise RuntimeError("신규 canary 예약액은 ₩1,600이어야 합니다.")
    if auth.get("prior_ledger_exposure_krw") != PRIOR_LEDGER_EXPOSURE_KRW:
        raise RuntimeError(f"기존 예약 노출 ₩{PRIOR_LEDGER_EXPOSURE_KRW:,}을 보존해야 합니다.")
    if auth.get("cumulative_exposure_cap_krw") != CUMULATIVE_EXPOSURE_CAP_KRW:
        raise RuntimeError(f"누적 예약 노출 상한은 ₩{CUMULATIVE_EXPOSURE_CAP_KRW:,}이어야 합니다.")
    if auth.get("external_post_limit") != 1:
        raise RuntimeError("외부 POST는 정확히 한 번이어야 합니다.")
    if auth.get("continuation") != "stop_after_one_for_user_visual_review":
        raise RuntimeError("한 장 뒤 사용자 육안 검토 전 중단 계약이 필요합니다.")
    if int(scene.get("index", -1)) != SCENE_INDEX or scene.get("scene_key") != SCENE_KEY:
        raise RuntimeError("scene07 신규 격리 계보만 허용합니다.")
    if spec.get("model") != "gemini-3-pro-image" or spec.get("service_tier") != "standard":
        raise RuntimeError("고정 모델 또는 service tier가 다릅니다.")
    if spec.get("scene42_frozen_and_excluded") is not True:
        raise RuntimeError("scene42 동결 계약이 없습니다.")
    if isolation.get("semantic_object_surface_binding_change_forbidden") is not True:
        raise RuntimeError("의미 표면 바인딩을 이번 변수에서 제외해야 합니다.")
    if isolation.get("expected_single_surface_id") != "main":
        raise RuntimeError("기존 단일 main 표면 계획을 그대로 보존해야 합니다.")
    if status.get("source") != "https://status.cloud.google.com/":
        raise RuntimeError("공식 공급자 상태 확인이 없습니다.")
    if status.get("result") != "no_broad_severe_incidents_model_capacity_unverified":
        raise RuntimeError("상태판의 범위를 과장하지 않은 판정이 필요합니다.")


def prepare_row(spec: dict) -> dict:
    """현재 공통 코드로 scene07 입력을 만들고 두 변경 외의 드리프트를 차단한다."""
    from app.v5.providers.gemini_provider import ensure_gemini_reference_contract
    from scripts.run_gemini_face_reference_pilot import prepare_rows

    source_path = REPO / spec["source"]["path"]
    original_spec_path = REPO / spec["original_three_scene_spec"]["path"]
    source_scenes = json.loads(source_path.read_text(encoding="utf-8"))
    original_spec = json.loads(original_spec_path.read_text(encoding="utf-8"))
    original_scene = next(
        item for item in original_spec["scenes"] if int(item["index"]) == SCENE_INDEX
    )
    scene = {**original_scene, "scene_key": SCENE_KEY}
    row = prepare_rows({**original_spec, "scenes": [scene]}, source_scenes)[0]
    row["scene_key"] = SCENE_KEY
    row["scene"]["scene_key"] = SCENE_KEY

    if row["prompt_sha256"] != spec["expected_prompt_sha256"]:
        raise RuntimeError("검증한 bounded 프롬프트 해시와 현재 코드 출력이 다릅니다.")
    final_prompt = ensure_gemini_reference_contract(row["prompt"], row["reference_paths"])
    if _sha(final_prompt.encode("utf-8")) != spec["expected_final_prompt_sha256"]:
        raise RuntimeError("실제 POST 직전 프롬프트 해시가 다릅니다.")
    if row["references"] != spec["expected_references"]:
        raise RuntimeError("실제 참조 선택 또는 참조 픽셀이 검증 상태와 다릅니다.")
    if _canonical_sha(row["scene"]["screen_text_plan"]) != spec["expected_surface_plan_sha256"]:
        raise RuntimeError("의도적으로 보존한 기존 표면 계획이 바뀌었습니다.")
    if _canonical_sha(row["scene"]) != spec["expected_scene_contract_sha256"]:
        raise RuntimeError("scene07 전체 입력 계약이 검증 상태와 다릅니다.")
    if {item.get("surface") for item in row["scene"]["screen_text_plan"]} != {"main"}:
        raise RuntimeError("이번 canary에서 의미 표면 바인딩을 변경하면 안 됩니다.")
    if [item.get("text") for item in row["scene"]["screen_text_plan"]] != [
        "삼성전자", "SK하이닉스", "코스피", "143조 원"
    ]:
        raise RuntimeError("보존 대상 정보 문자열이 바뀌었습니다.")
    if "calm uniform interior" not in row["prompt"]:
        raise RuntimeError("결정론 표면 충돌 제거 문구가 없습니다.")
    if "non-linguistic shapes" in row["prompt"]:
        raise RuntimeError("결정론 표면에 도형을 요구하던 충돌 문구가 남았습니다.")
    if "Two unlettered containers" not in row["prompt"]:
        raise RuntimeError("두 제외 기업을 뜻하는 소품 수량이 보존되지 않았습니다.")
    row["final_prompt"] = final_prompt
    row["final_prompt_sha256"] = _sha(final_prompt.encode("utf-8"))
    return row


def _validate_immutable_inputs(spec: dict) -> None:
    immutable = [
        (REPO / spec["source"]["path"], spec["source"]["sha256"], "Job52 보존 입력"),
        (
            REPO / spec["original_three_scene_spec"]["path"],
            spec["original_three_scene_spec"]["sha256"],
            "원본 3장 명세",
        ),
        (
            REPO / spec["scene42_frozen_ledger"]["path"],
            spec["scene42_frozen_ledger"]["sha256"],
            "scene42 동결 원장",
        ),
    ]
    prior_total = 0
    for item in spec["prior_ledgers"]:
        path = REPO / item["path"]
        immutable.append((path, item["sha256"], "이전 canary 원장"))
        ledger = json.loads(path.read_text(encoding="utf-8"))
        if int(ledger.get("reserved_exposure_krw", -1)) != int(item["reserved_exposure_krw"]):
            raise RuntimeError("이전 원장의 예약 노출 합계가 다릅니다.")
        if (ledger.get("items") or [{}])[-1].get("attempt_id") != item["latest_attempt_id"]:
            raise RuntimeError("이전 canary attempt 계보가 다릅니다.")
        prior_total += int(item["reserved_exposure_krw"])
    if prior_total != PRIOR_LEDGER_EXPOSURE_KRW:
        raise RuntimeError("이전 원장들의 누적 예약 노출 합계가 다릅니다.")
    for path, expected, label in immutable:
        if not path.is_file() or _sha(path.read_bytes()) != expected:
            raise RuntimeError(f"{label} 해시가 실행 명세와 다릅니다.")


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
    _validate_immutable_inputs(spec)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["GEMINI_REQUEST_STATE_PATH"] = str(output / "request_state.sqlite3")
    project_scope_prefix = str(spec.get("project_scope_prefix") or "wo-img01-g-surfacefix")
    os.environ["GEMINI_PROJECT_SCOPE"] = f"{project_scope_prefix}-{_sha(spec_bytes)[:12]}"
    row = prepare_row(spec)
    _, usd_krw = _read_prices(args.pricing_config)
    (output / "bounded-prompt.txt").write_text(row["prompt"], encoding="utf-8")
    (output / "final-gemini-prompt.txt").write_text(row["final_prompt"], encoding="utf-8")

    preflight = {
        "version": spec["version"],
        "status": "authorized_preflight",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "spec_sha256": _sha(spec_bytes),
        "scene_index": SCENE_INDEX,
        "scene_key": SCENE_KEY,
        "prompt_sha256": row["prompt_sha256"],
        "final_prompt_sha256": row["final_prompt_sha256"],
        "references": row["references"],
        "screen_text_plan": row["scene"]["screen_text_plan"],
        "surface_plan_sha256": _canonical_sha(row["scene"]["screen_text_plan"]),
        "known_surface_semantic_mismatch_preserved": True,
        "provider_status_check": spec["provider_status_check"],
        "incremental_reserved_krw": INCREMENTAL_RESERVED_KRW,
        "prior_ledger_exposure_krw": PRIOR_LEDGER_EXPOSURE_KRW,
        "cumulative_exposure_cap_krw": CUMULATIVE_EXPOSURE_CAP_KRW,
        "reservation_interpretation": "보수적 노출 상한이며 예상 비용 또는 확정 지출이 아님",
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
        raise RuntimeError("surfacefix canary는 이미 시작됐습니다. 중복 POST를 차단합니다.")
    claim.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    from app import runtime_config
    from app.utils.budget import ProviderRequestAudit
    from app.utils.canary_visual_review import build_canary_visual_review_packet
    from app.utils.image_request_control import ImageRequestHeld
    from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider

    runtime_config.update(gemini_scene_request_limit=1)
    contract_fingerprint = _canonical_sha(row["scene"])
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
            "attempt_policy": str(
                spec.get("attempt_policy") or "one_surfacefix_canary_then_user_visual_review"
            ),
            "prior_ledger_sha256s": [item["sha256"] for item in spec["prior_ledgers"]],
            "prior_ledger_exposure_krw": PRIOR_LEDGER_EXPOSURE_KRW,
            "cumulative_exposure_cap_krw": CUMULATIVE_EXPOSURE_CAP_KRW,
            "provider_status_check": spec["provider_status_check"],
            "standing_authorization_basis": spec["authorization"]["basis"],
            "known_surface_semantic_mismatch_preserved": True,
        },
    )
    manifest = {**preflight, "status": "running", "started_at": datetime.now(timezone.utc).isoformat()}
    _write_json(manifest_path, manifest)
    try:
        result = GeminiProvider(use_batch=False).generate(
            row["prompt"], reference_image_paths=row["reference_paths"], request_audit=audit
        )
        raw_path = output / "scene_07_raw.png"
        raw_path.write_bytes(result.image_bytes)
        raw_sha256 = _sha(result.image_bytes)
        visual_review = build_canary_visual_review_packet(
            raw_path,
            raw_sha256,
            automated_findings={
                "face_contract": "awaiting_quantitative_review",
                "text_gate": "not_a_canary_approval_basis",
                "production_holistic_visual_qa": "not_executed_user_visual_review_required",
                "surface_semantic_binding": "known_mismatch_preserved_not_under_test",
            },
        )
        manifest.update(
            status="pending_user_visual_review",
            provider_status="http_200",
            raw_path=str(raw_path),
            raw_sha256=raw_sha256,
            holistic_visual_review=visual_review,
            approval_blocked=True,
            continuation_allowed=False,
        )
        preview_path = output / "scene_07_deterministic_preview.png"
        preview_path.write_bytes(result.image_bytes)
        try:
            from app.services.semantic_surface_text import render_semantic_surface_text

            render_semantic_surface_text(row["scene"], str(preview_path))
            manifest.update(
                deterministic_preview_status="rendered_not_approval",
                deterministic_preview_path=str(preview_path),
                deterministic_preview_sha256=_sha(preview_path.read_bytes()),
                deterministic_preview_text_integrity=row["scene"].get("final_frame_text_integrity"),
            )
        except Exception as exc:
            manifest.update(
                deterministic_preview_status="needs_review",
                deterministic_preview_error_type=type(exc).__name__,
                deterministic_preview_error=str(exc),
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
        "raw_path": manifest.get("raw_path"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
