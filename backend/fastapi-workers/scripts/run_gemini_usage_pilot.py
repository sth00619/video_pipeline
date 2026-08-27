#!/usr/bin/env python3
"""기존 장면과 Gemini 경로로 1회만 사용량을 실측한다. 별도 LLM/QA/Fal/조립 호출은 없다."""
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_prices(path: Path) -> tuple[Decimal, Decimal]:
    """가격/환산율을 중복 하드코딩하지 않고 중앙 Java 선언에서 읽는다."""
    source = path.read_text(encoding="utf-8")
    values = []
    for key in ("GEMINI_3_PRO_IMAGE_2K_USD", "USD_TO_KRW_BUDGET_RATE"):
        match = re.search(rf"\b{key}\s*=\s*BigDecimal.valueOf\(([\d_.]+)[DL]?\)", source)
        if not match:
            raise ValueError(f"중앙 가격 선언 확인 불가: {key}")
        value = Decimal(match[1].replace("_", ""))
        if value <= 0:
            raise ValueError("중앙 가격은 양수여야 합니다.")
        values.append(value)
    return values[0], values[1]


def claim_once(output: Path) -> None:
    """실행을 다시 시작해도 이 승인으로 두 번째 POST를 만들지 않는다."""
    if (output / "request_ledger.json").exists():
        raise RuntimeError("기존 요청 원장이 있습니다. 추가 호출을 차단합니다.")
    with (output / "execute_once.claim").open("x") as handle:
        handle.write(datetime.now(timezone.utc).isoformat())
        handle.flush()
        os.fsync(handle.fileno())


def validate_retry(output: Path, manifest: dict, previous_id: str) -> dict:
    """첫 실패의 다음 1회만 허용한다. 이전 증거 파일은 덮어쓰지 않는다."""
    if (output / "retry_2.claim").exists():
        raise RuntimeError("추가 1회 승인은 이미 소비됐습니다.")
    ledger = json.loads((output / "request_ledger.json").read_text())
    prior = json.loads((output / "manifest.json").read_text())
    items = ledger.get("items", [])
    if (len(items) != 1 or items[0].get("attempt_id") != previous_id
            or items[0].get("status") != "http_503" or items[0].get("status_code") != 503
            or prior.get("status") != "request_failed_no_retry"):
        raise RuntimeError("첫 503 실패 직후의 단일 재시도만 승인할 수 있습니다.")
    for key in ("model", "service_tier", "image_size", "source_scene_index", "source_sha256",
                "narration_sha256", "prompt_sha256_before_provider_wrapper", "references", "pricing_config_sha256"):
        if manifest.get(key) != prior.get(key):
            raise RuntimeError(f"기존 실측 입력과 불일치: {key}")
    return items[0]


