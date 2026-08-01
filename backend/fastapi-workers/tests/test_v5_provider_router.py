"""V5 라우터는 벤치마크 근거·예산 가드·명시적 강등을 지킨다."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw
import io

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.cost_ledger import Bucket, CostLedger
from app.v5.providers.bfl_flux_provider import ImageResult
from app.v5.providers.router import (
    ArchetypeApprovalRequired,
    CutawayRequired,
    FinalLaneApprovalRequired,
    HumanRegenerationDecisionRequired,
    ImageProviderRouter,
    ProviderAdapter,
    RenderSpec,
)
from app.v5.scene.prompt_builder import BENCHMARK_SCENES


def _adapter(name: str, model: str, bucket: Bucket, cost: float) -> ProviderAdapter:
    return ProviderAdapter(
        name=name, model=model, bucket=bucket,
        estimate_cost_usd=lambda _width, _height: cost,
        generate=lambda spec: ImageResult(b"image", model, spec.width, spec.height, spec.seed, None, "test-request"),
    )


def _router(*, final_lane_approved: bool = False) -> ImageProviderRouter:
    return ImageProviderRouter(
        gemini_pro=_adapter("gemini_pro", "gemini-3-pro-image", Bucket.IMAGE_FINAL, .14),
        bfl_klein=_adapter("bfl_klein", "flux-2-klein-9b", Bucket.IMAGE_DRAFT, .02),
        final_lane_approved=final_lane_approved,
    )


def _ledger(monkeypatch) -> CostLedger:
    monkeypatch.setenv("FX_USD_KRW", "1500")
    return CostLedger("router-test")


def test_final_scenes_route_to_gemini_and_drafts_to_klein(monkeypatch):
    router = _router()
    hero = RenderSpec(BENCHMARK_SCENES[0], "prompt", "hero")
    draft = RenderSpec(BENCHMARK_SCENES[0], "prompt", "draft")
    assert router.decide(hero, _ledger(monkeypatch)).provider == "gemini_pro"
    assert router.decide(draft, _ledger(monkeypatch)).provider == "bfl_klein"


def test_final_scene_uses_klein_only_when_gemini_final_budget_is_short(monkeypatch):
    ledger = _ledger(monkeypatch)
    ledger.record(
        scene_id="spent", provider="test", model="test", request_kind="reserve", bucket=Bucket.IMAGE_FINAL,
        estimated_usd=4.55, actual_usd=4.55, rate=1500, status="ok",
    )
    decision = _router().decide(RenderSpec(BENCHMARK_SCENES[0], "prompt", "body"), ledger)
    assert decision.provider == "bfl_klein"


def test_router_records_every_render_and_never_makes_a_silent_cutaway(monkeypatch):
    ledger = _ledger(monkeypatch)
    result = _router(final_lane_approved=True).render(RenderSpec(BENCHMARK_SCENES[0], "prompt", "hero"), ledger)
    assert result.model == "gemini-3-pro-image"
    assert ledger.summary()["entries"][-1]["provider"] == "gemini_pro"

    exhausted = _ledger(monkeypatch)
    for bucket in (Bucket.IMAGE_FINAL, Bucket.IMAGE_DRAFT):
        exhausted.record(
            scene_id="spent", provider="test", model="test", request_kind="reserve", bucket=bucket,
            estimated_usd=100, actual_usd=100, rate=1500, status="ok",
        )
    try:
        _router(final_lane_approved=True).render(RenderSpec(BENCHMARK_SCENES[0], "prompt", "hero"), exhausted)
        assert False, "컷어웨이 강등은 조용한 이미지 대체가 아니라 명시적 예외여야 합니다."
    except CutawayRequired:
        pass


def _blank_png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (1280, 720), "#45607a").save(output, format="PNG")
    return output.getvalue()


def _detailed_png() -> bytes:
    image = Image.new("RGB", (1280, 720), "#45607a")
    draw = ImageDraw.Draw(image)
    for x in range(40, 1000, 120):
        draw.rectangle((x, 80, x + 85, 300), outline="#f6c344", width=10)
        draw.line((x, 650, x + 85, 360), fill="#6be7ff", width=8)
    draw.ellipse((820, 170, 1170, 590), fill="#f2b52d", outline="#40240f", width=12)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _foreign_screen_png() -> bytes:
    image = Image.new("RGB", (1280, 720), "#45607a")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 150, 160, 450), fill="#8dffff", outline="#173a53", width=14)
    draw.rectangle((310, 140, 990, 490), fill="#e6f4f0", outline="#40240f", width=14)
    for x in range(350, 900, 100):
        draw.line((x, 430, x + 55, 245), fill="#567a99", width=10)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_quality_gate_retries_exactly_once_and_records_both_attempts(monkeypatch):
    calls = iter([_blank_png(), _detailed_png()])
    adapter = ProviderAdapter(
        name="gemini_pro", model="gemini-3-pro-image", bucket=Bucket.IMAGE_FINAL,
        estimate_cost_usd=lambda _width, _height: .14,
        generate=lambda spec: ImageResult(next(calls), "gemini-3-pro-image", spec.width, spec.height, spec.seed, None, "test-request"),
    )
    router = ImageProviderRouter(
        gemini_pro=adapter, bfl_klein=_adapter("bfl_klein", "flux-2-klein-9b", Bucket.IMAGE_DRAFT, .02),
        final_lane_approved=True,
    )
    ledger = _ledger(monkeypatch)
    result, card = router.render_checked(RenderSpec(BENCHMARK_SCENES[0], "prompt", "hero"), ledger, retry_budget_available=True)
    assert result.image_bytes == _detailed_png()
    assert card.passed
    assert len(ledger.summary()["entries"]) == 2


def test_screen_panel_failure_never_triggers_automatic_regeneration(monkeypatch):
    calls = 0

    def generate(spec):
        nonlocal calls
        calls += 1
        return ImageResult(_foreign_screen_png(), "gemini-3-pro-image", spec.width, spec.height, spec.seed, None, "test-request")

    adapter = ProviderAdapter(
        name="gemini_pro", model="gemini-3-pro-image", bucket=Bucket.IMAGE_FINAL,
        estimate_cost_usd=lambda _width, _height: .14, generate=generate,
    )
    router = ImageProviderRouter(
        gemini_pro=adapter, bfl_klein=_adapter("bfl_klein", "flux-2-klein-9b", Bucket.IMAGE_DRAFT, .02),
        final_lane_approved=True,
    )
    ledger = _ledger(monkeypatch)
    scene = BENCHMARK_SCENES[0]
    scene = type(scene)("screen-panel", "briefing_podium", "confidence", "formal", "present", character_position="center")

    try:
        router.render_checked(RenderSpec(scene, "prompt", "hero"), ledger, retry_budget_available=True)
        assert False, "화면형 보조 소품은 사람 승인 없이 재생성하면 안 됩니다."
    except HumanRegenerationDecisionRequired:
        pass
    assert calls == 1
    assert len(ledger.summary()["entries"]) == 1


def test_unapproved_final_lane_cannot_make_a_paid_render(monkeypatch):
    try:
        _router().render(RenderSpec(BENCHMARK_SCENES[0], "prompt", "hero"), _ledger(monkeypatch))
        assert False, "오염 검증 전 최종 lane은 차단되어야 합니다."
    except FinalLaneApprovalRequired:
        pass


def test_default_final_lane_is_open_but_earnings_stage_remains_blocked(monkeypatch):
    router = ImageProviderRouter(
        gemini_pro=_adapter("gemini_pro", "gemini-3-pro-image", Bucket.IMAGE_FINAL, .14),
        bfl_klein=_adapter("bfl_klein", "flux-2-klein-9b", Bucket.IMAGE_DRAFT, .02),
    )
    scene = type(BENCHMARK_SCENES[0])(
        "earnings-blocked", "earnings_stage", "confidence", "formal", "present", character_position="center",
    )
    ledger = _ledger(monkeypatch)

    try:
        router.render(RenderSpec(scene, "prompt", "hero"), ledger)
        assert False, "earnings_stage는 개별 재검증 전 실비 생성이 차단돼야 합니다."
    except ArchetypeApprovalRequired:
        pass
    assert not ledger.summary()["entries"]
