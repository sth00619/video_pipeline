#!/usr/bin/env python3
"""Job52 보존 대본 47장에 동일 계약을 적용해 Gemini 모델 정책을 비교한다."""
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

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1] if len(ROOT.parents) > 1 else ROOT
sys.path.insert(0, str(ROOT))

from scripts.run_gemini_eight_scene_pilot import (  # noqa: E402
    _measure_generated_labels,
    _remove_historical_unbound_commodity_prompt,
    _sha,
    _write_json,
)


MODELS = ("gemini-3-pro-image", "gemini-3.1-flash-image")
SCENES = tuple(index for index in range(48) if index != 42)
TOTAL_POSTS = len(SCENES) * len(MODELS)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _pricing_config() -> Path:
    return REPO / "backend/spring-app/src/main/java/com/pipeline/video/config/PricingConfig.java"


def _model_prices(spec: dict) -> tuple[dict[str, Decimal], Decimal, str]:
    """중앙 Java 가격표에서만 모델 단가와 예산 환율을 읽는다."""
    path = _pricing_config()
    raw = path.read_text(encoding="utf-8")
    profiles = spec.get("profiles") or {}
    pro_priority = str((profiles.get(MODELS[0]) or {}).get("service_tier") or "standard") == "priority"
    names = {
        MODELS[0]: (
            "GEMINI_3_PRO_IMAGE_PRIORITY_2K_USD"
            if pro_priority else "GEMINI_3_PRO_IMAGE_2K_USD"
        ),
        MODELS[1]: "GEMINI_3_1_FLASH_IMAGE_2K_USD",
    }
    prices: dict[str, Decimal] = {}
    for model, name in names.items():
        match = re.search(rf"{name}\s*=\s*BigDecimal\.valueOf\((?P<value>[0-9.]+)D?\)", raw)
        if not match:
            raise RuntimeError(f"PricingConfig.java에서 {name}을 찾지 못했습니다.")
        prices[model] = Decimal(match.group("value"))
    fx_match = re.search(r"USD_TO_KRW_BUDGET_RATE\s*=\s*BigDecimal\.valueOf\((?P<value>[0-9_]+)L?\)", raw)
    if not fx_match:
        raise RuntimeError("PricingConfig.java에서 예산 환율을 찾지 못했습니다.")
    fx = Decimal(fx_match.group("value").replace("_", ""))
    return prices, fx, _sha(path.read_bytes())


def validate_spec(spec: dict) -> None:
    auth = spec.get("authorization") or {}
    if spec.get("paid_execution_authorized") is not True:
        raise RuntimeError("유료 전체 비교 승인이 없습니다.")
    if tuple(spec.get("models") or ()) != MODELS:
        raise RuntimeError("승인 모델이 Pro/Flash 비교 계약과 다릅니다.")
    if auth.get("external_image_post_limit") != TOTAL_POSTS:
        raise RuntimeError(f"외부 POST 상한은 {TOTAL_POSTS}회여야 합니다.")
    if auth.get("attempts_per_model_scene") != 1 or auth.get("retry_on_failure") is not False:
        raise RuntimeError("장면·모델별 1회, 자동 재시도 없음 계약이 필요합니다.")
    if int(auth.get("approved_total_budget_cap_krw") or 0) > 40000:
        raise RuntimeError("5분 미만 영상 총비용 상한 40000원을 넘길 수 없습니다.")
    if spec.get("scene42_frozen_and_excluded") is not True:
        raise RuntimeError("scene42 동결·제외 계약이 필요합니다.")
    contract = spec.get("common_prompt_contract") or {}
    if contract.get("approved_wording_format") != "plain_prose_no_array_or_json":
        raise RuntimeError("대괄호 격리에서 검증한 평문 문구 계약이 필요합니다.")
    profiles = spec.get("profiles") or {}
    if profiles:
        pro = profiles.get(MODELS[0]) or {}
        flash = profiles.get(MODELS[1]) or {}
        if pro.get("service_tier") != "priority" or pro.get("thinking_level") is not None:
            raise RuntimeError("최종 정책 비교의 Pro 레인은 Priority이며 thinking level을 보내지 않아야 합니다.")
        if flash.get("service_tier") != "standard" or flash.get("thinking_level") != "high":
            raise RuntimeError("최종 정책 비교의 Flash 레인은 Standard + High thinking이어야 합니다.")
        if contract.get("semantic_basis_mode") != "operation_sanitized_no_narration_copy":
            raise RuntimeError("최종 정책 비교는 승인 내레이션 원문을 Gemini에 복사하지 않아야 합니다.")


