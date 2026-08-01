#!/usr/bin/env python3
"""검증 대본의 첫 3씬에 맞는 V5 Gemini 배경을 생성하고 사실 오버레이 계약을 갱신한다.

Gemini가 그릴 수 있는 표기는 선택된 장면 속 물리 소품의 장식으로만 제한한다.
같은 파일의 ``verified_facts``는 이후 Pillow 단계가 결정론적으로 합성한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
from app.v5.scene.prompt_builder import SceneSpec, build_prompt
from app.v5.scene.scene_type_archetypes import ArchetypeSelection, recommend_v5_archetype
from app.workers.script_worker import _classify_scene_types
from scripts.validate_v5_pilot_input import validate_payload


PRESENTATION_BY_ARCHETYPE = {
    "port_emergency": ("alarm", "safety_vest", "alarmed_run", "right"),
    "retail_shock": ("surprise", "analyst", "calculator_hold", "left"),
    "classroom": ("explain", "professor", "point_left", "right"),
    "weather_map": ("explain", "reporter", "present", "right"),
    "risk_control_room": ("concern", "formal", "present", "center"),
    "trade_calculator": ("confidence", "vest", "think", "left"),
    "data_lab": ("explain", "reporter", "present", "right"),
}


def _reference_paths() -> list[str]:
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
    for role, path in zip(("character", "style"), paths):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected.get(role):
            raise GeminiProviderError(f"참조 자산 해시가 일치하지 않습니다: {role}")
    return [str(path) for path in paths]


def _metadata(references: list[str], layout: str, selection: ArchetypeSelection) -> dict[str, Any]:
    return {
        "reference_contract": "v3_textless_no_layout_raster",
        "reference_artifacts": [
            {"role": role, "filename": Path(path).name, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
            for role, path in zip(("character", "style"), references)
        ],
        "layout_contract": layout,
        # 배경의 영문·장식 표기는 primary 물리 표면의 정보 밀도만 만든다. 실제 사실은
        # 이후 Pillow가 검증된 좌표에 합성하므로 두 종류를 혼동하지 않는다.
        "visual_text_policy": "diegetic_decorative",
        "scene_type": selection.scene_type,
        "selected_archetype": selection.archetype,
        "physical_surfaces": list(selection.physical_surfaces),
        "primary_physical_surface": selection.primary_physical_surface,
        "selection_reason": selection.selection_reason,
        "automatic_retry": False,
    }


def _anchor_for(position: str) -> dict[str, Any]:
    return {
        "right": {"x": 0.10, "y": 0.31, "width": 0.27, "height": 0.17, "kind": "embedded_monitor"},
        "center": {"x": 0.07, "y": 0.25, "width": 0.25, "height": 0.17, "kind": "embedded_monitor"},
        "left": {"x": 0.62, "y": 0.29, "width": 0.27, "height": 0.17, "kind": "embedded_monitor"},
    }[position]


def _prompt(spec: SceneSpec, selection: ArchetypeSelection, layout_instruction: str) -> str:
    return build_prompt(
        spec,
        character_position=spec.character_position,
        layout_instruction=layout_instruction,
        visual_text_policy="diegetic_decorative",
        scene_type_selection=selection,
    )


def _source_scene(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": raw.get("scene_id", ""),
        "content": raw.get("narration", ""),
        "visual_intent": raw.get("visual_intent", ""),
        "section": "data",
    }


def _scene_pairs(payload: dict[str, Any]) -> list[tuple[dict[str, Any], ArchetypeSelection, SceneSpec]]:
    """파일럿 대본을 1·2단계 계약으로 추천 무대와 함께 준비한다."""
    classified = _classify_scene_types([_source_scene(raw) for raw in payload["scenes"]])
    pairs: list[tuple[dict[str, Any], ArchetypeSelection, SceneSpec]] = []
    for raw, scene in zip(payload["scenes"], classified):
        selection = recommend_v5_archetype(scene)
        emotion, costume, pose, position = PRESENTATION_BY_ARCHETYPE[selection.archetype]
        spec = SceneSpec(raw["scene_id"], selection.archetype, emotion, costume, pose, character_position=position)
        pairs.append((raw, selection, spec))
    return pairs


def preflight(payload: dict[str, Any]) -> tuple[GeminiProvider, float, float, list[str]]:
    validate_payload(payload)
    if len(payload["scenes"]) != 3:
        raise ValueError("검증 대본 파일럿은 정확히 3씬이어야 합니다.")
    provider = GeminiProvider(use_batch=False)
    unit_usd = provider.estimate_cost_usd(GeminiModel.PRO, 2048, 1152)
    rate = FxProvider().usd_to_krw()
    total_krw = round(unit_usd * rate) * len(payload["scenes"])
    if total_krw > 7000:
        raise BudgetExceeded(f"3씬 이미지 파일럿 예상 비용이 IMAGE_FINAL 상한을 넘습니다: {total_krw}원")
    references = _reference_paths()
    return provider, unit_usd, rate, references


def _generated_payload(
    original: dict[str, Any], out_dir: Path,
    pairs: list[tuple[dict[str, Any], ArchetypeSelection, SceneSpec]],
) -> dict[str, Any]:
    result = {key: value for key, value in original.items() if key != "scenes"}
    result["requires_image_generation"] = False
    result["scenes"] = []
    for scene, selection, spec in pairs:
        copied = dict(scene)
        copied["background_path"] = str((out_dir / f"{spec.scene_id}.png").relative_to(ROOT)).replace("\\", "/")
        copied["scene_type"] = selection.scene_type
        copied["selected_archetype"] = selection.archetype
        copied["archetype_selection_reason"] = selection.selection_reason
        copied["physical_surfaces"] = list(selection.physical_surfaces)
        copied["primary_physical_surface"] = selection.primary_physical_surface
        copied["v5_verified_overlays"] = [dict(scene["v5_verified_overlays"][0])]
        copied["v5_verified_overlays"][0]["anchor"] = _anchor_for(spec.character_position)
        result["scenes"].append(copied)
    return result


def _prior_request_state(path: Path, scene_id: str) -> str | None:
    """이전 요청의 원격 결과가 확정되기 전에는 같은 장면을 다시 보내지 않는다."""
    if not path.is_file():
        return None
    try:
        items = json.loads(path.read_text(encoding="utf-8")).get("items", [])
    except (OSError, ValueError, AttributeError) as exc:
        raise RuntimeError("기존 요청 원장을 읽을 수 없어 중복 호출을 차단합니다.") from exc
    statuses = [str(item.get("status") or "") for item in items if item.get("scene_key") == scene_id]
    if "reserved" in statuses:
        return "unknown_remote_outcome"
    if "http_200" in statuses:
        return "confirmed_remote_success"
    return statuses[-1] if statuses else None


def main() -> int:
    parser = argparse.ArgumentParser(description="V5 검증 대본 3씬 배경 생성")
    parser.add_argument("--input", required=True, help="검증 사실이 포함된 3씬 파일럿 JSON")
    parser.add_argument("--run-id", default="kospi_july_2026_verified_backgrounds")
    parser.add_argument(
        "--scene-id",
        action="append",
        help="생성할 씬 ID. 여러 번 지정하면 각 씬을 정확히 한 번씩 호출합니다.",
    )
    parser.add_argument("--execute", action="store_true", help="사전검증 통과 후 Gemini Pro를 3회 호출")
    args = parser.parse_args()
    if not args.run_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("run-id는 영문·숫자·밑줄·하이픈만 사용할 수 있습니다.")
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    provider, unit_usd, rate, references = preflight(payload)
    all_pairs = _scene_pairs(payload)
    known_scene_ids = {spec.scene_id for _, _, spec in all_pairs}
    requested_scene_ids = tuple(args.scene_id or ())
    unknown_scene_ids = sorted(set(requested_scene_ids) - known_scene_ids)
    if unknown_scene_ids:
        raise ValueError(f"알 수 없는 scene-id: {', '.join(unknown_scene_ids)}")
    if len(set(requested_scene_ids)) != len(requested_scene_ids):
        raise ValueError("같은 scene-id를 중복 지정할 수 없습니다.")
    selected_pairs = [
        pair for pair in all_pairs
        if not requested_scene_ids or pair[2].scene_id in requested_scene_ids
    ]
    summary = {
        "status": "preflight_passed" if not args.execute else "running",
        "scene_count": len(selected_pairs),
        "model": GeminiModel.PRO.value,
        "estimated_per_image_usd": unit_usd,
        "estimated_total_usd": round(unit_usd * len(selected_pairs), 6),
        "estimated_total_krw": round(unit_usd * rate) * len(selected_pairs),
        "automatic_retry": False,
        "reference_count": len(references),
    }
    if not args.execute:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    out_dir = ROOT / "out/v5_pilot/kospi_july_2026/generated_backgrounds" / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    request_ledger_path = out_dir / "_request_ledger.json"
    ledger = CostLedger(video_id=args.run_id, fx=FxProvider())
    manifest: list[dict[str, Any]] = []
    for scene, selection, spec in selected_pairs:
        try:
            target = out_dir / f"{spec.scene_id}.png"
            prior = _prior_request_state(request_ledger_path, spec.scene_id)
            if prior == "unknown_remote_outcome":
                raise RuntimeError(f"{spec.scene_id}: 이전 요청이 reserved 상태입니다. 콘솔 로그 대조 전 재호출을 차단합니다.")
            if prior == "confirmed_remote_success":
                if target.is_file() and target.stat().st_size > 0:
                    manifest.append({"scene_id": spec.scene_id, "status": "already_saved_no_new_request"})
                    continue
                raise RuntimeError(f"{spec.scene_id}: 이전 HTTP 200은 확인됐지만 이미지 파일이 없습니다. 중복 과금 방지를 위해 재호출을 차단합니다.")
            ledger.guard(Bucket.IMAGE_FINAL, unit_usd)
            layout = LayoutSketcher.for_mascot_position(spec.scene_id, occupancy=spec.frame_occupancy, position=spec.character_position)
            audit = ProviderRequestAudit.for_path(
                path=request_ledger_path,
                scene_key=spec.scene_id,
                model=GeminiModel.PRO.value,
                unit_usd=unit_usd,
                usd_krw=rate,
                budget_limit_krw=7000,
                request_metadata=_metadata(references, layout.prompt_instruction(), selection),
            )
            started = time.monotonic()
            result = provider.generate(
                _prompt(spec, selection, layout.prompt_instruction()),
                model=GeminiModel.PRO,
                width=2048,
                height=1152,
                seed=201 + len(manifest),
                reference_image_paths=references,
                request_audit=audit,
            )
            target.write_bytes(result.image_bytes)
            entry = ledger.record(
                scene_id=spec.scene_id, provider="gemini", model=GeminiModel.PRO.value,
                request_kind="generate", bucket=Bucket.IMAGE_FINAL, estimated_usd=unit_usd,
                actual_usd=None, rate=rate, status="ok",
                cost_status="unverified_until_console_reconciliation", metadata=result.meta,
            )
            manifest.append({
                "scene_id": spec.scene_id, "status": "ok", "seconds": round(time.monotonic() - started, 1),
                "scene_type": selection.scene_type, "selected_archetype": selection.archetype,
                "physical_surfaces": list(selection.physical_surfaces),
                "primary_physical_surface": selection.primary_physical_surface,
                "estimated_cost_usd": unit_usd, "cost_status": entry.cost_status,
            })
        except (GeminiProviderError, BudgetExceeded, RuntimeError) as exc:
            manifest.append({"scene_id": spec.scene_id, "status": f"failed:{type(exc).__name__}", "message": str(exc)})
            break

    all_requested_backgrounds_saved = all(
        (out_dir / f"{spec.scene_id}.png").is_file() for _, _, spec in selected_pairs
    )
    all_pilot_backgrounds_saved = all(
        (out_dir / f"{spec.scene_id}.png").is_file() for _, _, spec in all_pairs
    )
    if all_pilot_backgrounds_saved:
        generated = _generated_payload(payload, out_dir, all_pairs)
        (out_dir / "v5_generated_background_pilot_input.json").write_text(json.dumps(generated, ensure_ascii=False, indent=2), encoding="utf-8")
    run_status = "completed" if all_requested_backgrounds_saved else "incomplete_or_blocked"
    (out_dir / "_manifest.json").write_text(json.dumps({
        **summary,
        "status": run_status,
        "all_pilot_backgrounds_saved": all_pilot_backgrounds_saved,
        "cost_status": "unverified_until_console_reconciliation",
        "console_reconciliation_required_before_next_paid_stage": True,
        "request_ledger_path": str(request_ledger_path),
        "scenes": manifest,
        "ledger": ledger.summary(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**summary, "status": run_status, "output_dir": str(out_dir), "scenes": manifest}, ensure_ascii=False, indent=2))
    return 0 if all(item["status"] in {"ok", "already_saved_no_new_request"} for item in manifest) else 4


if __name__ == "__main__":
    raise SystemExit(main())
