#!/usr/bin/env python3
"""대괄호 없는 scene15 문구 계약을 Pro와 Flash에 각 한 번 실증한다."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1] if len(ROOT.parents) > 1 else ROOT
sys.path.insert(0, str(ROOT))

from scripts.run_gemini_eight_scene_pilot import _measure_generated_labels, _read_prices, _sha, _write_json  # noqa: E402
from scripts.run_gemini_provider_stage1_comparison import prepare_rows  # noqa: E402

MODELS = ("gemini-3-pro-image", "gemini-3.1-flash-image")
TOTAL_KRW = 3200
UNIT_KRW = 1600


def validate_spec(spec: dict) -> None:
    auth = spec.get("authorization") or {}
    scenes = spec.get("scenes") or []
    if spec.get("paid_execution_authorized") is not True:
        raise RuntimeError("대괄호 격리 유료 승인이 없습니다.")
    if tuple(spec.get("models") or ()) != MODELS:
        raise RuntimeError("승인된 비교 모델이 아닙니다.")
    if [int(item.get("index", -1)) for item in scenes] != [15]:
        raise RuntimeError("대괄호 격리는 scene15 한 장만 허용합니다.")
    if auth.get("external_image_post_limit") != 2 or auth.get("attempts_per_model_scene") != 1:
        raise RuntimeError("모델별 1회, 총 2회만 허용합니다.")
    if auth.get("retry_on_failure") is not False:
        raise RuntimeError("자동 재시도를 허용하지 않습니다.")
    if auth.get("approved_total_reserved_krw") != TOTAL_KRW or auth.get("reserved_per_attempt_krw") != UNIT_KRW:
        raise RuntimeError("승인 예약 상한이 다릅니다.")
    if spec.get("scene42_frozen_and_excluded") is not True:
        raise RuntimeError("scene42 동결 계약이 필요합니다.")


def _sheet(output: Path, results: list[dict]) -> Path | None:
    paths = [Path(row["raw_path"]) for row in results if row.get("raw_path")]
    if not paths:
        return None
    canvas = Image.new("RGB", (1536, 486), "#111827")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/AppleSDGothicNeo.ttc", 25)
    except OSError:
        font = ImageFont.load_default()
    for column, row in enumerate(results):
        if not row.get("raw_path"):
            continue
        image = Image.open(row["raw_path"]).convert("RGB")
        image.thumbnail((768, 432))
        x = column * 768
        draw.text((x + 12, 12), row["model"], fill="white", font=font)
        canvas.paste(image, (x + (768 - image.width) // 2, 54))
    path = output / "scene15_bracket_isolation_contact_sheet.png"
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
    row = prepare_rows(spec, json.loads(source_bytes))[0]
    if "[엇갈림]" in row["final_prompt"] or '[{"text"' in row["final_prompt"]:
        raise RuntimeError("최종 프롬프트에 대괄호 또는 JSON 표기가 남았습니다.")
    if row["final_prompt"].count("Approved wording 1 is 엇갈림.") != 1:
        raise RuntimeError("승인 문구 평문 계약이 정확히 한 번이어야 합니다.")
    _, usd_krw = _read_prices(args.pricing_config)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "scene_15_final_prompt.txt").write_text(row["final_prompt"], encoding="utf-8")
    manifest = {
        "version": spec["version"], "status": "authorized_preflight",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "spec_sha256": _sha(spec_bytes), "source_sha256": _sha(source_bytes),
        "final_prompt_sha256": row["final_prompt_sha256"], "references": row["references"],
        "bracket_or_json_artifact_present": False, "scene42_frozen_and_excluded": True,
        "results": [],
    }
    _write_json(output / "preflight.json", manifest)
    if not args.execute:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY 미설정")
    claim = output / "execute_once.claim"
    if claim.exists():
        raise RuntimeError("이미 시작된 격리 실험입니다.")
    claim.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    os.environ["GEMINI_REQUEST_STATE_PATH"] = str(output / "request_state.sqlite3")
    os.environ["GEMINI_PROJECT_SCOPE"] = f"bracket-{_sha(spec_bytes)[:12]}"
    from app import runtime_config
    from app.utils.budget import ProviderRequestAudit
    from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider
    from app.workers.images_worker import _inspect_generated_textless_image
    runtime_config.update(gemini_scene_request_limit=1)
    enum_by_value = {item.value: item for item in GeminiModel}
    ledger = output / "request_ledger.json"
    for model in MODELS:
        result = {"index": 15, "model": model, "status": "running"}
        manifest["results"].append(result)
        audit = ProviderRequestAudit.for_path(
            path=ledger, scene_key=f"provider02-bracket:15:{model}", model=model,
            unit_usd=float(Decimal(UNIT_KRW) / usd_krw), usd_krw=float(usd_krw),
            budget_limit_krw=TOTAL_KRW,
            request_metadata={"comparison_only": True, "automatic_fallback": False,
                              "contract_fingerprint": row["scene_contract_sha256"]},
        )
        try:
            generated = GeminiProvider(use_batch=False).generate(
                row["bounded_prompt"], model=enum_by_value[model],
                reference_image_paths=row["reference_paths"], request_audit=audit,
            )
            slug = "pro" if model == MODELS[0] else "flash"
            raw = output / f"scene_15_{slug}_raw.png"
            raw.write_bytes(generated.image_bytes)
            result.update(status="pending_user_visual_review", raw_path=str(raw), raw_sha256=_sha(generated.image_bytes))
            result["ocr_measurement"] = _measure_generated_labels(raw, row["scene"]["screen_texts"])
            try:
                result["strict_generated_text_gate"] = {"status": "passed", "result": _inspect_generated_textless_image(row["scene"], str(raw))}
            except Exception as exc:
                result["strict_generated_text_gate"] = {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}
        except Exception as exc:
            result.update(status="provider_request_failed", error_type=type(exc).__name__, error=str(exc))
        result["request_summary"] = audit.summary()
        _write_json(output / "manifest.json", manifest)
    manifest.update(status="pending_user_visual_review", approval_blocked=True,
                    finished_at=datetime.now(timezone.utc).isoformat(), external_image_post_count=2)
    sheet = _sheet(output, manifest["results"])
    if sheet:
        manifest["contact_sheet_path"] = str(sheet)
        manifest["contact_sheet_sha256"] = _sha(sheet.read_bytes())
    _write_json(output / "manifest.json", manifest)
    print(json.dumps({"status": manifest["status"], "results": [{"model": row["model"], "status": row["status"], "strict_gate": (row.get("strict_generated_text_gate") or {}).get("status")} for row in manifest["results"]]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
