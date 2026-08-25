from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from app.services.final_frame_text_integrity import (
    FinalFrameTextIntegrityError,
    expected_final_frame_texts,
    inspect_final_frame_text_integrity,
    require_final_frame_text_integrity,
)
from app.workers.images_worker import DeterministicSurfaceMissingError, ImagesWorker


def _caption_scene() -> dict:
    return {
        "scene_id": "forecast-01",
        "v5_render_contract": {
            "visual_text_policy": "deterministic_surface_text",
            "primary_surface_region": [0.08, 0.12, 0.52, 0.40],
            "surface_caption": {
                "korean": "현재 전망\n수정 전망",
                "texts": ["현재 전망", "수정 전망"],
            },
        },
    }


def _save_blank_panel(path: Path) -> None:
    image = Image.new("RGB", (1280, 720), "#20354d")
    draw = ImageDraw.Draw(image)
    draw.rectangle((110, 85, 760, 390), fill="#d9edf7", outline="#091523", width=12)
    image.save(path)


def test_expected_text_prefers_verified_label_and_value_over_generic_caption():
    scene = _caption_scene()
    scene["v5_verified_overlays"] = [{"label": "영업이익", "value": "6조 8,130억원"}]

    assert expected_final_frame_texts(scene) == ["영업이익", "6조 8,130억원"]


def test_final_ocr_accepts_exact_approved_korean_across_rows(tmp_path: Path):
    report = inspect_final_frame_text_integrity(
        str(tmp_path / "unused.png"),
        _caption_scene(),
        ocr_rows=[{"text": "현재 전망", "conf": "94"}, {"text": "수정 전망", "conf": "92"}],
    )

    assert report["passed"] is True
    assert report["missing_or_altered"] == []


@pytest.mark.parametrize("recognized", ["현력 큰풍 수정 전망", "현재 전망 수정 계샥환"])
def test_final_ocr_rejects_korean_typo_or_gibberish(tmp_path: Path, recognized: str):
    with pytest.raises(FinalFrameTextIntegrityError):
        require_final_frame_text_integrity(
            str(tmp_path / "unused.png"),
            _caption_scene(),
            ocr_rows=[{"text": recognized, "conf": "96"}],
        )


def test_final_ocr_rejects_numeric_character_change(tmp_path: Path):
    scene = _caption_scene()
    scene["v5_verified_overlays"] = [{"label": "PER", "value": "4배"}]

    with pytest.raises(FinalFrameTextIntegrityError):
        require_final_frame_text_integrity(
            str(tmp_path / "unused.png"),
            scene,
            ocr_rows=[{"text": "PER 4X", "conf": "96"}],
        )


def test_worker_bakes_caption_on_existing_surface_without_ai_text(tmp_path: Path):
    image_path = tmp_path / "scene.png"
    _save_blank_panel(image_path)
    before = Image.open(image_path).copy()

    ImagesWorker()._apply_deterministic_surface_caption(_caption_scene(), str(image_path))

    after = Image.open(image_path).convert("RGB")
    assert ImageChops.difference(before.convert("RGB"), after).getbbox() is not None


def test_exact_deterministic_pixel_provenance_can_override_tesseract_misread(tmp_path: Path):
    image_path = tmp_path / "scene.png"
    _save_blank_panel(image_path)
    scene = _caption_scene()
    ImagesWorker()._apply_deterministic_surface_caption(scene, str(image_path))

    report = inspect_final_frame_text_integrity(
        str(image_path),
        scene,
        ocr_rows=[{"text": "현력 큰풍 수정 계샥환", "conf": "96"}],
    )

    assert report["passed"] is True
    assert report["ocr_passed"] is False
    assert report["deterministic_provenance"]["passed"] is True


def test_tampered_render_region_cannot_use_deterministic_provenance(tmp_path: Path):
    image_path = tmp_path / "scene.png"
    _save_blank_panel(image_path)
    scene = _caption_scene()
    ImagesWorker()._apply_deterministic_surface_caption(scene, str(image_path))
    left, top, _, _ = scene["deterministic_text_regions"][0]["bbox"]
    with Image.open(image_path) as source:
        changed = source.convert("RGB")
    changed.putpixel((left, top), (255, 0, 0))
    changed.save(image_path)

    with pytest.raises(FinalFrameTextIntegrityError):
        require_final_frame_text_integrity(
            str(image_path),
            scene,
            ocr_rows=[{"text": "현력 큰풍 수정 계샥환", "conf": "96"}],
        )


def test_worker_refuses_static_coordinate_fallback_when_no_physical_surface_exists(tmp_path: Path):
    image_path = tmp_path / "open-background.png"
    Image.new("RGB", (1280, 720), "#d9edf7").save(image_path)

    with pytest.raises(DeterministicSurfaceMissingError):
        ImagesWorker()._apply_deterministic_surface_caption(_caption_scene(), str(image_path))
