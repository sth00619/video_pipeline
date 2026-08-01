#!/usr/bin/env python3
"""V5 archetype 하나를 단일 호출로 검증한다.

이 도구는 사실 수치를 이미지 모델에 전달하지 않는다. primary physical surface에
장식 문자가 자연스럽게 들어가는지만 검증하며, 자동 재시도는 지원하지 않는다.
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
from app.v5.scene.layout_sketcher import LayoutSketcher
from app.v5.scene.prompt_builder import ARCHETYPES, SceneSpec, build_prompt
from app.v5.scene.scene_type_archetypes import ARCHETYPE_SURFACES, ArchetypeSelection, recommend_v5_archetype


PRESENTATION_BY_ARCHETYPE = {
    "port_emergency": ("alarm", "safety_vest", "alarmed_run", "right"),
    "retail_shock": ("surprise", "analyst", "calculator_hold", "left"),
    "classroom": ("explain", "professor", "point_left", "right"),
    "weather_map": ("explain", "reporter", "present", "right"),
    "risk_control_room": ("concern", "formal", "present", "center"),
    "trade_calculator": ("confidence", "vest", "think", "left"),
    "data_lab": ("explain", "reporter", "present", "right"),
    "earnings_stage": ("confidence", "formal", "present", "center"),
    "briefing_podium": ("explain", "reporter", "present", "center"),
    "real_estate_office": ("explain", "analyst", "present", "right"),
    "job_market_hall": ("happy", "reporter", "present", "left"),
}

DEFAULT_CONTEXT = {
    "port_emergency": ("text", "항만 물류의 핵심 경고 문구를 설명하는 장면"),
    "retail_shock": ("metric", "매장 가격과 소비 지표를 설명하는 장면"),
    "classroom": ("diagram", "경제 흐름의 구조와 원리를 설명하는 장면"),
    "weather_map": ("graph", "지역별 시장 변동을 지도 위에서 비교하는 그래프 장면"),
    "risk_control_room": ("metric", "시장의 급락과 변동 위험 지표를 설명하는 장면"),
    "trade_calculator": ("graph", "비교 막대와 비율을 설명하는 장면"),
    "data_lab": ("graph", "시장 추이를 설명하는 일반 그래프 장면"),
    "earnings_stage": ("graph", "quarterly earnings and performance trend validation scene"),
    "briefing_podium": ("text", "policy or CEO briefing validation scene"),
    "real_estate_office": ("metric", "property price and interest-rate metric validation scene"),
    "job_market_hall": ("metric", "employment and hiring metric validation scene"),
}

# 신규 archetype은 운영 scene_type 자동 매핑에 넣지 않는다. 이 표는
# primary-surface 단독 검증에서만 고정 선택을 만들기 위한 전용 계약이다.
VALIDATION_ONLY_ARCHETYPES = frozenset({
    "earnings_stage", "briefing_podium", "real_estate_office", "job_market_hall",
})


def _validation_selection(archetype: str, scene_type: str) -> ArchetypeSelection:
    if archetype not in VALIDATION_ONLY_ARCHETYPES:
        raise ValueError(f"검증 전용 archetype이 아닙니다: {archetype}")
    surfaces = ARCHETYPE_SURFACES[archetype]
    return ArchetypeSelection(
        scene_type=scene_type,
        archetype=archetype,
        alternatives=(),
        selection_reason="신규 archetype primary-surface 단독 검증용 고정 선택",
        physical_surfaces=surfaces,
        primary_physical_surface=surfaces[0],
    )


def _reference_paths() -> tuple[list[str], list[dict[str, str]]]:
    """해시가 검증된 캐릭터·스타일 참조만 전달한다."""
    reference_root = ROOT / "out" / "references"
    manifest_path = reference_root / "reference_manifest_v4_identity_style_clean.json"
    paths = [
        reference_root / "character_reference_v4_identity_clean.png",
        reference_root / "style_reference_v4_medium_clean.png",
    ]
    if any(not path.is_file() for path in paths):
        raise GeminiProviderError("검증된 캐릭터·스타일 참조 자산이 없습니다.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {item["role"]: item["sha256"] for item in manifest["artifacts"]}
    artifacts: list[dict[str, str]] = []
    for role, path in zip(("character", "style"), paths):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected.get(role):
            raise GeminiProviderError(f"참조 자산 해시가 일치하지 않습니다: {role}")
        artifacts.append({"role": role, "filename": path.name, "sha256": digest})
    return [str(path) for path in paths], artifacts


def _prior_state(request_ledger_path: Path, scene_key: str) -> str | None:
    if not request_ledger_path.is_file():
        return None
    try:
        items = json.loads(request_ledger_path.read_text(encoding="utf-8")).get("items", [])
    except (OSError, ValueError, AttributeError) as exc:
        raise RuntimeError("기존 요청 원장을 읽을 수 없어 중복 호출을 차단합니다.") from exc
    states = [str(item.get("status") or "") for item in items if item.get("scene_key") == scene_key]
    if "reserved" in states:
        return "unknown_remote_outcome"
    if "http_200" in states:
        return "confirmed_remote_success"
    return states[-1] if states else None


def _write_manifest(output_dir: Path, payload: dict[str, Any]) -> None:
    (output_dir / "_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="V5 archetype 단일 이미지 검증")
    parser.add_argument("--archetype", required=True, choices=tuple(PRESENTATION_BY_ARCHETYPE))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--execute", action="store_true", help="승인된 1회 Gemini 호출을 실행")
    args = parser.parse_args()
    if not args.run_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("run-id는 영문·숫자·밑줄·하이픈만 허용합니다.")

    scene_type, content = DEFAULT_CONTEXT[args.archetype]
    selection = recommend_v5_archetype({"scene_type": scene_type, "content": content})
    if args.archetype in VALIDATION_ONLY_ARCHETYPES:
        selection = _validation_selection(args.archetype, scene_type)
    if selection.archetype != args.archetype:
        raise ValueError(f"검증 문맥이 요청 archetype을 선택하지 않았습니다: {selection.archetype}")
    emotion, costume, pose, position = PRESENTATION_BY_ARCHETYPE[args.archetype]
    scene_id = f"{args.archetype}_primary_validation"
    spec = SceneSpec(scene_id, args.archetype, emotion, costume, pose, character_position=position)
    layout = LayoutSketcher.for_mascot_position(
        scene_id, occupancy=spec.frame_occupancy, position=spec.character_position,
    )
    prompt = build_prompt(
        spec,
        scene_type_selection=selection,
        layout_instruction=layout.prompt_instruction(),
        visual_text_policy="diegetic_decorative",
    )
    provider = GeminiProvider(use_batch=False)
    unit_usd = provider.estimate_cost_usd(GeminiModel.PRO, 2048, 1152)
    rate = FxProvider().usd_to_krw()
    estimated_krw = round(unit_usd * rate)
    references, artifacts = _reference_paths()
    output_dir = ROOT / "out" / "v5_archetype_validation" / args.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = output_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    request_ledger_path = output_dir / "_request_ledger.json"
    summary: dict[str, Any] = {
        "status": "preflight_passed" if not args.execute else "running",
        "scene_id": scene_id,
        "archetype": args.archetype,
        "scene_type": selection.scene_type,
        "primary_physical_surface": selection.primary_physical_surface,
        "estimated_cost_usd": unit_usd,
        "estimated_cost_krw": estimated_krw,
        "automatic_retry": False,
        "reference_artifacts": artifacts,
        "request_ledger_path": str(request_ledger_path),
        "prompt_path": str(prompt_path),
    }
    if not args.execute:
        _write_manifest(output_dir, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    prior = _prior_state(request_ledger_path, scene_id)
    if prior is not None:
        raise RuntimeError(f"기존 요청 상태({prior})가 있어 중복 호출을 차단합니다.")
    ledger = CostLedger(video_id=args.run_id, fx=FxProvider())
    ledger.guard(Bucket.IMAGE_FINAL, unit_usd)
    if estimated_krw > 7000:
        raise BudgetExceeded(f"IMAGE_FINAL 호출 상한을 넘습니다: {estimated_krw}원")
    audit = ProviderRequestAudit.for_path(
        path=request_ledger_path,
        scene_key=scene_id,
        model=GeminiModel.PRO.value,
        unit_usd=unit_usd,
        usd_krw=rate,
        budget_limit_krw=7000,
        request_metadata={
            "reference_contract": "v3_textless_no_layout_raster",
            "reference_artifacts": artifacts,
            "layout_contract": layout.prompt_instruction(),
            "visual_text_policy": "diegetic_decorative",
            "selected_archetype": selection.archetype,
            "primary_physical_surface": selection.primary_physical_surface,
            "automatic_retry": False,
        },
    )
    started = time.monotonic()
    try:
        result = provider.generate(
            prompt,
            model=GeminiModel.PRO,
            width=2048,
            height=1152,
            seed=401,
            reference_image_paths=references,
            request_audit=audit,
        )
    except GeminiProviderError as exc:
        entry = ledger.record(
            scene_id=scene_id, provider="gemini", model=GeminiModel.PRO.value,
            request_kind="generate", bucket=Bucket.IMAGE_FINAL, estimated_usd=unit_usd,
            actual_usd=None, rate=rate, status=f"failed:{type(exc).__name__}",
            cost_status="unverified_until_console_reconciliation", metadata={"error_type": type(exc).__name__},
        )
        summary.update({
            "status": "failed", "message": str(exc), "seconds": round(time.monotonic() - started, 1),
            "cost_status": entry.cost_status, "ledger": ledger.summary(),
        })
        _write_manifest(output_dir, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 4

    image_path = output_dir / f"{scene_id}.png"
    image_path.write_bytes(result.image_bytes)
    entry = ledger.record(
        scene_id=scene_id, provider="gemini", model=GeminiModel.PRO.value,
        request_kind="generate", bucket=Bucket.IMAGE_FINAL, estimated_usd=unit_usd,
        actual_usd=None, rate=rate, status="ok",
        cost_status="unverified_until_console_reconciliation", metadata=result.meta,
    )
    summary.update({
        "status": "completed", "image_path": str(image_path), "seconds": round(time.monotonic() - started, 1),
        "cost_status": entry.cost_status, "ledger": ledger.summary(),
    })
    _write_manifest(output_dir, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
