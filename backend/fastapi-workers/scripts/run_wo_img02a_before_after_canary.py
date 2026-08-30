#!/usr/bin/env python3
"""Job52 네 장면을 현재 Pro Priority 계약으로 각 한 번 재생성한다."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1] if len(ROOT.parents) > 1 else ROOT
sys.path.insert(0, str(ROOT))

from scripts.run_gemini_eight_scene_pilot import _measure_generated_labels, _sha, _write_json  # noqa: E402
from scripts.run_gemini_provider_stage2_full_comparison import _model_prices, prepare_rows  # noqa: E402


MODEL = "gemini-3-pro-image"
SCENES = (0, 7, 15, 28)
UNIT_RESERVED_KRW = 1600
TOTAL_RESERVED_KRW = 6400


def _git_head() -> str:
    injected = os.environ.get("VIDEO_PIPELINE_RUNNER_COMMIT", "").strip()
    if injected:
        return injected
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True,
    ).strip()


def _validate_spec(spec: dict) -> None:
    auth = spec.get("authorization") or {}
    if spec.get("paid_execution_authorized") is not True:
        raise RuntimeError("WO-IMG-02-A 유료 실행 승인이 없습니다.")
    if spec.get("model") != MODEL or spec.get("service_tier") != "priority":
        raise RuntimeError("실증 모델은 Pro Priority로 고정합니다.")
    if tuple(spec.get("scenes") or ()) != SCENES:
        raise RuntimeError("실증 장면은 00·07·15·28입니다.")
    if auth.get("external_image_post_limit") != 4 or auth.get("attempts_per_scene") != 1:
        raise RuntimeError("장면별 1회, 총 4회만 허용합니다.")
    if auth.get("retry_on_failure") is not False:
        raise RuntimeError("자동 재시도를 허용하지 않습니다.")
    if auth.get("approved_total_reserved_krw") != TOTAL_RESERVED_KRW:
        raise RuntimeError("총 예약 상한은 ₩6,400이어야 합니다.")
    if auth.get("reserved_per_attempt_krw") != UNIT_RESERVED_KRW:
        raise RuntimeError("시도당 예약액은 ₩1,600이어야 합니다.")
    if spec.get("scene42_frozen_and_excluded") is not True:
        raise RuntimeError("scene42 동결 계약이 필요합니다.")


def _before_after_sheet(output: Path, results: list[dict], source_dir: Path) -> Path:
    cell_w, cell_h, header = 768, 432, 54
    canvas = Image.new("RGB", (cell_w * 2, (cell_h + header) * len(SCENES)), "#111827")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/AppleSDGothicNeo.ttc", 25)
    except OSError:
        font = ImageFont.load_default()
    by_scene = {int(row["index"]): row for row in results}
    for position, index in enumerate(SCENES):
        y = position * (cell_h + header)
        for column, label in enumerate(("Job52 before", "current Pro Priority after")):
            draw.text((column * cell_w + 12, y + 12), f"scene {index:02d} | {label}", fill="white", font=font)
        before = source_dir / f"scene_{index:03d}.png"
        after_value = by_scene.get(index, {}).get("final_path") or by_scene.get(index, {}).get("raw_path")
        for column, path in enumerate((before, Path(after_value) if after_value else None)):
            if path is None or not path.is_file():
                draw.text((column * cell_w + 20, y + 100), "생성 결과 없음", fill="#fca5a5", font=font)
                continue
            image = Image.open(path).convert("RGB")
            image.thumbnail((cell_w, cell_h))
            canvas.paste(image, (column * cell_w + (cell_w - image.width) // 2, y + header))
    path = output / "wo_img02a_job52_before_after_contact_sheet.jpg"
    canvas.save(path, quality=94)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    spec_bytes = args.spec.read_bytes()
    spec = json.loads(spec_bytes)
    _validate_spec(spec)
    source_path = REPO / spec["source"]["path"]
    source_bytes = source_path.read_bytes()
    if _sha(source_bytes) != spec["source"]["sha256"]:
        raise RuntimeError("Job52 보존 입력 해시가 바뀌었습니다.")
    source_scenes = json.loads(source_bytes)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # prepare_rows()가 app 모듈을 처음 불러오기 전에 영속 상태 경로를 고정한다.
    # 뒤에서 환경 변수를 바꾸면 image_request_control은 기본 비활성 저장소를
    # 이미 캐시하므로 외부 POST 전에 전 장면이 보류된다.
    os.environ["GEMINI_REQUEST_STATE_PATH"] = str(output / "request_state.sqlite3")
    os.environ["GEMINI_PROJECT_SCOPE"] = f"wo-img02a-{_sha(spec_bytes)[:12]}"
    comparison_spec = {
        "profiles": {MODEL: {"service_tier": "priority"}},
        "common_prompt_contract": {
            "approved_wording_format": "plain_prose_no_array_or_json",
            "semantic_basis_mode": "operation_sanitized_no_narration_copy",
        },
    }
    # 운영 ImagesWorker가 생성 직전에 수행하는 V5 계약 부착을 실증 harness도
    # 반드시 동일하게 수행한다. 이 단계가 빠지면 raw는 생성돼도 결정론 수치
    # 오버레이 계획이 없어 최종 경로를 검증할 수 없다.
    from app.utils.scene_screen_text_planner import attach_scene_screen_texts
    from app.v5.scene.runtime_contract import attach_v5_scene_contracts
    # 보존된 Job52 전체 48장에는 당시 유효했던 과거 파일럿 archetype도
    # 포함된다. 네 장면 canary가 선택하지 않은 과거 장면까지 최신 V5 계약으로
    # 재검증하면 외부 POST 전에 무관한 장면 때문에 실행이 중단된다. 운영 경로의
    # 선택 장면 재생성과 동일하게 이번 실행 대상만 먼저 고른 뒤 계약을 붙인다.
    selected_source_scenes = [
        copy.deepcopy(scene)
        for scene in source_scenes
        if int(scene.get("index", -1)) in SCENES
    ]
    planned_scenes = attach_v5_scene_contracts(attach_scene_screen_texts(selected_source_scenes))
    rows = [row for row in prepare_rows(comparison_spec, planned_scenes) if row["index"] in SCENES]
    if tuple(row["index"] for row in rows) != SCENES:
        raise RuntimeError("네 장면의 준비 순서가 계약과 다릅니다.")

    prices, fx, pricing_sha = _model_prices(comparison_spec)
    estimated_krw = prices[MODEL] * fx * len(rows)
    if estimated_krw > Decimal(TOTAL_RESERVED_KRW):
        raise RuntimeError("중앙 가격표 예상액이 승인 예약 상한을 넘습니다.")

    for row in rows:
        (output / f"scene_{row['index']:02d}_final_prompt.txt").write_text(row["final_prompt"], encoding="utf-8")

    manifest = {
        "version": spec["version"],
        "status": "authorized_preflight",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operational_contract_commit": spec["operational_contract_commit"],
        "runner_commit": _git_head(),
        "spec_sha256": _sha(spec_bytes),
        "source_sha256": _sha(source_bytes),
        "pricing_config_sha256": pricing_sha,
        "model": MODEL,
        "service_tier": "priority",
        "central_price_estimate_krw": float(estimated_krw),
        "approved_reserved_cap_krw": TOTAL_RESERVED_KRW,
        "scene42_frozen_and_excluded": True,
        "scenes": [
            {
                key: value for key, value in row.items()
                if key not in {"scene", "bounded_prompt", "final_prompt", "reference_paths"}
            }
            for row in rows
        ],
        "results": [],
    }
    _write_json(output / "preflight.json", manifest)
    if not args.execute:
        print(json.dumps({"status": manifest["status"], "scenes": list(SCENES), "estimated_krw": float(estimated_krw)}, ensure_ascii=False, indent=2))
        return 0
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY 미설정. 유료 실행을 시작하지 않습니다.")
    claim = output / "execute_once.claim"
    if claim.exists():
        raise RuntimeError("이미 시작된 WO-IMG-02-A 실행입니다.")
    claim.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    from app import runtime_config
    from app.utils.budget import ProviderRequestAudit
    from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider
    from app.workers.images_worker import ImagesWorker, _inspect_generated_textless_image, _inspect_generated_visual_image

    runtime_config.update(gemini_scene_request_limit=1)
    ledger = output / "request_ledger.json"
    manifest["status"] = "running"
    manifest["started_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(output / "manifest.json", manifest)
    for row in rows:
        index = row["index"]
        result = {
            "index": index,
            "status": "running",
            "approved_texts": row["approved_texts"],
            "generated_texts": row["generated_texts"],
            "deterministic_texts": row["deterministic_texts"],
            "final_prompt_sha256": row["final_prompt_sha256"],
            "references": row["references"],
        }
        manifest["results"].append(result)
        audit = ProviderRequestAudit.for_path(
            path=ledger,
            scene_key=f"wo-img02a:{index}:pro-priority",
            model=MODEL,
            unit_usd=float(prices[MODEL]),
            usd_krw=float(fx),
            budget_limit_krw=TOTAL_RESERVED_KRW,
            request_metadata={
                "operational_contract_commit": spec["operational_contract_commit"],
                "runner_commit": manifest["runner_commit"],
                "contract_fingerprint": row["contract_fingerprint"],
                "attempt_policy": "one_external_post_no_retry",
            },
        )
        try:
            generated = GeminiProvider(use_batch=False).generate(
                row["bounded_prompt"],
                model=GeminiModel.PRO,
                reference_image_paths=row["reference_paths"],
                request_audit=audit,
                service_tier="priority",
            )
            raw = output / f"scene_{index:02d}_pro_priority_raw.png"
            raw.write_bytes(generated.image_bytes)
            result.update(status="pending_user_visual_review", raw_path=str(raw), raw_sha256=_sha(generated.image_bytes))
            if row["generated_texts"]:
                result["ocr_measurement"] = _measure_generated_labels(raw, row["generated_texts"])
            try:
                result["base_raster_text_gate"] = {
                    "status": "passed",
                    "result": _inspect_generated_textless_image(copy.deepcopy(row["scene"]), str(raw)),
                }
            except Exception as exc:
                result["base_raster_text_gate"] = {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}

            # 승인 문구가 실제 모니터·팻말에 붙었는지는 현재 자동 좌표 계약이
            # 완성되지 않았다. 단일 표면 검사기를 다중 표면 장면에 적용해 0/4를
            # 만드는 대신, 육안 보류를 명시하고 결정론 수치 표면과 분리한다.
            result["generated_text_anchor_gate"] = {
                "status": "pending_user_visual_review" if row["generated_texts"] else "not_applicable",
                "reason": "다중 생성문자 표면의 픽셀 좌표 결박은 아직 자동 승인하지 않습니다.",
            }

            final_scene = copy.deepcopy(row["scene"])
            final = output / f"scene_{index:02d}_pro_priority_final.png"
            shutil.copyfile(raw, final)
            if row["deterministic_texts"]:
                try:
                    ImagesWorker()._apply_image_overlays(final_scene, str(final))
                    visual_result = _inspect_generated_visual_image(final_scene, str(final))
                    result["deterministic_surface_gate"] = {
                        "status": "passed",
                        "surface_detection": final_scene.get("deterministic_surface_detection"),
                        "final_frame_text_integrity": final_scene.get("final_frame_text_integrity"),
                        "visual_result": visual_result,
                    }
                    result.update(final_path=str(final), final_sha256=_sha(final.read_bytes()))
                except Exception as exc:
                    final.unlink(missing_ok=True)
                    result["deterministic_surface_gate"] = {
                        "status": "failed", "error_type": type(exc).__name__, "error": str(exc),
                        "surface_detection": final_scene.get("deterministic_surface_detection"),
                    }
                    result["status"] = "rejected_finalization_failed"
            else:
                result["deterministic_surface_gate"] = {"status": "not_applicable"}
                result.update(final_path=str(final), final_sha256=_sha(final.read_bytes()))
        except Exception as exc:
            result.update(status="provider_request_failed", error_type=type(exc).__name__, error=str(exc))
        result["request_summary"] = audit.summary()
        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(output / "manifest.json", manifest)

    source_images = REPO / spec["before_images_dir"]
    sheet = _before_after_sheet(output, manifest["results"], source_images)
    manifest.update(
        status="pending_user_visual_review",
        completed_at=datetime.now(timezone.utc).isoformat(),
        external_image_post_count=sum(int((row.get("request_summary") or {}).get("attempt_count") or 0) for row in manifest["results"]),
        contact_sheet_path=str(sheet),
        contact_sheet_sha256=_sha(sheet.read_bytes()),
        automatic_and_visual_judgment_are_separate=True,
    )
    _write_json(output / "manifest.json", manifest)
    print(json.dumps({
        "status": manifest["status"],
        "generated": sum(1 for row in manifest["results"] if row.get("raw_path")),
        "failed": sum(1 for row in manifest["results"] if not row.get("raw_path")),
        "contact_sheet": str(sheet),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
