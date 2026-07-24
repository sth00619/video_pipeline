from pathlib import Path

import pytest
from PIL import Image

from app.services.thumbnail import ThumbnailGenerator, PhotoLicenseError
from app.services.thumbnail.generator import LONGFORM_SIZE, SHORTS_SIZE


def _scene(path: Path, index: int = 0) -> dict:
    Image.new("RGB", (1920, 1080), (28 + index * 10, 75, 120)).save(path)
    return {"scene_id": str(index), "index": index, "image_path": str(path), "used_in_final_video": True}


def test_scene_thumbnail_uses_actual_scene_and_longform_ratio(tmp_path):
    result = ThumbnailGenerator().render(
        job_id=1,
        format_name="longform",
        output_path=str(tmp_path / "thumb.png"),
        candidates=[_scene(tmp_path / "scene.png")],
        brief={"hook_line": "{y:검증된 핵심}", "punch_line": "{r:지금 확인}",
               "badge": {"value": "+13.74%", "source_ref": "verified_facts[0]"}, "source_scene_ids": ["0"]},
    )
    assert result["mode"] == "scene"
    assert result["variants"][0]["source_scene_id"] == "0"
    with Image.open(tmp_path / "thumb.png") as rendered:
        assert rendered.size == LONGFORM_SIZE
        # Reference layout uses an opaque lower text shelf, not AI-generated
        # title glyphs embedded in the scene image.
        assert max(rendered.getpixel((10, 700))[:3]) < 20


def test_scene_thumbnail_shorts_ratio(tmp_path):
    ThumbnailGenerator().render(
        job_id=2, format_name="shorts", output_path=str(tmp_path / "short.png"),
        candidates=[_scene(tmp_path / "short_scene.png")], brief={"hook_line": "핵심", "punch_line": "정리"},
    )
    with Image.open(tmp_path / "short.png") as rendered:
        assert rendered.size == SHORTS_SIZE


def test_unapproved_person_photo_is_rejected_before_render(tmp_path):
    scene = _scene(tmp_path / "scene.png")
    with pytest.raises(PhotoLicenseError, match="PHOTO_LICENSE_MISSING"):
        ThumbnailGenerator().render(
            job_id=3, format_name="longform", output_path=str(tmp_path / "blocked.png"),
            candidates=[scene], person_photos=[{"photo_id": "unknown", "license_type": "UNKNOWN", "approved": False}],
        )


def test_approved_person_cutout_is_composited_without_regenerating_face(tmp_path):
    scene = _scene(tmp_path / "scene.png")
    cutout = tmp_path / "approved-cutout.png"
    Image.new("RGBA", (260, 520), (230, 190, 120, 255)).save(cutout)
    result = ThumbnailGenerator().render(
        job_id=4,
        format_name="longform",
        output_path=str(tmp_path / "person.png"),
        candidates=[scene],
        person_photos=[{
            "photo_id": "approved-photo", "license_type": "PRESS_KIT", "license_ref": "https://example.test/press",
            "approved": True, "rights_review_status": "APPROVED", "cutout_path": str(cutout),
        }],
    )
    regions = result["variants"][0]["subject_regions"]
    assert len(regions) == 1
    assert regions[0]["cutout_path"] == str(cutout)
