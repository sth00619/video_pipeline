"""Three Goals 이미지 4장면 파일럿 실행기.

기본 실행은 입력 계약, 프롬프트 수치 차단, 예산을 검증하는 dry run이다.
실제 Gemini Pro 호출은 사용자가 명시적으로 ``--execute``를 전달한 경우에만 발생한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent.parent
sys.path.insert(0, str(ROOT))

# 로컬 실행에서도 Compose와 같은 .env를 사용하되, 프로세스 환경 변수는 우선한다.
load_dotenv(PROJECT_ROOT / ".env", override=False)

from app import runtime_config
from app.providers.real.image import NanaBananaProvider
from app.utils.budget import ProviderRequestAudit, plan_preflight
from app.v5.overlay.diegetic_fact_overlay import (
    apply_verified_scene_facts,
    validated_facts_from_verified_scene,
)
from app.v5.scene.runtime_contract import attach_v5_scene_contracts, prompt_for_scene


MODEL = "gemini-3-pro-image"
POLICY_VERSION = "three-goals-e2e-2026-08-02"
EXPECTED_SCENE_TYPES = ("graph", "diagram", "metric", "general")
TARGET_SIZE = (1920, 1080)
CANONICAL_CHARACTER_REFERENCE = ROOT / "assets" / "character" / "goldie_sheet_v1.png"


def _canonical_character_reference() -> dict[str, str]:
    """유료 요청에 첨부할 채널 마스코트 기준 시트를 fail-closed로 확인한다."""
    if not CANONICAL_CHARACTER_REFERENCE.is_file():
        raise RuntimeError(f"마스코트 기준 시트를 찾을 수 없습니다: {CANONICAL_CHARACTER_REFERENCE}")
    return {
        "path": str(CANONICAL_CHARACTER_REFERENCE),
        "sha256": hashlib.sha256(CANONICAL_CHARACTER_REFERENCE.read_bytes()).hexdigest(),
    }


def _read_input(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"입력 JSON을 읽을 수 없습니다: {path}") from exc
    scenes = payload.get("scenes") if isinstance(payload, dict) else None
    if not isinstance(scenes, list) or len(scenes) != 4:
        raise ValueError("파일럿 입력에는 정확히 4개의 scenes가 필요합니다.")
    if tuple(str(scene.get("scene_type") or "") for scene in scenes) != EXPECTED_SCENE_TYPES:
        raise ValueError("장면 순서는 graph, diagram, metric, general 이어야 합니다.")
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise ValueError(f"scene[{index}]가 객체가 아닙니다.")
        if not str(scene.get("scene_id") or scene.get("id") or "").strip():
            raise ValueError(f"scene[{index}]에 scene_id가 필요합니다.")
        is_verified_scene = index < 3
        has_facts = bool(scene.get("verified_facts") or scene.get("facts"))
        has_overlays = bool(scene.get("v5_verified_overlays"))
        if is_verified_scene and not (has_facts and has_overlays):
            raise ValueError(f"scene[{index}]에는 검증 사실과 V5 오버레이가 모두 필요합니다.")
        if not is_verified_scene and (has_facts or has_overlays):
            raise ValueError("일반 장면에는 검증 사실 또는 V5 오버레이를 넣을 수 없습니다.")
    return [dict(scene) for scene in scenes]


def build_plan(input_path: Path, *, budget_limit_krw: int = 70_000) -> dict[str, Any]:
    """외부 호출 없이 실행 계약과 비용 상한을 검증한다."""
    scenes = attach_v5_scene_contracts(_read_input(input_path))
    character_reference = _canonical_character_reference()
    for scene in scenes:
        # provider 호출 직전과 동일한 프롬프트 guard를 dry run에서도 통과해야 한다.
        prompt_for_scene(scene)
        # 생성 뒤가 아니라 생성 전에 출처·값·소품 표면 좌표 계약을 검증한다.
        validated_facts_from_verified_scene(scene)
    preflight = plan_preflight(
        scene_count=len(scenes),
        quality_tier="pro",
        requested_pro=len(scenes),
        requested_kling=0,
        budget_limit_krw=budget_limit_krw,
        policy_version=POLICY_VERSION,
    )
    if not preflight["allowed"]:
        raise ValueError("4장면 Gemini Pro 파일럿이 작업 예산 상한을 초과합니다.")
    return {
        "mode": "dry_run",
        "model": MODEL,
        "policy_version": POLICY_VERSION,
        "gemini_key_configured": bool(
            os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
        ),
        "preflight": preflight,
        "character_reference": {
            "file_name": CANONICAL_CHARACTER_REFERENCE.name,
            "sha256": character_reference["sha256"],
            "attached_to_every_gemini_request": True,
        },
        "scenes": [
            {
                "scene_id": scene["v5_render_contract"]["scene_id"],
                "scene_type": scene["v5_render_contract"]["scene_type"],
                "model": scene["image_profile"]["model"],
                "prompt_guard": "passed",
                "verified_overlay": bool(scene.get("v5_verified_overlays")),
                "review_kind": "verified_surface" if scene.get("v5_verified_overlays") else "general_scene",
            }
            for scene in scenes
        ],
        "review_contract": {
            "automatic_regeneration": False,
            "require_manual_decision_before_regeneration": True,
            "required_artifacts_per_scene": ["background.png", "final.png"],
            "required_checks": [
                "PNG 해상도와 파일 무결성",
                "원본 배경의 읽을 수 있는 수치·한글 텍스트 유무",
                "마스코트 얼굴·비율·카메라 구도 보존",
                "검증 장면의 소품 표면 오버레이 위치·출처·값 일치",
                "일반 장면의 검증 수치 오버레이 부재",
            ],
        },
        "_planned_scenes": scenes,
    }


def _candidate_directory(output_dir: Path, scene_id: str) -> tuple[Path, int]:
    root = output_dir / "candidates" / scene_id
    attempts = [path for path in root.glob("attempt-*") if path.is_dir()]
    attempt = len(attempts) + 1
    candidate = root / f"attempt-{attempt:02d}"
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate, attempt


def _png_summary(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        return {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "width": image.width,
            "height": image.height,
            "format": image.format,
        }


def _normalize_to_target_canvas(source_png: bytes) -> tuple[bytes, dict[str, Any]]:
    """원본을 보존한 채 최종 산출물만 16:9 1920×1080으로 결정론적 변환한다."""
    target_width, target_height = TARGET_SIZE
    target_ratio = target_width / target_height
    with Image.open(io.BytesIO(source_png)) as opened:
        image = opened.convert("RGB")
    source_width, source_height = image.size
    if source_width < target_width or source_height < target_height:
        raise RuntimeError(
            f"Gemini Pro 원본 해상도가 최종 캔버스보다 작습니다: {source_width}x{source_height}"
        )
    source_ratio = source_width / source_height
    if abs(source_ratio - target_ratio) > 0.03:
        raise RuntimeError(
            f"Gemini Pro 원본 비율이 16:9 정규화 허용 범위를 벗어났습니다: {source_width}x{source_height}"
        )
    if source_ratio > target_ratio:
        crop_width = round(source_height * target_ratio)
        left = (source_width - crop_width) // 2
        crop_box = (left, 0, left + crop_width, source_height)
    else:
        crop_height = round(source_width / target_ratio)
        top = (source_height - crop_height) // 2
        crop_box = (0, top, source_width, top + crop_height)
    normalized = image.crop(crop_box).resize(TARGET_SIZE, Image.Resampling.LANCZOS)
    output = io.BytesIO()
    normalized.save(output, format="PNG")
    return output.getvalue(), {
        "method": "center_crop_then_lanczos_resize",
        "source_size": [source_width, source_height],
        "crop_box": list(crop_box),
        "target_size": list(TARGET_SIZE),
    }


def _ocr_status(path: Path) -> dict[str, Any]:
    """OCR은 자동 승인에 쓰지 않고, 사람이 확인할 보조 자료로만 남긴다."""
    try:
        import cv2
        from app.services.info_surface.phase_b.ocr_readers import TesseractReader

        image = cv2.imread(str(path))
        if image is None:
            raise RuntimeError("PNG를 OCR 입력으로 읽을 수 없습니다.")
        texts = [text.strip() for text in TesseractReader().read_texts(image) if text.strip()]
        return {
            "status": "ADVISORY_REVIEW_REQUIRED",
            "reader": "tesseract",
            "detected_texts": texts,
            "automatic_approval": False,
        }
    except Exception as exc:  # OCR 도구 부재와 판독 실패도 검수 대상이다.
        return {
            "status": "UNAVAILABLE_OR_FAILED",
            "reader": "tesseract",
            "error": str(exc),
            "automatic_approval": False,
        }


def _load_review_dossier(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"기존 검수 dossier를 읽을 수 없습니다: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("scenes"), list):
        raise ValueError("기존 검수 dossier 형식이 올바르지 않습니다.")
    return payload


def _load_review_decisions(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"검토 결정 파일을 읽을 수 없습니다: {path}") from exc
    decisions = payload.get("decisions") if isinstance(payload, dict) else None
    if not isinstance(decisions, list):
        raise ValueError("검토 결정 파일에는 decisions 목록이 필요합니다.")
    return [item for item in decisions if isinstance(item, dict)]


def _require_regeneration_decisions(
    path: Path,
    scene_ids: set[str],
    dossier: dict[str, Any] | None = None,
) -> None:
    decisions = _load_review_decisions(path)
    approved = {
        str(item.get("scene_id")): item
        for item in decisions if isinstance(item, dict)
        and str(item.get("decision") or "").upper() == "REGENERATE"
        and str(item.get("reason") or "").strip()
    }
    missing = sorted(scene_ids - set(approved))
    if missing:
        raise ValueError(f"명시적 재생성 승인 또는 사유가 없는 장면입니다: {', '.join(missing)}")
    if dossier is None:
        return
    reviewed = {str(item.get("scene_id")): item for item in dossier["scenes"] if isinstance(item, dict)}
    for scene_id in sorted(scene_ids):
        item = approved[scene_id]
        expected_attempt = reviewed.get(scene_id, {}).get("current_attempt")
        if not isinstance(expected_attempt, int):
            raise ValueError(f"{scene_id}의 기존 검수 후보를 찾을 수 없습니다.")
        if item.get("reviewed_attempt") != expected_attempt:
            raise ValueError(
                f"{scene_id} 재생성 승인은 현재 검수 회차({expected_attempt})를 "
                "reviewed_attempt로 명시해야 합니다."
            )


def _record_manual_review(dossier: dict[str, Any], path: Path) -> dict[str, Any]:
    """현재 후보 회차를 지정한 사람의 승인·재생성 판단을 dossier에 고정한다."""
    decisions = {
        str(item.get("scene_id")): item
        for item in _load_review_decisions(path)
        if str(item.get("decision") or "").upper() in {"APPROVE", "REGENERATE"}
        and str(item.get("reason") or "").strip()
    }
    scenes = dossier.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("검수 dossier에 장면 목록이 없습니다.")
    expected_ids = {str(scene.get("scene_id")) for scene in scenes if isinstance(scene, dict)}
    if expected_ids != set(decisions):
        raise ValueError("승인 기록은 dossier의 모든 장면을 정확히 한 번씩 포함해야 합니다.")
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        decision = decisions[str(scene["scene_id"])]
        if decision.get("reviewed_attempt") != scene.get("current_attempt"):
            raise ValueError(f"{scene['scene_id']}의 reviewed_attempt가 현재 후보 회차와 다릅니다.")
        scene["decision"] = str(decision["decision"]).upper()
        scene["review_reason"] = str(decision["reason"]).strip()
        scene["reviewed_attempt"] = int(decision["reviewed_attempt"])
        scene["reviewed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    dossier["status"] = "APPROVED" if all(
        scene.get("decision") == "APPROVE" for scene in scenes if isinstance(scene, dict)
    ) else "ACTION_REQUIRED"
    return dossier


def _review_dossier(
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    by_scene = {str(item["scene_id"]): item for item in plan["scenes"]}
    previous = {
        str(item.get("scene_id")): item
        for item in (existing or {}).get("scenes", []) if isinstance(item, dict)
    }
    new_results = {str(item["scene_id"]): item for item in results}
    scenes: list[dict[str, Any]] = []
    for scene_id, scene in by_scene.items():
        prior = previous.get(scene_id, {})
        attempts = list(prior.get("attempts", []))
        if scene_id in new_results:
            attempts.append(new_results[scene_id])
        current = attempts[-1] if attempts else None
        scenes.append({
            "scene_id": scene_id,
            "scene_type": scene["scene_type"],
            "review_kind": scene["review_kind"],
            "current_attempt": current.get("attempt") if current else None,
            "attempts": attempts,
            "decision": "PENDING" if scene_id in new_results else prior.get("decision", "PENDING"),
            "decision_template": {
                "decision": "APPROVE 또는 REGENERATE",
                "reason": "검토 근거를 기록",
                "reviewed_attempt": "재생성 시 현재 검수 회차의 정수",
            },
        })
    return {
        "status": "PENDING_MANUAL_REVIEW",
        "automatic_regeneration": False,
        "review_contract": plan["review_contract"],
        "scenes": scenes,
    }


def execute(plan: dict[str, Any], output_dir: Path, *, scene_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """명시적으로 승인된 Gemini Pro 호출만 실행하고, 결과를 원장과 함께 저장한다."""
    if not plan["gemini_key_configured"]:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않아 유료 파일럿을 시작할 수 없습니다.")
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = runtime_config.get()
    character_reference = _canonical_character_reference()
    results: list[dict[str, Any]] = []
    planned_scenes = list(plan["_planned_scenes"])
    if scene_ids is not None:
        planned_scenes = [
            scene for scene in planned_scenes
            if str(scene["v5_render_contract"]["scene_id"]) in scene_ids
        ]
        missing = scene_ids - {str(scene["v5_render_contract"]["scene_id"]) for scene in planned_scenes}
        if missing:
            raise ValueError(f"재생성 대상에 없는 scene_id가 포함됐습니다: {', '.join(sorted(missing))}")
    for scene in planned_scenes:
        scene_id = str(scene["v5_render_contract"]["scene_id"])
        candidate_dir, attempt = _candidate_directory(output_dir, scene_id)
        background_path = candidate_dir / "background.png"
        final_path = candidate_dir / "final.png"
        prompt = prompt_for_scene(scene) or ""
        audit = ProviderRequestAudit.for_path(
            path=output_dir / "cost_ledger.json",
            scene_key=f"{scene_id}:attempt-{attempt:02d}",
            model=MODEL,
            unit_usd=float(cfg["img_cost_pro_2k_usd"]),
            usd_krw=float(cfg["usd_krw"]),
            budget_limit_krw=int(plan["preflight"]["budget_limit_krw"]),
            request_metadata={
                "policy_version": POLICY_VERSION,
                "e2e_run": True,
                "candidate_attempt": attempt,
                # 원문 프롬프트 대신 재현 검증에 필요한 해시만 원장에 남긴다.
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "verified_number_prompt_guard": "passed",
                "character_reference_sha256": character_reference["sha256"],
            },
        )
        NanaBananaProvider().generate(
            prompt=prompt,
            output_path=str(background_path),
            image_provider="gemini",
            gemini_model=MODEL,
            gemini_image_size="2K",
            gemini_service_tier="standard",
            gemini_max_attempts=1,
            gemini_request_audit=audit,
            gemini_reference_contract_declared=True,
            character_image_paths=[character_reference["path"]],
            suppress_legacy_style_lock=True,
            style_locked=True,
        )
        normalized_background, normalization = _normalize_to_target_canvas(background_path.read_bytes())
        if scene.get("v5_verified_overlays"):
            final_path.write_bytes(apply_verified_scene_facts(normalized_background, scene))
        else:
            final_path.write_bytes(normalized_background)
        background = _png_summary(background_path)
        final = _png_summary(final_path)
        if (final["width"], final["height"]) != TARGET_SIZE:
            raise RuntimeError(f"최종 PNG 해상도가 1920x1080이 아닙니다: {scene_id}")
        normalized_hash = hashlib.sha256(normalized_background).hexdigest()
        if bool(scene.get("v5_verified_overlays")) == (normalized_hash == final["sha256"]):
            raise RuntimeError(f"검증 오버레이 합성 결과가 장면 계약과 일치하지 않습니다: {scene_id}")
        results.append({
            "scene_id": scene_id,
            "attempt": attempt,
            "status": "completed",
            "background": background,
            "final": final,
            "normalization": normalization,
            "ocr": _ocr_status(final_path),
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="검증된 4장면 입력 JSON")
    parser.add_argument("--execute", action="store_true", help="Gemini Pro 유료 요청을 실제로 전송")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "out" / "three_goals_e2e")
    parser.add_argument("--run-id", help="실행 결과와 원장을 분리할 식별자")
    parser.add_argument("--rerun-scene", action="append", default=[], help="수동 검토 후 재생성할 scene_id")
    parser.add_argument("--review-decisions", type=Path, help="재생성 승인과 사유가 담긴 JSON 파일")
    parser.add_argument("--record-review", action="store_true", help="외부 호출 없이 dossier에 최종 검토 결정을 기록")
    args = parser.parse_args()

    plan = build_plan(args.input)
    plan.pop("_planned_scenes", None)
    rerun_scene_ids = {str(scene_id) for scene_id in args.rerun_scene}
    if args.record_review:
        if args.execute or rerun_scene_ids or not args.run_id or args.review_decisions is None:
            raise ValueError("최종 검토 기록에는 --run-id와 --review-decisions만 함께 사용합니다.")
        dossier_path = args.output_dir / args.run_id / "review_dossier.json"
        dossier = _record_manual_review(_load_review_dossier(dossier_path), args.review_decisions)
        dossier_path.write_text(json.dumps(dossier, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"mode": "review_recorded", "run_id": args.run_id, "review_dossier_path": str(dossier_path), "status": dossier["status"]}, ensure_ascii=False, indent=2))
        return 0
    if rerun_scene_ids and not args.execute:
        raise ValueError("재생성 대상 지정은 --execute와 함께만 사용할 수 있습니다.")
    if rerun_scene_ids and not args.run_id:
        raise ValueError("재생성에는 최초 실행의 --run-id가 필요합니다.")
    run_id = args.run_id or dt.datetime.now(dt.timezone.utc).strftime("gemini-pilot-%Y%m%dT%H%M%SZ")
    run_dir = args.output_dir / run_id
    existing_dossier: dict[str, Any] | None = None
    if rerun_scene_ids:
        if args.review_decisions is None:
            raise ValueError("재생성에는 --review-decisions 승인 파일이 필요합니다.")
        existing_dossier = _load_review_dossier(run_dir / "review_dossier.json")
        _require_regeneration_decisions(args.review_decisions, rerun_scene_ids, existing_dossier)
    elif args.execute and run_dir.exists():
        raise ValueError("동일 run-id 결과가 이미 있습니다. 새 run-id를 사용하세요.")
    if args.execute:
        # 실행 모드는 결과 파일과 원장을 남기므로 dry run과 분리해 명시적으로 선언한다.
        execution_plan = build_plan(args.input)
        plan["mode"] = "executing"
        plan["run_id"] = run_id
        plan["run_dir"] = str(run_dir)
        plan["results"] = execute(execution_plan, run_dir, scene_ids=rerun_scene_ids or None)
        dossier = _review_dossier(plan, plan["results"], existing_dossier)
        dossier_path = run_dir / "review_dossier.json"
        dossier_path.write_text(json.dumps(dossier, ensure_ascii=False, indent=2), encoding="utf-8")
        plan["review_dossier_path"] = str(dossier_path)
        plan["mode"] = "completed"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "report.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
