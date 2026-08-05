"""V5 QualityGate는 빈 이미지와 재시도·강등 규칙을 결정론적으로 처리한다."""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.scene.prompt_builder import BENCHMARK_SCENES
from app.v5.scene.prompt_builder import SceneSpec
from app.v5.scene.quality_gate import QualityGate


def _png(*, detailed: bool) -> bytes:
    image = Image.new("RGB", (1280, 720), "#45607a")
    if detailed:
        draw = ImageDraw.Draw(image)
        for x in range(40, 1000, 120):
            draw.rectangle((x, 80, x + 85, 300), outline="#f6c344", width=10)
            draw.line((x, 650, x + 85, 360), fill="#6be7ff", width=8)
        draw.ellipse((820, 170, 1170, 590), fill="#f2b52d", outline="#40240f", width=12)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_blank_scene_is_rejected_and_then_downgraded():
    card = QualityGate.score(_png(detailed=False), BENCHMARK_SCENES[0])
    assert not card.passed
    assert "빈 배경 비율이 높음" in card.failures
    assert QualityGate.next_action(card, generation_attempt=0, retry_budget_available=True) == "retry_once"
    assert QualityGate.next_action(card, generation_attempt=1, retry_budget_available=True) == "downgrade_to_v4_cutaway"


def test_detailed_scene_passes_rule_based_gate():
    card = QualityGate.score(_png(detailed=True), BENCHMARK_SCENES[0])
    assert card.passed
    assert card.prop_detail_regions >= 3
    assert QualityGate.next_action(card, generation_attempt=0, retry_budget_available=True) == "pass"


def test_luminous_rectangle_outside_primary_requires_manual_review():
    image = Image.new("RGB", (1280, 720), "#45607a")
    draw = ImageDraw.Draw(image)
    # earnings_stage의 중앙 primary 표면은 제외하고, 좌측 벽에 생긴 발광 보조
    # 스크린만 감지 대상으로 만든다.
    draw.rectangle((0, 150, 160, 450), fill="#8dffff", outline="#173a53", width=14)
    draw.rectangle((310, 140, 990, 490), fill="#e6f4f0", outline="#40240f", width=14)
    for x in range(350, 900, 100):
        draw.line((x, 430, x + 55, 245), fill="#567a99", width=10)
    output = io.BytesIO()
    image.save(output, format="PNG")
    spec = SceneSpec("screen-panel", "briefing_podium", "confidence", "formal", "present", character_position="center")

    card = QualityGate.score(output.getvalue(), spec)

    assert not card.passed
    assert "primary 외 화면형 보조 소품 감지" in card.failures
    assert card.foreign_screen_panels
    assert QualityGate.next_action(card, generation_attempt=0, retry_budget_available=True) == "manual_review_required"


def test_luminous_primary_surface_is_excluded_from_screen_detection():
    image = Image.new("RGB", (1280, 720), "#45607a")
    draw = ImageDraw.Draw(image)
    # 중앙 표면의 발광 그래프는 정보 primary이므로 화면형 보조 소품으로 세지 않는다.
    draw.rectangle((310, 140, 990, 490), fill="#8dffff", outline="#173a53", width=14)
    for x in range(350, 900, 100):
        draw.line((x, 430, x + 55, 245), fill="#45607a", width=10)
    output = io.BytesIO()
    image.save(output, format="PNG")
    spec = SceneSpec("primary-only", "briefing_podium", "confidence", "formal", "present", character_position="center")

    card = QualityGate.score(output.getvalue(), spec)

    assert not card.foreign_screen_panels