def claim_retry(output: Path, authorization: dict) -> None:
    with (output / "retry_2.claim").open("x") as handle:
        json.dump(authorization, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-scenes", type=Path, required=True)
    parser.add_argument("--scene-index", type=int, required=True)
    parser.add_argument("--pricing-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--budget-krw", type=int, required=True)
    parser.add_argument("--retry-of", help="사용자가 승인한 첫 503의 attempt ID. 다음 1회만 실행")
    parser.add_argument("--reservation-krw", type=int, help="재시도 추가 예약액. 단가/예상 청구액이 아님")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.budget_krw <= 0:
        raise ValueError("승인 예산은 양수여야 합니다.")
    if args.retry_of and (not args.reservation_krw or args.reservation_krw <= 0):
        raise ValueError("재시도에는 별도 승인된 예약액이 필요합니다.")
    if args.execute and not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY 미설정. 실행을 시작하지 않습니다.")

    from app import runtime_config
    from app.utils.budget import ProviderRequestAudit
    from app.v5.providers.gemini_provider import GeminiProvider, GeminiModel, select_contextual_reference_paths
    from app.workers.images_worker import _bounded_text_generation_prompt

    original_bytes = args.source_scenes.read_bytes()
    source = next(s for s in json.loads(original_bytes) if s.get("index") == args.scene_index)
    scene = copy.deepcopy(source)
    narration = str(scene.get("content") or scene.get("text") or "")
    if not narration or not scene.get("prompt_en"):
        raise ValueError("기존 내레이션과 장면 프롬프트가 모두 필요합니다.")
    prompt = _bounded_text_generation_prompt(scene["prompt_en"], audit_target=scene)
    references = select_contextual_reference_paths(prompt)
    unit, fx = read_prices(args.pricing_config)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not args.retry_of and ((output / "execute_once.claim").exists() or (output / "request_ledger.json").exists()):
        raise RuntimeError("이미 실행을 시작한 파일럿입니다. 새 POST와 산출물 덮어쓰기를 차단합니다.")
    manifest = {
        "status": "preflight_only", "model": GeminiModel.PRO.value, "service_tier": "standard", "image_size": "2K",
        "pilot_id": output.name, "source_scene_index": args.scene_index,
        "source_sha256": digest(original_bytes), "narration": narration,
        "narration_sha256": digest(narration.encode()), "source_prompt": source["prompt_en"], "prompt": prompt,
        "prompt_sha256_before_provider_wrapper": digest(prompt.encode()),
        "text_contract": scene.get("image_text_contract"),
        "references": [{"name": Path(p).name, "sha256": digest(Path(p).read_bytes())} for p in references],
        "pricing_config_sha256": digest(args.pricing_config.read_bytes()),
        "output_only_estimate_usd": str(unit), "usd_krw": str(fx), "authorized_budget_krw": args.budget_krw,
        "reservation_basis": "entire_authorized_budget_not_image_unit_price",
        "scope": "단일 요청 사용량 실측. 이미지 텍스트/화풍 최종 승인이나 전체 영상 검증 아님.",
    }
    retry_metadata = {}
    reservation = args.budget_krw
    suffix = ""
    if args.retry_of:
        previous = validate_retry(output, manifest, args.retry_of)
        reservation = args.reservation_krw
        prior_reserved = int(previous["reserved_amount_krw"])
        if prior_reserved + reservation > args.budget_krw:
            raise ValueError("기존 청구 미확정 예약과 추가 예약 합계가 승인 상한을 넘습니다.")
        suffix = "_retry2"
        retry_metadata = {
            "approved_retry_of": args.retry_of, "approved_retry_prior_count": 1,
            "approved_retry_failure_n": previous["request_control"]["failure_n"],
            "authorization_scope": "동일 요청 추가 1회; 결과와 무관하게 자동 재시도 금지",
            "original_pilot_budget_krw": prior_reserved,
            "authorized_combined_reservation_cap_krw": args.budget_krw,
            "additional_reservation_krw": reservation,
            "cost_interpretation": "보수적 예약 상한; Gemini 단가/예상 비용/확정 지출 아님",
        }
        manifest.update(retry_metadata)
        manifest["reservation_basis"] = "additional_authorized_contingency_not_unit_price_or_spend"
    if not args.execute:
        write_json(output / f"preflight{suffix}.json", manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    if args.retry_of:
        claim_retry(output, {**retry_metadata, "at": datetime.now(timezone.utc).isoformat()})
    else:
        claim_once(output)
    # 별도 프로세스에만 적용한다. 영속 프로젝트 저장 경로/범위는 그대로 공유한다.
    runtime_config.update(gemini_scene_request_limit=2 if args.retry_of else 1)
    owner = ProviderRequestAudit.for_path(path=output / "request_ledger.json", scene_key=f"image:{args.scene_index}",
        model=GeminiModel.PRO.value, unit_usd=float(Decimal(reservation) / fx), usd_krw=float(fx),
        budget_limit_krw=args.budget_krw,
        request_metadata={"job_id": output.name, "run_id": output.name,
                          "contract_fingerprint": digest(json.dumps(scene, ensure_ascii=False, sort_keys=True).encode()),
                          "reservation_basis": manifest["reservation_basis"], **retry_metadata})
    manifest["status"] = "running"
    write_json(output / f"manifest{suffix}.json", manifest)
    try:
        result = GeminiProvider(use_batch=False).generate(prompt, reference_image_paths=references, request_audit=owner)
        image_path = output / f"scene_{args.scene_index:03d}_raw{suffix}.png"
        image_path.write_bytes(result.image_bytes)
        manifest.update(status="generated_measurement_only", image_path=str(image_path), image_sha256=digest(result.image_bytes))
    except Exception as exc:
        # 키나 공급자 본문이 예외 메시지에 섞일 수 있어 타입만 별도 저장한다.
        manifest.update(status="request_failed_no_retry", error_type=type(exc).__name__)
    manifest["request_summary"] = owner.summary()
    entries = manifest["request_summary"]["entries"]
    if entries and entries[-1].get("usage_metadata_status") == "present":
        write_json(output / f"usageMetadata{suffix}.json", entries[-1]["usage_metadata"])
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(output / f"manifest{suffix}.json", manifest)
    print(json.dumps({"status": manifest["status"], "output_dir": str(output), "request_summary": manifest["request_summary"]}, ensure_ascii=False, indent=2))
    return 0 if manifest["status"] == "generated_measurement_only" else 4


if __name__ == "__main__":
    raise SystemExit(main())