def prepare_rows(spec: dict, source_scenes: list[dict]) -> list[dict]:
    """승인 대본을 바꾸지 않고 공통 화면 문구·프롬프트·참조 계약을 만든다."""
    from app.utils.image_text_contract import build_scene_text_contract
    from app.utils.scene_screen_text_planner import attach_scene_screen_texts
    from app.utils.scene_entity_binder import bind_scene_entities
    from app.v5.providers.gemini_provider import (
        ensure_gemini_reference_contract,
        select_contextual_reference_paths,
    )
    from app.workers.images_worker import _bounded_text_generation_prompt

    planned = attach_scene_screen_texts(source_scenes)
    bindings = bind_scene_entities(planned, verified_facts=[], keyword_news=[])
    binding_by_index = {int(item.scene_index): item for item in bindings}
    by_index = {int(scene["index"]): scene for scene in planned}
    requested_scenes = tuple(int(index) for index in (spec.get("scenes") or SCENES))
    missing_scenes = [index for index in requested_scenes if index not in by_index]
    if missing_scenes:
        raise ValueError(f"요청 장면이 입력에 없습니다: {missing_scenes}")
    rows = []
    for index in requested_scenes:
        scene = copy.deepcopy(by_index[index])
        binding = binding_by_index.get(index)
        if binding is not None:
            scene["core_entities"] = list(binding.core_entities)
            scene["core_figures"] = list(binding.core_figures)
        narration = str(scene.get("text_for_tts") or scene.get("content") or scene.get("text") or "").strip()
        text_contract = build_scene_text_contract(scene)
        source_prompt = _remove_historical_unbound_commodity_prompt(str(scene.get("prompt_en") or ""), narration)
        if (spec.get("common_prompt_contract") or {}).get("semantic_basis_mode") == "operation_sanitized_no_narration_copy":
            semantic_basis = (
                "SCENE MEANING CONTRACT: preserve the scene-specific causal objects and action already described above. "
                "The approved narration remains the TTS and subtitle source of truth, but its literal financial values are withheld from image generation. "
                "Do not invent, infer, translate, or render financial figures."
            )
        else:
            semantic_basis = (
                "SCENE MEANING CONTRACT: visually explain the causal meaning of the approved narration. "
                "Do not render the narration as a paragraph. Approved narration semantic basis: "
                + narration
            )
        bounded = _bounded_text_generation_prompt(f"{source_prompt}\n\n{semantic_basis}", audit_target=scene)
        # Stage 1에서 발견한 원인이 전체 비교에 다시 섞이지 않게 실제 최종
        # 프롬프트의 배열/JSON 승인 문구 형식을 실행 전에 차단한다.
        if "case-sensitive string list:" in bounded or "Follow these scene-specific text placements: [" in bounded:
            raise RuntimeError(f"scene {index:02d}에 과거 배열/JSON 문구 계약이 남았습니다.")
        reference_paths = select_contextual_reference_paths(bounded)
        final_prompt = ensure_gemini_reference_contract(bounded, reference_paths)
        rows.append({
            "index": index,
            "scene": scene,
            "narration_sha256": _sha(narration.encode("utf-8")),
            "approved_texts": text_contract["approved_texts"],
            "generated_texts": text_contract["generated_texts"],
            "deterministic_texts": text_contract["deterministic_texts"],
            "composition_density_profile": dict(scene.get("composition_density_profile") or {}),
            "bounded_prompt": bounded,
            "final_prompt": final_prompt,
            "final_prompt_sha256": _sha(final_prompt.encode("utf-8")),
            "reference_paths": reference_paths,
            "references": [
                {"name": Path(path).name, "sha256": _sha(Path(path).read_bytes())}
                for path in reference_paths
            ],
            "contract_fingerprint": _canonical_sha({
                "scene": scene,
                "text_contract": text_contract,
                "final_prompt_sha256": _sha(final_prompt.encode("utf-8")),
            }),
        })
    return rows


