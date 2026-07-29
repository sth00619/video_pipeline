#!/usr/bin/env python3
"""P1-b: Gemini Pro 2K 표준 티어 8씬 비교 실행기."""
from __future__ import annotations

import json
import hashlib
import os
import sys
import time
import argparse
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# 사용자가 관리하는 저장소 루트 .env만 읽는다. 키 값은 로그에 출력하지 않는다.
load_dotenv(ROOT.parent.parent / ".env")

from app.v5.cost_ledger import Bucket, BudgetExceeded, CostLedger, FxProvider
from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider, GeminiProviderError
from app.v5.scene.prompt_builder import BENCHMARK_SCENES, build_prompt
from app.utils.budget import ProviderRequestAudit


def _reference_paths() -> list[str]:
    root = ROOT / "out" / "references"
    manifest_path = root / "reference_manifest_v3_textless_no_layout_raster.json"
    paths = [
        root / "character_reference_v2_textless.png",
        root / "style_reference_v2_textless.png",
    ]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise GeminiProviderError("P1-b 참조 자산이 없습니다: " + ", ".join(missing))
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        recorded = {item["role"]: item["sha256"] for item in manifest["artifacts"]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise GeminiProviderError("P1-b 무문자 참조 자산 manifest를 검증할 수 없습니다") from exc
    for role, path in zip(("character", "style"), paths):
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if recorded.get(role) != actual:
            raise GeminiProviderError(f"P1-b 참조 자산 해시 불일치: {role}")
    return [str(path) for path in paths]


def _reference_metadata(references: list[str]) -> dict:
    roles = ("character", "style")
    return {
        "reference_contract": "v3_textless_no_layout_raster",
        "reference_artifacts": [
            {"role": role, "filename": Path(path).name, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
            for role, path in zip(roles, references)
        ],
    }


def preflight(scenes: list) -> tuple[GeminiProvider, float, float, list[str]]:
    provider = GeminiProvider(use_batch=False)
    per_image_usd = provider.estimate_cost_usd(GeminiModel.PRO, 2048, 1152)
    total_usd = per_image_usd * len(scenes)
    references = _reference_paths()
    ledger = CostLedger(video_id="p1b_preflight", fx=FxProvider())
    for _ in scenes:
        ledger.guard(Bucket.IMAGE_FINAL, per_image_usd)
        ledger.record(scene_id="preflight", provider="gemini", model=GeminiModel.PRO.value, request_kind="reserve", bucket=Bucket.IMAGE_FINAL, estimated_usd=per_image_usd, actual_usd=None, rate=ledger._fx.usd_to_krw(), status="reserved", cost_status="unverified_until_console_reconciliation")
    if ledger.total_spent_krw() > 7000:
        raise BudgetExceeded(f"IMAGE_FINAL 버킷 초과: KRW {ledger.total_spent_krw()} > KRW 7000")
    print("P1-b PRE-FLIGHT (외부 Gemini 호출 없음)")
    print(f"GEMINI_API_KEY={'configured' if provider._key else 'missing'}")
    print(f"V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD=${per_image_usd:.3f}")
    print(f"scenes={len(scenes)}, estimated_total_usd=${total_usd:.3f}")
    print(f"IMAGE_FINAL_reserved_krw={ledger.total_spent_krw()} / 7000")
    print(f"reference_images={len(references)} (character, style; layout is text-only)")
    print("service_tier=standard, batch=false, fallback=false")
    return provider, per_image_usd, ledger._fx.usd_to_krw(), references


def main() -> int:
    parser = argparse.ArgumentParser(description="P1-b Gemini 벤치마크 실행기")
    parser.add_argument("--scene-id", help="승인된 단일 씬 ID. 생략하면 전체 벤치마크를 실행합니다.")
    parser.add_argument("--preflight-only", action="store_true", help="외부 요청 없이 예산과 참조 자산만 확인합니다.")
    parser.add_argument("--run-id", default="gemini_pro", help="기존 산출물을 보존할 실행 디렉터리 이름")
    args = parser.parse_args()
    if not args.run_id.replace("_", "").replace("-", "").isalnum():
        print("ERROR run-id는 영문·숫자·밑줄·하이픈만 사용할 수 있습니다")
        return 2
    selected_scenes = list(BENCHMARK_SCENES)
    if args.scene_id:
        selected_scenes = [scene for scene in selected_scenes if scene.scene_id == args.scene_id]
        if len(selected_scenes) != 1:
            print(f"ERROR 승인 씬을 찾을 수 없습니다: {args.scene_id}")
            return 2
    try:
        provider, per_image_usd, rate, references = preflight(selected_scenes)
    except (GeminiProviderError, BudgetExceeded) as exc:
        print(f"ERROR P1-b 사전 승인 실패: {exc}")
        return 2

    if args.preflight_only:
        print("PRE-FLIGHT ONLY: 외부 Gemini 요청을 실행하지 않았습니다.")
        return 0

    out_dir = ROOT / "out" / "benchmark" / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    request_ledger_path = out_dir / "_request_ledger.json"
    ledger = CostLedger(video_id="p1b_gemini_pro", fx=FxProvider())
    manifest: list[dict] = []
    for spec in selected_scenes:
        index = BENCHMARK_SCENES.index(spec) + 1
        try:
            ledger.guard(Bucket.IMAGE_FINAL, per_image_usd)
        except BudgetExceeded as exc:
            print(f"ERROR {spec.scene_id}: 예산 차단 — {exc}")
            return 3
        started = time.monotonic()
        try:
            request_audit = ProviderRequestAudit.for_path(
                path=request_ledger_path,
                scene_key=spec.scene_id,
                model=GeminiModel.PRO.value,
                unit_usd=per_image_usd,
                usd_krw=rate,
                budget_limit_krw=7000,
                request_metadata=_reference_metadata(references),
            )
            result = provider.generate(
                build_prompt(spec), model=GeminiModel.PRO, width=2048, height=1152,
                seed=100 + index, reference_image_paths=references, request_audit=request_audit,
            )
        except GeminiProviderError as exc:
            ledger.record(scene_id=spec.scene_id, provider="gemini", model=GeminiModel.PRO.value, request_kind="generate", bucket=Bucket.IMAGE_FINAL, estimated_usd=per_image_usd, actual_usd=None, rate=rate, status=f"failed:{type(exc).__name__}", cost_status="unverified_until_console_reconciliation", metadata={"reference_image_count": len(references)})
            manifest.append({"scene_id": spec.scene_id, "status": f"failed:{type(exc).__name__}"})
            print(f"ERROR {spec.scene_id}: {exc}")
            continue
        (out_dir / f"{spec.scene_id}.png").write_bytes(result.image_bytes)
        entry = ledger.record(scene_id=spec.scene_id, provider="gemini", model=GeminiModel.PRO.value, request_kind="generate", bucket=Bucket.IMAGE_FINAL, estimated_usd=per_image_usd, actual_usd=None, rate=rate, status="ok", cost_status="unverified_until_console_reconciliation", metadata=result.meta)
        manifest.append({"scene_id": spec.scene_id, "archetype": spec.archetype, "status": "ok", "estimated_cost_usd": per_image_usd, "actual_cost_usd": None, "cost_status": entry.cost_status, "seconds": round(time.monotonic() - started, 1), "seed": result.seed})
        _write_manifest(out_dir, per_image_usd, manifest, ledger, request_ledger_path, len(selected_scenes), run_status="running")
        print(f"PASS {spec.scene_id}: estimated ${per_image_usd:.3f}, billing reconciliation pending")
    successful = sum(1 for scene in manifest if scene["status"] == "ok")
    run_status = "completed" if successful == len(selected_scenes) else "failed"
    _write_manifest(out_dir, per_image_usd, manifest, ledger, request_ledger_path, len(selected_scenes), run_status=run_status)
    print(f"P1-b 실행 결과: {successful}/{len(selected_scenes)}개, run_status={run_status}")
    return 0 if successful == len(selected_scenes) else 4


def _write_manifest(
    out_dir: Path, per_image_usd: float, scenes: list[dict], ledger: CostLedger,
    request_ledger_path: Path, scene_count: int, *, run_status: str,
) -> None:
    try:
        request_ledger = json.loads(request_ledger_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        request_ledger = {"items": [], "total_krw": 0}
    payload = {
        "provider": "gemini", "model": GeminiModel.PRO.value, "service_tier": "standard", "batch": False,
        "run_status": run_status, "estimated_total_usd": round(per_image_usd * scene_count, 6),
        "cost_status": "unverified_until_console_reconciliation",
        "console_reconciliation_required_before_next_paid_stage": True,
        "request_ledger_path": str(request_ledger_path),
        "request_ledger": request_ledger,
        "scenes": scenes, "ledger": ledger.summary(),
    }
    (out_dir / "_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
