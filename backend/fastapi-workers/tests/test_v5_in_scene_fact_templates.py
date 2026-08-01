"""그림 내부 소품 템플릿 회귀 테스트."""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.overlay.diegetic_fact_overlay import SurfaceAnchor, VerifiedFact
from app.v5.overlay.in_scene_fact_templates import InSceneTemplate, apply_checkout_total


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (1000, 600), "#27435b").save(output, format="PNG")
    return output.getvalue()


def test_checkout_template_changes_only_the_declared_display_interior():
    base = _png()
    rendered = apply_checkout_total(
        base,
        VerifiedFact("코스피 종가", "5663.24", "facts[0]", SurfaceAnchor(.10, .20, .30, .20, "embedded_monitor")),
        InSceneTemplate("checkout_total", .10, .20, .30, .20),
    )
    before = Image.open(io.BytesIO(base)).convert("RGB")
    after = Image.open(io.BytesIO(rendered)).convert("RGB")
    assert before.getpixel((30, 30)) == after.getpixel((30, 30))
    assert before.getpixel((200, 180)) != after.getpixel((200, 180))


def test_checkout_template_rejects_wrong_template_kind():
    try:
        apply_checkout_total(
            _png(),
            VerifiedFact("코스피 종가", "5663.24", "facts[0]", SurfaceAnchor(.10, .20, .30, .20, "embedded_monitor")),
            InSceneTemplate("risk_warning", .10, .20, .30, .20),
        )
        assert False, "계산대 템플릿 종류가 다르면 실패해야 합니다."
    except ValueError as exc:
        assert "checkout_total" in str(exc)
