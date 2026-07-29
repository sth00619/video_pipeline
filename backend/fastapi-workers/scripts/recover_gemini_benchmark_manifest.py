#!/usr/bin/env python3
"""중단된 P1-b 실행의 저장 이미지에서 부분 원장을 복구한다.

이 스크립트는 이미지 API를 호출하지 않는다. 파일이 저장된 씬만 추정 비용을
예약 상태로 기록하고, 콘솔 청구 대조 전에는 실비를 확정하지 않는다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.cost_ledger import Bucket, CostLedger, FxProvider
from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider
from app.v5.scene.prompt_builder import BENCHMARK_SCENES


def main() -> int:
    provider = GeminiProvider(use_batch=False)
    per_image_usd = provider.estimate_cost_usd(GeminiModel.PRO, 2048, 1152)
    out_dir = ROOT / "out" / "benchmark" / "gemini_pro"
    ledger = CostLedger(video_id="p1b_gemini_pro_interrupted", fx=FxProvider())
    scenes: list[dict] = []
    for spec in BENCHMARK_SCENES:
        output = out_dir / f"{spec.scene_id}.png"
        if not output.exists():
            scenes.append({"scene_id": spec.scene_id, "archetype": spec.archetype, "status": "missing_or_interrupted"})
            continue
        _, rate = ledger.guard(Bucket.IMAGE_FINAL, per_image_usd)
        entry = ledger.record(scene_id=spec.scene_id, provider="gemini", model=GeminiModel.PRO.value, request_kind="generate", bucket=Bucket.IMAGE_FINAL, estimated_usd=per_image_usd, actual_usd=None, rate=rate, status="recovered_saved_output", cost_status="unverified_until_console_reconciliation", metadata={"recovered_from_saved_file": True})
        scenes.append({"scene_id": spec.scene_id, "archetype": spec.archetype, "status": "recovered_saved_output", "estimated_cost_usd": per_image_usd, "actual_cost_usd": None, "cost_status": entry.cost_status})
    payload = {
        "provider": "gemini", "model": GeminiModel.PRO.value, "run_status": "interrupted",
        "cost_status": "unverified_until_console_reconciliation", "console_reconciliation_required_before_retry": True,
        "scenes": scenes, "ledger": ledger.summary(),
    }
    (out_dir / "_manifest.partial.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS 부분 원장 복구: 성공 파일 {sum(1 for scene in scenes if scene['status'] == 'recovered_saved_output')}장")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
