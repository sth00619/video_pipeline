"""V5 이미지 워커가 검증 수치 오버레이 계획을 실제 파일에 합성하는지 검증한다."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

from app.workers.images_worker import ImagesWorker


def _scene_with_overlay() -> dict:
    return {
        "scene_id": "retail-shock-01",
        "verified_facts": [{"fact": "이번 장바구니 총액은 1,125,000원이었다.", "figure": "1,125,000원"}],
        # retail_shock의 primary_surface_region == (0.28, 0.34, 0.28, 0.26) 안에
        # 완전히 들어가는 좌표만 사용한다(verified_overlay_planner의 계산과 동일 규칙).
        "v5_verified_overlays": [{
            "label": "장바구니 총액",
            "value": "1,125,000원",
            "source_ref": "facts[0]",
            "anchor": {"x": .3328, "y": .5116, "width": .1736, "height": .0676, "kind": "monitor"},
        }],
        "v5_render_contract": {"selection": {"archetype": "retail_shock"}},
    }


def test_applies_verified_fact_overlay_onto_the_generated_png(tmp_path: Path):
    img_path = tmp_path / "scene_000.png"
    Image.new("RGB", (1920, 1080), "#334155").save(img_path, "PNG")
    before = Image.open(img_path).convert("RGB").copy()

    ImagesWorker()._apply_verified_fact_overlay(_scene_with_overlay(), str(img_path))

    after = Image.open(img_path).convert("RGB")
    assert after.size == before.size
    assert ImageChops.difference(before, after).getbbox() is not None


def test_applies_verified_fact_overlay_onto_a_jpeg_and_keeps_the_format(tmp_path: Path):
    img_path = tmp_path / "scene_000.jpg"
    Image.new("RGB", (1920, 1080), "#334155").save(img_path, "JPEG")
    before = Image.open(img_path).convert("RGB").copy()

    ImagesWorker()._apply_verified_fact_overlay(_scene_with_overlay(), str(img_path))

    after = Image.open(img_path)
    assert after.format == "JPEG"
    assert ImageChops.difference(before, after.convert("RGB")).getbbox() is not None


def test_scene_without_a_verified_overlay_plan_is_left_untouched(tmp_path: Path):
    img_path = tmp_path / "scene_001.png"
    Image.new("RGB", (1920, 1080), "#334155").save(img_path, "PNG")
    before_bytes = img_path.read_bytes()

    ImagesWorker()._apply_verified_fact_overlay({"scene_id": "no-overlay"}, str(img_path))

    assert img_path.read_bytes() == before_bytes


def test_a_value_not_present_in_verified_facts_fails_closed_instead_of_silently_dropping(tmp_path: Path):
    img_path = tmp_path / "scene_002.png"
    Image.new("RGB", (1920, 1080), "#334155").save(img_path, "PNG")
    scene = _scene_with_overlay()
    scene["v5_verified_overlays"][0]["value"] = "999,999원"  # verified_facts에 없는 값

    try:
        ImagesWorker()._apply_verified_fact_overlay(scene, str(img_path))
        raise AssertionError("검증 원문에 없는 값은 조용히 통과하면 안 됩니다.")
    except ValueError as exc:
        assert "원문" in str(exc)
