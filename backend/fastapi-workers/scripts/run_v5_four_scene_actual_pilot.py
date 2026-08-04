#!/usr/bin/env python3
"""V5 정보형 3씬과 일반형 1씬을 동일 계약으로 소규모 실증한다.

이미지 API 호출은 ``--execute``일 때만 발생한다. 각 요청은 Gemini 전송 직전에
영속 원장에 개별 예약되고, 제공자 내부 자동 재시도는 V5 어댑터에서 한 번으로
고정된다. 정보형은 생성 뒤에만 Pillow 사실 오버레이를 적용하며, 일반형은
검증 수치 오버레이를 절대 받지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent.parent / ".env")

from app.utils.budget import ProviderRequestAudit
from app.v5.cost_ledger import Bucket, BudgetExceeded, CostLedger, FxProvider
from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider, GeminiProviderError
from app.v5.scene.runtime_contract import attach_v5_scene_contracts
from app.workers.script_worker import _classify_scene_types


GENERAL_SCENE = {
    "scene_id": "general_port_narrative_04",
    "title": "",
    "content": "The mascot walks through a busy harbor beside containers and a cargo ship.",
    # 부정문에 들어간 graph/metric도 분류기에는 신호가 된다. 일반형의
    # 시각 의도에는 금지 목록이 아니라 서사·장소 단서만 둔다.
    "visual_intent": "Character-focused harbor story with a continuous cartoon set.",
    "verified_facts": [],
    "v5_verified_overlays": [],
}


def _reference_paths() -> tuple[list[str], list[dict[str, str]]]:
    reference_root = ROOT / "out" / "references"
    manifest_path = reference_root / "reference_manifest_v4_identity_style_clean.json"
    paths = [
        reference_root / "character_reference_v4_identity_clean.png",
        reference_root / "style_reference_v4_medium_clean.png",
    ]
    if any(not path.is_file() for path in paths):
        raise GeminiProviderError("V5 참조 자산이 없어 파일럿 생성을 시작할 수 없습니다.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {item["role"]: item["sha256"] for item in manifest["artifacts"]}
    artifacts: list[dict[str, str]] = []
    for role, path in zip(("character", "style"), paths):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected.get(role):
            raise GeminiProviderError(f"참조 자산 해시가 일치하지 않습니다: {role}")
        artifacts.append({"role": role, "filename": path.name, "sha256": digest})
    return [str(path) for path in paths], artifacts


def _worker_scene(raw: dict[str, Any]) -> dict[str, Any]:
    """씬 ID의 숫자가 수치형 장면 분류 신호가 되지 않게 한다."""
    narration = str(raw.get("narration") or raw.get("content") or raw.get("text") or "")
    return {
        **raw,
        "title": str(raw.get("title") or ""),
        "content": narration,
        "text": narration,
        "visual_intent": str(raw.get("visual_intent") or ""),
    }


def _reject_numeric_overlay_payload(scene: dict[str, Any]) -> None:
    """대본 의미형 문구 전용 파일럿에 수치·사실 오버레이가 섞이지 않게 차단한다."""
    scene_id = str(scene.get("scene_id") or "(unknown)")
    prohibited_keys = ("verified_facts", "v5_verified_overlays", "market_chart", "numeric_overlays")
    supplied = [key for key in prohibited_keys if scene.get(key)]
    if supplied:
        raise ValueError(
            f"{scene_id}: 수치·사실 오버레이는 이 파일럿에서 사용할 수 없습니다: {', '.join(supplied)}"
        )


def _planned_scenes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    source = list(payload.get("scenes") or [])
    if len(source) != 3:
        raise ValueError("이 파일럿은 검증 사실이 있는 정보형 3씬을 입력으로 요구합니다.")
    for scene in source:
        _reject_numeric_overlay_payload(scene)
    source.append(dict(GENERAL_SCENE))
    classified = _classify_scene_types([_worker_scene(raw) for raw in source])
    planned = attach_v5_scene_contracts(classified)
    if [scene["v5_render_contract"]["scene_type"] for scene in planned] != ["graph", "graph", "metric", "general"]:
        raise ValueError("파일럿 scene_type 계약이 예상과 다릅니다. 이미지 호출을 차단합니다.")
    if planned[-1].get("v5_verified_overlays") or planned[-1].get("verified_facts"):
        raise ValueError("일반형 씬에 검증 사실 오버레이가 있어 이미지 호출을 차단합니다.")
    return planned


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--run-id", default="v5_actual_four_scene_pilot_20260801")
    parser.add_argument("--scene-ids", nargs="+", help="실제 호출할 씬 ID만 지정한다. 미지정 시 4씬 전체를 사용한다.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--resume", action="store_true",
        help="이미 저장된 원본·최종 PNG를 복구하고, 해당 씬의 Gemini 재호출을 금지합니다.",
    )
    args = parser.parse_args()
    if not args.run_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("run-id는 영문·숫자·밑줄·하이픈만 사용할 수 있습니다.")

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    scenes = _planned_scenes(payload)
    if args.scene_ids:
        requested = set(args.scene_ids)
        scenes = [scene for scene in scenes if scene["scene_id"] in requested]
        missing = requested - {scene["scene_id"] for scene in scenes}
        if missing:
            raise ValueError(f"알 수 없는 scene_id가 포함되었습니다: {', '.join(sorted(missing))}")
        if not scenes:
            raise ValueError("실행할 씬을 하나 이상 지정해야 합니다.")
    provider = GeminiProvider(use_batch=False)
    unit_usd = provider.estimate_cost_usd(GeminiModel.PRO, 2048, 1152)
    rate = FxProvider().usd_to_krw()
    estimated_krw = round(unit_usd * rate)
    if estimated_krw * len(scenes) > 7_000:
        raise BudgetExceeded("4씬 파일럿이 IMAGE_FINAL 버킷 상한을 초과합니다.")
    references, artifacts = _reference_paths()
    out_dir = ROOT / "out" / "v5_pilot" / "kospi_july_2026" / "actual_four_scene" / args.run_id
    request_ledger_path = out_dir / "_request_ledger.json"
    manifest_path = out_dir / "_manifest.json"
    summary: dict[str, Any] = {
        "status": "preflight_passed_no_api_call" if not args.execute else (
            "recovering_without_api_call" if args.resume else "running"
        ),
        "run_id": args.run_id,
        "scene_count": len(scenes),
        "model": GeminiModel.PRO.value,
        "estimated_per_image_usd": unit_usd,
        "estimated_total_usd": round(unit_usd * len(scenes), 6),
        "estimated_total_krw": estimated_krw * len(scenes),
        "automatic_retry": False,
        "reference_artifacts": artifacts,
        "scenes": [
            {
                "scene_id": scene["scene_id"],
                "scene_type": scene["v5_render_contract"]["scene_type"],
                "archetype": scene["v5_render_contract"]["selection"]["archetype"],
                "tier": scene["v5_render_contract"]["tier"],
                "visual_text_policy": scene["v5_render_contract"]["visual_text_policy"],
                "style_contract_version": scene["v5_render_contract"]["style_contract_version"],
                "verified_overlay_present": False,
            }
            for scene in scenes
        ],
    }
    _write(manifest_path, summary)
    if not args.execute:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    ledger = CostLedger(video_id=args.run_id, fx=FxProvider())
    results: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes):
        contract = scene["v5_render_contract"]
        scene_id = str(scene["scene_id"])
        raw_path = out_dir / f"{scene_id}_background.png"
        final_path = out_dir / f"{scene_id}.png"
        if args.resume and raw_path.is_file() and raw_path.stat().st_size > 0 and final_path.is_file() and final_path.stat().st_size > 0:
            results.append({
                "scene_id": scene_id,
                "status": "recovered_existing_file",
                "background_path": str(raw_path),
                "final_path": str(final_path),
                "cost_status": "request_ledger_reconciliation_required",
            })
            continue
        ledger.guard(Bucket.IMAGE_FINAL, unit_usd)
        audit = ProviderRequestAudit.for_path(
            path=request_ledger_path,
            scene_key=scene_id,
            model=GeminiModel.PRO.value,
            unit_usd=unit_usd,
            usd_krw=rate,
            budget_limit_krw=7_000,
            request_metadata={
                "automatic_retry": False,
                "reference_artifacts": artifacts,
                "scene_type": contract["scene_type"],
                "selected_archetype": contract["selection"]["archetype"],
                "visual_text_policy": contract["visual_text_policy"],
                "verified_overlay_mode": contract["verified_overlay_mode"],
            },
        )
        try:
            started = time.monotonic()
            result = provider.generate(
                contract["prompt_en"], model=GeminiModel.PRO, width=2048, height=1152,
                seed=601 + index, reference_image_paths=references, request_audit=audit,
            )
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(result.image_bytes)
            # 최종 문구는 프롬프트의 소품 표면에만 포함한다. Pillow 수치 오버레이는 사용하지 않는다.
            final_path.write_bytes(result.image_bytes)
            entry = ledger.record(
                scene_id=scene_id, provider="gemini", model=GeminiModel.PRO.value,
                request_kind="generate", bucket=Bucket.IMAGE_FINAL, estimated_usd=unit_usd,
                actual_usd=None, rate=rate, status="ok",
                cost_status="unverified_until_console_reconciliation", metadata=result.meta,
            )
            results.append({
                "scene_id": scene_id, "status": "ok", "seconds": round(time.monotonic() - started, 1),
                "background_path": str(raw_path), "final_path": str(final_path),
                "cost_status": entry.cost_status,
            })
        except (GeminiProviderError, BudgetExceeded, RuntimeError, ValueError) as exc:
            results.append({"scene_id": scene_id, "status": f"failed:{type(exc).__name__}", "message": str(exc)})
            break

    summary.update({
        "status": (
            "completed_recovered_no_api_call"
            if len(results) == len(scenes) and all(item["status"] == "recovered_existing_file" for item in results)
            else "completed"
            if len(results) == len(scenes) and all(item["status"] in {"ok", "recovered_existing_file"} for item in results)
            else "incomplete_or_blocked"
        ),
        "cost_status": "unverified_until_console_reconciliation",
        "console_reconciliation_required_before_next_paid_stage": True,
        "request_ledger_path": str(request_ledger_path),
        "results": results,
        "ledger": ledger.summary(),
    })
    _write(manifest_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] in {"completed", "completed_recovered_no_api_call"} else 4


if __name__ == "__main__":
    raise SystemExit(main())
