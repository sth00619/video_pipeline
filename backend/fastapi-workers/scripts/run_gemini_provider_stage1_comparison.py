#!/usr/bin/env python3
"""동일한 네 장면 계약으로 Gemini Pro와 Flash를 장면당 한 번 비교한다."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
# 로컬 저장소에서는 fastapi-workers의 두 단계 위가 저장소 루트이고,
# 운영 컨테이너의 /app에서는 /app 자체가 실행용 저장소 루트다.
REPO = ROOT.parents[1] if len(ROOT.parents) > 1 else ROOT
sys.path.insert(0, str(ROOT))

from scripts.run_gemini_eight_scene_pilot import (  # noqa: E402
    _measure_generated_labels,
    _read_prices,
    _remove_historical_unbound_commodity_prompt,
    _sha,
    _write_json,
    prepare_pilot_scene,
)


MODELS = ("gemini-3-pro-image", "gemini-3.1-flash-image")
SCENES = (7, 15, 28, 35)
RESERVED_PER_ATTEMPT_KRW = 1600
TOTAL_RESERVED_KRW = 12800


def _canonical_sha(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_spec(spec: dict) -> None:
    """승인된 두 모델·네 장면·각 1회 비교 외의 유료 실행을 차단한다."""
    auth = spec.get("authorization") or {}
    if spec.get("paid_execution_authorized") is not True:
        raise RuntimeError("유료 비교 승인이 명세에 없습니다.")
    if tuple(spec.get("models") or ()) != MODELS:
        raise RuntimeError("승인된 비교 모델이 아닙니다.")
    if tuple(int(row.get("index", -1)) for row in spec.get("scenes") or []) != SCENES:
        raise RuntimeError("승인된 비교 장면은 07·15·28·35입니다.")
    if auth.get("external_image_post_limit") != 8 or auth.get("attempts_per_model_scene") != 1:
        raise RuntimeError("외부 POST는 모델×장면별 1회, 총 8회여야 합니다.")
    if auth.get("retry_on_failure") is not False:
        raise RuntimeError("1단계 비교는 자동 재시도를 허용하지 않습니다.")
    if auth.get("approved_total_reserved_krw") != TOTAL_RESERVED_KRW:
        raise RuntimeError("총 예약 상한은 ₩12,800이어야 합니다.")
    if auth.get("reserved_per_attempt_krw") != RESERVED_PER_ATTEMPT_KRW:
        raise RuntimeError("시도당 보수적 예약액은 ₩1,600이어야 합니다.")
    if spec.get("service_tier") != "standard" or spec.get("image_size") != "2K":
        raise RuntimeError("1단계는 standard 2K 비교입니다.")
    if spec.get("scene42_frozen_and_excluded") is not True:
        raise RuntimeError("scene42 동결 계약이 필요합니다.")


def prepare_rows(spec: dict, source_scenes: list[dict]) -> list[dict]:
    """승인 대본에서 모델 공통 최종 프롬프트와 참조 계보를 한 번만 만든다."""
    from app.v5.providers.gemini_provider import (
        ensure_gemini_reference_contract,
        select_contextual_reference_paths,
    )
    from app.workers.images_worker import _bounded_text_generation_prompt

    by_index = {int(row["index"]): row for row in source_scenes}
    prepared = []
    for item in spec["scenes"]:
        index = int(item["index"])
        scene = prepare_pilot_scene(by_index[index], item)
        scene["scene_spec"] = copy.deepcopy(item["scene_spec_override"])
        narration = str(scene.get("content") or scene.get("text") or "")
        source_prompt = _remove_historical_unbound_commodity_prompt(scene["prompt_en"], narration)
        bounded_prompt = _bounded_text_generation_prompt(
            f"{source_prompt}\n\nSCENE MEANING CONTRACT: {item['visual_contract']}",
            audit_target=scene,
        )
        reference_paths = select_contextual_reference_paths(bounded_prompt)
        references = [
            {"name": Path(path).name, "sha256": _sha(Path(path).read_bytes())}
            for path in reference_paths
        ]
        if not references or references[0] != spec["face_reference"]:
            raise RuntimeError(f"scene {index:02d}의 첫 참조가 승인 얼굴 v2가 아닙니다.")
        final_prompt = ensure_gemini_reference_contract(bounded_prompt, reference_paths)
        prepared.append({
            "index": index,
            "lane": item["lane"],
            "scene": scene,
            "narration": narration,
            "narration_sha256": _sha(narration.encode("utf-8")),
            "bounded_prompt": bounded_prompt,
            "bounded_prompt_sha256": _sha(bounded_prompt.encode("utf-8")),
            "final_prompt": final_prompt,
            "final_prompt_sha256": _sha(final_prompt.encode("utf-8")),
            "reference_paths": reference_paths,
            "references": references,
            "scene_contract_sha256": _canonical_sha(scene),
        })
    return prepared


def _public_row(row: dict) -> dict:
    hidden = {"scene", "narration", "bounded_prompt", "final_prompt", "reference_paths"}
    return {key: value for key, value in row.items() if key not in hidden}


def _contact_sheet(output: Path, manifest: dict) -> Path | None:
    successful = [row for row in manifest["results"] if row.get("raw_path")]
    if not successful:
        return None
    cell_w, cell_h, header = 768, 432, 54
    canvas = Image.new("RGB", (cell_w * 2, (cell_h + header) * 4), "#111827")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/AppleSDGothicNeo.ttc", 26)
    except OSError:
        font = ImageFont.load_default()
    columns = {MODELS[0]: 0, MODELS[1]: 1}
    rows = {scene: position for position, scene in enumerate(SCENES)}
    for result in successful:
        image = Image.open(result["raw_path"]).convert("RGB")
        image.thumbnail((cell_w, cell_h))
        x = columns[result["model"]] * cell_w
        y = rows[result["index"]] * (cell_h + header)
        draw.text((x + 12, y + 12), f"scene {result['index']:02d} | {result['model']}", fill="white", font=font)
        canvas.paste(image, (x + (cell_w - image.width) // 2, y + header))
    path = output / "provider_comparison_contact_sheet.png"
    canvas.save(path)
    return path


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
    source_path = REPO / spec["source"]["path"]
    source_bytes = source_path.read_bytes()
    if _sha(source_bytes) != spec["source"]["sha256"]:
        raise RuntimeError("Job52 보존 입력 해시가 바뀌었습니다.")
    prepared = prepare_rows(spec, json.loads(source_bytes))
    _, usd_krw = _read_prices(args.pricing_config)

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["GEMINI_REQUEST_STATE_PATH"] = str(output / "request_state.sqlite3")
    os.environ["GEMINI_PROJECT_SCOPE"] = f"provider02-{_sha(spec_bytes)[:12]}"
    for row in prepared:
        (output / f"scene_{row['index']:02d}_final_prompt.txt").write_text(row["final_prompt"], encoding="utf-8")
    manifest = {
        "version": spec["version"],
        "status": "authorized_preflight",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "spec_sha256": _sha(spec_bytes),
        "source_sha256": _sha(source_bytes),
        "models": list(MODELS),
        "model_selection_policy": "comparison_only_no_automatic_fallback",
        "same_prompt_and_references_required": True,
        "scene42_frozen_and_excluded": True,
        "provider_status_check": spec["provider_status_check"],
        "scenes": [_public_row(row) for row in prepared],
        "results": [],
    }
    _write_json(output / "preflight.json", manifest)
    if not args.execute:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY 미설정. 유료 실행을 시작하지 않습니다.")
    claim = output / "execute_once.claim"
    if claim.exists():
        raise RuntimeError("이미 시작된 비교입니다. 중복 POST를 차단합니다.")
    claim.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    from app import runtime_config
    from app.utils.budget import ProviderRequestAudit
    from app.utils.canary_visual_review import build_canary_visual_review_packet
    from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider

    runtime_config.update(gemini_scene_request_limit=1)
    ledger_path = output / "request_ledger.json"
    model_enums = {item.value: item for item in GeminiModel}
    # 시간대 편향을 줄이기 위해 장면마다 선행 모델을 교차한다.
    order = []
    for position, row in enumerate(prepared):
        pair = MODELS if position % 2 == 0 else tuple(reversed(MODELS))
        order.extend((row, model) for model in pair)
    manifest["status"] = "running"
    manifest["started_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(output / "manifest.json", manifest)
    for row, model in order:
        index = row["index"]
        result_row = {
            "index": index,
            "model": model,
            "final_prompt_sha256": row["final_prompt_sha256"],
            "references": row["references"],
            "status": "running",
        }
        manifest["results"].append(result_row)
        audit = ProviderRequestAudit.for_path(
            path=ledger_path,
            scene_key=f"provider02-stage1:{index}:{model}",
            model=model,
            unit_usd=float(Decimal(RESERVED_PER_ATTEMPT_KRW) / usd_krw),
            usd_krw=float(usd_krw),
            budget_limit_krw=TOTAL_RESERVED_KRW,
            request_metadata={
                "pilot_id": output.name,
                "contract_fingerprint": row["scene_contract_sha256"],
                "comparison_only": True,
                "automatic_fallback": False,
                "provider_status_check": spec["provider_status_check"],
            },
        )
        try:
            generated = GeminiProvider(use_batch=False).generate(
                row["bounded_prompt"],
                model=model_enums[model],
                reference_image_paths=row["reference_paths"],
                request_audit=audit,
            )
            raw_path = output / f"scene_{index:02d}_{'pro' if model == MODELS[0] else 'flash'}_raw.png"
            raw_path.write_bytes(generated.image_bytes)
            raw_sha = _sha(generated.image_bytes)
            result_row.update(status="pending_user_visual_review", raw_path=str(raw_path), raw_sha256=raw_sha)
            if row["lane"] == "deterministic_information":
                preview = output / f"scene_{index:02d}_{'pro' if model == MODELS[0] else 'flash'}_deterministic_preview.png"
                preview.write_bytes(generated.image_bytes)
                try:
                    from app.services.semantic_surface_text import render_semantic_surface_text
                    render_semantic_surface_text(copy.deepcopy(row["scene"]), str(preview))
                    result_row.update(deterministic_preview_status="rendered_not_approval", deterministic_preview_path=str(preview), deterministic_preview_sha256=_sha(preview.read_bytes()))
                except Exception as exc:
                    result_row.update(deterministic_preview_status="needs_review", deterministic_preview_error=f"{type(exc).__name__}: {exc}")
            else:
                measurement = _measure_generated_labels(raw_path, row["scene"]["screen_texts"])
                result_row["generated_label_measurement"] = measurement
                try:
                    from app.workers.images_worker import _inspect_generated_textless_image

                    strict_result = _inspect_generated_textless_image(
                        copy.deepcopy(row["scene"]), str(raw_path)
                    )
                    result_row["strict_generated_text_gate"] = {
                        "status": "passed",
                        "result": strict_result,
                    }
                except Exception as exc:
                    result_row["strict_generated_text_gate"] = {
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
            result_row["holistic_visual_review"] = build_canary_visual_review_packet(
                raw_path, raw_sha,
                automated_findings={"provider_comparison": "awaiting_user_full_frame_review", "approval": "blocked"},
            )
        except Exception as exc:
            result_row.update(status="provider_request_failed", error_type=type(exc).__name__, error=str(exc), approval_blocked=True)
        result_row["request_summary"] = audit.summary()
        _write_json(output / "manifest.json", manifest)

    manifest["status"] = "pending_user_visual_review"
    manifest["approval_blocked"] = True
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["external_image_post_count"] = sum(len((row.get("request_summary") or {}).get("entries") or []) for row in manifest["results"])
    sheet = _contact_sheet(output, manifest)
    if sheet:
        manifest["contact_sheet_path"] = str(sheet)
        manifest["contact_sheet_sha256"] = _sha(sheet.read_bytes())
    _write_json(output / "manifest.json", manifest)
    print(json.dumps({"status": manifest["status"], "external_image_post_count": manifest["external_image_post_count"], "contact_sheet_path": manifest.get("contact_sheet_path"), "results": [{"index": row["index"], "model": row["model"], "status": row["status"]} for row in manifest["results"]]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
