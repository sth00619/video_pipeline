#!/usr/bin/env python3
"""P1-a: BFL Klein 8장 배경 스타일 벤치마크.

정확한 수치·한글은 넣지 않는다. 이 실행은 배경의 카툰 질감, 무대 전환,
비사실적 정보 소품 밀도만 비교하기 위한 유료 시험이다.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.cost_ledger import Bucket, BudgetExceeded, CostLedger, FxProvider
from app.v5.providers.bfl_flux_provider import BflError, BflFluxProvider, BflModel
from app.v5.scene.prompt_builder import BENCHMARK_SCENES, build_prompt


MAX_BENCHMARK_USD = 0.12


def main() -> int:
    provider = BflFluxProvider()
    model, width, height = BflModel.KLEIN_9B, 1280, 720
    per_image_usd = provider.estimate_cost_usd(model, width, height)
    estimated_total = per_image_usd * len(BENCHMARK_SCENES)
    if estimated_total > MAX_BENCHMARK_USD:
        print(f"ERROR P1-a 승인 상한 초과: ${estimated_total:.3f} > ${MAX_BENCHMARK_USD:.2f}")
        return 2

    out_dir = ROOT / "out" / "benchmark" / "bfl_klein"
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = CostLedger(video_id="p1a_bfl_klein", fx=FxProvider())
    manifest: list[dict] = []
    print(f"P1-a 시작: {len(BENCHMARK_SCENES)}장, 예상 최대 ${estimated_total:.3f}")

    for index, spec in enumerate(BENCHMARK_SCENES, start=1):
        prompt = build_prompt(spec)
        try:
            _, rate = ledger.guard(Bucket.IMAGE_DRAFT, per_image_usd)
        except BudgetExceeded as exc:
            print(f"ERROR {spec.scene_id}: 예산 차단 — {exc}")
            return 3
        started = time.monotonic()
        try:
            result = provider.generate(prompt, model=model, width=width, height=height, seed=40 + index)
        except BflError as exc:
            ledger.record(scene_id=spec.scene_id, provider="bfl", model=model.value, request_kind="generate", bucket=Bucket.IMAGE_DRAFT, estimated_usd=per_image_usd, actual_usd=0.0, rate=rate, status=f"failed:{type(exc).__name__}")
            manifest.append({"scene_id": spec.scene_id, "status": f"failed:{type(exc).__name__}"})
            print(f"ERROR {spec.scene_id}: {exc}")
            continue
        (out_dir / f"{spec.scene_id}.png").write_bytes(result.image_bytes)
        entry = ledger.record(scene_id=spec.scene_id, provider="bfl", model=model.value, request_kind="generate", bucket=Bucket.IMAGE_DRAFT, estimated_usd=per_image_usd, actual_usd=result.actual_cost_usd, rate=rate, status="ok")
        elapsed = round(time.monotonic() - started, 1)
        manifest.append({"scene_id": spec.scene_id, "archetype": spec.archetype, "status": "ok", "actual_cost_usd": result.actual_cost_usd, "actual_cost_krw": entry.actual_cost_krw, "seconds": elapsed, "seed": result.seed})
        print(f"PASS {spec.scene_id}: ${result.actual_cost_usd:.3f}, {elapsed}s")

    payload = {"provider": "bfl", "model": model.value, "purpose": "background_style_only", "estimated_total_usd": round(estimated_total, 6), "scenes": manifest, "ledger": ledger.summary()}
    (out_dir / "_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    successful = sum(1 for scene in manifest if scene["status"] == "ok")
    print(f"P1-a 완료: {successful}/{len(BENCHMARK_SCENES)}장, 원장 합계 KRW {ledger.total_spent_krw()}")
    return 0 if successful == len(BENCHMARK_SCENES) else 4


if __name__ == "__main__":
    raise SystemExit(main())
