#!/usr/bin/env python3
"""Stage2와 동일한 scene00 계약으로 Flash를 두 번 격리 실증한다."""
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

from scripts.run_gemini_eight_scene_pilot import _sha, _write_json  # noqa: E402
from scripts.run_gemini_provider_stage2_full_comparison import (  # noqa: E402
    _model_prices,
    prepare_rows,
)


MODEL = "gemini-3.1-flash-image"
POST_LIMIT = 2


def _sheet(output: Path, results: list[dict]) -> Path | None:
    available = [row for row in results if row.get("raw_path")]
    if not available:
        return None
    canvas = Image.new("RGB", (1536, 486), "#111827")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/AppleSDGothicNeo.ttc", 25)
    except OSError:
        font = ImageFont.load_default()
    for column, row in enumerate(results[:2]):
        draw.text((column * 768 + 12, 12), f"scene00 Flash attempt {row['attempt_number']}", fill="white", font=font)
        if not row.get("raw_path"):
            draw.text((column * 768 + 12, 100), "공급자 요청 실패", fill="#fca5a5", font=font)
            continue
        image = Image.open(row["raw_path"]).convert("RGB")
        image.thumbnail((768, 432))
        canvas.paste(image, (column * 768 + (768 - image.width) // 2, 54))
    path = output / "scene00_flash_reproduction_contact_sheet.png"
    canvas.save(path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    source_bytes = args.source.read_bytes()
    if _sha(source_bytes) != args.source_sha256:
        raise RuntimeError("Job52 보존 입력 해시가 바뀌었습니다.")
    source_scenes = json.loads(source_bytes)
    spec = {
        "version": "wo-provider-02-scene00-flash-reproduction-v1",
        "source": {"path": str(args.source), "sha256": args.source_sha256},
        "common_prompt_contract": {"approved_wording_format": "plain_prose_no_array_or_json"},
    }
    row = next(item for item in prepare_rows(spec, source_scenes) if item["index"] == 0)
    prices, fx, pricing_sha = _model_prices()
    estimated_cap = prices[MODEL] * fx * Decimal(POST_LIMIT)
    if estimated_cap > Decimal("40000"):
        raise RuntimeError("공통 영상 예산 상한을 넘습니다.")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "scene_00_final_prompt.txt").write_text(row["final_prompt"], encoding="utf-8")
    manifest = {
        "version": spec["version"],
        "status": "authorized_preflight",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": args.source_sha256,
        "pricing_config_sha256": pricing_sha,
        "model": MODEL,
        "external_post_limit": POST_LIMIT,
        "automatic_retry": False,
        "central_price_estimate_krw": float(estimated_cap),
        "final_prompt_sha256": row["final_prompt_sha256"],
        "references": row["references"],
        "approved_texts": row["approved_texts"],
        "generated_texts": row["generated_texts"],
        "deterministic_texts": row["deterministic_texts"],
        "scene42_frozen_and_excluded": True,
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
        raise RuntimeError("이미 실행된 격리 실험입니다.")
    claim.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    os.environ["GEMINI_REQUEST_STATE_PATH"] = str(output / "request_state.sqlite3")
    os.environ["GEMINI_PROJECT_SCOPE"] = f"provider02-scene00-{_sha(row['final_prompt'].encode())[:12]}"
    from app import runtime_config
    from app.utils.budget import ProviderRequestAudit
    from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider

    runtime_config.update(gemini_scene_request_limit=1)
    ledger = output / "request_ledger.json"
    manifest["status"] = "running"
    _write_json(output / "manifest.json", manifest)
    for attempt_number in range(1, POST_LIMIT + 1):
        result = {"attempt_number": attempt_number, "status": "running"}
        manifest["results"].append(result)
        audit = ProviderRequestAudit.for_path(
            path=ledger,
            scene_key=f"provider02-scene00-flash-reproduction:{attempt_number}",
            model=MODEL,
            unit_usd=float(prices[MODEL]),
            usd_krw=float(fx),
            budget_limit_krw=float(estimated_cap),
            request_metadata={
                "comparison_only": True,
                "automatic_fallback": False,
                "automatic_retry": False,
                "attempt_policy": "two_independent_single_posts",
                "contract_fingerprint": row["contract_fingerprint"],
            },
        )
        try:
            generated = GeminiProvider(use_batch=False).generate(
                row["bounded_prompt"],
                model=GeminiModel.FLASH,
                reference_image_paths=row["reference_paths"],
                request_audit=audit,
            )
            raw = output / f"scene_00_flash_attempt_{attempt_number}.png"
            raw.write_bytes(generated.image_bytes)
            result.update(
                status="pending_user_visual_review",
                raw_path=str(raw),
                raw_sha256=_sha(generated.image_bytes),
            )
        except Exception as exc:
            result.update(status="provider_request_failed", error_type=type(exc).__name__, error=str(exc))
        result["request_summary"] = audit.summary()
        entries = result["request_summary"].get("entries") or []
        if entries and entries[-1].get("usage_metadata"):
            result["usage_metadata"] = entries[-1]["usage_metadata"]
        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(output / "manifest.json", manifest)

    sheet = _sheet(output, manifest["results"])
    manifest.update(
        status="pending_user_visual_review",
        completed_at=datetime.now(timezone.utc).isoformat(),
        actual_external_post_count=sum(
            int((item.get("request_summary") or {}).get("attempt_count") or 0)
            for item in manifest["results"]
        ),
    )
    if sheet:
        manifest["contact_sheet_path"] = str(sheet)
        manifest["contact_sheet_sha256"] = _sha(sheet.read_bytes())
    _write_json(output / "manifest.json", manifest)
    print(json.dumps({
        "status": manifest["status"],
        "results": [{"attempt_number": item["attempt_number"], "status": item["status"]} for item in manifest["results"]],
        "actual_external_post_count": manifest["actual_external_post_count"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
