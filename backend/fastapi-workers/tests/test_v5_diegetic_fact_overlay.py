"""V5 검증 사실은 장면 속 지정 소품 표면에만 합성한다."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.overlay.diegetic_fact_overlay import (
    SurfaceAnchor,
    VerifiedFact,
    apply_facts_to_surfaces,
    facts_from_verified_scene,
)
from app.v5.scene.scene_type_archetypes import PRIMARY_SURFACE_REGIONS


def _png(color: str = "#334155") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (1280, 720), color).save(output, format="PNG")
    return output.getvalue()


def test_verified_fact_changes_only_the_declared_prop_surface():
    base = _png()
    result = apply_facts_to_surfaces(base, (
        VerifiedFact(
            label="검증 관세율",
            value="15.0%",
            source_ref="facts[2]",
            anchor=SurfaceAnchor(0.10, 0.20, 0.26, 0.14, "monitor"),
        ),
    ))
    original = Image.open(io.BytesIO(base)).convert("RGB")
    rendered = Image.open(io.BytesIO(result)).convert("RGB")
    assert rendered.size == original.size
    assert rendered.getpixel((20, 20)) == original.getpixel((20, 20))
    assert rendered.getpixel((200, 180)) != original.getpixel((200, 180))


def test_verified_fact_requires_provenance_and_in_canvas_anchor():
    no_source = VerifiedFact("항목", "1", "", SurfaceAnchor(0.1, 0.2, 0.2, 0.1, "monitor"))
    try:
        apply_facts_to_surfaces(_png(), (no_source,))
        assert False, "출처 없는 값은 렌더할 수 없어야 합니다."
    except ValueError as exc:
        assert "출처" in str(exc)

    outside = VerifiedFact("항목", "1", "facts[0]", SurfaceAnchor(0.9, 0.9, 0.2, 0.2, "monitor"))
    try:
        apply_facts_to_surfaces(_png(), (outside,))
        assert False, "캔버스 밖 좌표는 렌더할 수 없어야 합니다."
    except ValueError as exc:
        assert "캔버스" in str(exc)


def test_scene_adapter_only_accepts_a_value_present_in_verified_fact():
    scene = {
        "verified_facts": [{"fact": "관세율은 15%로 조정됐다.", "figure": "15%"}],
        "v5_verified_overlays": [{
            "label": "확정 관세율",
            "value": "15%",
            "source_ref": "facts[0]",
            "anchor": {"x": .10, "y": .20, "width": .26, "height": .14, "kind": "placard"},
        }],
    }
    facts = facts_from_verified_scene(scene)
    assert facts[0].value == "15%"
    assert facts[0].source_ref == "facts[0]"


def test_scene_adapter_rejects_a_value_not_in_verified_fact():
    scene = {
        "verified_facts": [{"fact": "관세율은 15%로 조정됐다.", "figure": "15%"}],
        "v5_verified_overlays": [{
            "label": "확정 관세율",
            "value": "20%",
            "source_ref": "facts[0]",
            "anchor": {"x": .10, "y": .20, "width": .26, "height": .14, "kind": "placard"},
        }],
    }
    try:
        facts_from_verified_scene(scene)
        assert False, "검증 원문에 없는 수치는 거부되어야 합니다."
    except ValueError as exc:
        assert "원문" in str(exc)


def test_embedded_monitor_updates_only_an_existing_display_interior():
    base = _png("#0f2940")
    result = apply_facts_to_surfaces(base, (
        VerifiedFact(
            label="코스피 종가",
            value="5663.24",
            source_ref="facts[0]",
            anchor=SurfaceAnchor(0.35, 0.30, 0.28, 0.18, "embedded_monitor"),
        ),
    ))
    rendered = Image.open(io.BytesIO(result)).convert("RGB")
    assert rendered.getpixel((20, 20)) == Image.open(io.BytesIO(base)).convert("RGB").getpixel((20, 20))
    assert rendered.getpixel((640, 280)) != Image.open(io.BytesIO(base)).convert("RGB").getpixel((640, 280))


def test_v5_contract_rejects_fact_anchor_outside_selected_primary_surface():
    scene = {
        "verified_facts": [{"fact": "종가는 5663.24였다.", "figure": "5663.24"}],
        "v5_verified_overlays": [{
            "label": "코스피 종가",
            "value": "5663.24",
            "source_ref": "facts[0]",
            "anchor": {"x": .06, "y": .12, "width": .27, "height": .16, "kind": "monitor"},
        }],
        "v5_render_contract": {"selection": {"archetype": "data_lab"}},
    }

    from app.v5.overlay.diegetic_fact_overlay import apply_verified_scene_facts

    try:
        apply_verified_scene_facts(_png(), scene)
        assert False, "data_lab 지도 패널 밖의 좌상단 카드가 차단돼야 합니다."
    except ValueError as exc:
        assert "primary" in str(exc)


def test_v5_contract_accepts_fact_anchor_inside_selected_primary_surface():
    scene = {
        "verified_facts": [{"fact": "종가는 5663.24였다.", "figure": "5663.24"}],
        "v5_verified_overlays": [{
            "label": "코스피 종가",
            "value": "5663.24",
            "source_ref": "facts[0]",
            "anchor": {"x": .24, "y": .42, "width": .22, "height": .13, "kind": "embedded_monitor"},
        }],
        "v5_render_contract": {"selection": {"archetype": "data_lab"}},
    }

    from app.v5.overlay.diegetic_fact_overlay import apply_verified_scene_facts

    rendered = Image.open(io.BytesIO(apply_verified_scene_facts(_png(), scene))).convert("RGB")
    assert rendered.getpixel((450, 350)) != Image.open(io.BytesIO(_png())).convert("RGB").getpixel((450, 350))


@pytest.mark.parametrize("archetype", sorted(PRIMARY_SURFACE_REGIONS))
def test_every_v5_archetype_rejects_a_verified_fact_outside_its_primary_surface(archetype: str):
    scene = {
        "verified_facts": [{"fact": "검증값은 15%였다.", "figure": "15%"}],
        "v5_verified_overlays": [{
            "label": "검증 지표",
            "value": "15%",
            "source_ref": "facts[0]",
            "anchor": {"x": .85, "y": .85, "width": .10, "height": .10, "kind": "monitor"},
        }],
        "v5_render_contract": {"selection": {"archetype": archetype}},
    }

    from app.v5.overlay.diegetic_fact_overlay import apply_verified_scene_facts

    with pytest.raises(ValueError, match="primary"):
        apply_verified_scene_facts(_png(), scene)


@pytest.mark.parametrize("archetype,region", sorted(PRIMARY_SURFACE_REGIONS.items()))
def test_every_v5_archetype_accepts_a_verified_fact_inside_its_primary_surface(
    archetype: str,
    region: tuple[float, float, float, float],
):
    x, y, width, height = region
    anchor_width = min(.08, width * .40)
    anchor_height = min(.06, height * .40)
    scene = {
        "verified_facts": [{"fact": "검증값은 15%였다.", "figure": "15%"}],
        "v5_verified_overlays": [{
            "label": "검증 지표",
            "value": "15%",
            "source_ref": "facts[0]",
            "anchor": {
                "x": x + (width - anchor_width) / 2,
                "y": y + (height - anchor_height) / 2,
                "width": anchor_width,
                "height": anchor_height,
                "kind": "embedded_monitor",
            },
        }],
        "v5_render_contract": {"selection": {"archetype": archetype}},
    }

    from app.v5.overlay.diegetic_fact_overlay import apply_verified_scene_facts

    assert apply_verified_scene_facts(_png(), scene)