def _public_row(row: dict) -> dict:
    hidden = {"scene", "bounded_prompt", "final_prompt", "reference_paths"}
    return {key: value for key, value in row.items() if key not in hidden}


def _contact_sheets(output: Path, results: list[dict]) -> list[str]:
    """사용자 육안 검토를 위해 4개 장면씩 Pro/Flash 대조표를 만든다."""
    by_key = {(row["index"], row["model"]): row for row in results if row.get("raw_path")}
    paths = []
    cell_w, cell_h, header = 640, 358, 48
    try:
        font = ImageFont.truetype("/System/Library/Fonts/AppleSDGothicNeo.ttc", 22)
    except OSError:
        font = ImageFont.load_default()
    for page, start in enumerate(range(0, len(SCENES), 4), start=1):
        page_scenes = SCENES[start:start + 4]
        canvas = Image.new("RGB", (cell_w * 2, (cell_h + header) * len(page_scenes)), "#111827")
        draw = ImageDraw.Draw(canvas)
        for row_number, index in enumerate(page_scenes):
            for column, model in enumerate(MODELS):
                y = row_number * (cell_h + header)
                draw.text((column * cell_w + 10, y + 10), f"scene {index:02d} | {model}", fill="white", font=font)
                result = by_key.get((index, model))
                if not result:
                    draw.text((column * cell_w + 10, y + 80), "생성 실패/보류", fill="#fca5a5", font=font)
                    continue
                image = Image.open(result["raw_path"]).convert("RGB")
                image.thumbnail((cell_w, cell_h))
                canvas.paste(image, (column * cell_w + (cell_w - image.width) // 2, y + header))
        path = output / f"provider_full_comparison_contact_sheet_{page:02d}.jpg"
        canvas.save(path, quality=92)
        paths.append(str(path))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.execute and args.resume:
        raise RuntimeError("새 실행과 재개를 동시에 지정할 수 없습니다.")

    spec_bytes = args.spec.read_bytes()
    spec = json.loads(spec_bytes)
    validate_spec(spec)
    source_path = REPO / spec["source"]["path"]
    source_bytes = source_path.read_bytes()
    if _sha(source_bytes) != spec["source"]["sha256"]:
        raise RuntimeError("Job52 보존 입력 해시가 바뀌었습니다.")
    source_scenes = json.loads(source_bytes)
    if len(source_scenes) != 48 or {int(row["index"]) for row in source_scenes} != set(range(48)):
        raise RuntimeError("Job52 보존 입력이 scene00~47 완전 집합이 아닙니다.")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    project_scope = f"provider02-stage2-{_sha(spec_bytes)[:12]}"
    # app 모듈을 처음 import하는 prepare_rows()보다 먼저 영속 상태 경로와
    # 프로젝트 범위를 고정한다. 뒤늦은 runtime update는 안전상 금지돼 있다.
    os.environ["GEMINI_REQUEST_STATE_PATH"] = str(output / "request_state.sqlite3")
    os.environ["GEMINI_PROJECT_SCOPE"] = project_scope
    rows = prepare_rows(spec, source_scenes)
    prices, fx, pricing_sha = _model_prices(spec)
    estimated_cap = sum(prices[model] * fx for _ in SCENES for model in MODELS)
    approved_cap = Decimal(str(spec["authorization"]["approved_total_budget_cap_krw"]))
    if estimated_cap > approved_cap:
        raise RuntimeError(f"중앙 가격표 예상액 {estimated_cap}원이 승인 상한을 넘습니다.")

    for row in rows:
        (output / f"scene_{row['index']:02d}_final_prompt.txt").write_text(row["final_prompt"], encoding="utf-8")
    manifest = {
        "version": spec["version"],
        "status": "authorized_preflight",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "spec_sha256": _sha(spec_bytes),
        "source_sha256": _sha(source_bytes),
        "pricing_config_sha256": pricing_sha,
        "model_unit_usd": {model: float(value) for model, value in prices.items()},
        "budget_fx_krw_per_usd": float(fx),
        "central_price_estimate_krw": float(estimated_cap),
        "approved_budget_cap_krw": float(approved_cap),
        "models": list(MODELS),
        "scene42_frozen_and_excluded": True,
        "same_prompt_and_references_required": True,
        "scenes": [_public_row(row) for row in rows],
        "results": [],
    }
    _write_json(output / "preflight.json", manifest)
    if not args.execute and not args.resume:
        print(json.dumps({
            "status": manifest["status"],
            "scene_count": len(rows),
            "post_count": TOTAL_POSTS,
            "central_price_estimate_krw": float(estimated_cap),
        }, ensure_ascii=False, indent=2))
        return 0
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY 미설정. 유료 실행을 시작하지 않습니다.")
    claim = output / "execute_once.claim"
    manifest_path = output / "manifest.json"
    if args.resume:
        if not claim.exists() or not manifest_path.exists():
            raise RuntimeError("재개할 전체 비교 원장 또는 실행 claim이 없습니다.")
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        # 냉각 게이트가 외부 POST 전에 보류한 항목은 실패가 아니다. 실제 요청
        # 원장이나 raw가 있는 항목만 보존하고 나머지는 다시 pending으로 돌린다.
        manifest = previous
        manifest["results"] = [
            result for result in previous.get("results") or []
            if result.get("raw_path")
            or int((result.get("request_summary") or {}).get("attempt_count") or 0) > 0
        ]
        manifest.setdefault("resume_events", []).append({
            "resumed_at": datetime.now(timezone.utc).isoformat(),
            "preserved_attempted_results": len(manifest["results"]),
        })
    else:
        if claim.exists() or (output / "request_ledger.json").exists():
            raise RuntimeError("이미 시작된 전체 비교입니다. 중복 POST를 차단합니다.")
        claim.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    from app import runtime_config
    from app.utils.budget import ProviderRequestAudit
    from app.utils.image_request_control import ImageRequestHeld
    from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider
    from app.workers.images_worker import _inspect_generated_textless_image

    runtime_config.update(gemini_scene_request_limit=1)
    model_enums = {item.value: item for item in GeminiModel}
    ledger_path = output / "request_ledger.json"
    manifest["status"] = "running"
    manifest.setdefault("started_at", datetime.now(timezone.utc).isoformat())
    manifest["active_project_scope"] = project_scope
    _write_json(manifest_path, manifest)
    completed_keys = {
        (int(result["index"]), str(result["model"]))
        for result in manifest["results"]
        if result.get("raw_path")
        or int((result.get("request_summary") or {}).get("attempt_count") or 0) > 0
    }
    deferred = False
    for position, row in enumerate(rows):
        # 시간·순서 편향을 줄이되 동일 장면의 두 모델은 인접 실행한다.
        pair = MODELS if position % 2 == 0 else tuple(reversed(MODELS))
        for model in pair:
            index = row["index"]
            if (index, model) in completed_keys:
                continue
            print(f"[stage2] scene {index:02d} | {model} 시작", flush=True)
            result_row = {
                "index": index,
                "model": model,
                "status": "running",
                "final_prompt_sha256": row["final_prompt_sha256"],
                "references": row["references"],
                "approved_texts": row["approved_texts"],
                "generated_texts": row["generated_texts"],
                "deterministic_texts": row["deterministic_texts"],
                "profile": (spec.get("profiles") or {}).get(model) or {
                    "service_tier": "standard", "thinking_level": None,
                },
            }
            manifest["results"].append(result_row)
            audit = ProviderRequestAudit.for_path(
                path=ledger_path,
                scene_key=f"provider02-stage2:{index}:{model}",
                model=model,
                unit_usd=float(prices[model]),
                usd_krw=float(fx),
                budget_limit_krw=float(approved_cap),
                request_metadata={
                    "pilot_id": output.name,
                    "contract_fingerprint": row["contract_fingerprint"],
                    "comparison_only": True,
                    "automatic_fallback": False,
                    "attempt_policy": "one_external_post_no_retry",
                },
            )
            held = False
            try:
                profile = result_row["profile"]
                generated = GeminiProvider(use_batch=False).generate(
                    row["bounded_prompt"],
                    model=model_enums[model],
                    reference_image_paths=row["reference_paths"],
                    request_audit=audit,
                    service_tier=str(profile.get("service_tier") or "standard"),
                    thinking_level=profile.get("thinking_level"),
                )
                suffix = "pro" if model == MODELS[0] else "flash"
                raw_path = output / f"scene_{index:02d}_{suffix}_raw.png"
                raw_path.write_bytes(generated.image_bytes)
                result_row.update(
                    status="pending_user_visual_review",
                    raw_path=str(raw_path),
                    raw_sha256=_sha(generated.image_bytes),
                )
                if row["generated_texts"]:
                    result_row["ocr_measurement"] = _measure_generated_labels(raw_path, row["generated_texts"])
                try:
                    result_row["strict_generated_text_gate"] = {
                        "status": "passed",
                        "result": _inspect_generated_textless_image(copy.deepcopy(row["scene"]), str(raw_path)),
                    }
                except Exception as gate_error:
                    result_row["strict_generated_text_gate"] = {
                        "status": "failed",
                        "error_type": type(gate_error).__name__,
                        "error": str(gate_error),
                    }
            except Exception as exc:
                held = isinstance(exc, ImageRequestHeld)
                result_row.update(
                    status="needs_review_request_failed",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            result_row["request_summary"] = audit.summary()
            result_row["completed_at"] = datetime.now(timezone.utc).isoformat()
            attempted = int(result_row["request_summary"].get("attempt_count") or 0) > 0
            if held:
                # 실제 503 뒤 프로젝트 냉각 또는 외부 POST 전 deferred를 만나면
                # 다른 장면을 실패로 도배하지 않고 즉시 중단한다. 다음 재개는
                # 이미 실제 시도한 키를 건너뛰므로 동일 요청을 자동 재시도하지 않는다.
                if not attempted:
                    manifest["results"].pop()
                manifest["status"] = "deferred_provider_cooldown"
                manifest["deferred_at"] = datetime.now(timezone.utc).isoformat()
                manifest["deferred_before"] = {"index": index, "model": model, "attempted": attempted}
                deferred = True
            _write_json(manifest_path, manifest)
            if deferred:
                break
        if deferred:
            break

    manifest["contact_sheets"] = _contact_sheets(output, manifest["results"])
    if deferred:
        _write_json(manifest_path, manifest)
        print(json.dumps({
            "status": manifest["status"],
            "attempted_results": len(manifest["results"]),
            "generated": sum(1 for result in manifest["results"] if result.get("raw_path")),
            "deferred_before": manifest["deferred_before"],
        }, ensure_ascii=False, indent=2))
        return 0
    manifest["status"] = "pending_user_visual_review"
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(manifest_path, manifest)
    print(json.dumps({
        "status": manifest["status"],
        "generated": sum(1 for row in manifest["results"] if row.get("raw_path")),
        "failed": sum(1 for row in manifest["results"] if not row.get("raw_path")),
        "contact_sheets": len(manifest["contact_sheets"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
