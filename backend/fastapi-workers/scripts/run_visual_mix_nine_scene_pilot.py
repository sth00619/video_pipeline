#!/usr/bin/env python3
"""기사형·상황형·정보형 3개씩을 한 원장으로 실행하는 9장면 파일럿."""
from __future__ import annotations

import argparse
import hashlib
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
from app.config import GEMINI_TEST_IMAGE_BUDGET_KRW
from app.models.article_evidence import ArticleCapture
from app.services.article.frame_editor import ArticleFrameEditor
from app.services.scene_frames.article_scene import ArticleSceneRenderer, ArticleSceneSpec
from app.services.scene_frames.emphasis_policy import BodyEmphasis, EmphasisPlan, TitleEmphasis
from app.v5.cost_ledger import Bucket, BudgetExceeded, CostLedger, FxProvider
from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider, GeminiProviderError
from run_visual_mix_nine_scene_preflight import build_preflight


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _reference_paths() -> tuple[dict[str, str], list[dict[str, str]]]:
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
    return {artifact["role"]: str(path) for artifact, path in zip(artifacts, paths)}, artifacts


def _article_result(asset: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """기사형은 원문 픽셀을 보존하며 결정론적 강조 레이어만 합성한다."""
    metadata = json.loads(Path(asset["metadata_path"]).read_text(encoding="utf-8"))
    capture = ArticleCapture.model_validate(metadata).model_copy(update={"local_path": asset["image_path"]})
    frame = ArticleFrameEditor().from_capture(capture)
    rendered = ArticleSceneRenderer().render(
        frame,
        ArticleSceneSpec(
            evidence_quote=capture.quote,
            key_phrase=capture.key_phrase or "",
            emphasis=EmphasisPlan(
                title=TitleEmphasis.NONE,
                body=BodyEmphasis.HIGHLIGHT_UNDERLINE,
            ),
        ),
    )
    plain_path = out_dir / f"{asset['scene_id']}_plain.png"
    emphasized_path = out_dir / f"{asset['scene_id']}.png"
    plain_path.parent.mkdir(parents=True, exist_ok=True)
    rendered.plain.save(plain_path, "PNG")
    rendered.emphasized.save(emphasized_path, "PNG")
    return {
        "scene_id": asset["scene_id"],
        "status": "verified_source_asset_emphasized",
        "plain_path": str(plain_path),
        "final_path": str(emphasized_path),
        "source_url": asset["source_url"],
        "emphasis": rendered.audit,
        "cost_status": "no_image_generation_cost",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--run-id", default="visual_mix_nine_scene_20260802")
    parser.add_argument("--execute", action="store_true", help="지정 시 상황형·정보형 6장을 Gemini로 생성합니다.")
    parser.add_argument("--scene-ids", nargs="+", help="재검수가 필요한 생성 장면만 선택합니다. 기사형 3장은 항상 원장에 포함합니다.")
    parser.add_argument("--resume", action="store_true", help="이미 성공한 PNG는 재호출하지 않고 원장만 복구합니다.")
    args = parser.parse_args()
    if not args.run_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("run-id는 영문·숫자·밑줄·하이픈만 사용할 수 있습니다.")

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    preflight = build_preflight(payload)
    if preflight["status"] != "ready":
        raise ValueError("검증된 서로 다른 기사형 자산 3개가 준비되지 않았습니다.")
    if not preflight["gemini_budget_preflight"]["allowed"]:
        raise BudgetExceeded("9장면 파일럿의 Gemini 이미지 예산이 허용 한도를 초과합니다.")

    out_dir = ROOT / "out" / "v5_pilot" / "visual_mix_nine_scene" / args.run_id
    manifest_path = out_dir / "_manifest.json"
    request_ledger_path = out_dir / "_request_ledger.json"
    base_summary: dict[str, Any] = {
        "run_id": args.run_id,
        "status": "preflight_passed_no_api_call" if not args.execute else "running",
        "mode_counts": preflight["mode_counts"],
        "article_assets": preflight["article_assets"],
        "article_scenes": preflight["article_scenes"],
        "gemini_budget_preflight": preflight["gemini_budget_preflight"],
        "generated_scenes": preflight["generated_scenes"],
        "article_policy": "verified_source_capture_only",
        "numeric_financial_overlay": "prohibited",
        "automatic_retry": False,
    }
    _write(manifest_path, base_summary)
    if not args.execute:
        print(json.dumps(base_summary, ensure_ascii=False, indent=2))
        return 0

    references_by_role, artifacts = _reference_paths()
    provider = GeminiProvider(use_batch=False)
    unit_usd = provider.estimate_cost_usd(GeminiModel.PRO, 2048, 1152)
    rate = FxProvider().usd_to_krw()
    generated_by_id = {scene["scene_id"]: scene for scene in payload["scenes"] if scene["visual_mode"] != "article_evidence"}
    contracts = {scene["scene_id"]: scene for scene in preflight["generated_scenes"]}
    # build_preflight에서 계약을 붙인 장면을 다시 얻어야 프롬프트 원문을 사용할 수 있다.
    from app.v5.scene.runtime_contract import attach_v5_scene_contracts

    planned = attach_v5_scene_contracts(list(generated_by_id.values()))
    if args.scene_ids:
        requested = set(args.scene_ids)
        planned = [scene for scene in planned if scene["scene_id"] in requested]
        missing = requested - {str(scene["scene_id"]) for scene in planned}
        if missing:
            raise ValueError(f"선택한 생성 장면을 찾을 수 없습니다: {', '.join(sorted(missing))}")
    ledger = CostLedger(video_id=args.run_id, fx=FxProvider())
    results = [_article_result(asset, out_dir) for asset in preflight["article_assets"]]
    for index, scene in enumerate(planned):
        scene_id = str(scene["scene_id"])
        raw_path = out_dir / f"{scene_id}_background.png"
        final_path = out_dir / f"{scene_id}.png"
        if args.resume and raw_path.is_file() and final_path.is_file() and raw_path.stat().st_size and final_path.stat().st_size:
            results.append({"scene_id": scene_id, "status": "recovered_existing_file", "final_path": str(final_path)})
            continue
        ledger.guard(Bucket.IMAGE_FINAL, unit_usd)
        contract = scene["v5_render_contract"]
        character_required = bool(contract["scene_spec"].get("character_required", True))
        reference_roles = ["character", "style"] if character_required else ["style"]
        references = [references_by_role[role] for role in reference_roles]
        audit = ProviderRequestAudit.for_path(
            path=request_ledger_path,
            scene_key=scene_id,
            model=GeminiModel.PRO.value,
            unit_usd=unit_usd,
            usd_krw=rate,
            budget_limit_krw=GEMINI_TEST_IMAGE_BUDGET_KRW,
            request_metadata={
                "automatic_retry": False,
                "reference_artifacts": artifacts,
                "reference_roles": reference_roles,
                "visual_mode": contract["visual_mode"],
                "visual_mode_contract": contract["visual_mode_contract"],
                "style_contract_version": contract["style_contract_version"],
                "selected_archetype": contract["selection"]["archetype"],
                "surface_caption": contract.get("surface_caption"),
                "prompt_sha256": hashlib.sha256(contract["prompt_en"].encode("utf-8")).hexdigest(),
            },
        )
        try:
            started = time.monotonic()
            generated = provider.generate(
                contract["prompt_en"], model=GeminiModel.PRO, width=2048, height=1152,
                seed=901 + index, reference_image_paths=references, request_audit=audit,
            )
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(generated.image_bytes)
            final_path.write_bytes(generated.image_bytes)
            entry = ledger.record(
                scene_id=scene_id, provider="gemini", model=GeminiModel.PRO.value,
                request_kind="generate", bucket=Bucket.IMAGE_FINAL, estimated_usd=unit_usd,
                actual_usd=None, rate=rate, status="ok",
                cost_status="unverified_until_console_reconciliation", metadata=generated.meta,
            )
            results.append({
                "scene_id": scene_id, "status": "ok", "seconds": round(time.monotonic() - started, 1),
                "background_path": str(raw_path), "final_path": str(final_path), "cost_status": entry.cost_status,
                "visual_mode_contract": contract["visual_mode_contract"],
                "style_contract_version": contract["style_contract_version"],
                "prompt_sha256": hashlib.sha256(contract["prompt_en"].encode("utf-8")).hexdigest(),
            })
        except (GeminiProviderError, BudgetExceeded, RuntimeError, ValueError) as exc:
            results.append({"scene_id": scene_id, "status": f"failed:{type(exc).__name__}", "message": str(exc)})
            break

    generated_results = [item for item in results if item["scene_id"] in contracts]
    completed = len(results) == 3 + len(planned) and all(
        item["status"] in {"ok", "verified_source_asset_emphasized", "recovered_existing_file"} for item in results
    )
    base_summary.update({
        "status": "completed" if completed else "incomplete_or_blocked",
        "reference_artifacts": artifacts,
        "cost_status": "unverified_until_console_reconciliation",
        "console_reconciliation_required_before_next_paid_stage": True,
        "request_ledger_path": str(request_ledger_path),
        "results": results,
        "generated_result_count": len(generated_results),
        "executed_generated_scene_ids": [str(scene["scene_id"]) for scene in planned],
        "ledger": ledger.summary(),
    })
    _write(manifest_path, base_summary)
    print(json.dumps(base_summary, ensure_ascii=False, indent=2))
    return 0 if completed else 4


if __name__ == "__main__":
    raise SystemExit(main())
