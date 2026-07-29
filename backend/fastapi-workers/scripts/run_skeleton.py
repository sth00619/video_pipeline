#!/usr/bin/env python3
"""P0/P0.5 V5 walking skeleton 단일 관통 실행기."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.cost_ledger import Bucket, BudgetExceeded, CostLedger, FxProvider, FxUnavailable
from app.v5.overlay.korean_overlay import FontMissing, OverlaySpec, apply_overlay
from app.v5.providers.bfl_flux_provider import BflError, BflFluxProvider, BflModel
from app.v5.scene.prompt_builder import BENCHMARK_SCENES, SceneSpec, build_prompt


OUT_DIR = ROOT / "out"


def run_one(spec: SceneSpec, subtitle: str, *, dry_run: bool) -> int:
    print(f"\n▶ SCENE: {spec.scene_id} ({spec.archetype} / {spec.emotion})")
    prompt = build_prompt(spec, character_position="right")
    print(f"[1] 프롬프트 생성 완료 ({len(prompt)}자)")
    ledger = CostLedger(video_id="v5_skeleton_demo", fx=FxProvider())
    model, width, height = BflModel.KLEIN_9B, 1280, 720
    estimated_usd = 0.015
    if not dry_run:
        try:
            provider = BflFluxProvider()
            estimated_usd = provider.estimate_cost_usd(model, width, height)
        except BflError as exc:
            print(f"[2] ERROR BFL 준비 실패: {exc}")
            return 2
    else:
        provider = None
    try:
        estimated_krw, rate = ledger.guard(Bucket.IMAGE_DRAFT, estimated_usd)
    except (FxUnavailable, BudgetExceeded) as exc:
        print(f"[2] ERROR 예산 사전 승인 실패: {exc}")
        return 2
    print(f"[2] 예산 승인: 예상 ${estimated_usd} = KRW {estimated_krw} (환율 {rate:.1f})")
    if dry_run:
        print("[3] DRY_RUN: BFL 호출을 생략했습니다.")
        return 0
    try:
        result = provider.generate(prompt, model=model, width=width, height=height, seed=42)
    except BflError as exc:
        ledger.record(scene_id=spec.scene_id, provider="bfl", model=model.value, request_kind="generate", bucket=Bucket.IMAGE_DRAFT, estimated_usd=estimated_usd, actual_usd=0.0, rate=rate, status=f"failed:{type(exc).__name__}")
        print(f"[3] ERROR 이미지 생성 실패: {exc}")
        return 3
    ledger.record(scene_id=spec.scene_id, provider="bfl", model=model.value, request_kind="generate", bucket=Bucket.IMAGE_DRAFT, estimated_usd=estimated_usd, actual_usd=result.actual_cost_usd, rate=rate, status="ok")
    try:
        final_png = apply_overlay(result.image_bytes, OverlaySpec(subtitle=subtitle, logo_text=os.environ.get("CHANNEL_LOGO_TEXT", "경제브리핑"), timestamp="2026.07"))
        print("[4] Pillow 한글 오버레이 합성 완료")
    except FontMissing as exc:
        print(f"[4] WARN 한글 글꼴 없음: 원본을 저장합니다. ({exc})")
        final_png = result.image_bytes
    OUT_DIR.mkdir(exist_ok=True)
    output = OUT_DIR / f"{spec.scene_id}.png"
    output.write_bytes(final_png)
    print(f"[5] 저장 완료: {output}")
    return 0


def main() -> int:
    dry_run = os.environ.get("DRY_RUN") == "1"
    print("### V5 DRY_RUN: 외부 BFL 호출 없음 ###" if dry_run else "### V5 P0.5: BFL 이미지 1장만 생성 ###")
    return run_one(BENCHMARK_SCENES[0], "그래서 관세가 무서운 거야.", dry_run=dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
